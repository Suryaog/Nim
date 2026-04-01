#!/usr/bin/env python3
"""
NVIDIA NIM · Terminal AI Client · v7.0
Usage:
  python nim_chat.py                        → new chat
  python nim_chat.py --chat "My Project"    → resume chat by name
  python nim_chat.py --chat 2               → resume chat by index
  python nim_chat.py --list                 → list all chats and exit
"""

import argparse, os, re, sys, json, time, shutil
from datetime import datetime
from pathlib  import Path

# ══════════════════════════════════════════════════════════════════════════════
#  DEPENDENCY GUARD
# ══════════════════════════════════════════════════════════════════════════════
MISSING = []
try:
    from rich.console   import Console
    from rich.panel     import Panel
    from rich.text      import Text
    from rich.table     import Table
    from rich.rule      import Rule
    from rich.syntax    import Syntax
    from rich.markdown  import Markdown
    from rich.markup    import escape
    from rich.live      import Live
    from rich.align     import Align
    from rich.columns   import Columns
    from rich.progress  import BarColumn, Progress, TextColumn
    from rich           import box
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
    from prompt_toolkit                import prompt   as _pt_prompt
    from prompt_toolkit.styles         import Style    as _PtStyle
    from prompt_toolkit.formatted_text import HTML     as _HTML
    from prompt_toolkit.history        import InMemoryHistory as _PTHistory
    HAS_PT = True
except ImportError:
    HAS_PT = False

if MISSING:
    print(f"\n[ SETUP ]  pip install {' '.join(MISSING)}")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
BASE_DIR   = Path.home() / ".nim_chat"
CHATS_DIR  = BASE_DIR   / "chats"
ENV_FILE   = BASE_DIR   / ".env"
SYS_FILE   = BASE_DIR   / "system_prompts.json"   # saved system prompt presets
CODES_ROOT = Path.cwd() / "codes"

for _d in (BASE_DIR, CHATS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

NIM_BASE_URL     = "https://integrate.api.nvidia.com/v1"
MAX_MEMORY_TURNS = 40
MAX_TOKENS       = 2048
VERSION          = "7.0"

MODELS = [
    {"id": "meta/llama-3.1-70b-instruct",        "label": "Llama 3.1 70B",    "ctx": 131072},
    {"id": "qwen/qwen3-coder-480b-a35b-instruct", "label": "Qwen3 Coder 480B", "ctx": 32768 },
]

NO_SAVE_LANGS = {"bash","shell","sh","zsh","fish","powershell","ps1","cmd","batch"}

LANG_EXT = {
    "python":"py","py":"py","javascript":"js","js":"js","typescript":"ts","ts":"ts",
    "jsx":"jsx","tsx":"tsx","html":"html","css":"css","scss":"scss","sass":"sass",
    "java":"java","kotlin":"kt","c":"c","cpp":"cpp","c++":"cpp","csharp":"cs",
    "cs":"cs","rust":"rs","go":"go","ruby":"rb","rb":"rb","php":"php",
    "swift":"swift","r":"r","sql":"sql","json":"json","yaml":"yaml","yml":"yaml",
    "toml":"toml","xml":"xml","md":"md","markdown":"md","dockerfile":"dockerfile",
    "makefile":"makefile","nginx":"conf","text":"txt","txt":"txt","lua":"lua",
    "perl":"pl","scala":"scala","dart":"dart","vue":"vue","svelte":"svelte",
}

CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z0-9+\-#._]*)\n(?P<code>.*?)```", re.DOTALL)

# ══════════════════════════════════════════════════════════════════════════════
#  PALETTE
# ══════════════════════════════════════════════════════════════════════════════
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
    "chat"   : "#ffb74d",
    "mem"    : "#4dd0e1",
    "sys"    : "#f48fb1",   # system prompt colour
    "warn"   : "#ff8a65",
}

con = Console(highlight=False)

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════
def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def msgs_tokens(messages: list) -> int:
    return sum(est_tokens(m.get("content","")) for m in messages)

def _safe_name(text: str, maxlen: int = 30) -> str:
    return re.sub(r"[^\w\-]", "_", text.strip())[:maxlen] or "chat"

def _now_str() -> str:
    return datetime.now().strftime("%A %B %d %Y  %H:%M")

def _elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m {s%60}s"
    return f"{s//3600}h {(s%3600)//60}m"

# ══════════════════════════════════════════════════════════════════════════════
#  PROMPT-TOOLKIT INPUT
# ══════════════════════════════════════════════════════════════════════════════
_PT_STYLE = None
_PT_HIST  = None
if HAS_PT:
    _PT_STYLE = _PtStyle.from_dict({
        "prompt"        : "#4fc3f7 bold",
        ""              : "#e0e0e0",
        "bottom-toolbar": "bg:#0d1117 #546e7a",
    })
    _PT_HIST = _PTHistory()

