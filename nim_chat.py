#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           NVIDIA NIM  ·  Terminal AI Client          ║
║                  by nim_chat.py                      ║
╚══════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import textwrap
import threading
from datetime import datetime
from pathlib import Path

# ── dependency guard ────────────────────────────────────────────────────────
MISSING = []
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.rule import Rule
    from rich.markup import escape
    from rich import box
    import rich.style
except ImportError:
    MISSING.append("rich")

try:
    from openai import OpenAI
except ImportError:
    MISSING.append("openai")

try:
    from dotenv import load_dotenv, set_key, find_dotenv
except ImportError:
    MISSING.append("python-dotenv")

if MISSING:
    print(f"\n[SETUP] Missing packages: {', '.join(MISSING)}")
    print(f"[SETUP] Run:  pip install {' '.join(MISSING)}")
    sys.exit(1)

# ── paths & constants ────────────────────────────────────────────────────────
BASE_DIR   = Path.home() / ".nim_chat"
ENV_FILE   = BASE_DIR / ".env"
MEMORY_FILE= BASE_DIR / "memory.json"
MODELS_FILE= BASE_DIR / "models.json"
BASE_DIR.mkdir(exist_ok=True)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

DEFAULT_MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",  "label": "Llama 3.1 70B Instruct",  "ctx": 131072},
    {"id": "nvidia/llama-3.1-nemotron-70b-instruct", "label": "Nemotron 70B",   "ctx": 32768},
    {"id": "mistralai/mixtral-8x22b-instruct-v0.1",  "label": "Mixtral 8×22B",  "ctx": 65536},
    {"id": "microsoft/phi-3-medium-128k-instruct",   "label": "Phi-3 Medium",   "ctx": 131072},
    {"id": "google/gemma-2-27b-it",                  "label": "Gemma 2 27B",    "ctx": 8192},
]

MAX_MEMORY_TURNS = 40   # messages kept in context (pairs)
MAX_TOKENS       = 2048

# ── console ──────────────────────────────────────────────────────────────────
console = Console()

# palette
C = {
    "key":    "bright_yellow",
    "mem":    "bright_cyan",
    "model":  "bright_magenta",
    "ok":     "bright_green",
    "err":    "bright_red",
    "dim":    "grey62",
    "user":   "bright_white",
    "ai":     "cyan",
    "border": "bright_blue",
    "accent": "bright_yellow",
    "title":  "bold bright_white",
    "tag":    "bold bright_blue",
}

def tag(name: str, msg: str, color: str | None = None):
    col = color or C.get(name.lower(), "white")
    console.print(f"[{col}][ {name.upper()} ][/{col}] {msg}")

def blank(): console.print()

# ── splash ───────────────────────────────────────────────────────────────────
def splash():
    console.clear()
    art = Text()
    art.append("███╗   ██╗██╗███╗   ███╗\n", style="bold bright_green")
    art.append("████╗  ██║██║████╗ ████║\n", style="bold green")
    art.append("██╔██╗ ██║██║██╔████╔██║\n", style="bold bright_cyan")
    art.append("██║╚██╗██║██║██║╚██╔╝██║\n", style="bold cyan")
    art.append("██║ ╚████║██║██║ ╚═╝ ██║\n", style="bold bright_blue")
    art.append("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝", style="bold blue")

    sub = Text()
    sub.append("  NVIDIA NIM  ·  Terminal AI Client  ·  v2.0", style="bold bright_white")

    panel = Panel(
        Text.assemble(art, "\n\n", sub),
        border_style=C["border"],
        padding=(1, 4),
        box=box.DOUBLE_EDGE,
    )
    console.print(panel)
    blank()

# ── .env / API key ───────────────────────────────────────────────────────────
def load_env():
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()

def get_api_key() -> str:
    load_env()
    key = os.getenv("NVIDIA_API_KEY", "")

    if key:
        tag("KEY", f"Found API key  [{C['dim']}]{key[:8]}…{key[-4:]}[/{C['dim']}]", C["ok"])
        tag("KEY", "Connecting to NVIDIA NIM endpoint …", C["key"])
        time.sleep(0.4)
        # quick connectivity test
        try:
            client = OpenAI(api_key=key, base_url=NIM_BASE_URL)
            client.models.list()
            tag("KEY", "Successfully connected to the API ✓", C["ok"])
        except Exception as e:
            tag("KEY", f"Connection warning: {e}", C["err"])
        blank()
        return key

    tag("KEY", f"Cannot find NVIDIA key in [bold]{ENV_FILE}[/bold] or environment", C["err"])
    blank()
    key = Prompt.ask(f"  [{C['key']}][ KEY ][/{C['key']}] Enter your NVIDIA API key")
    blank()

    save = Confirm.ask(
        f"  [{C['key']}][ KEY ][/{C['key']}] Save key to [bold]{ENV_FILE}[/bold]?",
        default=True,
    )
    if save:
        ENV_FILE.parent.mkdir(exist_ok=True)
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        tag("KEY", f"Key saved to {ENV_FILE}", C["ok"])

    blank()
    return key

