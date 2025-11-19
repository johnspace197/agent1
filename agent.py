import os
import asyncio
from google import genai
from google.genai import types
from mcp_client import MCPClientManager

class Agent:
    def __init__(self, mcp_client: MCPClientManager):
        self.mcp_client = mcp_client
        self.model_name = "gemini-1.5-flash"
        self.client = None
        self.chat = None
        self._configure_genai()

    def _configure_genai(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("Warning: GOOGLE_API_KEY not set.")
        else:
            self.client = genai.Client(api_key=api_key)

    def _get_tools(self):
        """Convert MCP tools to google-genai Tool objects"""
        mcp_tools = self.mcp_client.get_tools_for_gemini()
        function_declarations = []
        
        for tool in mcp_tools:
            # Ensure parameters schema is compatible
            parameters = tool["parameters"]
            if parameters.get("type") != "object":
                 parameters = {
                     "type": "object",
                     "properties": {"arg": parameters}
                 }

            func_decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=parameters
            )
            function_declarations.append(func_decl)
            
        if not function_declarations:
            return None
            
        return [types.Tool(function_declarations=function_declarations)]

    def start_chat(self):
        tools = self._get_tools()
        
        system_instruction = """You are a helpful developer assistant. 
You have access to tools for web search (DuckDuckGo) and library documentation (Context7). 
Use them to answer the user's questions comprehensively.
When using Context7, you might need to resolve the library ID first if not obvious.
Always cite your sources if possible."""

        # Create chat session
        # Note: google-genai SDK handles chat history differently than google-generativeai
        self.chat = self.client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                tools=tools,
                system_instruction=system_instruction,
                temperature=0.7
            )
        )

    async def process_message(self, user_message: str):
        if not self.chat:
            self.start_chat()

        # Send message and handle tool calls manually loop
        # google-genai SDK might have auto-function calling, but we want manual control for MCP
        # Actually, the new SDK supports automatic tool execution if we provide the functions.
        # But here we have dynamic MCP tools.
        # We will use the manual turn-by-turn approach similar to before.
        
        response = await self.chat.send_message(user_message)
        
        max_turns = 10
        current_turn = 0

        while current_turn < max_turns:
            # Check for function calls
            # In new SDK, response.candidates[0].content.parts contains function calls
            
            if not response.candidates:
                return "Error: No response from model."
            
            candidate = response.candidates[0]
            
            function_calls = []
            for part in candidate.content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)
            
            if not function_calls:
                return response.text

            # Execute tools
            parts_response = []
            for fc in function_calls:
                tool_name = fc.name
                args = fc.args
                
                print(f"Executing tool: {tool_name} with args: {args}")
                
                try:
                    tool_result = await self.mcp_client.call_tool(tool_name, args)
                except Exception as e:
                    tool_result = f"Error executing tool {tool_name}: {str(e)}"
                
                parts_response.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_result}
                    )
                )

            # Send tool outputs back to model
            response = await self.chat.send_message(parts_response)
            current_turn += 1

        return "Error: Maximum tool execution turns reached."
