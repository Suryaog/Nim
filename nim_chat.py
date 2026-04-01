#!/usr/bin/env python3
"""NVIDIA NIM · Terminal AI Client · v4.1"""

import os, re, sys, json, time
from datetime import datetime
from pathlib import Path

# ── deps ──────────────────────────────────────────────────────────────────────
MISSING = []
try:
    from rich.console  import Console
    from rich.panel    import Panel
    from rich.text     import Text
    from rich.table    import Table
    from rich.rule     import Rule
    from rich.syntax   import Syntax
    from rich.markdown import Markdown
    from rich.markup   import escape
    from rich.live     import Live
    from rich.align    import Align
    from rich          import box
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

try:
    from prompt_toolkit                  import prompt as _pt_prompt
    from prompt_toolkit.styles           import Style  as _PtStyle
    from prompt_toolkit.formatted_text   import HTML   as _HTML
    HAS_PT = True
except ImportError:
    HAS_PT = False

if MISSING:
    print(f"\n[ SETUP ] pip install {' '.join(MISSING)}")
    sys.exit(1)

# ── config ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / ".nim_chat"
ENV_FILE    = BASE_DIR / ".env"
MEMORY_FILE = BASE_DIR / "memory.json"
MODELS_FILE = BASE_DIR / "models.json"
CODES_DIR   = Path.cwd() / "codes"
BASE_DIR.mkdir(exist_ok=True)

NIM_BASE_URL     = "https://integrate.api.nvidia.com/v1"
MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048
NO_SYSTEM_ROLE   = {"gemma", "falcon"}      # models that reject system role

DEFAULT_MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",             "label": "Llama 3.1 70B",      "ctx": 131072},
    {"id": "nvidia/llama-3.1-nemotron-70b-instruct",   "label": "Nemotron 70B",        "ctx": 32768 },
    {"id": "mistralai/mixtral-8x22b-instruct-v0.1",    "label": "Mixtral 8x22B",       "ctx": 65536 },
    {"id": "microsoft/phi-3-medium-128k-instruct",     "label": "Phi-3 Medium 128k",   "ctx": 131072},
    {"id": "google/gemma-2-27b-it",                    "label": "Gemma 2 27B",         "ctx": 8192  },
    {"id": "deepseek-ai/deepseek-coder-6.7b-instruct", "label": "DeepSeek Coder 6.7B", "ctx": 16384 },
]

LANG_EXT = {
    "python":"py","py":"py","javascript":"js","js":"js","typescript":"ts","ts":"ts",
    "jsx":"jsx","tsx":"tsx","html":"html","css":"css","scss":"scss","bash":"sh",
    "shell":"sh","sh":"sh","zsh":"sh","powershell":"ps1","ps1":"ps1","java":"java",
    "kotlin":"kt","c":"c","cpp":"cpp","c++":"cpp","csharp":"cs","cs":"cs","rust":"rs",
    "go":"go","ruby":"rb","rb":"rb","php":"php","swift":"swift","r":"r","sql":"sql",
    "json":"json","yaml":"yaml","yml":"yaml","toml":"toml","xml":"xml","md":"md",
    "dockerfile":"dockerfile","makefile":"makefile","nginx":"conf","text":"txt",
}

CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```", re.DOTALL)

# ── palette ───────────────────────────────────────────────────────────────────
P = {
    "border" : "#4fc3f7",
    "ai"     : "#80deea",
    "user"   : "#e0e0e0",
    "dim"    : "#455a64",
    "accent" : "#ffd54f",
    "ok"     : "#69f0ae",
    "err"    : "#ef5350",
    "code"   : "#a5d6a7",
    "model"  : "#ce93d8",
    "saved"  : "#69f0ae",
    "mem"    : "#4dd0e1",
}

con = Console(highlight=False)
nl  = con.print  # shortcut — call nl() for blank line

# ── prompt_toolkit input ──────────────────────────────────────────────────────
_PT_STYLE = None
if HAS_PT:
    _PT_STYLE = _PtStyle.from_dict({
        "prompt"         : "#4fc3f7 bold",
        ""               : "#e0e0e0",
        "bottom-toolbar" : "bg:#0d1117 #455a64",
    })

def get_input(model_label: str, turn: int) -> str:
    """Google-CLI style input with bottom toolbar."""
    if HAS_PT and _PT_STYLE:
        toolbar = _HTML(
            f"  <b>NIM</b>  ·  {model_label}  ·  "
            f"turn <b>{turn}</b>  ·  /help for commands"
        )
        try:
            return _pt_prompt(
                "  ❯  ",
                style=_PT_STYLE,
                bottom_toolbar=toolbar,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
    return con.input(f"[{P['border']}]  ❯  [/{P['border']}]").strip()

# ── splash ────────────────────────────────────────────────────────────────────
def splash():
    con.clear()
    art = Text(justify="center")
    for line, style in [
        ("███╗   ██╗██╗███╗   ███╗", "bold #4fc3f7"),
        ("████╗  ██║██║████╗ ████║", "bold #4dd0e1"),
        ("██╔██╗ ██║██║██╔████╔██║", "bold #80deea"),
        ("██║╚██╗██║██║██║╚██╔╝██║", "bold #69f0ae"),
        ("██║ ╚████║██║██║ ╚═╝ ██║", "bold #a5d6a7"),
        ("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝", "bold #455a64"),
    ]:
        art.append(line + "\n", style=style)
    art.append("\nNVIDIA NIM  ·  Terminal AI  ·  v4.1", style="bold white")
    nl(Panel(Align.center(art), border_style=P["border"], padding=(1, 6), box=box.DOUBLE_EDGE))
    nl()

# ── API key ───────────────────────────────────────────────────────────────────
def load_env():
    load_dotenv(ENV_FILE) if ENV_FILE.exists() else load_dotenv()

def get_api_key() -> str:
    load_env()
    key = os.getenv("NVIDIA_API_KEY", "")

    if key:
        try:
            OpenAI(api_key=key, base_url=NIM_BASE_URL).models.list()
            nl(f"  [{P['ok']}]✓[/{P['ok']}]  [{P['dim']}]API connected  ·  {key[:8]}…{key[-4:]}[/{P['dim']}]")
        except Exception as e:
            nl(f"  [{P['err']}]![/{P['err']}]  [{P['dim']}]{e}[/{P['dim']}]")
        nl()
        return key

    nl(f"  [{P['err']}]No NVIDIA API key found.[/{P['err']}]")
    nl()
    key = con.input(f"  [{P['accent']}]API key:[/{P['accent']}] ").strip()
    nl()
    save = con.input(f"  [{P['dim']}]Save key? (y/n):[/{P['dim']}] ").strip().lower()
    if save in ("y", "yes"):
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        nl(f"  [{P['ok']}]✓  Saved[/{P['ok']}]")
    nl()
    return key

# ── memory ────────────────────────────────────────────────────────────────────
def load_memory() -> list:
    if not MEMORY_FILE.exists():
        nl(f"  [{P['dim']}]No prior memory[/{P['dim']}]"); nl()
        return []
    try:
        msgs = json.loads(MEMORY_FILE.read_text()).get("messages", [])
        if len(msgs) > MAX_MEMORY_TURNS * 2:
            msgs = msgs[-(MAX_MEMORY_TURNS * 2):]
        nl(f"  [{P['mem']}]↑[/{P['mem']}]  [{P['dim']}]{len(msgs)//2} turns loaded from memory[/{P['dim']}]")
        nl()
        return msgs
    except Exception:
        nl(f"  [{P['err']}]Memory load failed — starting fresh[/{P['err']}]"); nl()
        return []

def save_memory(m: list):
    try:
        MEMORY_FILE.write_text(json.dumps({"messages": m}, indent=2))
    except Exception:
        pass

def forget_memory():
    MEMORY_FILE.unlink(missing_ok=True)

# ── models ────────────────────────────────────────────────────────────────────
def load_models() -> list:
    if MODELS_FILE.exists():
        try: return json.loads(MODELS_FILE.read_text())
        except Exception: pass
    return list(DEFAULT_MODELS)

def save_models(m: list):
    MODELS_FILE.write_text(json.dumps(m, indent=2))

def print_model_table(models: list):
    t = Table(box=box.SIMPLE_HEAD, border_style=P["dim"],
              header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2))
    t.add_column("#",     style="bold white",  width=4)
    t.add_column("Model", style=P["ai"],       min_width=22)
    t.add_column("ID",    style=P["dim"],      min_width=20)
    t.add_column("Ctx",   style=P["model"],    width=9)
    for i, m in enumerate(models, 1):
        ctx = f"{m.get('ctx',0):,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(str(i), m["label"], m["id"], ctx)
    t.add_row(str(len(models)+1), f"[bold {P['accent']}]+ Add model[/bold {P['accent']}]", "", "")
    nl(t)

def choose_model() -> dict:
    models = load_models()
    while True:
        print_model_table(models)
        raw = con.input(
            f"  [{P['model']}]Select[/{P['model']}] [{P['dim']}](number · -N removes · Enter=1):[/{P['dim']}] "
        ).strip() or "1"
        nl()

        # ── remove model ──────────────────────────────────────────────────
        if raw.startswith("-"):
            try:
                del_idx = int(raw[1:]) - 1
                if 0 <= del_idx < len(models):
                    gone = models.pop(del_idx)
                    save_models(models)
                    nl(f"  [{P['err']}]✕[/{P['err']}]  Removed [bold]{gone['label']}[/bold]")
                    nl()
                    continue
            except ValueError:
                pass
            nl(f"  [{P['err']}]Invalid remove index[/{P['err']}]"); nl(); continue

        try:
            idx = int(raw) - 1
        except ValueError:
            nl(f"  [{P['err']}]Invalid input[/{P['err']}]"); nl(); continue

        # ── add new ───────────────────────────────────────────────────────
        if idx == len(models):
            nid  = con.input(f"  Model ID: ").strip()
            nlbl = con.input(f"  Display name [{nid}]: ").strip() or nid
            nctx = con.input(f"  Context length [32768]: ").strip() or "32768"
            nm   = {"id": nid, "label": nlbl, "ctx": int(nctx)}
            models.append(nm); save_models(models)
            nl(f"  [{P['ok']}]✓  Added {nlbl}[/{P['ok']}]"); nl()
            return nm

        # ── select ────────────────────────────────────────────────────────
        if 0 <= idx < len(models):
            sel = models[idx]
            nl(f"  [{P['ok']}]✓[/{P['ok']}]  [bold]{sel['label']}[/bold]  [{P['dim']}]{sel['id']}[/{P['dim']}]")
            nl()
            return sel

        nl(f"  [{P['err']}]Out of range — try again[/{P['err']}]"); nl()

# ── message builder (system role compat) ──────────────────────────────────────
def build_messages(sys_content: str, history: list, model_id: str) -> list:
    if any(k in model_id.lower() for k in NO_SYSTEM_ROLE):
        return [
            {"role": "user",      "content": f"[System] {sys_content}"},
            {"role": "assistant", "content": "Understood."},
        ] + history
    return [{"role": "system", "content": sys_content}] + history

def system_prompt(model: dict) -> str:
    return (
        f"You are a highly capable AI assistant inside NVIDIA NIM powered by {model['label']}. "
        f"Today is {datetime.now().strftime('%A %B %d %Y %H:%M')}. "
        "Be concise and helpful. Use markdown: **bold**, *italic*, `code`, lists, headers. "
        "Always wrap code in fenced blocks with the language tag, e.g. ```python."
    )