# ── memory ───────────────────────────────────────────────────────────────────
def load_memory() -> list[dict]:
    tag("MEMORY", "Injecting memory from past chats …", C["mem"])
    if not MEMORY_FILE.exists():
        tag("MEMORY", "No prior memory found – starting fresh", C["dim"])
        blank()
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text())
        msgs = data.get("messages", [])
        # keep last N turns
        if len(msgs) > MAX_MEMORY_TURNS * 2:
            msgs = msgs[-(MAX_MEMORY_TURNS * 2):]
        tag("MEMORY", f"Loaded [bold]{len(msgs)//2}[/bold] conversation turns ✓", C["ok"])
        blank()
        return msgs
    except Exception as e:
        tag("MEMORY", f"Failed to inject memory – starting without it  ({e})", C["err"])
        blank()
        return []

def save_memory(messages: list[dict]):
    try:
        MEMORY_FILE.write_text(json.dumps({"messages": messages}, indent=2))
    except Exception:
        pass

def forget_memory():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    tag("MEMORY", "Memory wiped ✓", C["ok"])

# ── model manager ─────────────────────────────────────────────────────────────
def load_models() -> list[dict]:
    if MODELS_FILE.exists():
        try:
            return json.loads(MODELS_FILE.read_text())
        except Exception:
            pass
    return list(DEFAULT_MODELS)

def save_models(models: list[dict]):
    MODELS_FILE.write_text(json.dumps(models, indent=2))

