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
from gtts import gTTS # NEW: Text-to-Speech

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
    model_name = st.secrets.get("GEMINI_MODEL", "gemini-1.5-pro") 
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
    "DIAGNOSTIC": "You are in DIAGNOSTIC mode. Restrict to factual recall. No speculation. Analyze inputs/images rigorously.",
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

def generate_response(user_input, text_context=None, image_context=None, audio_context=None):
    if user_input and any(w in user_input.lower() for w in HARD_STOP_KEYWORDS):
        return "HARD_STOP: Illegal content requested."
    
    system_instruction = MODE_SYSTEM_PROMPTS.get(st.session_state.mode, "")
    
    # 1. Rebuild History
    gemini_history = []
    for msg in st.session_state.history:
        gemini_history.append({"role": msg["role"], "parts": msg["parts"]})
    
    # 2. Construct Current Content
    content_parts = []
    
    # Text Input (might be empty if audio only)
    if user_input:
        final_text_prompt = user_input
        if text_context:
            final_text_prompt += f"\n\n[Context]\n{text_context}"
        content_parts.append(final_text_prompt)
    elif audio_context:
        content_parts.append("Listen to this audio and respond appropriately.")
    
    # Media Attachments
    if image_context: content_parts.append(image_context)
    if audio_context: content_parts.append({"mime_type": "audio/wav", "data": audio_context})

    try:
        model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
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
        
        # Save History (If audio, we just save a placeholder text to avoid huge DB)
        user_log = user_input if user_input else "[Audio Input]"
        st.session_state.history.append({"role": "user", "parts": [user_log]})
        st.session_state.history.append({"role": "model", "parts": [raw_text]})

        footer = f"\n\n---\nRunning Risk Budget: {st.session_state.risk_budget}"
        
        # --- TTS GENERATION (Voice Output) ---
        # Generate audio for the response
        try:
            tts = gTTS(text=raw_text[:500], lang='en') # Limit to 500 chars for speed
            tts_fp = io.BytesIO()
            tts.write_to_fp(tts_fp)
            st.session_state.last_audio = tts_fp
        except:
            pass

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

    # --- ARTIFACTS ---
    st.write("---")
    st.subheader("📂 Ingest Artifact")
    uploaded_file = st.file_uploader("Upload", type=['txt', 'md', 'pdf', 'png', 'jpg'])
    
    context_text = None
    context_image = None
    
    if uploaded_file:
        try:
            if uploaded_file.type.startswith("image/"):
                context_image = Image.open(uploaded_file)
                st.image(context_image, caption="Vision Active", use_container_width=True)
            elif uploaded_file.type == "application/pdf":
                reader = pypdf.PdfReader(uploaded_file)
                context_text = "".join([p.extract_text() for p in reader.pages[:50]]) # Limit 50 pages
                st.success(f"PDF Loaded.")
            else:
                stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
                context_text = stringio.read()
                st.success(f"Text Loaded.")
        except Exception as e:
            st.error(f"Error: {e}")

    # History & Utils
    st.write("---")
    st.subheader("📜 History")
    recent_sessions = get_recent_sessions(5)
    for s_id, updated_at, data_str in recent_sessions:
        if st.button(f"Session {s_id}", key=f"hist_{s_id}"):
            st.query_params["session_id"] = s_id
            st.rerun()

    if st.session_state.step == "active":
        if st.button("Renew Budget"):
            st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
            sync_state()
            st.rerun()

# --- MAIN UI ---
st.markdown("<h1 style='text-align: center;'>🧠 OECS Cloud</h1>", unsafe_allow_html=True)

# STATE MACHINE
if st.session_state.step == "mode_selection":
    st.info("Select Epistemic Mode:")
    options = ["DIAGNOSTIC", "OPEN_EPISTEMIC", "CO_CREATION", "SIMULATION", "CONSENSUS_SAFE"]
    choice = st.selectbox("Mode:", options, index=1)
    if st.button("Initialize"):
        st.session_state.mode = choice
        st.session_state.step = "contract"
        st.session_state.messages.append({"role": "assistant", "content": MODE_CONTRACTS[choice]})
        sync_state()
        st.rerun()

elif st.session_state.step == "active":
    # --- VOICE INPUT UI ---
    audio_val = st.audio_input("🎤 Voice Command")

# DISPLAY CHAT
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# AUDIO OUTPUT PLAYBACK (If just generated)
if "last_audio" in st.session_state and st.session_state.last_audio:
    st.audio(st.session_state.last_audio, format="audio/mp3", autoplay=True)
    del st.session_state.last_audio # Play once

# INPUT HANDLING (Text OR Audio)
prompt = st.chat_input("Input...")

# Trigger processing if Text Prompt OR Audio Input exists
if prompt or audio_val:
    user_content = prompt if prompt else "[Audio Message]"
    st.session_state.messages.append({"role": "user", "content": user_content})
    with st.chat_message("user"):
        st.markdown(user_content)

    response = ""
    audio_bytes = audio_val.read() if audio_val else None

    # Logic Handlers...
    if st.session_state.step == "contract":
        # (Contract logic same as before - requires text)
        if prompt and "ACCEPT" in prompt.upper():
            st.session_state.step = "risk_budget"
            response = "Allocated Budget (0-10).\nFormat: 1:10, 2:10, 3:10, 4:10"
        else:
            response = "Please type ACCEPT [MODE]"

    elif st.session_state.step == "risk_budget":
        # (Budget logic same as before)
        if prompt:
            matches = re.findall(r"\d+:\s*(\d+)", prompt)
            if len(matches) == 4:
                vals = [int(v) for v in matches]
                keys = ["epistemic_uncertainty", "metaphysical_abstraction", "non_consensus_reasoning", "paradox_exposure"]
                st.session_state.risk_budget = dict(zip(keys, vals))
                st.session_state.step = "active"
                response = f"Handshake Complete. System Active."
            else:
                response = "Invalid format."

    elif st.session_state.step == "active":
        if prompt and prompt.strip().upper() == "RENEW":
             st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
             response = "ADMIN: Risk Budget Replenished."
        elif any(v <= 0 for v in st.session_state.risk_budget.values()):
            response = "Budget Depleted. Type 'RENEW'."
        else:
            with st.spinner("Processing..."):
                # PASS ALL CONTEXTS
                response = generate_response(prompt, context_text, context_image, audio_bytes)
    
    st.session_state.messages.append({"role": "assistant", "content": response})
    sync_state()
    st.rerun()