# ── code saving ───────────────────────────────────────────────────────────────
_code_n: dict = {}

def save_codes(reply: str):
    CODES_DIR.mkdir(exist_ok=True)
    saved_any = False
    for m in CODE_FENCE.finditer(reply):
        lang = m.group("lang").strip().lower() or "text"
        code = m.group("code")
        ext  = LANG_EXT.get(lang, lang if lang else "txt")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        _code_n[ext] = _code_n.get(ext, 0) + 1
        sfx  = f"_{_code_n[ext]}" if _code_n[ext] > 1 else ""
        path = CODES_DIR / f"{lang or 'code'}_{ts}{sfx}.{ext}"
        path.write_text(code, encoding="utf-8")
        try:    rel = path.relative_to(Path.cwd())
        except: rel = path
        nl(f"  [{P['code']}]↓[/{P['code']}]  [{P['saved']}]{rel}[/{P['saved']}]  [{P['dim']}]({len(code.splitlines())} lines)[/{P['dim']}]")
        saved_any = True
    if saved_any:
        nl()

# ── render code panels after streaming ───────────────────────────────────────
def render_code_panels(reply: str):
    """Print syntax-highlighted panels for every code block found."""
    for m in CODE_FENCE.finditer(reply):
        lang = m.group("lang").strip().lower() or "text"
        code = m.group("code")
        ext  = LANG_EXT.get(lang, lang if lang else "txt")
        theme = "monokai" if lang in {"bash","shell","sh","powershell","dockerfile"} else "one-dark"

        badge = f"  {lang.upper() if lang else 'CODE'}  "
        syn = Syntax(code, lang if lang else "text", theme=theme,
                     line_numbers=True, word_wrap=False, indent_guides=True,
                     background_color="default")
        nl(Panel(
            syn,
            title=f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]"
                  f"  [{P['dim']}].{ext}[/{P['dim']}]",
            title_align="left",
            border_style=P["code"],
            box=box.HEAVY,
            padding=(0, 1),
        ))

