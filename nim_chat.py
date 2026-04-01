#!/usr/bin/env python3
"""
NVIDIA NIM · Terminal AI Client · v4.0
"""

import os, re, sys, json, time
from datetime import datetime
from pathlib import Path

# ── dependency guard ──────────────────────────────────────────────────────────
MISSING = []
try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.text    import Text
    from rich.table   import Table
    from rich.rule    import Rule
    from rich.syntax  import Syntax
    from rich.markdown import Markdown
    from rich.markup  import escape
    from rich.prompt  import Confirm
    from rich         import box
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
    print(f"\n[ SETUP ] Missing: {', '.join(MISSING)}")
    print(f"[ SETUP ] Run: pip install {' '.join(MISSING)}")
    sys.exit(1)

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / ".nim_chat"
ENV_FILE    = BASE_DIR / ".env"
MEMORY_FILE = BASE_DIR / "memory.json"
MODELS_FILE = BASE_DIR / "models.json"
CODES_DIR   = Path.cwd() / "codes"
BASE_DIR.mkdir(exist_ok=True)

NIM_BASE_URL     = "https://integrate.api.nvidia.com/v1"
MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048

# Models that reject the system role (send as injected user turn instead)
NO_SYSTEM_ROLE = {"gemma", "falcon", "phi-3"}

DEFAULT_MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",             "label": "Llama 3.1 70B",      "ctx": 131072},
    {"id": "nvidia/llama-3.1-nemotron-70b-instruct",   "label": "Nemotron 70B",        "ctx": 32768 },
    {"id": "mistralai/mixtral-8x22b-instruct-v0.1",    "label": "Mixtral 8x22B",       "ctx": 65536 },
    {"id": "microsoft/phi-3-medium-128k-instruct",     "label": "Phi-3 Medium 128k",   "ctx": 131072},
    {"id": "google/gemma-2-27b-it",                    "label": "Gemma 2 27B",         "ctx": 8192  },
    {"id": "deepseek-ai/deepseek-coder-6.7b-instruct", "label": "DeepSeek Coder 6.7B", "ctx": 16384 },
]

LANG_EXT = {
    "python":"py","py":"py","javascript":"js","js":"js","typescript":"ts",
    "ts":"ts","jsx":"jsx","tsx":"tsx","html":"html","css":"css","scss":"scss",
    "bash":"sh","shell":"sh","sh":"sh","zsh":"sh","powershell":"ps1","ps1":"ps1",
    "java":"java","kotlin":"kt","c":"c","cpp":"cpp","c++":"cpp","csharp":"cs",
    "cs":"cs","rust":"rs","go":"go","ruby":"rb","rb":"rb","php":"php",
    "swift":"swift","r":"r","sql":"sql","json":"json","yaml":"yaml","yml":"yaml",
    "toml":"toml","xml":"xml","md":"md","dockerfile":"dockerfile",
    "makefile":"makefile","nginx":"conf","conf":"conf","text":"txt",
}

CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```", re.DOTALL)

# ── console + palette ─────────────────────────────────────────────────────────
con = Console(highlight=False)

# Clean slate palette — dark terminal, neon accents
P = {
    "border" : "#4fc3f7",   # ice blue
    "ai"     : "#80deea",   # teal
    "user"   : "#ffffff",
    "key"    : "#ffd54f",   # amber
    "mem"    : "#4dd0e1",   # cyan
    "model"  : "#ce93d8",   # lavender
    "code"   : "#a5d6a7",   # soft green
    "ok"     : "#69f0ae",   # green
    "err"    : "#ef5350",   # red
    "dim"    : "#546e7a",   # slate
    "accent" : "#ffd54f",   # amber
    "saved"  : "#69f0ae",
}

def tag(section: str, msg: str, col: str = ""):
    c = col or P.get(section.lower(), P["ai"])
    con.print(f"[{c}][ {section.upper()} ][/{c}] {msg}")

def nl(): con.print()

# ── helpers ───────────────────────────────────────────────────────────────────
def model_supports_system(model_id: str) -> bool:
    mid = model_id.lower()
    return not any(k in mid for k in NO_SYSTEM_ROLE)

def build_messages(system_content: str, history: list, model_id: str) -> list:
    """
    If the model supports system role: prepend {"role":"system",...}
    Otherwise: inject the system content as the first user/assistant exchange.
    """
    if model_supports_system(model_id):
        return [{"role": "system", "content": system_content}] + history
    else:
        # Inject system prompt as a silent user/assistant pair at the front
        injected = [
            {"role": "user",      "content": f"[Instructions] {system_content}"},
            {"role": "assistant", "content": "Understood. I am ready to help."},
        ]
        return injected + history

def system_prompt(model: dict) -> str:
    now = datetime.now().strftime("%A %B %d %Y, %H:%M")
    return (
        f"You are a highly capable AI assistant inside NVIDIA NIM, powered by {model['label']}. "
        f"Today is {now}. Be concise, accurate, and helpful. "
        "Use markdown in your replies: **bold**, *italic*, `inline code`, headers, lists. "
        "When writing code always wrap it in a fenced block with the correct language tag, "
        "e.g. ```python or ```javascript."
    )

# ── splash ────────────────────────────────────────────────────────────────────
def splash():
    con.clear()
    lines = [
        ("███╗   ██╗██╗███╗   ███╗",  "bold #4fc3f7"),
        ("████╗  ██║██║████╗ ████║",  "bold #4dd0e1"),
        ("██╔██╗ ██║██║██╔████╔██║",  "bold #80deea"),
        ("██║╚██╗██║██║██║╚██╔╝██║",  "bold #69f0ae"),
        ("██║ ╚████║██║██║ ╚═╝ ██║",  "bold #a5d6a7"),
        ("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝",  "bold #546e7a"),
    ]
    art = Text()
    for line, style in lines:
        art.append(line + "\n", style=style)
    art.append("\n  NVIDIA NIM  ·  Terminal AI Client  ·  v4.0", style="bold white")

    con.print(Panel(art, border_style=P["border"], padding=(1, 4), box=box.DOUBLE_EDGE))
    nl()

# ── API key ───────────────────────────────────────────────────────────────────
def load_env():
    load_dotenv(ENV_FILE) if ENV_FILE.exists() else load_dotenv()

def get_api_key() -> str:
    load_env()
    key = os.getenv("NVIDIA_API_KEY", "")

    if key:
        tag("KEY", f"Found API key  [{P['dim']}]{key[:8]}…{key[-4:]}[/{P['dim']}]", P["ok"])
        tag("KEY", "Connecting to NVIDIA NIM …", P["key"])
        try:
            OpenAI(api_key=key, base_url=NIM_BASE_URL).models.list()
            tag("KEY", "Successfully connected to the API ✓", P["ok"])
        except Exception as e:
            tag("KEY", f"Warning: {e}", P["err"])
        nl()
        return key

    tag("KEY", f"Cannot find NVIDIA key in [bold]{ENV_FILE}[/bold]", P["err"])
    nl()
    key = con.input(f"  [{P['key']}][ KEY ][/{P['key']}] Enter your NVIDIA API key: ").strip()
    nl()
    if Confirm.ask(f"  [{P['key']}][ KEY ][/{P['key']}] Save key to [bold]{ENV_FILE}[/bold]?", default=True):
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        tag("KEY", f"Key saved ✓", P["ok"])
    nl()
    return key

# ── memory ────────────────────────────────────────────────────────────────────
def load_memory() -> list:
    tag("MEMORY", "Injecting memory from past chats …", P["mem"])
    if not MEMORY_FILE.exists():
        tag("MEMORY", "No prior memory — starting fresh", P["dim"])
        nl(); return []
    try:
        msgs = json.loads(MEMORY_FILE.read_text()).get("messages", [])
        if len(msgs) > MAX_MEMORY_TURNS * 2:
            msgs = msgs[-(MAX_MEMORY_TURNS * 2):]
        tag("MEMORY", f"Loaded [bold]{len(msgs)//2}[/bold] conversation turns ✓", P["ok"])
        nl(); return msgs
    except Exception as e:
        tag("MEMORY", f"Failed to inject memory ({e})", P["err"])
        nl(); return []

def save_memory(messages: list):
    try:
        MEMORY_FILE.write_text(json.dumps({"messages": messages}, indent=2))
    except Exception:
        pass

def forget_memory():
    MEMORY_FILE.unlink(missing_ok=True)
    tag("MEMORY", "Memory wiped ✓", P["ok"])

# ── models ────────────────────────────────────────────────────────────────────
def load_models() -> list:
    if MODELS_FILE.exists():
        try: return json.loads(MODELS_FILE.read_text())
        except Exception: pass
    return list(DEFAULT_MODELS)

def save_models(m: list):
    MODELS_FILE.write_text(json.dumps(m, indent=2))

def choose_model() -> dict:
    models = load_models()

    t = Table(box=box.SIMPLE_HEAD, border_style=P["border"],
              header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2))
    t.add_column("#",      style="bold white",  width=4)
    t.add_column("Model",  style=P["ai"],       min_width=24)
    t.add_column("ID",     style=P["dim"],      min_width=20)
    t.add_column("Ctx",    style=P["model"],    width=9)

    for i, m in enumerate(models, 1):
        ctx = f"{m.get('ctx',0):,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(str(i), m["label"], m["id"], ctx)
    t.add_row(str(len(models)+1), f"[bold {P['accent']}]+ Add new model[/bold {P['accent']}]", "", "")

    tag("MODEL", "Saved models:", P["model"])
    con.print(t)
    nl()

    while True:
        raw = con.input(f"  [{P['model']}][ MODEL ][/{P['model']}] Select number [1]: ").strip() or "1"
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(models):
                sel = models[idx]
                tag("MODEL", f"Using [bold]{sel['label']}[/bold]  [{P['dim']}]{sel['id']}[/{P['dim']}]", P["ok"])
                nl(); return sel
            if idx == len(models):
                nid  = con.input(f"  [{P['model']}][ MODEL ][/{P['model']}] Model ID: ").strip()
                nlbl = con.input(f"  [{P['model']}][ MODEL ][/{P['model']}] Display name [{nid}]: ").strip() or nid
                nctx = con.input(f"  [{P['model']}][ MODEL ][/{P['model']}] Context length [32768]: ").strip() or "32768"
                nm   = {"id": nid, "label": nlbl, "ctx": int(nctx)}
                models.append(nm); save_models(models)
                tag("MODEL", f"Added [bold]{nlbl}[/bold] ✓", P["ok"]); nl(); return nm
        except (ValueError, IndexError):
            pass
        tag("MODEL", "Invalid — try again", P["err"])

# ── code saving ───────────────────────────────────────────────────────────────
_code_n: dict = {}

def save_codes_from_reply(reply: str):
    """Extract every fenced code block from reply and save to codes/."""
    CODES_DIR.mkdir(exist_ok=True)
    for m in CODE_FENCE.finditer(reply):
        lang = m.group("lang").strip().lower() or "text"
        code = m.group("code")
        ext  = LANG_EXT.get(lang, lang if lang else "txt")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        _code_n[ext] = _code_n.get(ext, 0) + 1
        n    = _code_n[ext]
        sfx  = f"_{n}" if n > 1 else ""
        path = CODES_DIR / f"{lang or 'code'}_{ts}{sfx}.{ext}"
        path.write_text(code, encoding="utf-8")
        try:
            rel = path.relative_to(Path.cwd())
        except ValueError:
            rel = path
        lines = len(code.splitlines())
        tag("CODE", f"Saved  [{P['saved']}]{rel}[/{P['saved']}]  [{P['dim']}]({lines} lines · .{ext})[/{P['dim']}]", P["code"])

# ── render markdown reply (with code blocks) ──────────────────────────────────
def render_markdown_reply(text: str, model_label: str):
    """
    Display the AI reply fully rendered:
    - Markdown (bold, italic, lists, headers) via rich Markdown
    - Code blocks get syntax highlighting + line numbers via custom panels
    """
    # Split into text segments and code block segments
    segments = []
    cursor   = 0
    for m in CODE_FENCE.finditer(text):
        s, e = m.span()
        if s > cursor:
            chunk = text[cursor:s].strip()
            if chunk:
                segments.append(("text", chunk, ""))
        segments.append(("code", m.group("code"), m.group("lang").strip().lower() or "text"))
        cursor = e
    tail = text[cursor:].strip()
    if tail:
        segments.append(("text", tail, ""))

    nl()
    con.print(Rule(f"[{P['ai']}]  {escape(model_label)}  [/{P['ai']}]", style=P["border"]))
    nl()

    for kind, content, lang in segments:
        if kind == "text":
            # render as proper markdown
            con.print(Markdown(content, code_theme="one-dark"), style=P["ai"])
            nl()
        else:
            # ── syntax panel ───────────────────────────────────────────
            ext   = LANG_EXT.get(lang, lang if lang else "txt")
            theme = "monokai" if lang in {"bash","shell","sh","powershell","dockerfile"} else "one-dark"

            badge = f"  {lang.upper() if lang else 'CODE'}  "
            title_str = f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]  [{P['dim']}].{ext}[/{P['dim']}]"

            syn = Syntax(
                content,
                lang if lang else "text",
                theme=theme,
                line_numbers=True,
                word_wrap=False,
                indent_guides=True,
                background_color="default",
            )
            con.print(Panel(
                syn,
                title=title_str,          # plain string — no more Table crash
                title_align="left",
                border_style=P["code"],
                box=box.HEAVY,
                padding=(0, 1),
            ))
            nl()

    con.print(Rule(style=P["border"]))
    nl()

# ── streaming ─────────────────────────────────────────────────────────────────
def stream_tokens(client: OpenAI, model: dict, messages: list) -> str:
    """Stream raw tokens in real-time, return full reply."""
    con.print(Rule(f"[{P['dim']}]  streaming …  [/{P['dim']}]", style=P["dim"]))
    con.print("  ", end="")

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
            fence_buf += delta
            if "```" in fence_buf:
                in_fence  = not in_fence
                fence_buf = ""
            colour = P["dim"] if in_fence else P["ai"]
            con.print(f"[{colour}]{escape(delta)}[/{colour}]", end="")

    except Exception as e:
        err = f"\n[Error: {e}]"
        con.print(f"[{P['err']}]{escape(err)}[/{P['err']}]")
        full.append(err)

    con.print()
    return "".join(full)

