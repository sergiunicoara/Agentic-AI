import streamlit as st
import requests
import uuid

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "is_paused" not in st.session_state:
    st.session_state.is_paused = False
if "messages" not in st.session_state:
    st.session_state.messages = []

st.set_page_config(page_title="HITL Approval Agent", layout="centered")
st.title("🤝 Search Approval Agent")

# Display History
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if not st.session_state.is_paused:
    if prompt := st.chat_input("Ask me a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        response = requests.post("http://localhost:8000/ask", json={"question": prompt, "thread_id": st.session_state.thread_id})
        
        if response.status_code == 200:
            res = response.json()
            if res["is_paused"]:
                st.session_state.is_paused = True
                st.session_state.pending_tool = res["pending_tool"]
                st.rerun()
            else:
                st.session_state.messages.append({"role": "assistant", "content": res["answer"]})
                st.rerun()
        else:
            st.error(f"Error: {response.text}")

else:
    tool_call = st.session_state.pending_tool
    st.warning(f"⚠️ Agent wants to search for: **{tool_call['args'].get('query', 'information')}**")
    
    col1, col2 = st.columns(2)
    
    def handle_action(action_type):
        resp = requests.post(f"http://localhost:8000/act?action={action_type}", 
                             json={"question": "", "thread_id": st.session_state.thread_id})
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.messages.append({"role": "assistant", "content": data["answer"]})
            st.session_state.is_paused = False
            st.rerun()
        else:
            st.error(f"Failed to process action: {resp.text}")

    with col1:
        if st.button("✅ Approve", use_container_width=True):
            handle_action("approve")
    with col2:
        if st.button("❌ Reject", use_container_width=True):
            handle_action("reject")