def get_input(chat_name: str, model_label: str, turn: int,
              sys_active: bool = False) -> str:
    sys_tag = "  [SYS]" if sys_active else ""
    if HAS_PT and _PT_STYLE:
        toolbar = _HTML(
            f"  <b>{chat_name}</b>  ·  {model_label}  ·  "
            f"turn <b>{turn}</b>{sys_tag}  ·  /help"
        )
        try:
            return _pt_prompt(
                "  ❯  ",
                style=_PT_STYLE,
                bottom_toolbar=toolbar,
                history=_PT_HIST,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
    return con.input(f"[{P['border']}]  ❯  [/{P['border']}]").strip()

# ══════════════════════════════════════════════════════════════════════════════
#  SPLASH
# ══════════════════════════════════════════════════════════════════════════════
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

    chats     = Chat.all_chats()
    total_tok = sum(c.token_in + c.token_out for c in chats)
    stats     = (
        f"[{P['dim']}]{len(chats)} chats  ·  "
        f"~{total_tok:,} total tokens  ·  v{VERSION}[/{P['dim']}]"
    )
    art.append(f"\nNVIDIA NIM  ·  Terminal AI  ·  v{VERSION}", style="bold white")

    con.print(Panel(
        Align.center(Text.assemble(art, "\n\n", stats)),
        border_style=P["border"],
        padding=(1, 6),
        box=box.DOUBLE_EDGE,
    ))
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  API KEY
# ══════════════════════════════════════════════════════════════════════════════
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
            con.print(
                f"  [{P['ok']}]✓[/{P['ok']}]  "
                f"[{P['dim']}]API connected · {key[:8]}…{key[-4:]}[/{P['dim']}]"
            )
        except Exception as exc:
            con.print(
                f"  [{P['warn']}]![/{P['warn']}]  "
                f"[{P['dim']}]{escape(str(exc)[:80])}[/{P['dim']}]"
            )
        con.print()
        return key

    con.print(f"  [{P['err']}]No NVIDIA API key found.[/{P['err']}]")
    con.print()
    key  = con.input(f"  [{P['accent']}]API key: [/{P['accent']}]").strip()
    save = con.input(f"  [{P['dim']}]Save key? (y/n): [/{P['dim']}]").strip().lower()
    if save in ("y", "yes"):
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        con.print(f"  [{P['ok']}]✓  Saved to {ENV_FILE}[/{P['ok']}]")
    con.print()
    return key

# ══════════════════════════════════════════════════════════════════════════════
#  MODEL PICKER
# ══════════════════════════════════════════════════════════════════════════════
def choose_model(current: dict | None = None) -> dict:
    t = Table(
        box=box.SIMPLE_HEAD, border_style=P["dim"],
        header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2),
    )
    t.add_column("#",     style="bold white", width=5)
    t.add_column("Model", style=P["ai"],      min_width=24)
    t.add_column("Ctx",   style=P["model"],   width=10)
    for i, m in enumerate(MODELS, 1):
        marker = f"[{P['ok']}]▶ [/{P['ok']}]" if (current and m["id"] == current["id"]) else "  "
        ctx    = f"{m['ctx']:,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(f"{marker}{i}", m["label"], ctx)
    con.print(Panel(
        t,
        title=f"[{P['model']}]  Choose Model  [/{P['model']}]",
        border_style=P["model"], box=box.ROUNDED, padding=(0, 1),
    ))
    while True:
        raw = con.input(
            f"  [{P['model']}]Select[/{P['model']}]"
            f" [{P['dim']}](Enter = 1): [/{P['dim']}]"
        ).strip() or "1"
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(MODELS):
                sel = MODELS[idx]
                con.print(f"  [{P['ok']}]✓  {sel['label']}[/{P['ok']}]")
                con.print()
                return sel
        except ValueError:
            pass
        con.print(f"  [{P['err']}]Invalid — try again[/{P['err']}]")

# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT PRESETS  (~/.nim_chat/system_prompts.json)
# ══════════════════════════════════════════════════════════════════════════════
def _load_presets() -> list:
    if SYS_FILE.exists():
        try:
            return json.loads(SYS_FILE.read_text())
        except Exception:
            pass
    return []

def _save_presets(presets: list):
    SYS_FILE.write_text(json.dumps(presets, indent=2))

