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

    async def connect(self):
        if self._is_connected:
            return

        try:
            # Connect to DuckDuckGo (Stdio)
            # npx -y duckduckgo-mcp-server
            ddg_params = StdioServerParameters(
                command="npx", 
                args=["-y", "duckduckgo-mcp-server"],
                env=os.environ.copy() # Pass environment variables
            )
            
            # stdio_client returns a context manager that yields (read, write)
            ddg_transport = await self.exit_stack.enter_async_context(stdio_client(ddg_params))
            self.sessions["duckduckgo"] = await self.exit_stack.enter_async_context(
                ClientSession(ddg_transport[0], ddg_transport[1])
            )
            
            # Initialize DuckDuckGo session
            await self.sessions["duckduckgo"].initialize()

            # Connect to Context7 (SSE)
            # https://mcp.context7.com/mcp
            c7_transport = await self.exit_stack.enter_async_context(
                sse_client("https://mcp.context7.com/mcp")
            )
            self.sessions["context7"] = await self.exit_stack.enter_async_context(
                ClientSession(c7_transport[0], c7_transport[1])
            )
            
            # Initialize Context7 session
            await self.sessions["context7"].initialize()

            await self.refresh_tools()
            self._is_connected = True
            print("Connected to MCP servers")

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
                    # Store tool info along with the server name
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
        """
        gemini_tools = []
        for tool in self.tools:
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
        
        # Format result for Gemini
        # Gemini expects a specific format or just text. 
        # MCP returns content list (TextContent or ImageContent).
        
        output = []
        if not result.isError:
            for content in result.content:
                if content.type == "text":
                    output.append(content.text)
                elif content.type == "image":
                    output.append(f"[Image: {content.mimeType}]") # Gemini might handle images differently, but for text-based tool use:
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

