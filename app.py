import streamlit as st
import asyncio
import nest_asyncio
from dotenv import load_dotenv
from mcp_client import MCPClientManager
from agent import Agent

# Load environment variables
load_dotenv()

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

st.set_page_config(page_title="Gemini MCP Agent", page_icon="🤖", layout="wide")

async def main():
    st.title("🔍 지능형 검색 에이전트")
    st.caption("Powered by Gemini 2.5 Pro, DuckDuckGo, and Context7")

    # Initialize Session State
    if "mcp_client" not in st.session_state:
        st.session_state.mcp_client = MCPClientManager()
        st.session_state.agent = None
        st.session_state.messages = []
        st.session_state.connected = False

    # Sidebar for connection management
    with st.sidebar:
        st.header("System Status")
        
        if not st.session_state.connected:
            st.warning("🔴 Disconnected")
            if st.button("Connect to MCP Servers", type="primary"):
                with st.spinner("Connecting to DuckDuckGo & Context7..."):
                    try:
                        await st.session_state.mcp_client.connect()
                        st.session_state.agent = Agent(st.session_state.mcp_client)
                        st.session_state.connected = True
                        
                        # 연결 상태 표시
                        connected_servers = list(st.session_state.mcp_client.sessions.keys())
                        if len(connected_servers) == 2:
                            st.success("✅ Connected to all servers!")
                        else:
                            st.warning(f"⚠️ Connected to: {', '.join(connected_servers)}")
                            if st.session_state.mcp_client.connection_errors:
                                with st.expander("Connection Errors"):
                                    for server, error in st.session_state.mcp_client.connection_errors.items():
                                        st.error(f"**{server}**: {error}")
                        
                        st.rerun()
                    except Exception as e:
                        st.error(f"Connection failed: {e}")
                        if hasattr(st.session_state.mcp_client, 'connection_errors'):
                            with st.expander("Detailed Error Information"):
                                for server, error in st.session_state.mcp_client.connection_errors.items():
                                    st.error(f"**{server}**: {error}")
        else:
            # 연결된 서버 표시
            connected_servers = list(st.session_state.mcp_client.sessions.keys())
            if len(connected_servers) == 2:
                st.success("🟢 Connected to all servers")
            else:
                st.warning(f"⚠️ Connected to: {', '.join(connected_servers)}")
            
            st.info(f"Loaded Tools: {len(st.session_state.mcp_client.tools)}")
            with st.expander("View Tools"):
                if st.session_state.mcp_client.tools:
                    for tool in st.session_state.mcp_client.tools:
                        st.code(f"{tool['name']} ({tool['server']})")
                else:
                    st.warning("No tools available")
            
            # 연결 에러가 있으면 표시
            if hasattr(st.session_state.mcp_client, 'connection_errors') and st.session_state.mcp_client.connection_errors:
                with st.expander("⚠️ Connection Warnings"):
                    for server, error in st.session_state.mcp_client.connection_errors.items():
                        st.error(f"**{server}**: {error}")
            
            # Search History
            if st.session_state.agent and hasattr(st.session_state.agent, 'search_history'):
                history = st.session_state.agent.get_search_history()
                if history:
                    st.subheader("📚 Search History")
                    st.info(f"Total searches: {len(history)}")
                    with st.expander("View Search History"):
                        for i, result in enumerate(reversed(history[-10:]), 1):
                            st.markdown(f"**{i}. {result['source'].upper()}** - `{result['query']}`")
                            st.caption(f"Time: {result['timestamp']}")
                    if st.button("Clear History"):
                        st.session_state.agent.clear_history()
                        st.rerun()
            
            if st.button("Disconnect"):
                await st.session_state.mcp_client.cleanup()
                st.session_state.connected = False
                st.session_state.agent = None
                st.rerun()

    # Chat Interface
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat Input
    if prompt := st.chat_input("Ask a development question..."):
        if not st.session_state.connected:
            st.error("Please connect to MCP servers first using the sidebar button.")
        else:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generate response
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                with st.spinner("Thinking..."):
                    try:
                        response = await st.session_state.agent.process_message(prompt)
                        message_placeholder.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())

