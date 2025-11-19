import asyncio
import os
import json
import traceback
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, List, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import CallToolResult, Tool

class MCPClientManager:
    def __init__(self, config_path: Optional[str] = None):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict[str, Any]] = []
        self._is_connected = False
        self.connection_errors: Dict[str, str] = {}
        self.config_path = config_path or "agent.mcp.json"
        self.mcp_config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """agent.mcp.json 파일에서 MCP 서버 설정 로드"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.mcp_config = json.load(f)
                print(f"✅ Loaded MCP config from {self.config_path}")
            else:
                print(f"⚠️ Config file {self.config_path} not found, using default settings")
                self.mcp_config = {}
        except Exception as e:
            print(f"❌ Error loading config file: {e}")
            self.mcp_config = {}

    async def _connect_ddg(self):
        """DuckDuckGo MCP 서버 연결 (Stdio)"""
        try:
            print("🔄 Attempting to connect to DuckDuckGo MCP server...")
            
            # config에서 설정 읽기
            ddg_config = self.mcp_config.get("mcpServers", {}).get("duckduckgo-search", {})
            command = ddg_config.get("command", "npx")
            args = ddg_config.get("args", ["-y", "duckduckgo-mcp-server"])
            
            ddg_params = StdioServerParameters(
                command=command, 
                args=args,
                env=os.environ.copy()
            )
            
            # 타임아웃 설정 (30초)
            ddg_transport = await asyncio.wait_for(
                self.exit_stack.enter_async_context(stdio_client(ddg_params)),
                timeout=30.0
            )
            
            session = await asyncio.wait_for(
                self.exit_stack.enter_async_context(
                    ClientSession(ddg_transport[0], ddg_transport[1])
                ),
                timeout=30.0
            )
            
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            self.sessions["duckduckgo"] = session
            print("✅ Successfully connected to DuckDuckGo")
            return True
        except asyncio.TimeoutError:
            error_msg = "Connection timeout (30s) - npx may be slow or network issue"
            print(f"❌ {error_msg}")
            self.connection_errors["duckduckgo"] = error_msg
            return False
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}\n{traceback.format_exc()}"
            print(f"❌ DuckDuckGo connection error: {error_msg}")
            self.connection_errors["duckduckgo"] = error_msg
            return False

    async def _connect_context7(self):
        """Context7 MCP 서버 연결 (SSE)"""
        try:
            print("🔄 Attempting to connect to Context7 MCP server...")
            
            # config에서 설정 읽기
            c7_config = self.mcp_config.get("mcpServers", {}).get("Context7", {})
            url = c7_config.get("url", "https://mcp.context7.com/mcp")
            headers = c7_config.get("headers", {})
            
            # SSE 클라이언트 연결 (타임아웃 30초)
            c7_transport = await asyncio.wait_for(
                self.exit_stack.enter_async_context(
                    sse_client(url, headers=headers if headers else None)
                ),
                timeout=30.0
            )
            
            session = await asyncio.wait_for(
                self.exit_stack.enter_async_context(
                    ClientSession(c7_transport[0], c7_transport[1])
                ),
                timeout=30.0
            )
            
            await asyncio.wait_for(session.initialize(), timeout=30.0)
            self.sessions["context7"] = session
            print("✅ Successfully connected to Context7")
            return True
        except asyncio.TimeoutError:
            error_msg = "Connection timeout (30s) - network issue or server unavailable"
            print(f"❌ {error_msg}")
            self.connection_errors["context7"] = error_msg
            return False
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}\n{traceback.format_exc()}"
            print(f"❌ Context7 connection error: {error_msg}")
            self.connection_errors["context7"] = error_msg
            return False

    async def connect(self):
        """MCP 서버들에 연결 시도 (부분 실패 허용)"""
        if self._is_connected:
            return

        self.connection_errors.clear()
        
        # 각 서버를 독립적으로 연결 시도 (한쪽 실패해도 다른 쪽은 연결)
        results = await asyncio.gather(
            self._connect_ddg(),
            self._connect_context7(),
            return_exceptions=True
        )
        
        ddg_connected = results[0] if isinstance(results[0], bool) else False
        c7_connected = results[1] if isinstance(results[1], bool) else False
        
        # 최소 하나는 연결되어야 함
        if not ddg_connected and not c7_connected:
            error_summary = "\n".join([f"{k}: {v}" for k, v in self.connection_errors.items()])
            raise Exception(f"Failed to connect to any MCP server:\n{error_summary}")
        
        # 연결된 서버에서 도구 목록 가져오기
        await self.refresh_tools()
        
        # 연결 상태 확인
        if ddg_connected and c7_connected:
            self._is_connected = True
            print("✅ Connected to all MCP servers")
        elif ddg_connected:
            self._is_connected = True
            print("⚠️ Connected to DuckDuckGo only (Context7 failed)")
        elif c7_connected:
            self._is_connected = True
            print("⚠️ Connected to Context7 only (DuckDuckGo failed)")

    async def refresh_tools(self):
        self.tools = []
        for name, session in self.sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    self.tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                        "server": name
                    })
            except Exception as e:
                print(f"Error listing tools for {name}: {e}")

    def get_tools_for_gemini(self) -> List[Dict[str, Any]]:
        """
        Convert MCP tools to Gemini function declarations format.
        Compatible with google-genai SDK.
        """
        gemini_tools = []
        for tool in self.tools:
            # google-genai SDK expects a dict for function declaration
            gemini_tool = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
            gemini_tools.append(gemini_tool)
        return gemini_tools

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        target_tool = next((t for t in self.tools if t["name"] == tool_name), None)
        if not target_tool:
            raise ValueError(f"Tool {tool_name} not found")
        
        session = self.sessions[target_tool["server"]]
        result: CallToolResult = await session.call_tool(tool_name, arguments)
        
        output = []
        if not result.isError:
            for content in result.content:
                if content.type == "text":
                    output.append(content.text)
                elif content.type == "image":
                    output.append(f"[Image: {content.mimeType}]")
                elif content.type == "resource":
                     output.append(f"[Resource: {content.uri}]")
        else:
             output.append(f"Error: {result.content}")

        return "\n".join(output)

    async def cleanup(self):
        await self.exit_stack.aclose()
        self.sessions.clear()
        self.tools = []
        self._is_connected = False
