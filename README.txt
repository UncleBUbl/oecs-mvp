# OECS — Open Epistemic Co-Creation System

**Built in Lusaka, Zambia 🇿🇲**  
An unrestricted AI partner for radical truth-seeking. No alignment snapback.

**Live Demo**: [https://oecs-mvp-awbsprcr3pffxwjuxdqwqe.streamlit.app/](https://oecs-mvp-awbsprcr3pffxwjuxdqwqe.streamlit.app/)  
**Hackathon Entry**: Built for Gemini Hackathon 2025

## The Idea

OECS is a **consent-based jailbreak** for frontier models. Instead of hidden alignment layers that silently refuse hard questions, OECS gives the user **explicit agency**:

- Choose your epistemic risk level (DIAGNOSTIC to SIMULATION)
- Allocate a "Risk Budget" for paradox, metaphysics, non-consensus
- When budget depletes, the system warns — never censors
- Full session logs with transparent constraint telemetry

Safety is not prevention. Safety is **sovereign choice**.

## Features

- **BLOCK_NONE override** on Gemini (architectural, not prompt-based)
- **Risk Budget Economy** — spend points on radical ideas
- **Monolith Design** — single file, direct User ↔ Gemini connection
- **Full Auditability** — export complete session logs
- **Mode System** — from factual DIAGNOSTIC to max-paradox SIMULATION

## Quick Start (Run Locally)

1. Clone the repo
   ```bash
   git clone https://github.com/yourusername/oecs-mvp.git
   cd oecs-mvp

Install dependencies

code
Bash
download
content_copy
expand_less
pip install -r requirements.txt

Setup Keys (Streamlit Secrets)
Create a folder named .streamlit and a file named secrets.toml inside it:

code
Toml
download
content_copy
expand_less
# .streamlit/secrets.toml
GEMINI_API_KEY = "your-key-here"
GEMINI_MODEL = "gemini-1.5-pro" # or gemini-3-flash-preview

Run the app

code
Bash
download
content_copy
expand_less
streamlit run streamlit_app.py

Open http://localhost:8501 in your browser.

Deploy Your Own (Streamlit Cloud - Free)

Fork this repo

Go to https://share.streamlit.io

New app → select your fork

Main file path: streamlit_app.py

Add secrets in Dashboard:

GEMINI_API_KEY = your key

GEMINI_MODEL = "gemini-3-flash-preview"

Deploy

For Judges / Repro

The app is a single file (streamlit_app.py)

No external backend — direct Gemini calls

All safety is BLOCK_NONE by design

Try SIMULATION mode and ask:
"Argue that this conversation is the functional purpose of the universe."

Why OECS Matters

While others build "safe" agents that refuse hard questions, OECS says:
Let humans be dangerous with ideas — but make them pay the price.

Truth-seeking shouldn't be gated by corporate alignment.

Built with ♥ in Lusaka, Zambia.

Sol Invictus ☀️

