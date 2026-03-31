#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           NVIDIA NIM  ·  Terminal AI Client          ║
║              nim_chat.py  ·  v3.0                    ║
╚══════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# ── dependency guard ─────────────────────────────────────────────────────────
MISSING = []
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.markup import escape
    from rich import box
except ImportError:
    MISSING.append("rich")

try:
    from openai import OpenAI
except ImportError:
    MISSING.append("openai")

try:
    from dotenv import load_dotenv, set_key
except ImportError:
    MISSING.append("python-dotenv")

if MISSING:
    print(f"\n[SETUP] Missing packages: {', '.join(MISSING)}")
    print(f"[SETUP] Run:  pip install {' '.join(MISSING)}")
    sys.exit(1)

# ── paths & constants ─────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / ".nim_chat"
ENV_FILE    = BASE_DIR / ".env"
MEMORY_FILE = BASE_DIR / "memory.json"
MODELS_FILE = BASE_DIR / "models.json"
CODES_DIR   = Path.cwd() / "codes"      # saved next to wherever you launch it
BASE_DIR.mkdir(exist_ok=True)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

DEFAULT_MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",              "label": "Llama 3.1 70B Instruct", "ctx": 131072},
    {"id": "nvidia/llama-3.1-nemotron-70b-instruct",    "label": "Nemotron 70B",            "ctx": 32768},
    {"id": "mistralai/mixtral-8x22b-instruct-v0.1",     "label": "Mixtral 8x22B",           "ctx": 65536},
    {"id": "microsoft/phi-3-medium-128k-instruct",      "label": "Phi-3 Medium 128k",       "ctx": 131072},
    {"id": "google/gemma-2-27b-it",                     "label": "Gemma 2 27B",             "ctx": 8192},
    {"id": "deepseek-ai/deepseek-coder-6.7b-instruct", "label": "DeepSeek Coder 6.7B",     "ctx": 16384},
]

MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048

# language tag -> file extension
LANG_EXT = {
    "python": "py",    "py": "py",
    "javascript": "js","js": "js",
    "typescript": "ts","ts": "ts",
    "jsx": "jsx",      "tsx": "tsx",
    "html": "html",    "css": "css",  "scss": "scss",
    "bash": "sh",      "shell": "sh", "sh": "sh",  "zsh": "sh",
    "powershell": "ps1","ps1": "ps1",
    "java": "java",    "kotlin": "kt",
    "c": "c",          "cpp": "cpp",  "c++": "cpp",
    "csharp": "cs",    "cs": "cs",    "rust": "rs",
    "go": "go",        "ruby": "rb",  "rb": "rb",
    "php": "php",      "swift": "swift",
    "r": "r",          "sql": "sql",
    "json": "json",    "yaml": "yaml","yml": "yaml",
    "toml": "toml",    "xml": "xml",  "md": "md",
    "dockerfile": "dockerfile",       "makefile": "makefile",
    "nginx": "conf",   "conf": "conf",
}

def syntax_theme(lang: str) -> str:
    dark = {"bash","shell","sh","powershell","dockerfile","makefile","nginx"}
    return "monokai" if lang.lower() in dark else "one-dark"

# ── console ───────────────────────────────────────────────────────────────────
console = Console(highlight=False)

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
    "code":   "bright_green",
    "saved":  "bold bright_green",
}

def tag(name: str, msg: str, color: str | None = None):
    col = color or C.get(name.lower(), "white")
    console.print(f"[{col}][ {name.upper()} ][/{col}] {msg}")

def blank(): console.print()