# ── info bar ──────────────────────────────────────────────────────────────────
def info_bar(model: dict, turn: int, mem_size: int):
    codes = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    g = Table.grid(expand=True, padding=(0, 2))
    g.add_column(justify="left")
    g.add_column(justify="center")
    g.add_column(justify="center")
    g.add_column(justify="right")
    g.add_row(
        f"[{P['model']}]{model['label']}[/{P['model']}]",
        f"[{P['dim']}]turn[/{P['dim']}] [{P['accent']}]{turn}[/{P['accent']}]",
        f"[{P['dim']}]memory[/{P['dim']}] [{P['mem']}]{mem_size} msgs[/{P['mem']}]",
        f"[{P['code']}]{codes} code files[/{P['code']}]",
    )
    con.print(Panel(g, border_style=P["dim"], padding=(0, 1), box=box.MINIMAL))
    nl()

# ── commands ──────────────────────────────────────────────────────────────────
COMMANDS = {
    "/help"  : "Show this help",
    "/forget": "Wipe conversation memory",
    "/model" : "Switch model mid-chat",
    "/save"  : "Force-save memory now",
    "/codes" : "List all saved code files",
    "/info"  : "Show session stats",
    "/clear" : "Clear the screen",
    "/exit"  : "Quit NIM Chat",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"], show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=10)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items():
        t.add_row(cmd, desc)
    con.print(t); nl()

def list_codes():
    if not CODES_DIR.exists() or not list(CODES_DIR.glob("*")):
        tag("CODE", f"No code files yet — will appear in [bold]{CODES_DIR}[/bold]", P["dim"]); nl(); return
    files = sorted(CODES_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    t = Table(box=box.SIMPLE_HEAD, border_style=P["code"],
              header_style=f"bold {P['code']}", padding=(0, 2))
    t.add_column("#",     style="bold white", width=4)
    t.add_column("File",  style=P["saved"],   min_width=30)
    t.add_column("Ext",   style=P["accent"],  width=8)
    t.add_column("Lines", style=P["dim"],     width=7)
    t.add_column("Saved", style=P["dim"],     width=16)
    for i, f in enumerate(files[:20], 1):
        try:    lines = len(f.read_text(encoding="utf-8").splitlines())
        except: lines = 0
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
        t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), mtime)
    tag("CODE", f"Files in [bold]{CODES_DIR}[/bold]:", P["code"])
    con.print(t); nl()

