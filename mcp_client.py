import asyncio
import os
import sys
import json
import traceback
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, List, Any, Optional

# Windows 인코딩 문제 해결
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
                print(f"[OK] Loaded MCP config from {self.config_path}")
            else:
                print(f"[WARN] Config file {self.config_path} not found, using default settings")
                self.mcp_config = {}
        except Exception as e:
            print(f"[ERROR] Error loading config file: {e}")
            self.mcp_config = {}

    async def _connect_ddg(self):
        """DuckDuckGo MCP 서버 연결 (Stdio)"""
        mcp_servers = self.mcp_config.get("mcpServers", {})
        
        # duckduckgo-search와 ddg-search 설정 모두 가져오기
        duckduckgo_search_config = mcp_servers.get("duckduckgo-search", {})
        ddg_search_config = mcp_servers.get("ddg-search")
        
        # 시도할 설정 목록 (duckduckgo-search 우선)
        configs_to_try = []
        if duckduckgo_search_config:
            configs_to_try.append(("duckduckgo-search", duckduckgo_search_config))
        if ddg_search_config:
            configs_to_try.append(("ddg-search", ddg_search_config))
        
        # 기본 설정
        if not configs_to_try:
            configs_to_try.append(("default", {"command": "npx", "args": ["-y", "duckduckgo-mcp-server"]}))
        
        # 각 설정을 순차적으로 시도
        for config_name, ddg_config in configs_to_try:
            try:
                print(f"[INFO] Attempting to connect to DuckDuckGo MCP server using {config_name}...")
                
                command = ddg_config.get("command", "npx")
                args = ddg_config.get("args", ["-y", "duckduckgo-mcp-server"])
                
                ddg_params = StdioServerParameters(
                    command=command, 
                    args=args,
                    env=os.environ.copy()
                )
                
                # 타임아웃 설정 (60초로 증가 - npx 설치 시간 고려)
                ddg_transport = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(stdio_client(ddg_params)),
                    timeout=60.0
                )
                
                session = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(
                        ClientSession(ddg_transport[0], ddg_transport[1])
                    ),
                    timeout=60.0
                )
                
                await asyncio.wait_for(session.initialize(), timeout=60.0)
                self.sessions["duckduckgo"] = session
                print(f"[OK] Successfully connected to DuckDuckGo using {config_name}")
                return True
            except FileNotFoundError:
                # 명령어를 찾을 수 없으면 다음 설정 시도
                print(f"[WARN] Command '{command}' not found, trying next configuration...")
                if config_name == configs_to_try[-1][0]:
                    # 마지막 설정도 실패하면 에러
                    error_msg = f"All DuckDuckGo configurations failed. Last error: Command '{command}' not found. Please install '{command}' or check PATH."
                    print(f"[ERROR] {error_msg}")
                    self.connection_errors["duckduckgo"] = error_msg
                    return False
                continue
            except asyncio.TimeoutError:
                # 타임아웃이면 다음 설정 시도
                print(f"[WARN] Connection timeout with {config_name}, trying next configuration...")
                if config_name == configs_to_try[-1][0]:
                    error_msg = "Connection timeout (60s) - all configurations failed. Try running the command manually first."
                    print(f"[ERROR] {error_msg}")
                    self.connection_errors["duckduckgo"] = error_msg
                    return False
                continue
            except Exception as e:
                # 다른 에러면 다음 설정 시도
                print(f"[WARN] Connection failed with {config_name}: {str(e)}, trying next configuration...")
                if config_name == configs_to_try[-1][0]:
                    error_msg = f"All DuckDuckGo configurations failed. Last error: {str(e)}"
                    print(f"[ERROR] DuckDuckGo connection error: {error_msg}")
                    self.connection_errors["duckduckgo"] = error_msg
                    return False
                continue
        
        return False

    async def _connect_context7(self):
        """Context7 MCP 서버 연결 (Stdio 또는 SSE)"""
        try:
            print("[INFO] Attempting to connect to Context7 MCP server...")
            
            # config에서 설정 읽기 (대소문자 구분 없이 시도)
            mcp_servers = self.mcp_config.get("mcpServers", {})
            c7_config = mcp_servers.get("context7") or mcp_servers.get("Context7", {})
            
            # command가 있으면 stdio 방식, url이 있으면 SSE 방식
            if "command" in c7_config:
                # Stdio 방식
                command = c7_config.get("command", "npx")
                args = c7_config.get("args", [])
                
                c7_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=os.environ.copy()
                )
                
                c7_transport = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(stdio_client(c7_params)),
                    timeout=60.0
                )
            else:
                # SSE 방식 (기존 방식, 하위 호환성)
                url = c7_config.get("url", "https://mcp.context7.com/mcp")
                headers = c7_config.get("headers", {})
                
                sse_kwargs = {"url": url}
                if headers:
                    sse_kwargs["headers"] = headers
                
                c7_transport = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(
                        sse_client(**sse_kwargs)
                    ),
                    timeout=60.0
                )
            
            session = await asyncio.wait_for(
                self.exit_stack.enter_async_context(
                    ClientSession(c7_transport[0], c7_transport[1])
                ),
                timeout=60.0
            )
            
            await asyncio.wait_for(session.initialize(), timeout=60.0)
            self.sessions["context7"] = session
            print("[OK] Successfully connected to Context7")
            return True
        except asyncio.TimeoutError:
            error_msg = "Connection timeout (60s) - npx may be slow or network issue"
            print(f"[ERROR] {error_msg}")
            self.connection_errors["context7"] = error_msg
            return False
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] Context7 connection error: {error_msg}")
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
            print("[OK] Connected to all MCP servers")
        elif ddg_connected:
            self._is_connected = True
            print("[WARN] Connected to DuckDuckGo only (Context7 failed)")
        elif c7_connected:
            self._is_connected = True
            print("[WARN] Connected to Context7 only (DuckDuckGo failed)")

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