# ── the streaming+replace panel (core feature) ───────────────────────────────
def _streaming_panel(text: str, model_label: str, done: bool) -> Panel:
    """
    While streaming  → plain text (fast rendering, real-time feel).
    After streaming  → full Markdown (bold/italic/lists render correctly).
    Border changes from dim to vivid when done.
    """
    if done and text.strip():
        # Strip code fences from displayed markdown — we show them separately
        display = CODE_FENCE.sub(
            lambda m: f"`({m.group('lang') or 'code'} block — see panel below)`",
            text
        ).strip()
        content = Markdown(display, code_theme="one-dark") if display else Text("")
    else:
        content = Text(text, style=P["ai"])

    return Panel(
        content,
        title=f"[{P['ai']}]  {escape(model_label)}  [/{P['ai']}]",
        title_align="left",
        border_style=P["border"] if done else P["dim"],
        box=box.ROUNDED,
        padding=(1, 2),
    )

def stream_and_render(client: OpenAI, model: dict, messages: list) -> str:
    """
    Stream tokens into a Live panel.
    When done → switch that same panel to formatted Markdown.
    Then print code panels separately below.
    """
    buf   = []
    error = None

    with Live(
        _streaming_panel("", model["label"], False),
        console=con,
        refresh_per_second=20,
        vertical_overflow="visible",
        transient=False,          # keep panel on screen after Live exits
    ) as live:
        try:
            stream = client.chat.completions.create(
                model=model["id"],
                messages=messages,
                max_tokens=MAX_TOKENS,
                stream=True,
                temperature=0.7,
            )
            for chunk in stream:
                # ── safe delta extraction (fixes list index out of range) ──
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta  = (choice.delta.content or "") if choice.delta else ""
                if delta:
                    buf.append(delta)
                    live.update(_streaming_panel("".join(buf), model["label"], False))

        except Exception as e:
            error = str(e)

        # ── replace streaming text with formatted markdown ─────────────
        reply = "".join(buf)
        if error:
            reply += f"\n\n[Error: {error}]"
        live.update(_streaming_panel(reply, model["label"], done=True))

    # Code blocks get their own syntax-highlighted panels below
    if CODE_FENCE.search(reply):
        nl()
        render_code_panels(reply)
        save_codes(reply)

    return reply