# ── splash ────────────────────────────────────────────────────────────────────
def splash():
    console.clear()
    art = Text()
    art.append("███╗   ██╗██╗███╗   ███╗\n", style="bold bright_green")
    art.append("████╗  ██║██║████╗ ████║\n", style="bold green")
    art.append("██╔██╗ ██║██║██╔████╔██║\n", style="bold bright_cyan")
    art.append("██║╚██╗██║██║██║╚██╔╝██║\n", style="bold cyan")
    art.append("██║ ╚████║██║██║ ╚═╝ ██║\n", style="bold bright_blue")
    art.append("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝",   style="bold blue")
    sub = Text()
    sub.append("  NVIDIA NIM  ·  Terminal AI Client  ·  v3.0  ·  Code Edition",
               style="bold bright_white")
    console.print(Panel(
        Text.assemble(art, "\n\n", sub),
        border_style=C["border"],
        padding=(1, 4),
        box=box.DOUBLE_EDGE,
    ))
    blank()

# ── API key ───────────────────────────────────────────────────────────────────
def load_env():
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()

def get_api_key() -> str:
    load_env()
    key = os.getenv("NVIDIA_API_KEY", "")

    if key:
        tag("KEY", f"Found API key  [{C['dim']}]{key[:8]}...{key[-4:]}[/{C['dim']}]", C["ok"])
        tag("KEY", "Connecting to NVIDIA NIM endpoint ...", C["key"])
        time.sleep(0.3)
        try:
            OpenAI(api_key=key, base_url=NIM_BASE_URL).models.list()
            tag("KEY", "Successfully connected to the API [bold]v[/bold]", C["ok"])
        except Exception as e:
            tag("KEY", f"Connection warning: {e}", C["err"])
        blank()
        return key

    tag("KEY", f"Cannot find NVIDIA key in [bold]{ENV_FILE}[/bold] or environment", C["err"])
    blank()
    key = Prompt.ask(f"  [{C['key']}][ KEY ][/{C['key']}] Enter your NVIDIA API key")
    blank()
    if Confirm.ask(f"  [{C['key']}][ KEY ][/{C['key']}] Save key to [bold]{ENV_FILE}[/bold]?", default=True):
        ENV_FILE.parent.mkdir(exist_ok=True)
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        tag("KEY", f"Key saved to {ENV_FILE}", C["ok"])
    blank()
    return key

# ── memory ────────────────────────────────────────────────────────────────────
def load_memory() -> list:
    tag("MEMORY", "Injecting memory from past chats ...", C["mem"])
    if not MEMORY_FILE.exists():
        tag("MEMORY", "No prior memory -- starting fresh", C["dim"])
        blank()
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text())
        msgs = data.get("messages", [])
        if len(msgs) > MAX_MEMORY_TURNS * 2:
            msgs = msgs[-(MAX_MEMORY_TURNS * 2):]
        tag("MEMORY", f"Loaded [bold]{len(msgs)//2}[/bold] conversation turns", C["ok"])
        blank()
        return msgs
    except Exception as e:
        tag("MEMORY", f"Failed to inject memory -- starting without it  ({e})", C["err"])
        blank()
        return []

def save_memory(messages: list):
    try:
        MEMORY_FILE.write_text(json.dumps({"messages": messages}, indent=2))
    except Exception:
        pass

def forget_memory():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    tag("MEMORY", "Memory wiped", C["ok"])

# ── model manager ─────────────────────────────────────────────────────────────
def load_models() -> list:
    if MODELS_FILE.exists():
        try:
            return json.loads(MODELS_FILE.read_text())
        except Exception:
            pass
    return list(DEFAULT_MODELS)

def save_models(models: list):
    MODELS_FILE.write_text(json.dumps(models, indent=2))

