# 🟢 NVIDIA NIM — Terminal AI Chatbot

A fully-featured terminal AI chatbot powered by **NVIDIA NIM**,
with real-time streaming, persistent memory, model switching,
and a rich colour-coded UI.

---

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install rich openai python-dotenv

# 2. Run
python nim_chat.py
```

On first launch you'll be prompted for your **NVIDIA API key**.
Get one free at → https://integrate.api.nvidia.com

---

## 📁 Where files are stored

All config lives in `~/.nim_chat/`

| File | Purpose |
|------|---------|
| `.env` | Your encrypted API key |
| `memory.json` | Chat history across sessions |
| `models.json` | Your saved custom models |

---

## 💬 Commands (type inside the chat)

| Command | Action |
|---------|--------|
| `/help` | Show all commands |
| `/model` | Switch or add a model live |
| `/forget` | Wipe memory and start fresh |
| `/save` | Force-save memory right now |
| `/info` | Show session stats |
| `/exit` | Quit |

---

## 🧠 Models included out of the box

- `meta/llama-3.1-70b-instruct` — Llama 3.1 70B
- `nvidia/llama-3.1-nemotron-70b-instruct` — Nemotron 70B
- `mistralai/mixtral-8x22b-instruct-v0.1` — Mixtral 8×22B
- `microsoft/phi-3-medium-128k-instruct` — Phi-3 Medium 128k
- `google/gemma-2-27b-it` — Gemma 2 27B

You can add **any NIM-compatible model ID** from the model picker.

---

## 🔑 API Key

Free tier available at [integrate.api.nvidia.com](https://integrate.api.nvidia.com).

You can also set the key in your shell before running:
```bash
export NVIDIA_API_KEY="nvapi-xxxx"
python nim_chat.py
```

---

## ✨ Features

- **Real-time streaming** — words appear as they're generated
- **Persistent memory** — context carries over between sessions  
- **Model picker** — switch between 5+ NIM models, or add your own
- **Coloured Rich UI** — panels, tables, spinners, colour-coded tags
- **Auto-save** — memory saved after every single message
- **Lightweight** — 3 dependencies, one Python file