def manage_system_prompt(chat: "Chat") -> str:
    """
    Interactive /system manager.
    Returns the chosen system prompt string (or current if unchanged).
    """
    presets = _load_presets()

    while True:
        # ── current status ─────────────────────────────────────────────────
        cur = chat.custom_system or ""
        if cur:
            con.print(Panel(
                f"[{P['sys']}]{escape(cur[:300])}{'…' if len(cur)>300 else ''}[/{P['sys']}]",
                title=f"[{P['sys']}]  Active System Prompt  [/{P['sys']}]",
                border_style=P["sys"], box=box.ROUNDED, padding=(0, 2),
            ))
        else:
            con.print(
                f"  [{P['dim']}]No custom system prompt active — using default.[/{P['dim']}]"
            )
        con.print()

        # ── presets table ──────────────────────────────────────────────────
        if presets:
            t = Table(
                box=box.SIMPLE_HEAD, border_style=P["sys"],
                header_style=f"bold {P['sys']}", show_lines=False, padding=(0, 2),
            )
            t.add_column("#",       style="bold white", width=4)
            t.add_column("Name",    style=P["ai"],      min_width=18)
            t.add_column("Preview", style=P["dim"],     min_width=30)
            for i, p in enumerate(presets, 1):
                prev = p["prompt"][:50].replace("\n", " ") + ("…" if len(p["prompt"]) > 50 else "")
                t.add_row(str(i), escape(p["name"]), escape(prev))
            con.print(Panel(
                t,
                title=f"[{P['sys']}]  Saved Presets  [/{P['sys']}]",
                border_style=P["sys"], box=box.ROUNDED, padding=(0, 1),
            ))
            con.print()

        # ── menu ───────────────────────────────────────────────────────────
        options = Table.grid(padding=(0, 3))
        options.add_column(style=f"bold {P['accent']}", width=4)
        options.add_column(style=P["dim"])
        options.add_row("n", "Write a new system prompt (one-time, for this chat)")
        options.add_row("s", "Write & save as preset")
        if presets:
            options.add_row("1…", "Apply a saved preset to this chat")
            options.add_row("-N", "Delete preset N")
        options.add_row("r", "Reset — remove custom prompt from this chat")
        options.add_row("q", "Done / back to chat")
        con.print(options)
        con.print()

        raw = con.input(f"  [{P['sys']}]Action: [/{P['sys']}]").strip().lower()
        con.print()

        if raw == "q" or raw == "":
            break

        if raw == "r":
            chat.custom_system = ""
            chat.save()
            con.print(f"  [{P['ok']}]✓  System prompt cleared[/{P['ok']}]")
            con.print()
            break

        if raw == "n":
            con.print(f"  [{P['sys']}]Enter system prompt (finish with a blank line):[/{P['sys']}]")
            lines = []
            while True:
                try:
                    line = con.input("  ").rstrip()
                except (EOFError, KeyboardInterrupt):
                    break
                if line == "" and lines:
                    break
                lines.append(line)
            prompt_text = "\n".join(lines).strip()
            if prompt_text:
                chat.custom_system = prompt_text
                chat.save()
                con.print(f"  [{P['ok']}]✓  System prompt applied to '{escape(chat.name)}'[/{P['ok']}]")
            con.print()
            break

        if raw == "s":
            con.print(f"  [{P['sys']}]Preset name: [/{P['sys']}]", end="")
            pname = con.input("").strip()
            if not pname:
                con.print(f"  [{P['err']}]Name required[/{P['err']}]"); con.print(); continue
            con.print(f"  [{P['sys']}]Enter prompt (finish with blank line):[/{P['sys']}]")
            lines = []
            while True:
                try:
                    line = con.input("  ").rstrip()
                except (EOFError, KeyboardInterrupt):
                    break
                if line == "" and lines:
                    break
                lines.append(line)
            prompt_text = "\n".join(lines).strip()
            if prompt_text:
                presets.append({"name": pname, "prompt": prompt_text})
                _save_presets(presets)
                chat.custom_system = prompt_text
                chat.save()
                con.print(f"  [{P['ok']}]✓  Preset '{escape(pname)}' saved & applied[/{P['ok']}]")
            con.print()
            break

        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(presets):
                    gone = presets.pop(di)
                    _save_presets(presets)
                    con.print(f"  [{P['ok']}]✓  Deleted preset '{escape(gone['name'])}'[/{P['ok']}]")
                    con.print(); continue
            except ValueError:
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]"); con.print(); continue

        # numeric → apply preset
        try:
            pi = int(raw) - 1
            if 0 <= pi < len(presets):
                chat.custom_system = presets[pi]["prompt"]
                chat.save()
                con.print(
                    f"  [{P['ok']}]✓  Applied preset '{escape(presets[pi]['name'])}'[/{P['ok']}]"
                )
                con.print()
                break
            else:
                con.print(f"  [{P['err']}]Out of range[/{P['err']}]"); con.print()
        except ValueError:
            con.print(f"  [{P['err']}]Invalid input[/{P['err']}]"); con.print()

    return chat.custom_system

