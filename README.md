# NVIDIA NIM Terminal AI Client

```
███╗   ██╗██╗███╗   ███╗
████╗  ██║██║████╗ ████║
██╔██╗ ██║██║██╔████╔██║
██║╚██╗██║██║██║╚██╔╝██║
██║ ╚████║██║██║ ╚═╝ ██║
╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝
```

A feature-rich terminal AI chatbot powered by [NVIDIA NIM](https://integrate.api.nvidia.com), available in both **Python** and **JavaScript (Node.js)**. Real-time streaming, per-chat memory, syntax-highlighted code panels, session management, system prompts, and a full settings system — all inside your terminal.

---

## Features

| Feature | Detail |
|---|---|
| **Real-time streaming** | Words print as they are generated — transient panel disappears cleanly and the formatted reply replaces it |
| **Multiple chat sessions** | Each chat has its own memory, code folder, and token history. Switch, create, and delete from `/chat` |
| **Persistent memory** | Conversations survive restarts. Resume any chat with `--chat "name"` or `--chat 2` |
| **Syntax-highlighted code** | Every code block gets its own panel with line numbers. Ask for the filename inline before saving |
| **Per-chat code folders** | Saved files land in `codes/<chat-name>/` for clean organisation |
| **System prompt manager** | Write custom instructions per chat, save named presets, apply them in one keystroke |
| **Full settings panel** | 10 configurable options — temperature, max tokens, code theme, auto-naming, and more |
| **Memory viewer** | Browse all past turns, delete any individual turn from memory |
| **Chat history search** | Full-text search across all messages with keyword highlighting |
| **Export to Markdown** | Dump any chat to a `.md` file with `/export` |
| **Token tracking** | Estimated token usage per reply, per chat, and across the session with a context-window progress bar |
| **Retry logic** | Auto-retries on transient 400/500 errors and system-role rejection |
| **CLI flags** | `--chat NAME`, `--list` for scripting and quick access |
| **Two models** | Llama 3.1 70B (general) and Qwen3 Coder 480B (code-focused) |

---

## Quickstart

### Python

```bash
pip install rich openai python-dotenv prompt_toolkit
python nim_chat.py
```

### JavaScript (Node.js 18+)

```bash
npm install
node nim_chat.js
```

> **Get a free NVIDIA API key** at [integrate.api.nvidia.com](https://integrate.api.nvidia.com)
> On first run you will be prompted to enter and optionally save your key.

---

## Usage

```bash
# Python
python nim_chat.py                        # Start a new chat
python nim_chat.py --chat "My Project"    # Resume chat by name
python nim_chat.py --chat 2               # Resume chat by index
python nim_chat.py --list                 # List all chats and exit

# JavaScript
node nim_chat.js                          # Start a new chat
node nim_chat.js --chat "My Project"      # Resume chat by name
node nim_chat.js --chat 2                 # Resume chat by index
node nim_chat.js --list                   # List all chats and exit
```

---

## Commands

Type any of these inside the chat at any time:

| Command | Description |
|---|---|
| `/help` | Show the full command list |
| `/chat` | Open the chat session manager — switch, create, or delete chats |
| `/model` | Switch between AI models mid-conversation |
| `/system` | Manage system prompts — write, save as preset, apply, or clear |
| `/settings` | Open the full settings panel |
| `/memory` | Browse all conversation turns, delete any turn |
| `/search` | Full-text search through chat history |
| `/codes` | Browse, view, or delete saved code files |
| `/export` | Export the current conversation to a Markdown file |
| `/rename` | Rename the current chat |
| `/info` | Detailed session info — tokens, context usage, model, turn count |
| `/forget` | Clear all memory for the current chat |
| `/clear` | Clear the terminal screen |
| `/exit` | Quit the client |

---

## Code Saving

Whenever the AI generates a code block it is displayed in a syntax-highlighted panel with line numbers. You are then prompted inline:

```
  Save as (name · 0 skip · Enter auto):
```

- Type a name like `auth_handler` to save as `codes/<chat>/auth_handler.py`
- Press **Enter** for an auto-generated timestamp name
- Type **`0`** to skip saving
- Shell/terminal blocks are shown but never saved by default

All code files for a chat live under `codes/<chat-name>/`.

---

## System Prompts

`/system` opens an interactive manager:

| Key | Action |
|---|---|
| `n` | Write a one-time prompt for this chat |
| `s` | Write and save a named preset for reuse |
| `1`, `2`... | Apply a saved preset instantly |
| `-1`, `-2`... | Delete a saved preset |
| `r` | Remove the custom prompt from this chat |
| `q` | Back to chat |

Active system prompts show a pink `[SYS]` tag in the chat header.
Presets are stored globally in `~/.nim_chat/system_prompts.json`.

---

## Settings

Open with `/settings`. Type a number to edit, Enter to exit.

| Setting | Default | Options |
|---|---|---|
| Max output tokens | 2048 | 512 / 1024 / 2048 / 4096 |
| Temperature | 0.7 | free value |
| Memory turns kept | 40 | 10 / 20 / 40 / 60 / 80 |
| Stream refresh rate | 6 fps | 4 / 6 / 8 / 12 |
| Code syntax theme | one-dark | one-dark / monokai / dracula / github-dark / solarized-dark |
| Auto-name code files | OFF | toggle |
| Show token count per reply | ON | toggle |
| Confirm before deleting | ON | toggle |
| Compact chat header | OFF | toggle |
| Save bash/shell blocks | OFF | toggle |

Settings are saved to `~/.nim_chat/settings.json`.

---

## Models

| Model | ID | Context |
|---|---|---|
| Llama 3.1 70B | `meta/llama-3.1-70b-instruct` | 131,072 tokens |
| Qwen3 Coder 480B | `qwen/qwen3-coder-480b-a35b-instruct` | 32,768 tokens |

Switch model at any time with `/model` without losing your conversation.

---

## File Structure

```
~/.nim_chat/
├── .env                       API key
├── settings.json              User settings
├── system_prompts.json        Saved system prompt presets
└── chats/
    ├── 20260101_143022_My_Project.json
    └── 20260102_091500_General.json

codes/                         Created next to nim_chat.py / nim_chat.js
├── My_Project/
│   ├── auth_handler.py
│   └── database_schema.sql
└── General/
    └── quick_script.js
```

---

## Requirements

### Python

```bash
pip install rich openai python-dotenv
pip install prompt_toolkit   # optional — for styled input bar
```

### JavaScript

```bash
npm install
# Installs: openai chalk@4 boxen@5 cli-table3 cli-highlight
#           marked@4 marked-terminal@5 minimist dotenv
```

Node.js 18 or higher is required.

---

## Tips

- **Resume a project**: `python nim_chat.py --chat "Backend API"` — resumes or creates that chat instantly.
- **See all chats**: `python nim_chat.py --list` — great for scripting.
- **Specialist persona**: set a system prompt like *"You are a senior Rust engineer. Be terse, idiomatic only."* and save it as a preset named `Rust expert`.
- **Fix a bad exchange**: `/memory` then `-3` to remove a single bad turn without losing everything.
- **Check context health**: `/info` shows a colour-coded bar — green below 60%, amber below 85%, red when nearly full.
- **Auto-save code**: enable `Auto-name code files` in `/settings` to skip the filename prompt entirely.

---

## License

MIT

---

*Built on [NVIDIA NIM](https://www.nvidia.com/en-us/ai/) · Llama 3.1 by Meta · Qwen3 by Alibaba*
