import os
import asyncio
import google.generativeai as genai
from google.ai.generativelanguage import FunctionDeclaration, Tool
from mcp_client import MCPClientManager

class Agent:
    def __init__(self, mcp_client: MCPClientManager):
        self.mcp_client = mcp_client
        self.model_name = "gemini-1.5-flash"
        self._configure_genai()
        self.chat_session = None
        self.model = None

    def _configure_genai(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            # For development, we might want to allow empty if set later, but for now warn.
            print("Warning: GOOGLE_API_KEY not set.")
        else:
            genai.configure(api_key=api_key)

    def _convert_tools(self, mcp_tools):
        """Convert MCP tools to Gemini FunctionDeclarations"""
        function_declarations = []
        for tool in mcp_tools:
            # Gemini expects a specific schema format. 
            # MCP schema is JSON Schema Draft 2020-12 usually.
            # We might need to ensure it's compatible.
            
            # Ensure parameters is a dict
            parameters = tool["parameters"]
            if parameters.get("type") != "object":
                 # Gemini requires top level type to be object
                 parameters = {
                     "type": "object",
                     "properties": {"arg": parameters}
                 }

            func_decl = FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=parameters
            )
            function_declarations.append(func_decl)
        
        return Tool(function_declarations=function_declarations)

    def start_chat(self):
        # Get tools from MCP client
        mcp_tools = self.mcp_client.get_tools_for_gemini()
        gemini_tools = self._convert_tools(mcp_tools)
        
        system_instruction = """You are a helpful developer assistant. 
You have access to tools for web search (DuckDuckGo) and library documentation (Context7). 
Use them to answer the user's questions comprehensively.
When using Context7, you might need to resolve the library ID first if not obvious.
Always cite your sources if possible."""

        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=[gemini_tools],
            system_instruction=system_instruction
        )
        self.chat_session = self.model.start_chat(enable_automatic_function_calling=False)

    async def process_message(self, user_message: str):
        if not self.chat_session:
            self.start_chat()

        # Send message
        response = await self.chat_session.send_message_async(user_message)
        
        # Tool execution loop
        # We limit the loop to prevent infinite loops
        max_turns = 10
        current_turn = 0

        while current_turn < max_turns:
            # Check if the response contains a function call
            # Gemini response can have multiple parts, but usually function call is distinct.
            
            # We need to check the first candidate
            if not response.candidates:
                return "Error: No response from model."
            
            candidate = response.candidates[0]
            
            # Look for function calls in parts
            function_calls = []
            for part in candidate.content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)
            
            if not function_calls:
                # No function calls, return text
                return response.text

            # Execute all function calls (Gemini can output parallel calls)
            parts_response = []
            for fc in function_calls:
                tool_name = fc.name
                args = dict(fc.args)
                
                print(f"Executing tool: {tool_name} with args: {args}")
                
                try:
                    tool_result = await self.mcp_client.call_tool(tool_name, args)
                except Exception as e:
                    tool_result = f"Error executing tool {tool_name}: {str(e)}"
                
                # Create function response part
                parts_response.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": tool_result}
                        )
                    )
                )

            # Send results back to model
            response = await self.chat_session.send_message_async(
                genai.protos.Content(parts=parts_response)
            )
            current_turn += 1

        return "Error: Maximum tool execution turns reached."