# ══════════════════════════════════════════════════════════════════════════════
#  CHAT CLASS
# ══════════════════════════════════════════════════════════════════════════════
class Chat:
    def __init__(self, path: Path):
        self.path = path
        d: dict   = {}
        if path.exists():
            try:
                d = json.loads(path.read_text())
            except Exception:
                pass
        self.name          = d.get("name",          "Chat")
        self.created       = d.get("created",       datetime.now().isoformat())
        self.messages      = d.get("messages",      [])
        self.token_in      = d.get("token_in",      0)
        self.token_out     = d.get("token_out",     0)
        self.api_calls     = d.get("api_calls",     0)
        self.custom_system = d.get("custom_system", "")   # per-chat system prompt

    @property
    def safe_name(self) -> str:
        return _safe_name(self.name)

    @property
    def codes_dir(self) -> Path:
        d = CODES_ROOT / self.safe_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def turns(self) -> int:
        return sum(1 for m in self.messages if m.get("role") == "assistant")

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
                "name"         : self.name,
                "created"      : self.created,
                "messages"     : self.messages,
                "token_in"     : self.token_in,
                "token_out"    : self.token_out,
                "api_calls"    : self.api_calls,
                "custom_system": self.custom_system,
            }, indent=2))
        except Exception:
            pass

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > MAX_MEMORY_TURNS * 2:
            self.messages = self.messages[-(MAX_MEMORY_TURNS * 2):]
        self.save()

    def record_usage(self, prompt_t: int, reply_t: int):
        self.token_in  += prompt_t
        self.token_out += reply_t
        self.api_calls += 1
        self.save()

    @staticmethod
    def create(name: str) -> "Chat":
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        safe = _safe_name(name)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CHATS_DIR / f"{ts}_{safe}.json"
        c    = Chat(path)
        c.name    = name.strip() or "New Chat"
        c.created = datetime.now().isoformat()
        c.save()
        return c

    @staticmethod
    def all_chats() -> list:
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        return [
            Chat(p)
            for p in sorted(
                CHATS_DIR.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        ]

    @staticmethod
    def find(query: str) -> "Chat | None":
        """Find chat by numeric index (1-based) or name substring."""
        chats = Chat.all_chats()
        if not chats:
            return None
        try:
            idx = int(query) - 1
            if 0 <= idx < len(chats):
                return chats[idx]
        except ValueError:
            pass
        q = query.lower()
        for c in chats:
            if q in c.name.lower():
                return c
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  /chat MANAGER
# ══════════════════════════════════════════════════════════════════════════════
def chat_manager(current: Chat) -> Chat:
    while True:
        chats = Chat.all_chats()
        t = Table(
            box=box.SIMPLE_HEAD, border_style=P["chat"],
            header_style=f"bold {P['chat']}", show_lines=False, padding=(0, 2),
        )
        t.add_column("#",      style="bold white", width=6)
        t.add_column("Name",   style=P["ai"],      min_width=20)
        t.add_column("Model",  style=P["dim"],     width=8)
        t.add_column("Turns",  style=P["dim"],     width=7)
        t.add_column("Tokens", style=P["dim"],     width=9)
        t.add_column("Active", style=P["dim"],     width=14)
        for i, c in enumerate(chats, 1):
            marker = f"[{P['ok']}]▶ [/{P['ok']}]" if c.path == current.path else "  "
            sys_dot = f"[{P['sys']}]●[/{P['sys']}] " if c.custom_system else "  "
            total   = c.token_in + c.token_out
            t.add_row(
                f"{marker}{i}",
                f"{sys_dot}{escape(c.name)}",
                "—",
                str(c.turns),
                f"~{total:,}",
                c.last_active,
            )
        t.add_row(
            f"  {len(chats)+1}",
            f"[bold {P['accent']}]+ New chat[/bold {P['accent']}]",
            "", "", "", "",
        )
        con.print(Panel(
            t,
            title=f"[{P['chat']}]  Chat Sessions  [/{P['chat']}]  [{P['sys']}]● = custom system prompt[/{P['sys']}]",
            border_style=P["chat"], box=box.ROUNDED, padding=(0, 1),
        ))
        con.print()
        raw = con.input(
            f"  [{P['chat']}]Select[/{P['chat']}]"
            f" [{P['dim']}](-N delete · Enter cancel): [/{P['dim']}]"
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
                        con.print(f"  [{P['err']}]Cannot delete active chat[/{P['err']}]")
                        con.print(); continue
                    gone.path.unlink(missing_ok=True)
                    con.print(f"  [{P['ok']}]✓  Deleted '{escape(gone.name)}'[/{P['ok']}]")
                    con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]"); con.print(); continue

        try:
            idx = int(raw) - 1
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue

        if idx == len(chats):
            name = con.input(
                f"  [{P['accent']}]Chat name: [/{P['accent']}]"
            ).strip() or f"Chat {len(chats)+1}"
            new = Chat.create(name)
            con.print(f"  [{P['ok']}]✓  Created '{escape(new.name)}'[/{P['ok']}]")
            con.print()
            return new

        if 0 <= idx < len(chats):
            sel = chats[idx]
            con.print(
                f"  [{P['ok']}]✓[/{P['ok']}]  Resumed "
                f"'[{P['chat']}]{escape(sel.name)}[/{P['chat']}]'"
                f"  [{P['dim']}]{sel.turns} turns[/{P['dim']}]"
            )
            con.print()
            return sel

        con.print(f"  [{P['err']}]Out of range[/{P['err']}]"); con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /memory
# ══════════════════════════════════════════════════════════════════════════════
def show_memory(chat: Chat):
    msgs = [m for m in chat.messages if m["role"] in ("user", "assistant")]
    if not msgs:
        con.print(f"  [{P['dim']}]No memory for this chat yet.[/{P['dim']}]")
        con.print(); return

    # pair into turns
    turns: list = []
    i = 0
    while i < len(msgs):
        u = msgs[i]   if msgs[i]["role"]   == "user"      else None
        a = msgs[i+1] if i+1 < len(msgs) and msgs[i+1]["role"] == "assistant" else None
        turns.append((u, a))
        i += 2 if (u and a) else 1

    con.print(Panel(
        f"[{P['mem']}]{escape(chat.name)}[/{P['mem']}]"
        f"  [{P['dim']}]· {len(turns)} turns · "
        f"~{msgs_tokens(msgs):,} tokens[/{P['dim']}]",
        border_style=P["mem"], box=box.ROUNDED, padding=(0, 2),
    ))
    con.print()

    for idx, (u, a) in enumerate(turns, 1):
        con.print(Rule(
            f"[{P['dim']}] Turn {idx} [/{P['dim']}]",
            style=P["dim"],
        ))
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
            try:
                content = Markdown(atxt)
            except Exception:
                content = Text(atxt, style=P["ai"])
            con.print(Panel(
                content,
                title=f"[{P['ai']}] AI [/{P['ai']}]",
                title_align="left",
                border_style=P["border"], box=box.ROUNDED, padding=(0, 2),
            ))
        con.print()

    while True:
        raw = con.input(
            f"  [{P['mem']}]-N delete turn  · Enter exit: [/{P['mem']}]"
        ).strip()
        if not raw:
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(turns):
                    u_del, a_del = turns[di]
                    chat.messages = [
                        m for m in chat.messages
                        if m is not u_del and m is not a_del
                    ]
                    chat.save()
                    con.print(f"  [{P['ok']}]✓  Turn {di+1} deleted[/{P['ok']}]")
                    con.print(); break
                con.print(f"  [{P['err']}]Invalid turn[/{P['err']}]")
            except ValueError:
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]")
        else:
            con.print(f"  [{P['err']}]Use -N to delete[/{P['err']}]")
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /codes
# ══════════════════════════════════════════════════════════════════════════════
def show_codes(chat: Chat):
    while True:
        files = sorted(
            chat.codes_dir.glob("*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            con.print(
                f"  [{P['dim']}]No code files yet in "
                f"[bold]{chat.codes_dir}[/bold][/{P['dim']}]"
            )
            con.print(); return

        t = Table(
            box=box.SIMPLE_HEAD, border_style=P["code"],
            header_style=f"bold {P['code']}", padding=(0, 2),
        )
        t.add_column("#",     style="bold white", width=4)
        t.add_column("File",  style=P["saved"],   min_width=28)
        t.add_column("Ext",   style=P["accent"],  width=7)
        t.add_column("Lines", style=P["dim"],     width=7)
        t.add_column("Size",  style=P["dim"],     width=8)
        t.add_column("When",  style=P["dim"],     width=14)
        for i, f in enumerate(files, 1):
            try:
                txt   = f.read_text(encoding="utf-8")
                lines = len(txt.splitlines())
                size  = f"{len(txt.encode()):,} B"
            except Exception:
                lines = 0; size = "?"
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
            t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), size, mtime)

        con.print(Panel(
            t,
            title=f"[{P['code']}]  {escape(chat.name)} · Code Files  [/{P['code']}]",
            border_style=P["code"], box=box.ROUNDED, padding=(0, 1),
        ))
        con.print()

        raw = con.input(
            f"  [{P['code']}]N view · -N delete · Enter exit: [/{P['code']}]"
        ).strip()
        con.print()
        if not raw:
            break

        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(files):
                    files[di].unlink()
                    con.print(f"  [{P['ok']}]✓  Deleted {files[di].name}[/{P['ok']}]")
                    con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid index[/{P['err']}]"); con.print(); continue

        try:
            vi = int(raw) - 1
            if 0 <= vi < len(files):
                f     = files[vi]
                lang  = f.suffix.lstrip(".")
                theme = "monokai" if lang in {"sh","ps1","conf"} else "one-dark"
                try:
                    code = f.read_text(encoding="utf-8")
                    con.print(Panel(
                        Syntax(
                            code, lang, theme=theme,
                            line_numbers=True, word_wrap=False,
                            background_color="default",
                        ),
                        title=(
                            f"[bold black on {P['code']}]  {f.name}  "
                            f"[/bold black on {P['code']}]"
                        ),
                        title_align="left",
                        border_style=P["code"], box=box.HEAVY, padding=(0, 1),
                    ))
                    con.print()
                except Exception as exc:
                    con.print(f"  [{P['err']}]Cannot read: {exc}[/{P['err']}]")
                    con.print()
            else:
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print()
        except ValueError:
            con.print(f"  [{P['err']}]N to view, -N to delete[/{P['err']}]"); con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /info
