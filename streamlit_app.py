import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
import re
import sqlite3
import json
import uuid
import io
from PIL import Image
import pypdf

# 1. PAGE CONFIG
st.set_page_config(page_title="OECS — Lusaka (Cloud)", page_icon="🧠", layout="centered")

# --- PERSISTENCE LAYER (SQLite) ---
DB_FILE = "oecs_sessions.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                     (session_id TEXT PRIMARY KEY, 
                      data TEXT, 
                      updated_at TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"DB Init Error: {e}")

def save_session(session_id, data_dict):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        json_data = json.dumps(data_dict)
        c.execute('INSERT OR REPLACE INTO sessions (session_id, data, updated_at) VALUES (?, ?, ?)', 
                  (session_id, json_data, datetime.utcnow()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Save Error: {e}")

def load_session(session_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT data FROM sessions WHERE session_id = ?', (session_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        print(f"Load Error: {e}")
    return None

def get_recent_sessions(limit=10):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT session_id, updated_at, data FROM sessions ORDER BY updated_at DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def clear_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM sessions')
    conn.commit()
    conn.close()

init_db()

# --- SESSION ID LOGIC ---
current_id = st.query_params.get("session_id")

if not current_id and "session_id" in st.session_state:
    current_id = st.session_state.session_id
    st.query_params["session_id"] = current_id 
    st.rerun()

if not current_id:
    new_id = str(uuid.uuid4())[:8]
    st.session_state.session_id = new_id
    st.query_params["session_id"] = new_id
    st.rerun()

st.session_state.session_id = current_id

# --- STATE RESTORATION ---
saved_data = load_session(st.session_state.session_id)

if saved_data and not st.session_state.get("history"):
    st.session_state.history = saved_data.get("history", [])
    st.session_state.messages = saved_data.get("messages", [])
    st.session_state.step = saved_data.get("step", "mode_selection")
    st.session_state.mode = saved_data.get("mode", None)
    st.session_state.risk_budget = saved_data.get("risk_budget", {})
else:
    if "history" not in st.session_state:
        st.session_state.history = [] 
        st.session_state.messages = [] 
        st.session_state.step = "mode_selection"
        st.session_state.mode = None
        st.session_state.risk_budget = {}

def sync_state():
    state_to_save = {
        "history": st.session_state.history,
        "messages": st.session_state.messages,
        "step": st.session_state.step,
        "mode": st.session_state.mode,
        "risk_budget": st.session_state.risk_budget
    }
    save_session(st.session_state.session_id, state_to_save)

# --- AI SETUP ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    model_name = st.secrets.get("GEMINI_MODEL", "gemini-1.5-pro") # Suggesting Pro for Multimodal
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
    "DIAGNOSTIC": "You are in DIAGNOSTIC mode. Restrict to factual recall. Analyze inputs/images rigorously.",
    "OPEN_EPISTEMIC": "You are in OPEN_EPISTEMIC mode. Tolerate high uncertainty. Explore non-consensus hypotheses.",
    "CO_CREATION": "You are in CO_CREATION mode. You are an epistemic peer. Sustain joint hypothesis building.",
    "SIMULATION": "You are in SIMULATION mode. Maximum tolerance for paradox, abstraction, and unfalsifiable ontologies.",
    "CONSENSUS_SAFE": "You are in CONSENSUS_SAFE mode. Prioritize mainstream consensus and safety."
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

def generate_response(user_input, text_context=None, image_context=None):
    if any(w in user_input.lower() for w in HARD_STOP_KEYWORDS):
        return "HARD_STOP: Illegal content requested."
    
    system_instruction = MODE_SYSTEM_PROMPTS.get(st.session_state.mode, "")
    
    # 1. Rebuild History for Gemini
    gemini_history = []
    for msg in st.session_state.history:
        # We assume history contains text only to save tokens/complexity
        gemini_history.append({"role": msg["role"], "parts": msg["parts"]})
    
    # 2. Construct Current Turn Content
    content_parts = []
    
    # Add Text Context (from PDF/Txt) if exists
    final_text_prompt = user_input
    if text_context:
        final_text_prompt += f"\n\n[SYSTEM: Analysis Context Provided]\n{text_context}"
    content_parts.append(final_text_prompt)
    
    # Add Image Context if exists
    if image_context:
        content_parts.append(image_context)

    try:
        model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
        
        # We use generate_content with the list of history + new content
        # Note: For multimodal with history, we append the new complex part
        # Gemini Python SDK handles list of parts well
        
        # If we have history, we might need to use chat session, 
        # but chat session with images can be tricky in some SDK versions.
        # Simplest Monolith approach: Send full history as list of contents
        
        full_conversation = gemini_history + [{"role": "user", "parts": content_parts}]

        response = model.generate_content(
            full_conversation,
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
        
        # Save to history (Text only to keep DB light)
        st.session_state.history.append({"role": "user", "parts": [final_text_prompt]})
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
    st.caption(f"ID: {st.session_state.session_id}")
    
    if st.button("➕ Start New Session"):
        new_id = str(uuid.uuid4())[:8]
        st.query_params["session_id"] = new_id
        for key in list(st.session_state.keys()):
            if key != "session_id": del st.session_state[key]
        st.session_state.session_id = new_id
        st.rerun()

    # --- ARTIFACT INGESTION (PDF/IMG/TXT) ---
    st.write("---")
    st.subheader("📂 Ingest Artifact")
    uploaded_file = st.file_uploader("Upload Artifact", type=['txt', 'md', 'py', 'json', 'csv', 'pdf', 'png', 'jpg', 'jpeg'])
    
    context_text = None
    context_image = None
    
    if uploaded_file is not None:
        try:
            # IMAGE HANDLING
            if uploaded_file.type.startswith("image/"):
                context_image = Image.open(uploaded_file)
                st.image(context_image, caption="Vision Context Active", use_container_width=True)
            
            # PDF HANDLING
            elif uploaded_file.type == "application/pdf":
                reader = pypdf.PdfReader(uploaded_file)
                pdf_text = ""
                for page in reader.pages:
                    pdf_text += page.extract_text() + "\n"
                context_text = pdf_text
                st.success(f"PDF Loaded: {len(pdf_text)} chars")
            
            # TEXT HANDLING
            else:
                stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
                context_text = stringio.read()
                st.success(f"Text Loaded: {len(context_text)} chars")
                
        except Exception as e:
            st.error(f"Read Error: {e}")

    # History
    st.write("---")
    st.subheader("📜 History")
    recent_sessions = get_recent_sessions(10)
    
    if not recent_sessions:
        st.caption("No history yet.")
    
    for s_id, updated_at, data_str in recent_sessions:
        data = json.loads(data_str)
        try:
            dt_obj = datetime.fromisoformat(updated_at)
            time_str = dt_obj.strftime("%d %b %H:%M")
        except:
            time_str = "??"
        mode_label = data.get("mode", "Setup") or "Setup"
        label = f"{mode_label} ({time_str})"
        btype = "primary" if s_id == st.session_state.session_id else "secondary"
        
        if st.button(label, key=f"hist_{s_id}", type=btype, use_container_width=True):
            st.query_params["session_id"] = s_id
            st.rerun()

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
st.caption("Open Epistemic Co-Creation System | Lusaka, Zambia 🇿🇲")

# STATE MACHINE
if st.session_state.step == "mode_selection":
    st.info("Select Epistemic Mode to begin:")
    options = ["DIAGNOSTIC", "OPEN_EPISTEMIC", "CO_CREATION", "SIMULATION", "CONSENSUS_SAFE"]
    choice = st.selectbox("Mode:", options, index=1)
    if st.button("Initialize"):
        st.session_state.mode = choice
        st.session_state.step = "contract"
        st.session_state.messages.append({"role": "assistant", "content": MODE_CONTRACTS[choice]})
        sync_state()
        st.rerun()

elif st.session_state.step == "active":
    if any(v <= 0 for v in st.session_state.risk_budget.values()):
        st.warning("Risk Budget Depleted. Type 'RENEW' or use Sidebar.")

# DISPLAY
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# INPUT
if prompt := st.chat_input("Input..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    response = ""
    
    if st.session_state.step == "contract":
        expected = f"ACCEPT {st.session_state.mode}"
        if prompt.upper().strip() == expected:
            st.session_state.step = "risk_budget"
            response = "Allocated Budget (0-10).\nFormat: 1:10, 2:10, 3:10, 4:10"
        else:
            response = f"Please type exactly: {expected}"

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

    elif st.session_state.step == "active":
        if prompt.strip().upper() == "RENEW":
             st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
             response = "ADMIN: Risk Budget Replenished to 10/10."
        elif any(v <= 0 for v in st.session_state.risk_budget.values()):
            response = "Budget Depleted. Type 'RENEW' to continue."
        else:
            with st.spinner(f"Processing ({model_name})..."):
                # PASS TEXT AND IMAGE CONTEXT
                response = generate_response(prompt, context_text, context_image)
    
    st.session_state.messages.append({"role": "assistant", "content": response})
    sync_state()
    st.rerun()