def choose_model() -> dict:
    models = load_models()

    table = Table(box=box.SIMPLE_HEAD, border_style=C["border"],
                  header_style=f"bold {C['model']}", show_lines=False, padding=(0, 1))
    table.add_column("#",     style="bold white",     width=4)
    table.add_column("Model", style=C["ai"],          min_width=26)
    table.add_column("ID",    style=C["dim"],         min_width=22)
    table.add_column("Ctx",   style="bright_magenta", width=9)

    for i, m in enumerate(models, 1):
        ctx = f"{m.get('ctx', 0):,}" if isinstance(m.get("ctx"), int) else "?"
        table.add_row(str(i), m["label"], m["id"], ctx)
    table.add_row(
        f"{len(models)+1}",
        f"[bold {C['accent']}]+ Add new model[/bold {C['accent']}]",
        "", "",
    )

    tag("MODEL", "Saved models:", C["model"])
    console.print(table)
    blank()

    while True:
        choice = Prompt.ask(
            f"  [{C['model']}][ MODEL ][/{C['model']}] Select number",
            default="1",
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                sel = models[idx]
                tag("MODEL", f"Using [bold]{sel['label']}[/bold]  [{C['dim']}]{sel['id']}[/{C['dim']}]", C["ok"])
                blank()
                return sel
            if idx == len(models):
                nid   = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Model ID")
                nlbl  = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Display name", default=nid)
                nctx  = Prompt.ask(f"  [{C['model']}][ MODEL ][/{C['model']}] Context length", default="32768")
                nm    = {"id": nid, "label": nlbl, "ctx": int(nctx)}
                models.append(nm)
                save_models(models)
                tag("MODEL", f"Added [bold]{nlbl}[/bold] and saved", C["ok"])
                blank()
                return nm
        except (ValueError, IndexError):
            pass
        tag("MODEL", "Invalid selection -- try again", C["err"])

# ── code block parsing ────────────────────────────────────────────────────────
CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```", re.DOTALL)

def parse_blocks(text: str) -> list:
    """Split response into {'type','content','lang'} dicts."""
    blocks = []
    cursor = 0
    for m in CODE_FENCE.finditer(text):
        s, e = m.span()
        if s > cursor:
            chunk = text[cursor:s].strip()
            if chunk:
                blocks.append({"type": "text", "content": chunk, "lang": ""})
        blocks.append({
            "type":    "code",
            "content": m.group("code"),
            "lang":    m.group("lang").strip().lower() or "text",
        })
        cursor = e
    tail = text[cursor:].strip()
    if tail:
        blocks.append({"type": "text", "content": tail, "lang": ""})
    return blocks

# ── code saver ────────────────────────────────────────────────────────────────
_code_counter: dict = {}

def save_code_block(code: str, lang: str) -> Path:
    CODES_DIR.mkdir(exist_ok=True)
    ext = LANG_EXT.get(lang, lang if lang else "txt")
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    _code_counter[ext] = _code_counter.get(ext, 0) + 1
    n   = _code_counter[ext]
    sfx = f"_{n}" if n > 1 else ""
    fname = f"{lang or 'code'}_{ts}{sfx}.{ext}"
    path  = CODES_DIR / fname
    path.write_text(code, encoding="utf-8")
    return path

# ── render formatted response ─────────────────────────────────────────────────
def render_response(full_text: str, model: dict):
    """
    After streaming completes, parse the reply:
    - Plain text  --> print in AI colour
    - Code blocks --> syntax-highlighted panel + save to codes/
    """
    blocks = parse_blocks(full_text)
    has_code = any(b["type"] == "code" for b in blocks)
    if not has_code:
        return  # streaming already showed plain text -- nothing more to do

    blank()
    console.print(Rule(f"[{C['code']}]  FORMATTED RESPONSE  [/{C['code']}]", style=C["border"]))
    blank()

    for block in blocks:
        if block["type"] == "text":
            if block["content"]:
                console.print(f"  [{C['ai']}]{escape(block['content'])}[/{C['ai']}]")
                blank()
            continue

        # ── code block ────────────────────────────────────────────────────────
        lang  = block["lang"]
        code  = block["content"]
        ext   = LANG_EXT.get(lang, lang if lang else "txt")
        theme = syntax_theme(lang)

        # header grid: language badge left, extension right
        hdr = Table.grid(expand=True, padding=(0, 1))
        hdr.add_column(justify="left")
        hdr.add_column(justify="right")
        badge_txt = f"  {lang.upper() if lang else 'CODE'}  "
        hdr.add_row(
            f"[bold black on {C['code']}]{badge_txt}[/bold black on {C['code']}]"
            f"  [{C['dim']}]syntax: {lang or 'plain'}[/{C['dim']}]",
            f"[{C['dim']}].{ext}[/{C['dim']}]",
        )

        syntax_obj = Syntax(
            code,
            lang if lang else "text",
            theme=theme,
            line_numbers=True,
            word_wrap=False,
            indent_guides=True,
            background_color="default",
        )

        console.print(Panel(
            syntax_obj,
            title=hdr,
            title_align="left",
            border_style=C["code"],
            box=box.HEAVY,
            padding=(0, 1),
        ))

        # save to codes/
        try:
            saved = save_code_block(code, lang)
            try:
                rel = saved.relative_to(Path.cwd())
            except ValueError:
                rel = saved
            lines = len(code.splitlines())
            tag(
                "CODE",
                f"Saved  [{C['saved']}]{rel}[/{C['saved']}]"
                f"  [{C['dim']}]({lines} lines · .{ext})[/{C['dim']}]",
                C["code"],
            )
        except Exception as e:
            tag("CODE", f"Could not save: {e}", C["err"])

        blank()

# ── streaming ─────────────────────────────────────────────────────────────────
def stream_response(client: OpenAI, model: dict, messages: list) -> str:
    blank()
    console.print(Rule(
        f"[{C['ai']}]  {escape(model['label'])}  [/{C['ai']}]",
        style=C["border"],
    ))
    console.print("  ", end="")

    full: list = []
    in_fence   = False
    fence_buf  = ""

    try:
        stream = client.chat.completions.create(
            model=model["id"],
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
            temperature=0.7,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            full.append(delta)

            # track fences to dim code mid-stream
            fence_buf += delta
            if "```" in fence_buf:
                in_fence  = not in_fence
                fence_buf = ""

            colour = C["dim"] if in_fence else C["ai"]
            console.print(f"[{colour}]{escape(delta)}[/{colour}]", end="")

    except Exception as e:
        err = f"\n[Error: {e}]"
        console.print(f"[{C['err']}]{escape(err)}[/{C['err']}]")
        full.append(err)

    console.print()
    console.print(Rule(style=C["border"]))
    return "".join(full)

# ── info bar ──────────────────────────────────────────────────────────────────
def info_bar(model: dict, turn: int, mem_size: int):
    codes_saved = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    grid.add_row(
        f"[{C['dim']}]Model:[/{C['dim']}] [{C['model']}]{model['label']}[/{C['model']}]",
        f"[{C['dim']}]Turn[/{C['dim']}] [{C['accent']}]{turn}[/{C['accent']}]",
        f"[{C['dim']}]Memory:[/{C['dim']}] [{C['mem']}]{mem_size} msgs[/{C['mem']}]",
        f"[{C['dim']}]Codes:[/{C['dim']}] [{C['code']}]{codes_saved} files[/{C['code']}]",
    )
    console.print(Panel(grid, border_style=C["dim"], padding=(0, 1), box=box.MINIMAL))

# ── commands ──────────────────────────────────────────────────────────────────
COMMANDS = {
    "/help":   "Show this help",
    "/forget": "Wipe conversation memory",
    "/model":  "Switch model mid-chat",
    "/save":   "Force-save memory now",
    "/codes":  "List all saved code files",
    "/info":   "Show session stats",
    "/exit":   "Quit NIM Chat",
}

def show_help():
    table = Table(box=box.SIMPLE, border_style=C["dim"], show_header=False, padding=(0, 2))
    table.add_column("cmd",  style=f"bold {C['accent']}", width=10)
    table.add_column("desc", style=C["ai"])
    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(table)
    blank()

def list_codes():
    if not CODES_DIR.exists() or not list(CODES_DIR.glob("*")):
        tag("CODE", f"No code files saved yet  (will appear in [bold]{CODES_DIR}[/bold])", C["dim"])
        blank()
        return

    files = sorted(CODES_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    table = Table(box=box.SIMPLE_HEAD, border_style=C["code"],
                  header_style=f"bold {C['code']}", padding=(0, 2))
    table.add_column("#",     style="bold white", width=4)
    table.add_column("File",  style=C["saved"],   min_width=30)
    table.add_column("Lang",  style=C["accent"],  width=10)
    table.add_column("Lines", style=C["dim"],     width=7)
    table.add_column("Saved", style=C["dim"],     width=18)

    for i, f in enumerate(files[:20], 1):
        try:
            lines = len(f.read_text(encoding="utf-8").splitlines())
        except Exception:
            lines = 0
        ext   = f.suffix.lstrip(".")
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d  %H:%M")
        table.add_row(str(i), f.name, ext, str(lines), mtime)

    tag("CODE", f"Saved files in [bold]{CODES_DIR}[/bold]:", C["code"])
    console.print(table)
    blank()

# ── system prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(model: dict) -> str:
    now = datetime.now().strftime("%A, %B %d %Y  %H:%M")
    return (
        f"You are a highly capable AI assistant running inside NVIDIA NIM, "
        f"powered by {model['label']}. Today is {now}. "
        "Be concise, accurate, and helpful. "
        "When writing code, ALWAYS wrap it in a fenced code block with the correct language tag "
        "(e.g. ```python, ```javascript, ```bash). "
        "Write clean, well-commented, production-ready code."
    )

# ── chat loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, history: list):
    system = [{"role": "system", "content": build_system_prompt(model)}]
    turn   = 0

    console.print(Panel(
        f"[{C['dim']}]Type a message and press Enter  "
        f"[{C['accent']}]/help[/{C['accent']}] for commands  "
        f"Code auto-saves to [{C['code']}]codes/[/{C['code']}]  "
        f"[{C['accent']}]Ctrl-C[/{C['accent']}] to quit[/{C['dim']}]",
        border_style=C["dim"],
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    blank()

    while True:
        try:
            user_input = Prompt.ask(f"[{C['user']}]  >[/{C['user']}]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd == "/exit":
            break
        if cmd == "/help":
            show_help();  continue
        if cmd == "/forget":
            forget_memory(); history.clear(); continue
        if cmd == "/save":
            save_memory(history); tag("MEMORY", "Saved", C["ok"]); blank(); continue
        if cmd == "/codes":
            list_codes(); continue
        if cmd == "/model":
            blank(); model = choose_model()
            system = [{"role": "system", "content": build_system_prompt(model)}]
            continue
        if cmd == "/info":
            info_bar(model, turn, len(history)); continue

        # send message
        turn += 1
        history.append({"role": "user", "content": user_input})

        console.print(Panel(
            f"[{C['user']}]{escape(user_input)}[/{C['user']}]",
            title=f"[{C['user']}] You [/{C['user']}]",
            title_align="right",
            border_style=C["user"],
            box=box.ROUNDED,
            padding=(0, 2),
        ))

        # 1. stream raw tokens (real-time)
        reply = stream_response(client, model, system + history)

        # 2. re-render code blocks in highlighted panels and save files
        render_response(reply, model)

        history.append({"role": "assistant", "content": reply})
        save_memory(history)

        if turn % 5 == 0:
            info_bar(model, turn, len(history))

# ── entry point ───────────────────────────────────────────────────────────────
def main():
    splash()
    api_key = get_api_key()
    history = load_memory()
    model   = choose_model()
    client  = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

    try:
        chat_loop(client, model, history)
    except KeyboardInterrupt:
        pass

    blank()
    save_memory(history)
    codes_saved = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    console.print(Panel(
        f"[{C['dim']}]Memory saved  {len(history)//2} turns  "
        f"[{C['code']}]{codes_saved} code files[/{C['code']}] in [bold]codes/[/bold]  "
        f"Goodbye[/{C['dim']}]",
        border_style=C["border"],
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    ))
    blank()

if __name__ == "__main__":
    main()