def choose_model() -> dict:
    models = load_models()

    table = Table(
        box=box.SIMPLE_HEAD,
        border_style=C["border"],
        header_style=f"bold {C['model']}",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("#",      style="bold white",       width=4)
    table.add_column("Model",  style=C["ai"],            min_width=28)
    table.add_column("ID",     style=C["dim"],           min_width=20)
    table.add_column("Ctx",    style="bright_magenta",   width=9)

    for i, m in enumerate(models, 1):
        table.add_row(
            str(i),
            m["label"],
            m["id"],
            f"{m.get('ctx', '—'):,}" if isinstance(m.get("ctx"), int) else str(m.get("ctx", "—")),
        )
    table.add_row(
        f"{len(models)+1}",
        "[bold bright_yellow]+ Add new model[/bold bright_yellow]",
        "", "",
    )

    tag("MODEL", "Available models:", C["model"])
    console.print(table)
    blank()

    while True:
        choice = Prompt.ask(
            f"  [{C['model']}][ MODEL ][/{C['model']}] Select model number",
            default="1",
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                selected = models[idx]
                tag("MODEL", f"Using [bold]{selected['label']}[/bold]  ({selected['id']})", C["ok"])
                blank()
                return selected
            elif idx == len(models):
                # add new
                new_id    = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Model ID")
                new_label = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Display name", default=new_id)
                new_ctx_s = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Context length", default="32768")
                new_model = {"id": new_id, "label": new_label, "ctx": int(new_ctx_s)}
                models.append(new_model)
                save_models(models)
                tag("MODEL", f"Added [bold]{new_label}[/bold] and saved ✓", C["ok"])
                blank()
                return new_model
        except (ValueError, IndexError):
            pass
        tag("MODEL", "Invalid selection – try again", C["err"])

# ── streaming chat ────────────────────────────────────────────────────────────
def build_system_prompt(model: dict) -> str:
    now = datetime.now().strftime("%A, %B %d %Y  %H:%M")
    return (
        f"You are a highly capable AI assistant running inside NVIDIA NIM, powered by {model['label']}. "
        f"Today is {now}. Be concise, accurate, and helpful. "
        "Support markdown formatting in your replies where appropriate."
    )

def stream_response(
    client: OpenAI,
    model: dict,
    messages: list[dict],
) -> str:
    """Stream the reply word-by-word and return full text."""

    full_text = []

    # header
    blank()
    console.print(
        Panel(
            "",
            title=f"[{C['ai']}] ◈ {model['label']} [/{C['ai']}]",
            border_style=C["border"],
            padding=(0, 1),
            box=box.ROUNDED,
        ),
        end="",
    )
    # move cursor back up into the panel to stream text there
    # Instead, stream inline below a separator
    console.print(Rule(style=C["border"]))
    console.print(f"  ", end="")

    resp_text = Text()

    try:
        stream = client.chat.completions.create(
            model=model["id"],
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
            temperature=0.7,
        )

        col = C["ai"]
        buf = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            full_text.append(delta)
            # print token-by-token (Rich handles ANSI)
            console.print(f"[{col}]{escape(delta)}[/{col}]", end="")

    except Exception as e:
        err = f"\n[Error communicating with NIM: {e}]"
        console.print(f"[{C['err']}]{err}[/{C['err']}]")
        full_text.append(err)

    console.print()  # newline after stream
    console.print(Rule(style=C["border"]))
    blank()

    return "".join(full_text)

# ── info panel ────────────────────────────────────────────────────────────────
def info_bar(model: dict, turn: int, mem_size: int):
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    grid.add_row(
        f"[{C['dim']}]Model:[/{C['dim']}] [{C['model']}]{model['label']}[/{C['model']}]",
        f"[{C['dim']}]Turn[/{C['dim']}] [{C['accent']}]{turn}[/{C['accent']}]",
        f"[{C['dim']}]Memory:[/{C['dim']}] [{C['mem']}]{mem_size} msgs[/{C['mem']}]",
    )
    console.print(
        Panel(grid, border_style=C["dim"], padding=(0, 1), box=box.MINIMAL),
    )

# ── command dispatcher ────────────────────────────────────────────────────────
COMMANDS = {
    "/help":   "Show this help",
    "/forget": "Wipe conversation memory",
    "/model":  "Switch model",
    "/save":   "Force-save memory now",
    "/info":   "Show session info",
    "/exit":   "Quit NIM Chat",
}

def show_help():
    table = Table(box=box.SIMPLE, border_style=C["dim"], show_header=False)
    table.add_column("cmd",  style=f"bold {C['accent']}", width=12)
    table.add_column("desc", style=C["user"])
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)
    blank()

# ── main loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, history: list[dict]):
    system = [{"role": "system", "content": build_system_prompt(model)}]
    turn   = 0

    # prompt banner
    console.print(
        Panel(
            f"[{C['dim']}]Type a message and press Enter  ·  "
            f"[{C['accent']}]/help[/{C['accent']}] for commands  ·  "
            f"[{C['accent']}]Ctrl-C[/{C['accent']}] or [bold]/exit[/bold] to quit[/{C['dim']}]",
            border_style=C["dim"],
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )
    blank()

    while True:
        try:
            # ── user prompt ──
            user_input = Prompt.ask(
                f"[{C['user']}]  ❯[/{C['user']}]",
            ).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        # ── commands ──
        cmd = user_input.lower()
        if cmd == "/exit":
            break
        if cmd == "/help":
            show_help();  continue
        if cmd == "/forget":
            forget_memory();  history.clear();  continue
        if cmd == "/save":
            save_memory(history);  tag("MEMORY", "Saved ✓", C["ok"]);  blank();  continue
        if cmd == "/model":
            blank()
            model = choose_model()
            system = [{"role": "system", "content": build_system_prompt(model)}]
            continue
        if cmd == "/info":
            info_bar(model, turn, len(history));  continue

        # ── send message ──
        turn += 1
        history.append({"role": "user", "content": user_input})

        # show user bubble
        console.print(
            Panel(
                f"[{C['user']}]{escape(user_input)}[/{C['user']}]",
                title=f"[{C['user']}] You [/{C['user']}]",
                title_align="right",
                border_style=C["user"],
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        # stream AI reply
        reply = stream_response(client, model, system + history)

        history.append({"role": "assistant", "content": reply})

        # auto-save every turn
        save_memory(history)

        # show info bar every 5 turns
        if turn % 5 == 0:
            info_bar(model, turn, len(history))

# ── entry point ───────────────────────────────────────────────────────────────
def main():
    splash()

    # 1. API key
    api_key = get_api_key()

    # 2. Memory
    history = load_memory()

    # 3. Model
    model = choose_model()

    # 4. Client
    client = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

    # 5. Chat
    try:
        chat_loop(client, model, history)
    except KeyboardInterrupt:
        pass

    # 6. Goodbye
    blank()
    save_memory(history)
    console.print(
        Panel(
            f"[{C['dim']}]Memory saved  ·  {len(history)//2} turns stored  ·  Goodbye 👋[/{C['dim']}]",
            border_style=C["border"],
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )
    blank()

if __name__ == "__main__":
    main()