# ══════════════════════════════════════════════════════════════════════════════
def show_info(chat: Chat, model: dict, turn: int, session_start: float):
    codes        = list(chat.codes_dir.glob("*"))
    sess_tokens  = msgs_tokens(chat.messages)
    ctx          = model.get("ctx", 32768)
    ctx_pct      = min(100, int(sess_tokens / ctx * 100))
    elapsed      = _elapsed(time.time() - session_start)
    total_tokens = chat.token_in + chat.token_out

    # context bar
    bar_width = 30
    filled    = int(bar_width * ctx_pct / 100)
    bar_color = P["ok"] if ctx_pct < 60 else (P["warn"] if ctx_pct < 85 else P["err"])
    bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][{P['dim']}]{'░' * (bar_width - filled)}[/{P['dim']}]"

    g = Table.grid(padding=(0, 3))
    g.add_column(justify="right", style=P["dim"],     min_width=20)
    g.add_column(justify="left",  style="bold white", min_width=24)

    g.add_row("", "")
    g.add_row(f"[{P['chat']}]CHAT[/{P['chat']}]",   "")
    g.add_row("Name",          escape(chat.name))
    g.add_row("Created",       chat.created[:16].replace("T", "  "))
    g.add_row("Session time",  elapsed)
    g.add_row("Turns (total)", str(chat.turns))
    g.add_row("Turns (now)",   str(turn))
    g.add_row("API calls",     str(chat.api_calls))
    g.add_row("System prompt", f"[{P['sys']}]Active[/{P['sys']}]" if chat.custom_system else f"[{P['dim']}]Default[/{P['dim']}]")

    g.add_row("", "")
    g.add_row(f"[{P['model']}]MODEL[/{P['model']}]", "")
    g.add_row("Name",          model["label"])
    g.add_row("ID",            f"[{P['dim']}]{model['id']}[/{P['dim']}]")
    g.add_row("Ctx window",    f"{ctx:,} tokens")
    g.add_row("Max output",    f"{MAX_TOKENS:,} tokens")

    g.add_row("", "")
    g.add_row(f"[{P['mem']}]TOKENS[/{P['mem']}]", "")
    g.add_row("Session ctx",   f"~{sess_tokens:,}")
    g.add_row("Ctx usage",     f"{bar}  {ctx_pct}%")
    g.add_row("Total in",      f"~{chat.token_in:,}")
    g.add_row("Total out",     f"~{chat.token_out:,}")
    g.add_row("Total used",    f"~{total_tokens:,}")
    if chat.api_calls > 0:
        avg = total_tokens // chat.api_calls
        g.add_row("Avg / call",    f"~{avg:,}")

    g.add_row("", "")
    g.add_row(f"[{P['code']}]CODES[/{P['code']}]", "")
    g.add_row("Files saved",   str(len(codes)))
    g.add_row("Folder",        str(chat.codes_dir))

    g.add_row("", "")
    g.add_row(f"[{P['accent']}]MEMORY[/{P['accent']}]", "")
    g.add_row("Stored turns",  f"{len(chat.messages)//2} / {MAX_MEMORY_TURNS}")
    g.add_row("Memory size",   f"~{msgs_tokens(chat.messages):,} tokens")

    con.print(Panel(
        g,
        title=f"[{P['border']}]  Session Info  [/{P['border']}]",
        border_style=P["border"], box=box.ROUNDED, padding=(1, 2),
    ))
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /search
# ══════════════════════════════════════════════════════════════════════════════
def search_history(chat: Chat):
    query = con.input(f"  [{P['accent']}]Search memory: [/{P['accent']}]").strip()
    if not query:
        con.print(); return
    q = query.lower()
    hits = [
        m for m in chat.messages
        if m.get("role") in ("user", "assistant") and q in m.get("content","").lower()
    ]
    if not hits:
        con.print(f"  [{P['dim']}]No results for '{escape(query)}'[/{P['dim']}]")
        con.print(); return

    con.print(f"  [{P['ok']}]{len(hits)} result(s) for '{escape(query)}'[/{P['ok']}]")
    con.print()
    for m in hits:
        role  = m["role"]
        txt   = m["content"]
        # highlight match
        hl    = re.sub(
            f"(?i)({re.escape(query)})",
            f"[bold {P['accent']}]\\1[/bold {P['accent']}]",
            escape(txt[:400]),
        )
        label = f"[{P['user']}] You [/{P['user']}]" if role == "user" else f"[{P['ai']}] AI [/{P['ai']}]"
        border = P["dim"] if role == "user" else P["border"]
        con.print(Panel(hl, title=label, title_align="right" if role=="user" else "left",
                        border_style=border, box=box.ROUNDED, padding=(0, 2)))
        con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /rename
