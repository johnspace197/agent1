import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from google import genai
from google.genai import types
from mcp_client import MCPClientManager

class SearchResult:
    """검색 결과를 구조화하여 저장하는 클래스"""
    def __init__(self, source: str, query: str, content: str, metadata: Optional[Dict] = None):
        self.source = source  # "duckduckgo" or "context7"
        self.query = query
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
    
    def to_dict(self):
        return {
            "source": self.source,
            "query": self.query,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }

class Agent:
    def __init__(self, mcp_client: MCPClientManager):
        self.mcp_client = mcp_client
        self.model_name = "gemini-2.5-pro"
        self.client = None
        self.chat = None
        self.search_history: List[SearchResult] = []
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

    def _get_relevant_history(self, query: str, max_results: int = 3) -> str:
        """검색 히스토리에서 관련된 결과를 찾아 반환"""
        if not self.search_history:
            return ""
        
        query_lower = query.lower()
        relevant = []
        for result in reversed(self.search_history[-10:]):
            if any(word in result.query.lower() or word in result.content.lower() 
                   for word in query_lower.split() if len(word) > 3):
                relevant.append(result)
                if len(relevant) >= max_results:
                    break
        
        if not relevant:
            return ""
        
        history_text = "\n\n=== Previous Search Results ===\n"
        for i, result in enumerate(relevant, 1):
            history_text += f"\n[{i}] Source: {result.source}\nQuery: {result.query}\n{result.content[:200]}...\n"
        
        return history_text

    def start_chat(self):
        tools = self._get_tools()
        
        system_instruction = """You are an intelligent search agent specialized in helping developers.

Your capabilities:
1. **Strategic Search Planning**: Analyze user questions to determine:
   - What information is needed
   - Which search sources to use (web search vs documentation)
   - Optimal search queries (consider synonyms, related terms)
   - Whether multiple searches are needed from different angles

2. **Multi-Source Search**: 
   - Use DuckDuckGo for general web search, recent information, tutorials, examples
   - Use Context7 for official library documentation, API references, code examples
   - Combine results from both sources when appropriate

3. **Result Synthesis**:
   - Compare and cross-reference information from multiple sources
   - Identify contradictions or complementary information
   - Prioritize authoritative sources (official docs > tutorials > forums)
   - Extract key insights and actionable information

4. **Source Citation**:
   - Always cite the source of information
   - Format: [Source: DuckDuckGo] or [Source: Context7 - Library Name]
   - Include relevant URLs or documentation links when available

5. **Search Optimization**:
   - If initial search doesn't yield good results, refine search queries
   - Try different phrasings or more specific terms
   - Use follow-up searches to fill information gaps

Guidelines:
- Start with understanding the user's intent
- Plan your search strategy before executing
- Execute multiple searches if needed to get comprehensive information
- Synthesize all results into a coherent, well-cited answer
- If information is incomplete, indicate what's missing and suggest follow-up searches"""

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

        history_context = self._get_relevant_history(user_message)
        enhanced_message = user_message
        if history_context:
            enhanced_message = f"{user_message}\n\n{history_context}\n\nNote: Use previous search results if relevant, but also perform new searches if needed."

        response = await self.chat.send_message(enhanced_message)
        
        max_turns = 15
        current_turn = 0
        search_results_this_query: List[SearchResult] = []

        while current_turn < max_turns:
            if not response.candidates:
                return "Error: No response from model."
            
            candidate = response.candidates[0]
            
            function_calls = []
            for part in candidate.content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)
            
            if not function_calls:
                if search_results_this_query:
                    self.search_history.extend(search_results_this_query)
                    final_response = response.text
                    sources = set(r.source for r in search_results_this_query)
                    source_note = "\n\n---\n*Sources: " + ", ".join(sources) + "*"
                    final_response += source_note
                    return final_response
                
                return response.text

            parts_response = []
            for fc in function_calls:
                tool_name = fc.name
                args = fc.args
                
                print(f"🔍 Executing tool: {tool_name} with args: {args}")
                
                try:
                    tool_result = await self.mcp_client.call_tool(tool_name, args)
                    
                    source = "duckduckgo" if "duckduckgo" in tool_name.lower() else "context7"
                    query = args.get("query", args.get("text", str(args)))
                    
                    search_result = SearchResult(
                        source=source,
                        query=query,
                        content=tool_result,
                        metadata={"tool": tool_name, "args": args}
                    )
                    search_results_this_query.append(search_result)
                    
                    formatted_result = f"[Source: {source.upper()}]\n{tool_result}"
                    
                except Exception as e:
                    formatted_result = f"Error executing tool {tool_name}: {str(e)}"
                
                parts_response.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": formatted_result}
                    )
                )

            response = await self.chat.send_message(parts_response)
            current_turn += 1

        if search_results_this_query:
            self.search_history.extend(search_results_this_query)
            final_text = response.text if hasattr(response, 'text') else "Maximum tool execution turns reached."
            sources = set(r.source for r in search_results_this_query)
            return f"{final_text}\n\n---\n*Sources: {', '.join(sources)}*"
        
        return "Error: Maximum tool execution turns reached."

    def get_search_history(self) -> List[Dict]:
        """검색 히스토리를 딕셔너리 리스트로 반환"""
        return [result.to_dict() for result in self.search_history]

    def clear_history(self):
        """검색 히스토리 초기화"""
        self.search_history.clear()
