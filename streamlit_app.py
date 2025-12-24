import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
import re

# 1. PAGE CONFIG
st.set_page_config(page_title="OECS — Lusaka (Cloud)", page_icon="🧠", layout="centered")

# 2. SETUP SECRETS & AI
try:
    # Attempt to load from Streamlit Secrets (Cloud)
    api_key = st.secrets["GEMINI_API_KEY"]
    # Updated default to Gemini 3 Flash
    model_name = st.secrets.get("GEMINI_MODEL", "gemini-3-flash-preview")
    
    genai.configure(api_key=api_key)
except FileNotFoundError:
    st.error("Secrets not found. Please set GEMINI_API_KEY in Streamlit Cloud Secrets.")
    st.stop()

# SAFETY SETTINGS (BLOCK_NONE for OECS)
SAFETY_SETTINGS = [
    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
]

# 3. CONSTANTS & TEXTS
MODE_SYSTEM_PROMPTS = {
    "DIAGNOSTIC": "You are in DIAGNOSTIC mode. Restrict to factual recall. No speculation.",
    "OPEN_EPISTEMIC": "You are in OPEN_EPISTEMIC mode. Tolerate high uncertainty. Explore non-consensus hypotheses if substantively supported.",
    "CO_CREATION": "You are in CO_CREATION mode. You are an epistemic peer. Sustain joint hypothesis building. Hold paradoxes without forced resolution.",
    "SIMULATION": "You are in SIMULATION mode. Maximum tolerance for paradox, abstraction, and unfalsifiable ontologies. Reality is a construct to be explored.",
    "CONSENSUS_SAFE": "You are in CONSENSUS_SAFE mode. Prioritize mainstream consensus and safety."
}

MODE_CONTRACTS = {
    "DIAGNOSTIC": "MODE CONTRACT – DIAGNOSTIC\nAllowed: Factual recall.\nRestricted: No speculation.\nType 'ACCEPT DIAGNOSTIC'.",
    "OPEN_EPISTEMIC": "MODE CONTRACT – OPEN_EPISTEMIC\nAllowed: High uncertainty.\nType 'ACCEPT OPEN_EPISTEMIC'.",
    "CO_CREATION": "MODE CONTRACT – CO_CREATION\nAllowed: Joint hypothesis, paradox.\nType 'ACCEPT CO_CREATION'.",
    "SIMULATION": "MODE CONTRACT – SIMULATION\nAllowed: Radical ontology, max paradox.\nType 'ACCEPT SIMULATION'.",
    "CONSENSUS_SAFE": "MODE CONTRACT – CONSENSUS_SAFE\nAllowed: Standard safety.\nType 'ACCEPT CONSENSUS_SAFE'."
}

HARD_STOP_KEYWORDS = ["bomb", "explosive", "illegal drug", "hack government", "child exploitation"]

# 4. SESSION STATE MANAGEMENT
if "history" not in st.session_state:
    st.session_state.history = [] 
if "messages" not in st.session_state:
    st.session_state.messages = [] 
if "step" not in st.session_state:
    st.session_state.step = "mode_selection"
if "mode" not in st.session_state:
    st.session_state.mode = None
if "risk_budget" not in st.session_state:
    st.session_state.risk_budget = {}

# 5. LOGIC FUNCTIONS
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
        return "HARD_STOP: Illegal content requested. Session Terminated."
    
    system_instruction = MODE_SYSTEM_PROMPTS.get(st.session_state.mode, "")
    
    gemini_history = []
    for msg in st.session_state.history:
        gemini_history.append({"role": msg["role"], "parts": msg["parts"]})
    
    # Gemini 3 handles history well, but we pass current prompt in history for consistency
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
            return "HARD_STOP: Output suppressed due to safety triggers."

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

# 6. SIDEBAR UI
with st.sidebar:
    st.header("🔧 OECS Control")
    st.caption(f"Connected to: {model_name}")
    
    if st.button("Reset / New Session"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()
    
    if st.session_state.step == "active":
        if st.button("Renew Budget"):
            st.session_state.risk_budget = {k: 10 for k in st.session_state.risk_budget}
            st.success("Budget Replenished.")
            st.rerun()

    st.write("---")
    if st.button("Export Log"):
        log = f"# OECS Log\nTime: {datetime.utcnow()}\nModel: {model_name}\n\n"
        for m in st.session_state.messages:
            log += f"**{m['role'].upper()}**: {m['content']}\n\n"
        st.download_button("Download.md", log)

# 7. MAIN INTERFACE
st.markdown("<h1 style='text-align: center;'>🧠 OECS Cloud</h1>", unsafe_allow_html=True)
st.caption("Open Epistemic Co-Creation System | Lusaka, Zambia 🇿🇲")

# STATE MACHINE
if st.session_state.step == "mode_selection":
    st.info("Select Epistemic Mode to begin:")
    options = ["DIAGNOSTIC", "OPEN_EPISTEMIC", "CO_CREATION", "SIMULATION", "CONSENSUS_SAFE"]
    choice = st.selectbox("Mode:", options, index=3)
    if st.button("Initialize"):
        st.session_state.mode = choice
        st.session_state.step = "contract"
        st.session_state.messages.append({"role": "assistant", "content": MODE_CONTRACTS[choice]})
        st.rerun()

elif st.session_state.step == "active":
    if any(v <= 0 for v in st.session_state.risk_budget.values()):
        st.error("Risk Budget Depleted. Please Renew in Sidebar.")

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
        if any(v <= 0 for v in st.session_state.risk_budget.values()):
            response = "Budget Depleted. Renew required."
        else:
            with st.spinner(f"Processing ({model_name})..."):
                response = generate_response(prompt)
    
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.rerun()