# ══════════════════════════════════════════════════════════════════════════════
def rename_chat(chat: Chat):
    new_name = con.input(
        f"  [{P['chat']}]New name for '{escape(chat.name)}': [/{P['chat']}]"
    ).strip()
    if not new_name:
        con.print(f"  [{P['dim']}]Cancelled[/{P['dim']}]"); con.print(); return
    chat.name = new_name
    chat.save()
    con.print(f"  [{P['ok']}]✓  Renamed to '{escape(new_name)}'[/{P['ok']}]")
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  /export
# ══════════════════════════════════════════════════════════════════════════════
def export_chat(chat: Chat):
    msgs  = [m for m in chat.messages if m["role"] in ("user","assistant")]
    if not msgs:
        con.print(f"  [{P['dim']}]Nothing to export[/{P['dim']}]"); con.print(); return

    lines = [
        f"# {chat.name}",
        f"*Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Turns: {chat.turns}  ·  ~{chat.token_in + chat.token_out:,} tokens*",
        "",
    ]
    for m in msgs:
        role  = "**You**" if m["role"] == "user" else "**AI**"
        lines += [f"### {role}", "", m["content"], ""]

    fname = chat.codes_dir.parent / f"{chat.safe_name}_export.md"
    fname.write_text("\n".join(lines), encoding="utf-8")
    con.print(f"  [{P['ok']}]✓  Exported to[/{P['ok']}]  [bold]{fname}[/bold]")
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE BUILDER
# ══════════════════════════════════════════════════════════════════════════════
_BASE_SYSTEM = (
    "Be concise and helpful. Use markdown: **bold**, *italic*, `code`, lists, headers. "
    "Always wrap code in fenced blocks with the correct language tag, "
    "e.g. ```python or ```javascript."
)

def build_system_content(chat: "Chat", model: dict) -> str:
    if chat.custom_system:
        # prepend custom, append base instructions
        return (
            chat.custom_system
            + f"\n\nYou are powered by {model['label']}. Today is {_now_str()}.\n"
            + _BASE_SYSTEM
        )
    return (
        f"You are a highly capable AI assistant inside NVIDIA NIM, "
        f"powered by {model['label']}. Today is {_now_str()}.\n" + _BASE_SYSTEM
    )

def build_api_messages(sys_content: str, history: list, model_id: str) -> list:
    no_sys = {"gemma", "falcon"}
    if any(k in model_id.lower() for k in no_sys):
        return [
            {"role": "user",      "content": f"[Instructions] {sys_content}"},
            {"role": "assistant", "content": "Understood."},
        ] + history
    return [{"role": "system", "content": sys_content}] + history

# ══════════════════════════════════════════════════════════════════════════════
#  STREAMING PANEL
# ══════════════════════════════════════════════════════════════════════════════
def _stream_panel(text: str, model_label: str) -> Panel:
    return Panel(
        Text(text, style=P["ai"]),
        title=f"[{P['ai']}]  {escape(model_label)}  ··· streaming[/{P['ai']}]",
        title_align="left",
        border_style=P["dim"],
        box=box.ROUNDED,
        padding=(1, 2),
    )

