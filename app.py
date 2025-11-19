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
    st.title("🤖 Gemini MCP Agent")
    st.caption("Powered by Gemini 1.5 Flash, DuckDuckGo, and Context7")

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
                        st.success("✅ Connected!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Connection failed: {e}")
        else:
            st.success("🟢 Connected")
            st.info(f"Loaded Tools: {len(st.session_state.mcp_client.tools)}")
            with st.expander("View Tools"):
                for tool in st.session_state.mcp_client.tools:
                    st.code(f"{tool['name']} ({tool['server']})")
            
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

