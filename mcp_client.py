import asyncio
import os
from contextlib import AsyncExitStack
from typing import Dict, List, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import CallToolResult, Tool

class MCPClientManager:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict[str, Any]] = []
        self._is_connected = False

    async def _connect_ddg(self):
        try:
            # Connect to DuckDuckGo (Stdio)
            ddg_params = StdioServerParameters(
                command="npx", 
                args=["-y", "duckduckgo-mcp-server"],
                env=os.environ.copy()
            )
            ddg_transport = await self.exit_stack.enter_async_context(stdio_client(ddg_params))
            session = await self.exit_stack.enter_async_context(
                ClientSession(ddg_transport[0], ddg_transport[1])
            )
            await session.initialize()
            self.sessions["duckduckgo"] = session
            print("Connected to DuckDuckGo")
        except Exception as e:
            print(f"Failed to connect to DuckDuckGo: {e}")
            raise e

    async def _connect_context7(self):
        try:
            # Connect to Context7 (SSE)
            c7_transport = await self.exit_stack.enter_async_context(
                sse_client("https://mcp.context7.com/mcp")
            )
            session = await self.exit_stack.enter_async_context(
                ClientSession(c7_transport[0], c7_transport[1])
            )
            await session.initialize()
            self.sessions["context7"] = session
            print("Connected to Context7")
        except Exception as e:
            print(f"Failed to connect to Context7: {e}")
            raise e

    async def connect(self):
        if self._is_connected:
            return

        try:
            # Connect to servers in parallel
            await asyncio.gather(
                self._connect_ddg(),
                self._connect_context7()
            )
            
            await self.refresh_tools()
            self._is_connected = True
            print("Connected to all MCP servers")

        except Exception as e:
            print(f"Error connecting to MCP servers: {e}")
            await self.cleanup()
            raise e

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