# ══════════════════════════════════════════════════════════════════════════════
#  RENDER FORMATTED REPLY
# ══════════════════════════════════════════════════════════════════════════════
def render_formatted_reply(reply: str, chat: Chat, model_label: str):
    """Segment reply → Markdown text + syntax-highlighted code panels."""
    segments = []
    cursor   = 0
    for m in CODE_FENCE.finditer(reply):
        s, e   = m.span()
        before = reply[cursor:s].strip()
        if before:
            segments.append(("text", before, ""))
        segments.append(("code", m.group("code"), m.group("lang").strip().lower() or "text"))
        cursor = e
    tail = reply[cursor:].strip()
    if tail:
        segments.append(("text", tail, ""))

    if not segments:
        return

    # Outer reply panel header
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
            continue

        # ── code block ────────────────────────────────────────────────────
        ext        = LANG_EXT.get(lang, lang if lang else "txt")
        theme      = "monokai" if lang in {"bash","shell","sh","zsh","powershell","dockerfile"} else "one-dark"
        skip_save  = lang in NO_SAVE_LANGS
        badge      = f"  {lang.upper() if lang else 'CODE'}  "
        badge_sfx  = (
            f"  [{P['err']}]terminal — not saved[/{P['err']}]"
            if skip_save
            else f"  [{P['dim']}].{ext}[/{P['dim']}]"
        )

        con.print(Panel(
            Syntax(
                content,
                lang if lang else "text",
                theme=theme,
                line_numbers=True,
                word_wrap=False,
                indent_guides=True,
                background_color="default",
            ),
            title=(
                f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]"
                + badge_sfx
            ),
            title_align="left",
            border_style=P["code"],
            box=box.HEAVY,
            padding=(0, 1),
        ))

        if skip_save:
            con.print()
            continue

        # ask for filename inline
        try:
            raw_name = con.input(
                f"  [{P['accent']}]Save as[/{P['accent']}]"
                f" [{P['dim']}](name · 0 skip · Enter auto): [/{P['dim']}]"
            ).strip()
        except Exception:
            raw_name = ""

        if raw_name == "0":
            con.print(f"  [{P['dim']}]Skipped[/{P['dim']}]")
            con.print(); continue

        if not raw_name:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_name = f"{lang or 'code'}_{ts}"

        safe      = re.sub(r"[^\w\-]", "_", raw_name)[:40]
        save_path = chat.codes_dir / f"{safe}.{ext}"
        n = 1
        while save_path.exists():
            save_path = chat.codes_dir / f"{safe}_{n}.{ext}"
            n += 1

        try:
            save_path.write_text(content, encoding="utf-8")
            try:    rel = save_path.relative_to(Path.cwd())
            except: rel = save_path
            con.print(
                f"  [{P['ok']}]↓[/{P['ok']}]  [{P['saved']}]{rel}[/{P['saved']}]"
                f"  [{P['dim']}]({len(content.splitlines())} lines)[/{P['dim']}]"
            )
        except Exception as exc:
            con.print(f"  [{P['err']}]Save failed: {escape(str(exc))}[/{P['err']}]")
        con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  STREAM → REPLACE