# ── chat loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, history: list):
    sys_content = system_prompt(model)
    turn        = 0

    con.print(Panel(
        f"[{P['dim']}]/help for commands  ·  code auto-saves to "
        f"[{P['code']}]codes/[/{P['code']}]  ·  Ctrl-C to quit[/{P['dim']}]",
        border_style=P["dim"], box=box.ROUNDED, padding=(0, 2),
    ))
    nl()

    while True:
        try:
            # Clean single-line input — no redundant prefix
            user_input = con.input(f"[{P['user']}]  You › [/{P['user']}]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd == "/exit":                                     break
        if cmd == "/help":     show_help();                    continue
        if cmd == "/forget":   forget_memory(); history.clear(); continue
        if cmd == "/save":     save_memory(history); tag("MEMORY", "Saved ✓", P["ok"]); nl(); continue
        if cmd == "/codes":    list_codes();                   continue
        if cmd == "/clear":    con.clear();                    continue
        if cmd == "/info":     info_bar(model, turn, len(history)); continue
        if cmd == "/model":
            nl(); model = choose_model()
            sys_content = system_prompt(model)
            continue

        # ── send ──────────────────────────────────────────────────────────────
        turn += 1
        history.append({"role": "user", "content": user_input})

        # Show user bubble (clean, right-aligned title, no external prompt echo)
        con.print(Panel(
            f"[{P['user']}]{escape(user_input)}[/{P['user']}]",
            title=f"[{P['user']}] You [/{P['user']}]",
            title_align="right",
            border_style=P["dim"],
            box=box.ROUNDED,
            padding=(0, 2),
        ))

        # Build message list (handles system role compatibility)
        msgs = build_messages(sys_content, history, model["id"])

        # 1 — stream raw tokens in real-time
        reply = stream_tokens(client, model, msgs)

        # 2 — re-render as proper markdown with syntax-highlighted code panels
        render_markdown_reply(reply, model["label"])

        # 3 — save any code blocks to codes/
        if CODE_FENCE.search(reply):
            save_codes_from_reply(reply)
            nl()

        history.append({"role": "assistant", "content": reply})
        save_memory(history)

        if turn % 5 == 0:
            info_bar(model, turn, len(history))

# ── entry ─────────────────────────────────────────────────────────────────────
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

    nl()
    save_memory(history)
    codes = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    con.print(Panel(
        f"[{P['dim']}]Memory saved  ·  {len(history)//2} turns  ·  "
        f"[{P['code']}]{codes} code files[/{P['code']}] in [bold]codes/[/bold]  ·  "
        f"Goodbye 👋[/{P['dim']}]",
        border_style=P["border"], box=box.DOUBLE_EDGE, padding=(0, 2),
    ))
    nl()

if __name__ == "__main__":
    main()
