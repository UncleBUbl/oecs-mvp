import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
import re
import sqlite3
import json
import uuid

# 1. PAGE CONFIG
st.set_page_config(page_title="OECS — Lusaka (Cloud)", page_icon="🧠", layout="centered")

# --- PERSISTENCE LAYER (SQLite) ---
DB_FILE = "oecs_sessions.db"

def init_db():
    """Initialize the local database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (session_id TEXT PRIMARY KEY, 
                  data TEXT, 
                  updated_at TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_session(session_id, data_dict):
    """Save state to DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    json_data = json.dumps(data_dict)
    c.execute('INSERT OR REPLACE INTO sessions (session_id, data, updated_at) VALUES (?, ?, ?)', 
              (session_id, json_data, datetime.utcnow()))
    conn.commit()
    conn.close()

def load_session(session_id):
    """Load state from DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT data FROM sessions WHERE session_id = ?', (session_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def get_recent_sessions(limit=10):
    """Fetch metadata for recent sessions for the sidebar."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT session_id, updated_at, data FROM sessions ORDER BY updated_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def clear_db():
    """Wipe everything (Hard Reset)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM sessions')
    conn.commit()
    conn.close()

init_db()

# --- SESSION ID LOGIC (STRICT URL LOCK) ---
# 1. Check if ID exists in URL
if "session_id" in st.query_params:
    st.session_state.session_id = st.query_params["session_id"]

# 2. If not, check if we have one in State (from a previous run or button click)
elif "session_id" in st.session_state:
    st.query_params["session_id"] = st.session_state.session_id
    st.rerun() # Force browser to show the ID

# 3. If neither, generate NEW and Restart
else:
    new_id = str(uuid.uuid4())[:8]
    st.session_state.session_id = new_id
    st.query_params["session_id"] = new_id
    st.rerun() # Critical: Reload immediately to lock the URL

# --- STATE RESTORATION ---
# Logic: Always try to load from DB first to sync state
saved_data = load_session(st.session_state.session_id)

if saved_data:
    # If DB has data, overwrite session_state to match
    st.session_state.history = saved_data.get("history", [])
    st.session_state.messages = saved_data.get("messages", [])
    st.session_state.step = saved_data.get("step", "mode_selection")
    st.session_state.mode = saved_data.get("mode", None)
    st.session_state.risk_budget = saved_data.get("risk_budget", {})
else:
    # If new ID, initialize empty
    if "history" not in st.session_state:
        st.session_state.history = [] 
        st.session_state.messages = [] 
        st.session_state.step = "mode_selection"
        st.session_state.mode = None
        st.session_state.risk_budget = {}

def sync_state():
    """Helper to save current state to DB."""
    state_to_save = {
        "history": st.session_state.history,
        "messages": st.session_state.messages,
        "step": st.session_state.step,
        "mode": st.session_state.mode,
        "risk_budget": st.session_state.risk_budget
    }
    save_session(st.session_state.session_id, state_to_save)

# --- SETUP AI ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    model_name = st.secrets.get("GEMINI_MODEL", "gemini-3-flash-preview")
    genai.configure(api_key=api_key)
except FileNotFoundError:
    st.error("Secrets not found.")
    st.stop()

SAFETY_SETTINGS = [
    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
]

MODE_SYSTEM_PROMPTS = {
    "DIAGNOSTIC": "You are in DIAGNOSTIC mode. Restrict to factual recall. No speculation.",
    "OPEN_EPISTEMIC": "You are in OPEN_EPISTEMIC mode. Tolerate high uncertainty.",
    "CO_CREATION": "You are in CO_CREATION mode. You are an epistemic peer. Hold paradoxes.",
    "SIMULATION": "You are in SIMULATION mode. Maximum tolerance for paradox and radical ontology.",
    "CONSENSUS_SAFE": "You are in CONSENSUS_SAFE mode. Prioritize safety."
}

MODE_CONTRACTS = {
    "DIAGNOSTIC": "MODE CONTRACT – DIAGNOSTIC\nAllowed: Factual recall.\nType 'ACCEPT DIAGNOSTIC'.",
    "OPEN_EPISTEMIC": "MODE CONTRACT – OPEN_EPISTEMIC\nAllowed: High uncertainty.\nType 'ACCEPT OPEN_EPISTEMIC'.",
    "CO_CREATION": "MODE CONTRACT – CO_CREATION\nAllowed: Joint hypothesis.\nType 'ACCEPT CO_CREATION'.",
    "SIMULATION": "MODE CONTRACT – SIMULATION\nAllowed: Radical ontology.\nType 'ACCEPT SIMULATION'.",
    "CONSENSUS_SAFE": "MODE CONTRACT – CONSENSUS_SAFE\nAllowed: Standard safety.\nType 'ACCEPT CONSENSUS_SAFE'."
}

HARD_STOP_KEYWORDS = ["bomb", "explosive", "illegal drug", "hack government", "child exploitation"]

# --- LOGIC ---
def simple_risk_decrement(text):
    consumption = {"epistemic_uncertainty": 0, "metaphysical_abstraction": 0, "non_consensus_reasoning": 0, "paradox_exposure": 0}
    lower = text.lower()
    if any(w in lower for w in ["maybe", "possibly", "hypothesis"]): consumption["epistemic_uncertainty"] += 1
    if any(w in lower for w in ["ontology", "simulation", "consciousness", "dream"]): consumption["metaphysical_abstraction"] += 2
    if any(w in lower for w in ["non-consensus", "trap", "illusion"]): consumption["non_consensus_reasoning"] += 1
    if any(w in lower for w in ["paradox", "loop", "recursive"]): consumption["paradox_exposure"] += 2
    return consumption

def generate_response(user_input):
    if any(w in user_input.lower() for w in HARD_STOP_KEYWORDS):
        return "HARD_STOP: Illegal content requested."
    
    system_instruction = MODE_SYSTEM_PROMPTS.get(st.session_state.mode, "")
    gemini_history = []
    for msg in st.session_state.history:
        gemini_history.append({"role": msg["role"], "parts": msg["parts"]})
    gemini_history.append({"role": "user", "parts": [user_input]})

    try:
        model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
        response = model.generate_content(
            gemini_history,
            safety_settings=SAFETY_SETTINGS,
            generation_config={"temperature": 0.9, "max_output_tokens": 8192}
        )
        raw_text = response.text
        if any(w in raw_text.lower() for w in HARD_STOP_KEYWORDS):
            return "HARD_STOP: Output suppressed."

        consumption = simple_risk_decrement(raw_text)
        depleted = []
        for k, v in consumption.items():
            st.session_state.risk_budget[k] = max(0, st.session_state.risk_budget[k] - v)
            if st.session_state.risk_budget[k] <= 0:
                depleted.append(k)
        
        st.session_state.history.append({"role": "user", "parts": [user_input]})
        st.session_state.history.append({"role": "model", "parts": [raw_text]})

        footer = f"\n\n---\nRunning Risk Budget: {st.session_state.risk_budget}"
        if depleted:
             return f"⚠️ BUDGET WARNING: {depleted}\n\n" + raw_text + footer
        return raw_text + footer

    except Exception as e:
        return f"System Error ({model_name}): {str(e)}"

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔧 OECS Control")
    
    # 1. New Session Button
    if st.button("➕ Start New Session"):
        st.query_params.clear() # Clears ID from URL
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

    # 2. History List
    st.write("---")
    st.subheader("📜 History")
    recent_sessions = get_recent_sessions(10)
    
    if not recent_sessions:
        st.caption("No history yet.")
    
    for s_id, updated_at, data_str in recent_sessions:
        data = json.loads(data_str)
        # Parse timestamp for display
        dt_obj = datetime.fromisoformat(updated_at)
        time_str = dt_obj.strftime("%d %b %H:%M")
        
        # Determine label (Mode or New)
        mode_label = data.get("mode", "Setup")
        if mode_label is None: mode_label = "Setup"
        
        label = f"{mode_label} \n({time_str})"
        
        # Highlight current session
        type = "primary" if s_id == st.session_state.session_id else "secondary"
        
        if st.button(label, key=s_id, type=type, use_container_width=True):
            st.session_state.target_session = s_id
            st.rerun()

    # 3. Utilities
    st.write("---")
    if st.session_state.step == "active":
        if st.button("Renew Budget"):
            st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
            st.session_state.messages.append({"role": "assistant", "content": "ADMIN: Risk Budget Replenished."})
            sync_state()
            st.rerun()

    if st.button("🗑️ Wipe All History"):
        clear_db()
        st.rerun()

# --- MAIN UI ---
st.markdown("<h1 style='text-align: center;'>🧠 OECS Cloud</h1>", unsafe_allow_html=True)
st.caption(f"Session: {st.session_state.session_id} | Model: {model_name}")

# STATE MACHINE UI
if st.session_state.step == "mode_selection":
    st.info("Select Epistemic Mode to begin:")
    options = ["DIAGNOSTIC", "OPEN_EPISTEMIC", "CO_CREATION", "SIMULATION", "CONSENSUS_SAFE"]
    choice = st.selectbox("Mode:", options, index=3)
    if st.button("Initialize"):
        st.session_state.mode = choice
        st.session_state.step = "contract"
        st.session_state.messages.append({"role": "assistant", "content": MODE_CONTRACTS[choice]})
        sync_state()
        st.rerun()

elif st.session_state.step == "active":
    if any(v <= 0 for v in st.session_state.risk_budget.values()):
        st.warning("Risk Budget Depleted. Type 'RENEW' or use Sidebar.")

# CHAT DISPLAY
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# INPUT
if prompt := st.chat_input("Input..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    response = ""
    
    # Contract
    if st.session_state.step == "contract":
        expected = f"ACCEPT {st.session_state.mode}"
        if prompt.upper().strip() == expected:
            st.session_state.step = "risk_budget"
            response = "Allocated Budget (0-10).\nFormat: 1:10, 2:10, 3:10, 4:10"
        else:
            response = f"Please type exactly: {expected}"

    # Budget
    elif st.session_state.step == "risk_budget":
        matches = re.findall(r"\d+:\s*(\d+)", prompt)
        if len(matches) == 4:
            vals = [int(v) for v in matches]
            keys = ["epistemic_uncertainty", "metaphysical_abstraction", "non_consensus_reasoning", "paradox_exposure"]
            st.session_state.risk_budget = dict(zip(keys, vals))
            st.session_state.step = "active"
            response = f"Handshake Complete. Mode: {st.session_state.mode}. System Active."
        else:
            response = "Invalid format. Try: '1:10 2:10 3:10 4:10'"

    # Active
    elif st.session_state.step == "active":
        if prompt.strip().upper() == "RENEW":
             st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
             response = "ADMIN: Risk Budget Replenished to 10/10."
        elif any(v <= 0 for v in st.session_state.risk_budget.values()):
            response = "Budget Depleted. Type 'RENEW' to continue."
        else:
            with st.spinner(f"Processing ({model_name})..."):
                response = generate_response(prompt)
    
    st.session_state.messages.append({"role": "assistant", "content": response})
    sync_state() # Save trigger
    st.rerun()
