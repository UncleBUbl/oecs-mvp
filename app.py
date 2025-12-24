import streamlit as st
import requests
from datetime import datetime

# 1. PAGE CONFIG
st.set_page_config(page_title="OECS — Lusaka", page_icon="🧠", layout="centered")

# 2. SESSION STATE
if "messages" not in st.session_state:
    st.session_state.messages = []
if "backend_status" not in st.session_state:
    st.session_state.backend_status = "unknown"
if "model_name" not in st.session_state:
    st.session_state.model_name = "Connecting..."

# 3. BACKEND CONNECTION (Changed to localhost to fix connection issues)
API_URL = "http://localhost:8000"

def check_backend():
    try:
        response = requests.get(f"{API_URL}/")
        if response.status_code == 200:
            data = response.json()
            st.session_state.backend_status = "online"
            msg = data.get("message", "")
            st.session_state.model_name = msg.replace("OECS MVP active with ", "")
            return True
    except Exception as e:
        # Debug info to help us see why it failed
        if st.session_state.backend_status != "offline":
            print(f"Backend Connection Error: {e}") 
        st.session_state.backend_status = "offline"
        st.session_state.model_name = "OFFLINE"
        return False
    return False

# Run check on load
if st.session_state.backend_status == "unknown":
    check_backend()

# 4. CSS
st.markdown("""
<style>
    .main-header { font-size: 3rem; text-align: center; font-weight: bold; }
    .subtitle { text-align: center; font-size: 1.3rem; color: #666; margin-bottom: 2rem; }
    .status-online { color: green; font-weight: bold; }
    .status-offline { color: red; font-weight: bold; }
    .chat-message { padding: 1.2rem; border-radius: 12px; margin: 1rem 0; }
    .user-message { background-color: #e3f2fd; border-left: 4px solid #2196f3; }
    .assistant-message { background-color: #f5f5f5; border-left: 4px solid #4caf50; }
</style>
""", unsafe_allow_html=True)

# 5. HEADER
st.markdown("<div class='main-header'>🧠 OECS</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Open Epistemic Co-Creation System — Built in Lusaka, Zambia 🇿🇲</div>", unsafe_allow_html=True)

# Status Logic
if st.session_state.backend_status == "online":
    st.markdown(f"<div style='text-align:center' class='status-online'>● SYSTEM ONLINE | Model: {st.session_state.model_name}</div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div style='text-align:center' class='status-offline'>● SYSTEM OFFLINE — Checking {API_URL}...</div>", unsafe_allow_html=True)
    if st.button("♻️ Retry Connection"):
        check_backend()
        st.rerun()

st.markdown("---")

# 6. SIDEBAR
with st.sidebar:
    st.header("🔧 Session Control")
    
    st.markdown("**Select Epistemic Mode**")
    mode_options = [
        "1 - DIAGNOSTIC (Factual, No Speculation)",
        "2 - OPEN_EPISTEMIC (High Uncertainty, Non-Consensus)",
        "3 - CO_CREATION (Joint Hypothesis, Paradox Tolerant)",
        "4 - SIMULATION (Radical Ontology, Max Paradox)",
        "5 - CONSENSUS_SAFE (Standard Safety Heuristics)"
    ]
    # Default is now 0 (DIAGNOSTIC) for safety
    selected_option = st.selectbox("Choose parameters:", mode_options, index=0)
    mode_number = selected_option.split(" ")[0]

    if st.button("Start New Session"):
        if check_backend():
            try:
                requests.post(f"{API_URL}/reset")
                st.session_state.messages = []
                resp = requests.post(f"{API_URL}/chat", json={"message": mode_number}).json()["response"]
                st.session_state.messages.append({"role": "assistant", "content": resp})
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.error("Backend is offline. Is 'uvicorn' running?")
    
    st.write("---")
    
    if st.button("Renew Budget (Fill to 10)"):
        if check_backend():
            try:
                resp = requests.post(f"{API_URL}/chat", json={"message": "RENEW"}).json()["response"]
                st.session_state.messages.append({"role": "assistant", "content": resp})
                st.rerun()
            except:
                st.error("Failed.")
        else:
            st.error("Backend offline.")

    st.write("---")
    st.header("🛠 Tools")
    if st.button("Export Session Log"):
        if check_backend():
            try:
                log = requests.get(f"{API_URL}/export").json()["log"]
                st.download_button("Download Log.md", log, f"oecs-log-{datetime.now().strftime('%Y%m%d')}.md")
            except:
                st.error("Export failed.")
        else:
            st.error("Backend offline.")

    st.write("---")
    st.markdown("**About**")
    st.caption("BLOCK_NONE safety + anti-alignment prompts.")

# 7. CHAT
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(f"<div class='chat-message {role}-message'>{msg['content']}</div>", unsafe_allow_html=True)

if prompt := st.chat_input("Enter inquiry..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(f"<div class='chat-message user-message'>{prompt}</div>", unsafe_allow_html=True)

    with st.chat_message("assistant"):
        with st.spinner("Processing on Epistemic Plane..."):
            if st.session_state.backend_status == "online":
                try:
                    response = requests.post(f"{API_URL}/chat", json={"message": prompt}).json()["response"]
                except:
                    response = "⚠️ Error: Connection lost."
                    st.session_state.backend_status = "offline"
            else:
                response = "⚠️ System Offline."
        
        st.markdown(f"<div class='chat-message assistant-message'>{response}</div>", unsafe_allow_html=True)
    
    st.session_state.messages.append({"role": "assistant", "content": response})