# ── help + list codes ─────────────────────────────────────────────────────────
COMMANDS = {
    "/help"   : "Show commands",
    "/forget" : "Wipe memory",
    "/model"  : "Switch model",
    "/save"   : "Save memory now",
    "/codes"  : "List saved code files",
    "/info"   : "Session stats",
    "/clear"  : "Clear screen",
    "/exit"   : "Quit",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"], show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=10)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items():
        t.add_row(cmd, desc)
    nl(t); nl()

def list_codes():
    if not CODES_DIR.exists() or not list(CODES_DIR.glob("*")):
        nl(f"  [{P['dim']}]No code files yet — saved to [bold]{CODES_DIR}[/bold][/{P['dim']}]"); nl(); return
    files = sorted(CODES_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    t = Table(box=box.SIMPLE_HEAD, border_style=P["code"],
              header_style=f"bold {P['code']}", padding=(0, 2))
    t.add_column("#",     style="bold white", width=4)
    t.add_column("File",  style=P["saved"],   min_width=28)
    t.add_column("Ext",   style=P["accent"],  width=6)
    t.add_column("Lines", style=P["dim"],     width=7)
    t.add_column("When",  style=P["dim"],     width=14)
    for i, f in enumerate(files[:20], 1):
        try:    lines = len(f.read_text(encoding="utf-8").splitlines())
        except: lines = 0
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
        t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), mtime)
    nl(f"  [{P['code']}]Code files →[/{P['code']}] [bold]{CODES_DIR}[/bold]")
    nl(t); nl()

def info_bar(model: dict, turn: int, mem_size: int):
    codes = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    g = Table.grid(expand=True, padding=(0, 2))
    g.add_column(justify="left")
    g.add_column(justify="center")
    g.add_column(justify="right")
    g.add_row(
        f"[{P['model']}]{model['label']}[/{P['model']}]",
        f"[{P['dim']}]turn {turn}  ·  {mem_size} msgs[/{P['dim']}]",
        f"[{P['code']}]{codes} code files[/{P['code']}]",
    )
    nl(Panel(g, border_style=P["dim"], padding=(0, 1), box=box.MINIMAL))
    nl()

# ── chat loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, history: list):
    sys_content = system_prompt(model)
    turn        = 0

    if not HAS_PT:
        nl(f"  [{P['dim']}]Tip: pip install prompt_toolkit for a better input experience[/{P['dim']}]")
    nl(Rule(style=P["dim"]))
    nl()

    while True:
        try:
            user_input = get_input(model["label"], turn)
        except KeyboardInterrupt:
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd == "/exit":                                                 break
        if cmd == "/help":     show_help();                                continue
        if cmd == "/clear":    con.clear();                                continue
        if cmd == "/codes":    list_codes();                               continue
        if cmd == "/save":     save_memory(history); nl(f"  [{P['ok']}]✓  Saved[/{P['ok']}]"); nl(); continue
        if cmd == "/info":     info_bar(model, turn, len(history));        continue
        if cmd == "/forget":
            forget_memory(); history.clear()
            nl(f"  [{P['ok']}]✓  Memory cleared[/{P['ok']}]"); nl();     continue
        if cmd == "/model":
            nl(); model = choose_model(); sys_content = system_prompt(model); continue

        # ── send ──────────────────────────────────────────────────────────
        turn += 1
        history.append({"role": "user", "content": user_input})

        # User bubble
        nl(Panel(
            f"[{P['user']}]{escape(user_input)}[/{P['user']}]",
            title=f"[{P['user']}] You [/{P['user']}]",
            title_align="right",
            border_style=P["dim"],
            box=box.ROUNDED,
            padding=(0, 2),
        ))
        nl()

        msgs  = build_messages(sys_content, history, model["id"])
        reply = stream_and_render(client, model, msgs)

        history.append({"role": "assistant", "content": reply})
        save_memory(history)
        nl()

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
    nl(Panel(
        f"[{P['dim']}]{len(history)//2} turns saved  ·  "
        f"[{P['code']}]{codes} code files[/{P['code']}] in [bold]codes/[/bold]  ·  "
        f"Goodbye 👋[/{P['dim']}]",
        border_style=P["border"], box=box.DOUBLE_EDGE, padding=(0, 2),
    ))
    nl()

if __name__ == "__main__":
    main()
