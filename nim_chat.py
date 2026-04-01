#!/usr/bin/env python3
"""NVIDIA NIM · Terminal AI Client · v5.0"""

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
    from prompt_toolkit                import prompt as _pt_prompt
    from prompt_toolkit.styles         import Style  as _PtStyle
    from prompt_toolkit.formatted_text import HTML   as _HTML
    HAS_PT = True
except ImportError:
    HAS_PT = False

if MISSING:
    print(f"\n[ SETUP ] pip install {' '.join(MISSING)}")
    sys.exit(1)

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path.home() / ".nim_chat"
CHATS_DIR = BASE_DIR / "chats"
ENV_FILE  = BASE_DIR / ".env"
CODES_DIR = Path.cwd() / "codes"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DIR.mkdir(parents=True, exist_ok=True)

NIM_BASE_URL     = "https://integrate.api.nvidia.com/v1"
MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048

MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",        "label": "Llama 3.1 70B",    "ctx": 131072},
    {"id": "qwen/qwen3-coder-480b-a35b-instruct", "label": "Qwen3 Coder 480B", "ctx": 32768 },
]

LANG_EXT = {
    "python":"py","py":"py","javascript":"js","js":"js","typescript":"ts","ts":"ts",
    "jsx":"jsx","tsx":"tsx","html":"html","css":"css","scss":"scss","bash":"sh",
    "shell":"sh","sh":"sh","zsh":"sh","powershell":"ps1","java":"java","kotlin":"kt",
    "c":"c","cpp":"cpp","c++":"cpp","csharp":"cs","cs":"cs","rust":"rs","go":"go",
    "ruby":"rb","rb":"rb","php":"php","swift":"swift","r":"r","sql":"sql",
    "json":"json","yaml":"yaml","yml":"yaml","toml":"toml","xml":"xml","md":"md",
    "dockerfile":"dockerfile","makefile":"makefile","text":"txt",
}