# ══════════════════════════════════════════════════════════════════════════════
def stream_response(
    client  : OpenAI,
    chat    : Chat,
    model   : dict,
    messages: list,
) -> str:
    def _attempt(msgs: list) -> tuple:
        buf = []
        err = None
        with Live(
            _stream_panel("", model["label"]),
            console=con,
            refresh_per_second=6,
            vertical_overflow="ellipsis",
            transient=True,
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

    reply, err = _attempt(messages)

    if err is not None:
        s = str(err).lower()
        if "system" in s and ("support" in s or "not allowed" in s):
            con.print(f"  [{P['dim']}]Retrying without system role…[/{P['dim']}]")
            reply, err = _attempt([m for m in messages if m.get("role") != "system"])
        if err is not None and not reply:
            con.print(f"  [{P['dim']}]Retrying in 2 s…[/{P['dim']}]")
            time.sleep(2)
            reply, err = _attempt(messages)

    chat.record_usage(msgs_tokens(messages), est_tokens(reply))

    if not reply and err is not None:
        reply = f"Error: {err}"
        con.print(f"  [{P['err']}]{escape(reply)}[/{P['err']}]")
        con.print()
        return reply

    con.print()
    render_formatted_reply(reply, chat, model["label"])
    return reply

# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════
COMMANDS = {
    "/help"   : "Show this panel",
    "/chat"   : "Switch · create · delete chats",
    "/model"  : "Switch AI model",
    "/system" : "Add · edit · manage system prompts",
    "/memory" : "View & delete conversation memory",
    "/search" : "Search through chat history",
    "/codes"  : "View · open · delete saved code files",
    "/export" : "Export chat to Markdown file",
    "/rename" : "Rename current chat",
    "/info"   : "Detailed session & token stats",
    "/forget" : "Clear all memory for current chat",
    "/clear"  : "Clear screen",
    "/exit"   : "Quit",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"], show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=12)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items():
        t.add_row(cmd, desc)
    con.print(Panel(
        t,
        title=f"[{P['border']}]  NIM Chat v{VERSION} — Commands  [/{P['border']}]",
        border_style=P["border"], box=box.ROUNDED, padding=(0, 1),
    ))
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAT HEADER
# ══════════════════════════════════════════════════════════════════════════════
def _chat_header(chat: Chat, model: dict):
    sys_tag = f"  [{P['sys']}][SYS][/{P['sys']}]" if chat.custom_system else ""
    codes   = len(list(chat.codes_dir.glob("*")))
    con.print(Panel(
        f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]{sys_tag}"
        f"  [{P['dim']}]·  [{P['model']}]{model['label']}[/{P['model']}]"
        f"  ·  {chat.turns} turns  ·  {codes} code files  ·  /help[/{P['dim']}]",
        border_style=P["chat"],
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAT LOOP
# ══════════════════════════════════════════════════════════════════════════════
def chat_loop(client: OpenAI, model: dict, chat: Chat):
    session_start = time.time()
    turn          = 0

    _chat_header(chat, model)

    while True:
        try:
            user_input = get_input(
                chat.name, model["label"], turn,
                sys_active=bool(chat.custom_system),
            )
        except KeyboardInterrupt:
            break

        if not user_input:
            continue

        cmd = user_input.lower().strip()

        if cmd == "/exit":                                           break
        if cmd == "/help":           show_help();                    continue
        if cmd == "/clear":          con.clear();                    continue
        if cmd == "/codes":          con.print(); show_codes(chat);  continue
        if cmd == "/memory":         con.print(); show_memory(chat); continue
        if cmd == "/search":         con.print(); search_history(chat); continue
        if cmd == "/export":         con.print(); export_chat(chat); continue
        if cmd == "/rename":
            con.print(); rename_chat(chat); _chat_header(chat, model); continue
        if cmd == "/info":
            con.print(); show_info(chat, model, turn, session_start); continue
        if cmd == "/forget":
            chat.messages.clear(); chat.save()
            con.print(f"  [{P['ok']}]✓  Memory cleared[/{P['ok']}]"); con.print(); continue
        if cmd == "/system":
            con.print(); manage_system_prompt(chat); _chat_header(chat, model); continue
        if cmd == "/chat":
            con.print(); chat = chat_manager(chat)
            _chat_header(chat, model); continue
        if cmd == "/model":
            con.print(); model = choose_model(current=model)
            con.print(); _chat_header(chat, model); continue

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

        sys_content = build_system_content(chat, model)
        msgs        = build_api_messages(sys_content, chat.messages, model["id"])
        reply       = stream_response(client, chat, model, msgs)

        chat.add("assistant", reply)
        con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  LIST CHATS  (--list flag)
# ══════════════════════════════════════════════════════════════════════════════
def cmd_list_chats():
    chats = Chat.all_chats()
    if not chats:
        con.print(f"  [{P['dim']}]No chats found.[/{P['dim']}]")
        return
    t = Table(
        box=box.SIMPLE_HEAD, border_style=P["chat"],
        header_style=f"bold {P['chat']}", show_lines=False, padding=(0, 2),
    )
    t.add_column("#",      style="bold white", width=4)
    t.add_column("Name",   style=P["ai"],      min_width=22)
    t.add_column("Turns",  style=P["dim"],     width=7)
    t.add_column("Tokens", style=P["dim"],     width=10)
    t.add_column("SYS",    style=P["sys"],     width=5)
    t.add_column("Active", style=P["dim"],     width=14)
    for i, c in enumerate(chats, 1):
        t.add_row(
            str(i),
            escape(c.name),
            str(c.turns),
            f"~{c.token_in+c.token_out:,}",
            "●" if c.custom_system else "",
            c.last_active,
        )
    con.print(Panel(
        t,
        title=f"[{P['chat']}]  All Chats  [/{P['chat']}]",
        border_style=P["chat"], box=box.ROUNDED, padding=(0, 1),
    ))
    con.print(
        f"  [{P['dim']}]Resume with:  "
        f"[bold]python nim_chat.py --chat \"name\"[/bold]  "
        f"or  [bold]python nim_chat.py --chat N[/bold][/{P['dim']}]"
    )
    con.print()

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        prog="nim_chat.py",
        description="NVIDIA NIM Terminal AI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python nim_chat.py\n"
            "  python nim_chat.py --chat 'My Project'\n"
            "  python nim_chat.py --chat 2\n"
            "  python nim_chat.py --list\n"
        ),
    )
    parser.add_argument(
        "--chat", metavar="NAME_OR_INDEX",
        help="Resume an existing chat by name or index",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all chats and exit",
    )
    args = parser.parse_args()

    # ── --list ───────────────────────────────────────────────────────────
    if args.list:
        cmd_list_chats()
        return

    splash()
    api_key = get_api_key()
    model   = choose_model()
    client  = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

    # ── --chat (resume) ──────────────────────────────────────────────────
    if args.chat:
        found = Chat.find(args.chat)
        if found:
            con.print(
                f"  [{P['ok']}]✓[/{P['ok']}]  Resuming "
                f"'[{P['chat']}]{escape(found.name)}[/{P['chat']}]'"
                f"  [{P['dim']}]{found.turns} turns · "
                f"~{found.token_in+found.token_out:,} tokens[/{P['dim']}]"
            )
            con.print()
            chat = found
        else:
            con.print(
                f"  [{P['warn']}]Chat '{escape(args.chat)}' not found — "
                f"starting new chat.[/{P['warn']}]"
            )
            con.print()
            chat = Chat.create(args.chat)
    else:
        # ── new chat ─────────────────────────────────────────────────────
        raw = con.input(
            f"  [{P['chat']}]New chat name[/{P['chat']}]"
            f" [{P['dim']}](Enter = 'New Chat'): [/{P['dim']}]"
        ).strip()
        chat = Chat.create(raw or "New Chat")
        con.print(
            f"  [{P['ok']}]✓[/{P['ok']}]  Started "
            f"'[{P['chat']}]{escape(chat.name)}[/{P['chat']}]'"
        )
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
        f"~{chat.token_in+chat.token_out:,} tokens  ·  Goodbye 👋[/{P['dim']}]",
        border_style=P["border"], box=box.DOUBLE_EDGE, padding=(0, 2),
    ))
    con.print()

if __name__ == "__main__":
    main()
