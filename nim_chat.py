#!/usr/bin/env python3
"""NVIDIA NIM · Terminal AI Client · v6.0"""

import os, re, sys, json, time, shutil
from datetime import datetime
from pathlib  import Path

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
CODES_ROOT = Path.cwd() / "codes"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DIR.mkdir(parents=True, exist_ok=True)

NIM_BASE_URL     = "https://integrate.api.nvidia.com/v1"
MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048

MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",        "label": "Llama 3.1 70B",    "ctx": 131072},
    {"id": "qwen/qwen3-coder-480b-a35b-instruct", "label": "Qwen3 Coder 480B", "ctx": 32768 },
]

# languages that should NOT be saved as files (shell/terminal commands)
NO_SAVE_LANGS = {"bash", "shell", "sh", "zsh", "fish", "powershell", "ps1", "cmd", "batch"}

LANG_EXT = {
    "python":"py","py":"py","javascript":"js","js":"js","typescript":"ts","ts":"ts",
    "jsx":"jsx","tsx":"tsx","html":"html","css":"css","scss":"scss","sass":"sass",
    "java":"java","kotlin":"kt","c":"c","cpp":"cpp","c++":"cpp","csharp":"cs",
    "cs":"cs","rust":"rs","go":"go","ruby":"rb","rb":"rb","php":"php",
    "swift":"swift","r":"r","sql":"sql","json":"json","yaml":"yaml","yml":"yaml",
    "toml":"toml","xml":"xml","md":"md","markdown":"md","dockerfile":"dockerfile",
    "makefile":"makefile","nginx":"conf","text":"txt","txt":"txt",
}

CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```", re.DOTALL)

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
    "mem"   : "#4dd0e1",
}

con = Console(highlight=False)

# ── token estimation ──────────────────────────────────────────────────────────
def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def msgs_tokens(messages: list) -> int:
    return sum(est_tokens(m.get("content", "")) for m in messages)

# ── prompt_toolkit input ──────────────────────────────────────────────────────
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
    for line, style in [
        ("███╗   ██╗██╗███╗   ███╗", "bold #4fc3f7"),
        ("████╗  ██║██║████╗ ████║", "bold #4dd0e1"),
        ("██╔██╗ ██║██║██╔████╔██║", "bold #80deea"),
        ("██║╚██╗██║██║██║╚██╔╝██║", "bold #69f0ae"),
        ("██║ ╚████║██║██║ ╚═╝ ██║", "bold #a5d6a7"),
        ("╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝", "bold #455a64"),
    ]:
        art.append(line + "\n", style=style)
    art.append("\nNVIDIA NIM  ·  Terminal AI  ·  v6.0", style="bold white")
    con.print(Panel(Align.center(art), border_style=P["border"], padding=(1, 6), box=box.DOUBLE_EDGE))
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
def choose_model(current: dict | None = None) -> dict:
    t = Table(box=box.SIMPLE_HEAD, border_style=P["dim"],
              header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2))
    t.add_column("#",     style="bold white", width=4)
    t.add_column("Model", style=P["ai"],      min_width=24)
    t.add_column("Ctx",   style=P["model"],   width=9)
    for i, m in enumerate(MODELS, 1):
        marker = f"[{P['ok']}]▶[/{P['ok']}] " if (current and m["id"] == current["id"]) else "  "
        ctx    = f"{m['ctx']:,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(f"{marker}{i}", m["label"], ctx)
    con.print(Panel(t, title=f"[{P['model']}]  Models  [/{P['model']}]",
                    border_style=P["model"], box=box.ROUNDED, padding=(0, 1)))
    while True:
        raw = con.input(
            f"  [{P['model']}]Select[/{P['model']}] [{P['dim']}](Enter=1):[/{P['dim']}] "
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
        self.name      = d.get("name", "Chat")
        self.created   = d.get("created", datetime.now().isoformat())
        self.messages  = d.get("messages", [])
        self.token_in  = d.get("token_in", 0)
        self.token_out = d.get("token_out", 0)
        self.api_calls = d.get("api_calls", 0)

    # safe name for filesystem use
    @property
    def safe_name(self) -> str:
        return re.sub(r"[^\w\-]", "_", self.name.strip())[:30] or "chat"

    @property
    def codes_dir(self) -> Path:
        d = CODES_ROOT / self.safe_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def turns(self) -> int:
        roles = [m["role"] for m in self.messages]
        return sum(1 for r in roles if r == "assistant")

    @property
    def last_active(self) -> str:
        if self.path.exists():
            return datetime.fromtimestamp(self.path.stat().st_mtime).strftime("%b %d %H:%M")
        return "new"

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps({
                "name"     : self.name,
                "created"  : self.created,
                "messages" : self.messages,
                "token_in" : self.token_in,
                "token_out": self.token_out,
                "api_calls": self.api_calls,
            }, indent=2))
        except Exception:
            pass

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > MAX_MEMORY_TURNS * 2:
            self.messages = self.messages[-(MAX_MEMORY_TURNS * 2):]
        self.save()

    def record_usage(self, prompt_tokens: int, completion_tokens: int):
        self.token_in  += prompt_tokens
        self.token_out += completion_tokens
        self.api_calls += 1
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

# ── /chat manager ─────────────────────────────────────────────────────────────
def chat_manager(current: Chat) -> Chat:
    while True:
        chats = Chat.all_chats()
        t = Table(box=box.SIMPLE_HEAD, border_style=P["chat"],
                  header_style=f"bold {P['chat']}", show_lines=False, padding=(0, 2))
        t.add_column("#",      style="bold white", width=6)
        t.add_column("Name",   style=P["ai"],      min_width=20)
        t.add_column("Turns",  style=P["dim"],     width=7)
        t.add_column("Tokens", style=P["dim"],     width=9)
        t.add_column("Active", style=P["dim"],     width=14)
        for i, c in enumerate(chats, 1):
            marker = f"[{P['ok']}]▶[/{P['ok']}] " if c.path == current.path else "  "
            total  = c.token_in + c.token_out
            t.add_row(f"{marker}{i}", escape(c.name), str(c.turns),
                      f"~{total:,}", c.last_active)
        t.add_row(f"  {len(chats)+1}", f"[bold {P['accent']}]+ New chat[/bold {P['accent']}]",
                  "", "", "")
        con.print(Panel(t, title=f"[{P['chat']}]  Chat Sessions  [/{P['chat']}]",
                        border_style=P["chat"], box=box.ROUNDED, padding=(0, 1)))
        con.print()
        raw = con.input(
            f"  [{P['chat']}]Select[/{P['chat']}] [{P['dim']}](-N delete · Enter cancel):[/{P['dim']}] "
        ).strip()
        con.print()
        if not raw:
            return current
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(chats):
                    gone = chats[di]
                    if gone.path == current.path:
                        con.print(f"  [{P['err']}]Cannot delete the active chat[/{P['err']}]"); con.print(); continue
                    gone.path.unlink(missing_ok=True)
                    con.print(f"  [{P['ok']}]✓  Deleted '{escape(gone.name)}'[/{P['ok']}]"); con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]"); con.print(); continue
        try:
            idx = int(raw) - 1
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        if idx == len(chats):
            name = con.input(f"  [{P['accent']}]Chat name:[/{P['accent']}] ").strip() or f"Chat {len(chats)+1}"
            new  = Chat.create(name)
            con.print(f"  [{P['ok']}]✓  Created '{escape(new.name)}'[/{P['ok']}]"); con.print()
            return new
        if 0 <= idx < len(chats):
            sel = chats[idx]
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  Switched to '[{P['chat']}]{escape(sel.name)}[/{P['chat']}]'  [{P['dim']}]({sel.turns} turns)[/{P['dim']}]"); con.print()
            return sel
        con.print(f"  [{P['err']}]Out of range[/{P['err']}]"); con.print()

# ── /memory viewer ────────────────────────────────────────────────────────────
def show_memory(chat: Chat):
    msgs = [m for m in chat.messages if m["role"] in ("user", "assistant")]
    if not msgs:
        con.print(f"  [{P['dim']}]No memory for '{escape(chat.name)}'[/{P['dim']}]")
        con.print(); return

    # Group into turns (user + assistant pairs)
    turns = []
    i = 0
    while i < len(msgs):
        u = msgs[i] if msgs[i]["role"] == "user" else None
        a = msgs[i+1] if i+1 < len(msgs) and msgs[i+1]["role"] == "assistant" else None
        turns.append((u, a))
        i += 2 if (u and a) else 1

    con.print(Panel(
        f"[{P['mem']}]{escape(chat.name)}[/{P['mem']}]  [{P['dim']}]· {len(turns)} turns · ~{msgs_tokens(msgs):,} tokens[/{P['dim']}]",
        border_style=P["mem"], box=box.ROUNDED, padding=(0, 2),
    ))
    con.print()

    for idx, (u, a) in enumerate(turns, 1):
        con.print(f"  [{P['dim']}]── Turn {idx} ──────────────────────────[/{P['dim']}]")
        if u:
            utxt = u["content"][:300] + ("…" if len(u["content"]) > 300 else "")
            con.print(Panel(
                f"[{P['user']}]{escape(utxt)}[/{P['user']}]",
                title=f"[{P['user']}] You [/{P['user']}]",
                title_align="right",
                border_style=P["dim"], box=box.ROUNDED, padding=(0, 2),
            ))
        if a:
            atxt = a["content"][:400] + ("…" if len(a["content"]) > 400 else "")
            con.print(Panel(
                Markdown(atxt),
                title=f"[{P['ai']}] AI [/{P['ai']}]",
                title_align="left",
                border_style=P["border"], box=box.ROUNDED, padding=(0, 2),
            ))
        con.print()

    while True:
        raw = con.input(
            f"  [{P['mem']}]Delete turn[/{P['mem']}] [{P['dim']}](-N removes a turn · Enter exit):[/{P['dim']}] "
        ).strip()
        if not raw:
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(turns):
                    u_del, a_del = turns[di]
                    new_msgs = []
                    skip_next = False
                    for m in chat.messages:
                        if skip_next:
                            skip_next = False; continue
                        if (u_del and m is u_del) or (a_del and m is a_del):
                            continue
                        new_msgs.append(m)
                    chat.messages = new_msgs
                    chat.save()
                    con.print(f"  [{P['ok']}]✓  Turn {di+1} deleted[/{P['ok']}]"); con.print(); break
                else:
                    con.print(f"  [{P['err']}]Invalid turn number[/{P['err']}]")
            except ValueError:
                con.print(f"  [{P['err']}]Invalid input[/{P['err']}]")
        else:
            con.print(f"  [{P['err']}]Use -N to delete a turn, or Enter to exit[/{P['err']}]")

# ── /codes manager ────────────────────────────────────────────────────────────
def show_codes(chat: Chat):
    codes_dir = chat.codes_dir
    files = sorted(codes_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        con.print(f"  [{P['dim']}]No code files yet in [bold]{codes_dir}[/bold][/{P['dim']}]")
        con.print(); return

    while True:
        files = sorted(codes_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        t = Table(box=box.SIMPLE_HEAD, border_style=P["code"],
                  header_style=f"bold {P['code']}", padding=(0, 2))
        t.add_column("#",     style="bold white", width=4)
        t.add_column("File",  style=P["saved"],   min_width=28)
        t.add_column("Ext",   style=P["accent"],  width=6)
        t.add_column("Lines", style=P["dim"],     width=7)
        t.add_column("When",  style=P["dim"],     width=14)
        for i, f in enumerate(files, 1):
            try:    lines = len(f.read_text(encoding="utf-8").splitlines())
            except: lines = 0
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
            t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), mtime)
        con.print(Panel(
            t,
            title=f"[{P['code']}]  {escape(chat.name)} · Code Files  [/{P['code']}]",
            border_style=P["code"], box=box.ROUNDED, padding=(0, 1),
        ))
        con.print()
        raw = con.input(
            f"  [{P['code']}]Action[/{P['code']}] [{P['dim']}](N view · -N delete · Enter exit):[/{P['dim']}] "
        ).strip()
        con.print()
        if not raw:
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(files):
                    gone = files[di]
                    gone.unlink()
                    con.print(f"  [{P['ok']}]✓  Deleted {gone.name}[/{P['ok']}]"); con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]"); con.print(); continue
        try:
            vi = int(raw) - 1
            if 0 <= vi < len(files):
                f    = files[vi]
                lang = f.suffix.lstrip(".")
                theme = "monokai" if lang in {"sh","ps1","conf"} else "one-dark"
                try:
                    code = f.read_text(encoding="utf-8")
                    con.print(Panel(
                        Syntax(code, lang, theme=theme, line_numbers=True,
                               word_wrap=False, background_color="default"),
                        title=f"[bold black on {P['code']}]  {f.name}  [/bold black on {P['code']}]",
                        title_align="left",
                        border_style=P["code"], box=box.HEAVY, padding=(0, 1),
                    ))
                    con.print()
                except Exception as exc:
                    con.print(f"  [{P['err']}]Cannot read: {exc}[/{P['err']}]"); con.print()
            else:
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print()
        except ValueError:
            con.print(f"  [{P['err']}]Invalid — use N to view, -N to delete[/{P['err']}]"); con.print()

# ── /info ─────────────────────────────────────────────────────────────────────
def show_info(chat: Chat, model: dict, turn: int):
    codes = list(chat.codes_dir.glob("*"))
    session_tokens = msgs_tokens(chat.messages)
    ctx_pct = int(session_tokens / max(model.get("ctx", 32768), 1) * 100)

    # Build info grid
    g = Table.grid(padding=(0, 3))
    g.add_column(justify="right", style=P["dim"],    min_width=18)
    g.add_column(justify="left",  style="bold white", min_width=22)

    # Chat section
    g.add_row("", "")
    g.add_row(f"[{P['chat']}]── CHAT[/{P['chat']}]", "")
    g.add_row("Name",      escape(chat.name))
    g.add_row("Created",   chat.created[:16].replace("T", "  "))
    g.add_row("Turns",     str(chat.turns))
    g.add_row("API calls", str(chat.api_calls))
    g.add_row("", "")
    g.add_row(f"[{P['model']}]── MODEL[/{P['model']}]", "")
    g.add_row("Name",      model["label"])
    g.add_row("ID",        f"[{P['dim']}]{model['id']}[/{P['dim']}]")
    g.add_row("Ctx window", f"{model.get('ctx', '?'):,} tokens")
    g.add_row("", "")
    g.add_row(f"[{P['mem']}]── TOKENS[/{P['mem']}]", "")
    g.add_row("Total in",   f"~{chat.token_in:,}")
    g.add_row("Total out",  f"~{chat.token_out:,}")
    g.add_row("Total used", f"~{chat.token_in + chat.token_out:,}")
    g.add_row("Session ctx", f"~{session_tokens:,}  ({ctx_pct}% of window)")
    g.add_row("", "")
    g.add_row(f"[{P['code']}]── CODES[/{P['code']}]", "")
    g.add_row("Files saved", str(len(codes)))
    g.add_row("Folder",      str(chat.codes_dir))
    g.add_row("", "")
    g.add_row(f"[{P['accent']}]── SESSION[/{P['accent']}]", "")
    g.add_row("Current turn", str(turn))
    g.add_row("Memory turns", f"{len(chat.messages)//2} / {MAX_MEMORY_TURNS}")

    con.print(Panel(
        g,
        title=f"[{P['border']}]  Session Info  [/{P['border']}]",
        border_style=P["border"], box=box.ROUNDED, padding=(1, 2),
    ))
    con.print()

# ── message builder ───────────────────────────────────────────────────────────
def system_prompt_text(model: dict) -> str:
    return (
        f"You are a highly capable AI assistant inside NVIDIA NIM, "
        f"powered by {model['label']}. "
        f"Today is {datetime.now().strftime('%A %B %d %Y %H:%M')}. "
        "Be concise and helpful. Use markdown: **bold**, *italic*, `code`, lists, headers. "
        "Always wrap code in fenced blocks with the correct language tag, "
        "e.g. ```python or ```javascript."
    )

def build_api_messages(sys_content: str, history: list, model_id: str) -> list:
    no_sys = {"gemma", "falcon"}
    if any(k in model_id.lower() for k in no_sys):
        return [
            {"role": "user",      "content": f"[Instructions] {sys_content}"},
            {"role": "assistant", "content": "Understood. Ready to help."},
        ] + history
    return [{"role": "system", "content": sys_content}] + history

# ── streaming panel builder ───────────────────────────────────────────────────
def _stream_panel(text: str, model_label: str) -> Panel:
    return Panel(
        Text(text, style=P["ai"]) if text else Text("", style=P["ai"]),
        title=f"[{P['ai']}]  {escape(model_label)}  streaming…[/{P['ai']}]",
        title_align="left",
        border_style=P["dim"],
        box=box.ROUNDED,
        padding=(1, 2),
    )

# ── format & render reply (after streaming) ───────────────────────────────────
def render_formatted_reply(reply: str, chat: Chat, model_label: str):
    """
    Print the final formatted reply. For text sections: Markdown.
    For code sections: syntax panel + ask for filename inline.
    Shell/bash blocks are shown but NOT saved.
    """
    segments = []
    cursor   = 0
    for m in CODE_FENCE.finditer(reply):
        s, e  = m.span()
        before = reply[cursor:s].strip()
        if before:
            segments.append(("text", before, ""))
        segments.append(("code", m.group("code"), m.group("lang").strip().lower() or "text"))
        cursor = e
    tail = reply[cursor:].strip()
    if tail:
        segments.append(("text", tail, ""))

    # Header panel
    con.print(Panel(
        "",
        title=f"[{P['ai']}]  {escape(model_label)}  [/{P['ai']}]",
        title_align="left",
        border_style=P["border"],
        box=box.ROUNDED,
        padding=(0, 0),
    ))

    for kind, content, lang in segments:
        if kind == "text":
            try:
                con.print(Panel(
                    Markdown(content, code_theme="one-dark"),
                    border_style=P["border"],
                    box=box.SIMPLE,
                    padding=(0, 2),
                ))
            except Exception:
                con.print(f"  [{P['ai']}]{escape(content)}[/{P['ai']}]")

        else:  # code block
            ext   = LANG_EXT.get(lang, lang if lang else "txt")
            theme = "monokai" if lang in {"bash","shell","sh","zsh","powershell","dockerfile"} else "one-dark"
            skip_save = lang in NO_SAVE_LANGS

            badge = f"  {lang.upper() if lang else 'CODE'}  "
            title_str = (
                f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]"
                + (f"  [{P['err']}](not saved — shell script)[/{P['err']}]" if skip_save else f"  [{P['dim']}].{ext}[/{P['dim']}]")
            )

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
                title=title_str,
                title_align="left",
                border_style=P["code"],
                box=box.HEAVY,
                padding=(0, 1),
            ))

            if skip_save:
                con.print(f"  [{P['dim']}]Shell/terminal commands are not saved as files.[/{P['dim']}]")
                con.print()
                continue

            # Ask for filename right here, inline
            try:
                raw_name = con.input(
                    f"  [{P['accent']}]Save as[/{P['accent']}]"
                    f" [{P['dim']}](name without ext · 0 to skip):[/{P['dim']}] "
                ).strip()
            except Exception:
                raw_name = ""

            if raw_name == "0" or raw_name == "":
                if raw_name == "0":
                    con.print(f"  [{P['dim']}]Skipped[/{P['dim']}]")
                else:
                    # auto-name
                    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
                    raw_name = f"{lang or 'code'}_{ts}"

            if raw_name != "0":
                safe      = re.sub(r"[^\w\-]", "_", raw_name)[:40]
                save_path = chat.codes_dir / f"{safe}.{ext}"
                # deduplicate
                if save_path.exists():
                    n = 1
                    while save_path.exists():
                        save_path = chat.codes_dir / f"{safe}_{n}.{ext}"
                        n += 1
                try:
                    save_path.write_text(content, encoding="utf-8")
                    try:
                        rel = save_path.relative_to(Path.cwd())
                    except ValueError:
                        rel = save_path
                    lines = len(content.splitlines())
                    con.print(
                        f"  [{P['ok']}]↓[/{P['ok']}]  [{P['saved']}]{rel}[/{P['saved']}]"
                        f"  [{P['dim']}]({lines} lines)[/{P['dim']}]"
                    )
                except Exception as exc:
                    con.print(f"  [{P['err']}]Save failed: {escape(str(exc))}[/{P['err']}]")
            con.print()

# ── core: stream then replace ─────────────────────────────────────────────────
def stream_response(client: OpenAI, chat: Chat, model: dict,
                    messages: list) -> str:
    """
    Phase 1: Stream raw tokens into a Live panel (transient=True so it
             fully disappears when done — no leftover / no splitting).
    Phase 2: Print the final formatted reply fresh below.
    Retry logic for transient 400/500 errors and system-role rejection.
    """

    def _do_stream(msgs: list) -> tuple:
        buf = []
        err = None
        # transient=True → Live clears itself cleanly on exit, no leftover text
        with Live(
            _stream_panel("", model["label"]),
            console=con,
            refresh_per_second=8,      # lower rate = less flicker
            vertical_overflow="ellipsis",  # prevent terminal scroll fighting
            transient=True,            # ← KEY FIX: removes panel cleanly on exit
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
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if not choice.delta:
                        continue
                    delta = choice.delta.content or ""
                    if delta:
                        buf.append(delta)
                        live.update(_stream_panel("".join(buf), model["label"]))
            except Exception as exc:
                err = exc
        return "".join(buf), err

    # ── attempt 1 ─────────────────────────────────────────────────────────
    reply, err = _do_stream(messages)

    if err is not None:
        err_s = str(err).lower()
        # system role not supported → rebuild without system msg
        if "system" in err_s and ("support" in err_s or "not allowed" in err_s):
            con.print(f"  [{P['dim']}]Retrying without system role…[/{P['dim']}]")
            no_sys_msgs = [m for m in messages if m.get("role") != "system"]
            reply, err  = _do_stream(no_sys_msgs)
        # still failing → wait and retry once
        if err is not None and not reply:
            con.print(f"  [{P['dim']}]Transient error — retrying in 2 s…[/{P['dim']}]")
            time.sleep(2)
            reply, err = _do_stream(messages)

    # estimate tokens from the exchange
    prompt_est = msgs_tokens(messages)
    reply_est  = est_tokens(reply)
    chat.record_usage(prompt_est, reply_est)

    if not reply and err is not None:
        reply = f"Error: {err}"
        con.print(f"  [{P['err']}]{escape(reply)}[/{P['err']}]")
        con.print()
        return reply

    # ── Phase 2: render formatted output ──────────────────────────────────
    con.print()
    render_formatted_reply(reply, chat, model["label"])

    return reply

# ── commands ──────────────────────────────────────────────────────────────────
COMMANDS = {
    "/help"  : "Show commands",
    "/chat"  : "Switch / manage chat sessions",
    "/model" : "Switch AI model",
    "/memory": "View & manage chat memory / history",
    "/codes" : "View, open, delete saved code files",
    "/info"  : "Detailed session & token stats",
    "/forget": "Clear current chat memory",
    "/clear" : "Clear screen",
    "/exit"  : "Quit",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"], show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=10)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items():
        t.add_row(cmd, desc)
    con.print(Panel(t, title=f"[{P['border']}]  Commands  [/{P['border']}]",
                    border_style=P["border"], box=box.ROUNDED, padding=(0, 1)))
    con.print()

def _chat_header(chat: Chat, model: dict):
    codes = len(list(chat.codes_dir.glob("*")))
    con.print(Panel(
        f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]"
        f"  [{P['dim']}]·[/{P['dim']}]  [{P['model']}]{model['label']}[/{P['model']}]"
        f"  [{P['dim']}]· {chat.turns} turns · {codes} code files · /help[/{P['dim']}]",
        border_style=P["chat"],
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    con.print()

# ── chat loop ─────────────────────────────────────────────────────────────────
def chat_loop(client: OpenAI, model: dict, chat: Chat):
    sys_content = system_prompt_text(model)
    turn        = 0

    _chat_header(chat, model)

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
            show_help(); continue
        if cmd == "/clear":
            con.clear(); continue
        if cmd == "/codes":
            con.print(); show_codes(chat); continue
        if cmd == "/memory":
            con.print(); show_memory(chat); continue
        if cmd == "/info":
            con.print(); show_info(chat, model, turn); continue
        if cmd == "/forget":
            chat.messages.clear(); chat.save()
            con.print(f"  [{P['ok']}]✓  Memory cleared[/{P['ok']}]"); con.print(); continue
        if cmd == "/chat":
            con.print(); chat = chat_manager(chat)
            sys_content = system_prompt_text(model)
            _chat_header(chat, model); continue
        if cmd == "/model":
            con.print(); model = choose_model(current=model)
            sys_content = system_prompt_text(model)
            con.print(); continue

        # ── send ──────────────────────────────────────────────────────────
        turn += 1
        chat.add("user", user_input)

        con.print(Panel(
            f"[{P['user']}]{escape(user_input)}[/{P['user']}]",
            title=f"[{P['user']}] You [/{P['user']}]",
            title_align="right",
            border_style=P["dim"],
            box=box.ROUNDED,
            padding=(0, 2),
        ))
        con.print()

        msgs  = build_api_messages(sys_content, chat.messages, model["id"])
        reply = stream_response(client, chat, model, msgs)

        chat.add("assistant", reply)
        con.print()

# ── entry ─────────────────────────────────────────────────────────────────────
def main():
    splash()
    api_key = get_api_key()
    model   = choose_model()
    client  = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

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
    codes = len(list(chat.codes_dir.glob("*")))
    con.print(Panel(
        f"[{P['dim']}]{escape(chat.name)}  ·  {chat.turns} turns  ·  "
        f"[{P['code']}]{codes} code files[/{P['code']}]  ·  "
        f"~{chat.token_in + chat.token_out:,} tokens  ·  Goodbye 👋[/{P['dim']}]",
        border_style=P["border"], box=box.DOUBLE_EDGE, padding=(0, 2),
    ))
    con.print()

if __name__ == "__main__":
    main()