CODE_FENCE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```",
    re.DOTALL,
)

# ── palette ───────────────────────────────────────────────────────────────────
P = {
    "border": "#4fc3f7",
    "ai"    : "#80deea",
    "user"  : "#e0e0e0",
    "dim"   : "#455a64",
    "accent": "#ffd54f",
    "ok"    : "#69f0ae",
    "err"   : "#ef5350",
    "code"  : "#a5d6a7",
    "model" : "#ce93d8",
    "saved" : "#69f0ae",
    "chat"  : "#ffb74d",
}

con = Console(highlight=False)

# ── styled input (prompt_toolkit) ─────────────────────────────────────────────
_PT_STYLE = None
if HAS_PT:
    _PT_STYLE = _PtStyle.from_dict({
        "prompt"        : "#4fc3f7 bold",
        ""              : "#e0e0e0",
        "bottom-toolbar": "bg:#0d1117 #546e7a",
    })

def get_input(chat_name: str, model_label: str, turn: int) -> str:
    if HAS_PT and _PT_STYLE:
        toolbar = _HTML(
            f"  <b>{chat_name}</b>  ·  {model_label}  ·  turn <b>{turn}</b>  ·  /help"
        )
        try:
            return _pt_prompt("  ❯  ", style=_PT_STYLE, bottom_toolbar=toolbar).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
    return con.input(f"[{P['border']}]  ❯  [/{P['border']}]").strip()

# ── splash ────────────────────────────────────────────────────────────────────
def splash():
    con.clear()
    art = Text(justify="center")
    rows = [
        ("███╗   ██╗██╗███╗   ███╗", "bold #4fc3f7"),
        ("████╗  ██║██║████╗ ████║", "bold #4dd0e1"),
        ("██╔██╗ ██║██║██╔████╔██║", "bold #80deea"),
        ("██║╚██╗██║██║██║╚██╔╝██║", "bold #69f0ae"),
        ("██║ ╚████║██║██║ ╚═╝ ██║", "bold #a5d6a7"),
        ("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝", "bold #455a64"),
    ]
    for line, style in rows:
        art.append(line + "\n", style=style)
    art.append("\nNVIDIA NIM  ·  Terminal AI  ·  v5.0", style="bold white")
    con.print(Panel(Align.center(art), border_style=P["border"],
                    padding=(1, 6), box=box.DOUBLE_EDGE))
    con.print()

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
        try:
            OpenAI(api_key=key, base_url=NIM_BASE_URL).models.list()
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  [{P['dim']}]API connected · {key[:8]}…{key[-4:]}[/{P['dim']}]")
        except Exception as exc:
            con.print(f"  [{P['err']}]![/{P['err']}]  [{P['dim']}]{escape(str(exc)[:80])}[/{P['dim']}]")
        con.print()
        return key

    con.print(f"  [{P['err']}]No NVIDIA API key found.[/{P['err']}]")
    con.print()
    key  = con.input(f"  [{P['accent']}]API key:[/{P['accent']}] ").strip()
    save = con.input(f"  [{P['dim']}]Save key? (y/n):[/{P['dim']}] ").strip().lower()
    if save in ("y", "yes"):
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        con.print(f"  [{P['ok']}]✓  Saved[/{P['ok']}]")
    con.print()
    return key

# ── model picker ──────────────────────────────────────────────────────────────
def choose_model() -> dict:
    t = Table(box=box.SIMPLE_HEAD, border_style=P["dim"],
              header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2))
    t.add_column("#",     style="bold white", width=4)
    t.add_column("Model", style=P["ai"],      min_width=22)
    t.add_column("Ctx",   style=P["model"],   width=9)
    for i, m in enumerate(MODELS, 1):
        ctx = f"{m['ctx']:,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(str(i), m["label"], ctx)
    con.print(t)
    while True:
        raw = con.input(
            f"  [{P['model']}]Model[/{P['model']}] [{P['dim']}](Enter=1):[/{P['dim']}] "
        ).strip() or "1"
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(MODELS):
                sel = MODELS[idx]
                con.print(f"  [{P['ok']}]✓[/{P['ok']}]  [bold]{sel['label']}[/bold]")
                con.print()
                return sel
        except ValueError:
            pass
        con.print(f"  [{P['err']}]Invalid — try again[/{P['err']}]")

# ── chat session ──────────────────────────────────────────────────────────────
class Chat:
    def __init__(self, path: Path):
        self.path = path
        d = {}
        if path.exists():
            try:
                d = json.loads(path.read_text())
            except Exception:
                pass
        self.name     = d.get("name", "Chat")
        self.created  = d.get("created", datetime.now().isoformat())
        self.messages = d.get("messages", [])

    @property
    def turns(self) -> int:
        return len(self.messages) // 2

    @property
    def last_active(self) -> str:
        if self.path.exists():
            return datetime.fromtimestamp(
                self.path.stat().st_mtime
            ).strftime("%b %d %H:%M")
        return "new"

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps({
                "name"    : self.name,
                "created" : self.created,
                "messages": self.messages,
            }, indent=2))
        except Exception:
            pass

    def append_msg(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > MAX_MEMORY_TURNS * 2:
            self.messages = self.messages[-(MAX_MEMORY_TURNS * 2):]
        self.save()

    @staticmethod
    def create(name: str) -> "Chat":
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        safe  = re.sub(r"[^\w\-]", "_", name.strip())[:30] or "chat"
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        path  = CHATS_DIR / f"{ts}_{safe}.json"
        c     = Chat(path)
        c.name    = name.strip() or "New Chat"
        c.created = datetime.now().isoformat()
        c.save()
        return c

    @staticmethod
    def all_chats() -> list:
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        paths = sorted(
            CHATS_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [Chat(p) for p in paths]

# ── chat manager ──────────────────────────────────────────────────────────────
def chat_manager(current: Chat) -> Chat:
    while True:
        chats = Chat.all_chats()

        t = Table(box=box.SIMPLE_HEAD, border_style=P["chat"],
                  header_style=f"bold {P['chat']}", show_lines=False, padding=(0, 2))
        t.add_column("#",      style="bold white", width=6)
        t.add_column("Name",   style=P["ai"],      min_width=20)
        t.add_column("Turns",  style=P["dim"],     width=7)
        t.add_column("Active", style=P["dim"],     width=14)

        for i, c in enumerate(chats, 1):
            marker = "▶ " if c.path == current.path else "  "
            t.add_row(f"{marker}{i}", escape(c.name), str(c.turns), c.last_active)

        t.add_row(
            f"  {len(chats)+1}",
            f"[bold {P['accent']}]+ New chat[/bold {P['accent']}]",
            "", "",
        )

        con.print(Panel(
            t,
            title=f"[{P['chat']}]  Chat Sessions  [/{P['chat']}]",
            border_style=P["chat"],
            box=box.ROUNDED,
            padding=(0, 1),
        ))
        con.print()

        raw = con.input(
            f"  [{P['chat']}]Select[/{P['chat']}]"
            f" [{P['dim']}](number · -N delete · Enter to cancel):[/{P['dim']}] "
        ).strip()
        con.print()

        if not raw:
            return current

        # delete
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(chats):
                    gone = chats[di]
                    if gone.path == current.path:
                        con.print(f"  [{P['err']}]Cannot delete the active chat[/{P['err']}]")
                        con.print()
                        continue
                    gone.path.unlink(missing_ok=True)
                    con.print(f"  [{P['ok']}]✓  Deleted '{escape(gone.name)}'[/{P['ok']}]")
                    con.print()
                    continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]")
            con.print()
            continue

        try:
            idx = int(raw) - 1
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]")
            con.print()
            continue

        # new chat
        if idx == len(chats):
            name = con.input(
                f"  [{P['accent']}]Chat name:[/{P['accent']}] "
            ).strip() or f"Chat {len(chats)+1}"
            new = Chat.create(name)
            con.print(f"  [{P['ok']}]✓  Created '{escape(new.name)}'[/{P['ok']}]")
            con.print()
            return new

        # switch
        if 0 <= idx < len(chats):
            sel = chats[idx]
            con.print(
                f"  [{P['ok']}]✓[/{P['ok']}]"
                f"  Switched to '[{P['chat']}]{escape(sel.name)}[/{P['chat']}]'"
                f"  [{P['dim']}]({sel.turns} turns)[/{P['dim']}]"
            )
            con.print()
            return sel

        con.print(f"  [{P['err']}]Out of range[/{P['err']}]")
        con.print()

# ── message helpers ───────────────────────────────────────────────────────────
def system_prompt_text(model: dict) -> str:
    now = datetime.now().strftime("%A %B %d %Y %H:%M")
    return (
        f"You are a highly capable AI assistant inside NVIDIA NIM, "
        f"powered by {model['label']}. Today is {now}. "
        "Be concise and helpful. Use markdown formatting: "
        "**bold**, *italic*, `inline code`, headers, lists. "
        "When writing code, always wrap it in a fenced block with "
        "the correct language tag, e.g. ```python or ```javascript."
    )

def _strip_system_to_user(messages: list) -> list:
    """
    Convert system message to a user/assistant injection pair.
    Used for models that reject the system role.
    """
    sys_msg = next((m for m in messages if m.get("role") == "system"), None)
    rest    = [m for m in messages if m.get("role") != "system"]
    if sys_msg:
        return [
            {"role": "user",      "content": f"[Instructions] {sys_msg['content']}"},
            {"role": "assistant", "content": "Understood. I am ready to help."},
        ] + rest
    return messages

def build_api_messages(sys_content: str, history: list) -> list:
    return [{"role": "system", "content": sys_content}] + history

# ── streaming panel ───────────────────────────────────────────────────────────
def _ai_panel(text: str, model_label: str, done: bool) -> Panel:
    if done and text.strip():
        # Replace code fences with placeholder — shown separately
        display = CODE_FENCE.sub(
            lambda m: f"\n`[ {(m.group('lang') or 'code').upper()} block — see panel below ]`\n",
            text,
        ).strip()
        try:
            content = Markdown(display or text, code_theme="one-dark")
        except Exception:
            content = Text(text, style=P["ai"])
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

# ── code block renderer + saver ───────────────────────────────────────────────
def _handle_code_blocks(reply: str):
    """For each code block: show syntax panel, prompt for name, save."""
    CODES_DIR.mkdir(exist_ok=True)

    for m in CODE_FENCE.finditer(reply):
        lang = m.group("lang").strip().lower() or "text"
        code = m.group("code")
        ext  = LANG_EXT.get(lang, lang if lang else "txt")
        theme = "monokai" if lang in {"bash", "shell", "sh", "powershell", "dockerfile"} \
                else "one-dark"

        badge = f"  {lang.upper() if lang else 'CODE'}  "
        syn   = Syntax(
            code,
            lang if lang else "text",
            theme=theme,
            line_numbers=True,
            word_wrap=False,
            indent_guides=True,
            background_color="default",
        )
        con.print(Panel(
            syn,
            title=(
                f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]"
                f"  [{P['dim']}].{ext}[/{P['dim']}]"
            ),
            title_align="left",
            border_style=P["code"],
            box=box.HEAVY,
            padding=(0, 1),
        ))

        # ask for name
        try:
            file_name = con.input(
                f"  [{P['accent']}]Name this file[/{P['accent']}]"
                f" [{P['dim']}](e.g. user_auth · Enter to auto-name):[/{P['dim']}] "
            ).strip()
        except Exception:
            file_name = ""

        # build final path
        if file_name:
            safe  = re.sub(r"[^\w\-]", "_", file_name)[:40]
            fname = f"{safe}.{ext}"
        else:
            ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{lang or 'code'}_{ts}.{ext}"

        save_path = CODES_DIR / fname
        # deduplicate
        if save_path.exists():
            stem = save_path.stem
            n    = 1
            while save_path.exists():
                save_path = CODES_DIR / f"{stem}_{n}.{ext}"
                n += 1

        try:
            save_path.write_text(code, encoding="utf-8")
            try:
                rel = save_path.relative_to(Path.cwd())
            except ValueError:
                rel = save_path
            lines = len(code.splitlines())
            con.print(
                f"  [{P['ok']}]↓[/{P['ok']}]  [{P['saved']}]{rel}[/{P['saved']}]"
                f"  [{P['dim']}]({lines} lines)[/{P['dim']}]"
            )
        except Exception as exc:
            con.print(f"  [{P['err']}]Save failed: {escape(str(exc))}[/{P['err']}]")

        con.print()

# ── core streaming with retry ─────────────────────────────────────────────────
def stream_response(client: OpenAI, model: dict, messages: list) -> str:
    """
    Stream tokens into a Live panel.
    On finish → panel updates to formatted Markdown.
    Retries on:
      - system role rejection (rebuilds without system message)
      - transient 400/500 errors (waits 2 s then retries once)
    """

    def _attempt(msgs: list) -> tuple:
        buf = []
        err = None

        with Live(
            _ai_panel("", model["label"], False),
            console=con,
            refresh_per_second=20,
            vertical_overflow="visible",
            transient=False,
        ) as live:
            try:
                stream = client.chat.completions.create(
                    model=model["id"],
                    messages=msgs,
                    max_tokens=MAX_TOKENS,
                    stream=True,
                    temperature=0.7,
                )
                for chunk in stream:
                    # safe extraction — fixes "list index out of range"
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if not choice.delta:
                        continue
                    delta = choice.delta.content or ""
                    if delta:
                        buf.append(delta)
                        live.update(_ai_panel("".join(buf), model["label"], False))
            except Exception as exc:
                err = exc

            reply = "".join(buf)
            try:
                live.update(_ai_panel(reply, model["label"], True))
            except Exception:
                pass

        return reply, err

    # ── attempt 1 ─────────────────────────────────────────────────────────
    reply, err = _attempt(messages)

    if err is not None:
        err_str = str(err).lower()

        # system role rejected → strip and retry
        if "system" in err_str and ("support" in err_str or "not" in err_str):
            con.print(f"  [{P['dim']}]Retrying without system role …[/{P['dim']}]")
            con.print()
            reply, err = _attempt(_strip_system_to_user(messages))

        # still erroring and no partial reply → transient, wait and retry
        if err is not None and not reply:
            con.print(f"  [{P['dim']}]Transient error — retrying in 2 s …[/{P['dim']}]")
            con.print()
            time.sleep(2)
            reply, err = _attempt(messages)

    # if we still have nothing, show the error inline
    if not reply and err is not None:
        reply = f"Error: {err}"
        con.print(f"  [{P['err']}]{escape(reply)}[/{P['err']}]")

    # render code panels + save
    if CODE_FENCE.search(reply):
        con.print()
        _handle_code_blocks(reply)

    return reply

# ── helpers ───────────────────────────────────────────────────────────────────
COMMANDS = {
    "/help"  : "Show commands",
    "/chat"  : "Switch / manage chat sessions",
    "/forget": "Clear current chat memory",
    "/codes" : "List saved code files",
    "/info"  : "Session stats",
    "/clear" : "Clear screen",
    "/exit"  : "Quit",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"],
              show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=10)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items():
        t.add_row(cmd, desc)
    con.print(t)
    con.print()

def list_codes():
    if not CODES_DIR.exists() or not list(CODES_DIR.glob("*")):
        con.print(
            f"  [{P['dim']}]No code files yet"
            f" — saved to [bold]{CODES_DIR}[/bold][/{P['dim']}]"
        )
        con.print()
        return
    files = sorted(CODES_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    t = Table(box=box.SIMPLE_HEAD, border_style=P["code"],
              header_style=f"bold {P['code']}", padding=(0, 2))
    t.add_column("#",     style="bold white", width=4)
    t.add_column("File",  style=P["saved"],   min_width=26)
    t.add_column("Ext",   style=P["accent"],  width=6)
    t.add_column("Lines", style=P["dim"],     width=7)
    t.add_column("When",  style=P["dim"],     width=14)
    for i, f in enumerate(files[:20], 1):
        try:
            lines = len(f.read_text(encoding="utf-8").splitlines())
        except Exception:
            lines = 0
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
        t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), mtime)
    con.print(f"  [{P['code']}]→[/{P['code']}] [bold]{CODES_DIR}[/bold]")
    con.print(t)
    con.print()

def show_info(chat: Chat, model: dict, turn: int):
    codes = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    g = Table.grid(expand=True, padding=(0, 2))
    g.add_column(justify="left")
    g.add_column(justify="center")
    g.add_column(justify="right")
    g.add_row(
        f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]"
        f"  [{P['dim']}]·[/{P['dim']}]  [{P['model']}]{model['label']}[/{P['model']}]",
        f"[{P['dim']}]turn {turn}  ·  {chat.turns} total[/{P['dim']}]",
        f"[{P['code']}]{codes} code files[/{P['code']}]",
    )
    con.print(Panel(g, border_style=P["dim"], padding=(0, 1), box=box.MINIMAL))
    con.print()

def _chat_header(chat: Chat):
    con.print(Panel(
        f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]"
        f"  [{P['dim']}]·  {chat.turns} prior turns  ·  /help for commands[/{P['dim']}]",
        border_style=P["chat"],
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    con.print()

# ── chat loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, chat: Chat):
    sys_content = system_prompt_text(model)
    turn        = 0

    _chat_header(chat)

    if not HAS_PT:
        con.print(
            f"  [{P['dim']}]Tip: pip install prompt_toolkit"
            f" for a styled input box[/{P['dim']}]"
        )
        con.print()

    while True:
        try:
            user_input = get_input(chat.name, model["label"], turn)
        except KeyboardInterrupt:
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd == "/exit":
            break
        if cmd == "/help":
            show_help()
            continue
        if cmd == "/clear":
            con.clear()
            continue
        if cmd == "/codes":
            list_codes()
            continue
        if cmd == "/info":
            show_info(chat, model, turn)
            continue
        if cmd == "/forget":
            chat.messages.clear()
            chat.save()
            con.print(f"  [{P['ok']}]✓  Chat memory cleared[/{P['ok']}]")
            con.print()
            continue
        if cmd == "/chat":
            con.print()
            chat = chat_manager(chat)
            _chat_header(chat)
            continue

        # ── send message ──────────────────────────────────────────────────
        turn += 1

        # show user bubble
        con.print(Panel(
            f"[{P['user']}]{escape(user_input)}[/{P['user']}]",
            title=f"[{P['user']}] You [/{P['user']}]",
            title_align="right",
            border_style=P["dim"],
            box=box.ROUNDED,
            padding=(0, 2),
        ))
        con.print()

        # append user message to history first
        chat.append_msg("user", user_input)

        # build API payload from full history
        msgs  = build_api_messages(sys_content, chat.messages)

        # stream (with retry logic inside)
        reply = stream_response(client, model, msgs)

        # save AI reply
        chat.append_msg("assistant", reply)
        con.print()

        if turn % 5 == 0:
            show_info(chat, model, turn)

# ── entry ─────────────────────────────────────────────────────────────────────
def main():
    splash()
    api_key = get_api_key()
    model   = choose_model()
    client  = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

    # always start a new chat — user names it
    raw_name = con.input(
        f"  [{P['chat']}]New chat name[/{P['chat']}]"
        f" [{P['dim']}](Enter for 'New Chat'):[/{P['dim']}] "
    ).strip()
    chat = Chat.create(raw_name or "New Chat")
    con.print(f"  [{P['ok']}]✓[/{P['ok']}]  Started '[{P['chat']}]{escape(chat.name)}[/{P['chat']}]'")
    con.print()

    try:
        chat_loop(client, model, chat)
    except KeyboardInterrupt:
        pass

    con.print()
    codes = len(list(CODES_DIR.glob("*"))) if CODES_DIR.exists() else 0
    con.print(Panel(
        f"[{P['dim']}]{escape(chat.name)}  ·  {chat.turns} turns  ·  "
        f"[{P['code']}]{codes} code files[/{P['code']}]  ·  Goodbye 👋[/{P['dim']}]",
        border_style=P["border"],
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    ))
    con.print()

if __name__ == "__main__":
    main()
