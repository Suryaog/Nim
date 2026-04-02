#!/usr/bin/env python3
"""
NVIDIA NIM · Terminal AI Client · v7.2
  python nim_chat.py                 → new chat
  python nim_chat.py --chat NAME/N   → resume chat
  python nim_chat.py --list          → list all chats
"""
import argparse, os, re, sys, json, time
from datetime import datetime
from pathlib  import Path

# ═══════════════════════════════════════════════════════════════════════════════
#  DEPS
# ═══════════════════════════════════════════════════════════════════════════════
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
    from prompt_toolkit                import prompt   as _pt_prompt
    from prompt_toolkit.styles         import Style    as _PtStyle
    from prompt_toolkit.formatted_text import HTML     as _HTML
    from prompt_toolkit.history        import InMemoryHistory as _PTHist
    HAS_PT = True
except ImportError:
    HAS_PT = False

if MISSING:
    print(f"\n[ SETUP ]  pip install {' '.join(MISSING)}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
BASE_DIR   = Path.home() / ".nim_chat"
CHATS_DIR  = BASE_DIR   / "chats"
ENV_FILE   = BASE_DIR   / ".env"
SYS_FILE   = BASE_DIR   / "system_prompts.json"
CFG_FILE   = BASE_DIR   / "settings.json"
CODES_ROOT = Path.cwd() / "codes"
for _d in (BASE_DIR, CHATS_DIR): _d.mkdir(parents=True, exist_ok=True)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
VERSION      = "7.2"

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

# ═══════════════════════════════════════════════════════════════════════════════
#  PALETTE
# ═══════════════════════════════════════════════════════════════════════════════
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
    "sys"   : "#f48fb1",
    "warn"  : "#ff8a65",
}

con = Console(highlight=False)

# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
SETTING_DEFS = {
    "max_tokens"           : ("Max output tokens",          "int",   2048,      [512, 1024, 2048, 4096]),
    "temperature"          : ("Temperature",                "float", 0.7,       None),
    "max_memory_turns"     : ("Memory turns kept",          "int",   40,        [10, 20, 40, 60, 80]),
    "stream_refresh"       : ("Stream refresh rate (fps)",  "int",   6,         [4, 6, 8, 12]),
    "code_theme"           : ("Code syntax theme",          "str",   "one-dark", ["one-dark","monokai","dracula","github-dark","solarized-dark"]),
    "auto_name_code"       : ("Auto-name code files",       "bool",  False,     None),
    "show_tokens_per_reply": ("Show token count per reply", "bool",  True,      None),
    "confirm_delete"       : ("Confirm before deleting",    "bool",  True,      None),
    "compact_header"       : ("Compact chat header",        "bool",  False,     None),
    "save_shell_scripts"   : ("Save bash/shell blocks",     "bool",  False,     None),
}

class Settings:
    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        base = {k: v[2] for k, v in SETTING_DEFS.items()}
        if CFG_FILE.exists():
            try:
                stored = json.loads(CFG_FILE.read_text())
                base.update({k: v for k, v in stored.items() if k in base})
            except Exception:
                pass
        self._data = base

    def save(self):
        try:
            CFG_FILE.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass

    def get(self, key):
        return self._data.get(key, SETTING_DEFS[key][2])

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def toggle(self, key):
        self._data[key] = not self._data[key]
        self.save()
        return self._data[key]

CFG = Settings()

# ═══════════════════════════════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════════════════════════════
def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def msgs_tokens(msgs: list) -> int:
    return sum(est_tokens(m.get("content", "")) for m in msgs)

def _safe(text: str, n: int = 30) -> str:
    return re.sub(r"[^\w\-]", "_", text.strip())[:n] or "chat"

def _now() -> str:
    return datetime.now().strftime("%A %B %d %Y  %H:%M")

def _elapsed(s: float) -> str:
    s = int(s)
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m {s%60}s"
    return f"{s//3600}h {(s%3600)//60}m"

# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT  (prompt_toolkit styled bar)
# ═══════════════════════════════════════════════════════════════════════════════
_PT_STYLE = None
_PT_HIST  = None
if HAS_PT:
    _PT_STYLE = _PtStyle.from_dict({
        "prompt"        : "#4fc3f7 bold",
        ""              : "#e0e0e0",
        "bottom-toolbar": "bg:#0d1117 #546e7a",
    })
    _PT_HIST = _PTHist()

def get_input(chat_name: str, model_label: str, turn: int, sys_active: bool = False) -> str:
    sys_tag = "  [SYS]" if sys_active else ""
    if HAS_PT and _PT_STYLE:
        toolbar = _HTML(
            f"  <b>{chat_name}</b>  ·  {model_label}"
            f"  ·  turn <b>{turn}</b>{sys_tag}  ·  /help"
        )
        try:
            return _pt_prompt(
                "  ❯  ", style=_PT_STYLE,
                bottom_toolbar=toolbar, history=_PT_HIST,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
    return con.input(f"[{P['border']}]  ❯  [/{P['border']}]").strip()

# ═══════════════════════════════════════════════════════════════════════════════
#  SPLASH
# ═══════════════════════════════════════════════════════════════════════════════
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
    chats = Chat.all_chats()
    total = sum(c.token_in + c.token_out for c in chats)
    art.append(f"\nNVIDIA NIM  ·  Terminal AI  ·  v{VERSION}", style="bold white")
    stats = f"[{P['dim']}]{len(chats)} chats  ·  ~{total:,} tokens[/{P['dim']}]"
    con.print(Panel(
        Align.center(Text.assemble(art, "\n\n", stats)),
        border_style=P["border"], padding=(1, 6), box=box.DOUBLE_EDGE,
    ))
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  API KEY
# ═══════════════════════════════════════════════════════════════════════════════
def load_env():
    if ENV_FILE.exists(): load_dotenv(ENV_FILE)
    else: load_dotenv()

def get_api_key() -> str:
    load_env()
    key = os.getenv("NVIDIA_API_KEY", "")
    if key:
        try:
            OpenAI(api_key=key, base_url=NIM_BASE_URL).models.list()
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  [{P['dim']}]API connected · {key[:8]}…{key[-4:]}[/{P['dim']}]")
        except Exception as e:
            con.print(f"  [{P['warn']}]![/{P['warn']}]  [{P['dim']}]{escape(str(e)[:80])}[/{P['dim']}]")
        con.print()
        return key
    con.print(f"  [{P['err']}]No NVIDIA API key found.[/{P['err']}]")
    con.print()
    key  = con.input(f"  [{P['accent']}]API key: [/{P['accent']}]").strip()
    save = con.input(f"  [{P['dim']}]Save? (y/n): [/{P['dim']}]").strip().lower()
    if save in ("y", "yes"):
        ENV_FILE.touch()
        set_key(str(ENV_FILE), "NVIDIA_API_KEY", key)
        con.print(f"  [{P['ok']}]✓  Saved[/{P['ok']}]")
    con.print()
    return key

# ═══════════════════════════════════════════════════════════════════════════════
#  MODEL PICKER
# ═══════════════════════════════════════════════════════════════════════════════
def choose_model(current: dict | None = None) -> dict:
    t = Table(box=box.SIMPLE_HEAD, border_style=P["dim"],
              header_style=f"bold {P['model']}", show_lines=False, padding=(0, 2))
    t.add_column("#",     style="bold white", width=5)
    t.add_column("Model", style=P["ai"],      min_width=24)
    t.add_column("Ctx",   style=P["model"],   width=10)
    for i, m in enumerate(MODELS, 1):
        mk  = f"[{P['ok']}]▶ [/{P['ok']}]" if (current and m["id"] == current["id"]) else "  "
        ctx = f"{m['ctx']:,}" if isinstance(m.get("ctx"), int) else "?"
        t.add_row(f"{mk}{i}", m["label"], ctx)
    con.print(Panel(t, title=f"[{P['model']}]  Choose Model  [/{P['model']}]",
                    border_style=P["model"], box=box.ROUNDED, padding=(0, 1)))
    while True:
        raw = con.input(
            f"  [{P['model']}]Select[/{P['model']}] [{P['dim']}](Enter=1): [/{P['dim']}]"
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
        con.print(f"  [{P['err']}]Invalid[/{P['err']}]")

# ═══════════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT PRESETS
# ═══════════════════════════════════════════════════════════════════════════════
def _load_presets() -> list:
    if SYS_FILE.exists():
        try: return json.loads(SYS_FILE.read_text())
        except Exception: pass
    return []

def _save_presets(p: list):
    SYS_FILE.write_text(json.dumps(p, indent=2))

def _multiline_input(prompt_text: str) -> str:
    con.print(f"  [{P['sys']}]{prompt_text}  (blank line to finish):[/{P['sys']}]")
    lines = []
    while True:
        try:
            line = con.input("  ").rstrip()
        except (EOFError, KeyboardInterrupt):
            break
        if line == "" and lines:
            break
        lines.append(line)
    return "\n".join(lines).strip()

def manage_system_prompt(chat: "Chat") -> str:
    presets = _load_presets()
    while True:
        cur = chat.custom_system or ""
        if cur:
            con.print(Panel(
                f"[{P['sys']}]{escape(cur[:300])}{'…' if len(cur) > 300 else ''}[/{P['sys']}]",
                title=f"[{P['sys']}]  Active System Prompt  [/{P['sys']}]",
                border_style=P["sys"], box=box.ROUNDED, padding=(0, 2),
            ))
        else:
            con.print(f"  [{P['dim']}]No custom prompt — using default.[/{P['dim']}]")
        con.print()

        if presets:
            t = Table(box=box.SIMPLE_HEAD, border_style=P["sys"],
                      header_style=f"bold {P['sys']}", show_lines=False, padding=(0, 2))
            t.add_column("#",       style="bold white", width=4)
            t.add_column("Name",    style=P["ai"],      min_width=18)
            t.add_column("Preview", style=P["dim"],     min_width=30)
            for i, p in enumerate(presets, 1):
                prev = p["prompt"][:50].replace("\n", " ") + ("…" if len(p["prompt"]) > 50 else "")
                t.add_row(str(i), escape(p["name"]), escape(prev))
            con.print(Panel(t, title=f"[{P['sys']}]  Presets  [/{P['sys']}]",
                            border_style=P["sys"], box=box.ROUNDED, padding=(0, 1)))
            con.print()

        g = Table.grid(padding=(0, 3))
        g.add_column(style=f"bold {P['accent']}", width=4)
        g.add_column(style=P["dim"])
        g.add_row("n",  "Write new prompt for this chat")
        g.add_row("s",  "Write & save as preset")
        if presets:
            g.add_row("N",  "Apply preset N")
            g.add_row("-N", "Delete preset N")
        g.add_row("r",  "Reset / remove custom prompt")
        g.add_row("q",  "Back")
        con.print(g)
        con.print()

        raw = con.input(f"  [{P['sys']}]Action: [/{P['sys']}]").strip().lower()
        con.print()

        if raw in ("q", ""):
            break
        if raw == "r":
            chat.custom_system = ""; chat.save()
            con.print(f"  [{P['ok']}]✓  Cleared[/{P['ok']}]"); con.print(); break
        if raw == "n":
            txt = _multiline_input("System prompt")
            if txt:
                chat.custom_system = txt; chat.save()
                con.print(f"  [{P['ok']}]✓  Applied[/{P['ok']}]"); con.print()
            break
        if raw == "s":
            pname = con.input(f"  [{P['sys']}]Preset name: [/{P['sys']}]").strip()
            if not pname:
                con.print(f"  [{P['err']}]Name required[/{P['err']}]"); con.print(); continue
            txt = _multiline_input("Prompt")
            if txt:
                presets.append({"name": pname, "prompt": txt}); _save_presets(presets)
                chat.custom_system = txt; chat.save()
                con.print(f"  [{P['ok']}]✓  Preset '{escape(pname)}' saved[/{P['ok']}]"); con.print()
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(presets):
                    gone = presets.pop(di); _save_presets(presets)
                    con.print(f"  [{P['ok']}]✓  Deleted '{escape(gone['name'])}'[/{P['ok']}]"); con.print(); continue
            except ValueError:
                pass
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        try:
            pi = int(raw) - 1
            if 0 <= pi < len(presets):
                chat.custom_system = presets[pi]["prompt"]; chat.save()
                con.print(f"  [{P['ok']}]✓  Applied '{escape(presets[pi]['name'])}'[/{P['ok']}]"); con.print(); break
            else:
                con.print(f"  [{P['err']}]Out of range[/{P['err']}]"); con.print()
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print()
    return chat.custom_system

# ═══════════════════════════════════════════════════════════════════════════════
#  /settings
# ═══════════════════════════════════════════════════════════════════════════════
def show_settings():
    while True:
        keys = list(SETTING_DEFS.keys())
        t = Table(box=box.SIMPLE_HEAD, border_style=P["accent"],
                  header_style=f"bold {P['accent']}", show_lines=False, padding=(0, 2))
        t.add_column("#",       style="bold white", width=4)
        t.add_column("Setting", style=P["ai"],      min_width=28)
        t.add_column("Value",   style="bold white", width=14)
        t.add_column("Options", style=P["dim"],     min_width=20)
        for i, (k, meta) in enumerate(SETTING_DEFS.items(), 1):
            label, typ, default, choices = meta
            val = CFG.get(k)
            if typ == "bool":
                vstr = f"[{P['ok']}]ON[/{P['ok']}]" if val else f"[{P['err']}]OFF[/{P['err']}]"
                opts = "toggle"
            elif choices:
                vstr = str(val)
                opts = " / ".join(str(c) for c in choices)
            else:
                vstr = str(val)
                opts = "free value"
            t.add_row(str(i), label, vstr, opts)
        con.print(Panel(
            t,
            title=f"[{P['accent']}]  Settings  ·  N to edit  ·  Enter exit  [/{P['accent']}]",
            border_style=P["accent"], box=box.ROUNDED, padding=(0, 1),
        ))
        con.print()

        raw = con.input(
            f"  [{P['accent']}]Edit #[/{P['accent']}] [{P['dim']}](Enter exit): [/{P['dim']}]"
        ).strip()
        con.print()
        if not raw:
            break
        try:
            si = int(raw) - 1
            if not (0 <= si < len(keys)):
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue

        k                          = keys[si]
        label, typ, default, choices = SETTING_DEFS[k]
        cur                        = CFG.get(k)

        if typ == "bool":
            new_val = CFG.toggle(k)
            state   = f"[{P['ok']}]ON[/{P['ok']}]" if new_val else f"[{P['err']}]OFF[/{P['err']}]"
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  {label} → {state}"); con.print(); continue

        if choices:
            try:
                ci  = choices.index(cur)
                nxt = choices[(ci + 1) % len(choices)]
            except ValueError:
                nxt = choices[0]
            CFG.set(k, nxt)
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  {label} → [bold]{nxt}[/bold]"); con.print(); continue

        new_raw = con.input(
            f"  [{P['accent']}]{label} [{P['dim']}](current: {cur})[/{P['dim']}]: [/{P['accent']}]"
        ).strip()
        if not new_raw:
            con.print(f"  [{P['dim']}]Unchanged[/{P['dim']}]"); con.print(); continue
        try:
            if   typ == "int":   CFG.set(k, int(new_raw))
            elif typ == "float": CFG.set(k, float(new_raw))
            else:                CFG.set(k, new_raw)
            con.print(f"  [{P['ok']}]✓  Saved[/{P['ok']}]")
        except ValueError:
            con.print(f"  [{P['err']}]Invalid value for {typ}[/{P['err']}]")
        con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT CLASS
# ═══════════════════════════════════════════════════════════════════════════════
class Chat:
    def __init__(self, path: Path):
        self.path = path
        d: dict = {}
        if path.exists():
            try: d = json.loads(path.read_text())
            except Exception: pass
        self.name          = d.get("name",          "Chat")
        self.created       = d.get("created",       datetime.now().isoformat())
        self.messages      = d.get("messages",      [])
        self.token_in      = d.get("token_in",      0)
        self.token_out     = d.get("token_out",     0)
        self.api_calls     = d.get("api_calls",     0)
        self.custom_system = d.get("custom_system", "")

    @property
    def safe_name(self) -> str:
        return _safe(self.name)

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
            return datetime.fromtimestamp(self.path.stat().st_mtime).strftime("%b %d %H:%M")
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
        mt = CFG.get("max_memory_turns")
        if len(self.messages) > mt * 2:
            self.messages = self.messages[-(mt * 2):]
        self.save()

    def record_usage(self, pi: int, ri: int):
        self.token_in  += pi
        self.token_out += ri
        self.api_calls += 1
        self.save()

    @staticmethod
    def create(name: str) -> "Chat":
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        safe = _safe(name)
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
            Chat(p) for p in sorted(
                CHATS_DIR.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        ]

    @staticmethod
    def find(query: str) -> "Chat | None":
        chats = Chat.all_chats()
        if not chats: return None
        try:
            idx = int(query) - 1
            if 0 <= idx < len(chats): return chats[idx]
        except ValueError:
            pass
        q = query.lower()
        for c in chats:
            if q in c.name.lower(): return c
        return None

# ═══════════════════════════════════════════════════════════════════════════════
#  /chat  MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
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
            mk  = f"[{P['ok']}]▶ [/{P['ok']}]" if c.path == current.path else "  "
            dot = f"[{P['sys']}]●[/{P['sys']}] " if c.custom_system else "  "
            t.add_row(f"{mk}{i}", f"{dot}{escape(c.name)}", str(c.turns),
                      f"~{c.token_in+c.token_out:,}", c.last_active)
        t.add_row(f"  {len(chats)+1}",
                  f"[bold {P['accent']}]+ New chat[/bold {P['accent']}]", "", "", "")
        con.print(Panel(t, title=f"[{P['chat']}]  Chats  [/{P['chat']}]",
                        border_style=P["chat"], box=box.ROUNDED, padding=(0, 1)))
        con.print()
        raw = con.input(
            f"  [{P['chat']}]-N delete · N switch · {len(chats)+1} new · Enter cancel: [/{P['chat']}]"
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
                        con.print(f"  [{P['err']}]Cannot delete active chat[/{P['err']}]"); con.print(); continue
                    if CFG.get("confirm_delete"):
                        yn = con.input(f"  [{P['warn']}]Delete '{escape(gone.name)}'? (y/n): [/{P['warn']}]").strip().lower()
                        if yn not in ("y", "yes"):
                            con.print(f"  [{P['dim']}]Cancelled[/{P['dim']}]"); con.print(); continue
                    gone.path.unlink(missing_ok=True)
                    con.print(f"  [{P['ok']}]✓  Deleted '{escape(gone.name)}'[/{P['ok']}]"); con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        try:
            idx = int(raw) - 1
        except ValueError:
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        if idx == len(chats):
            name = con.input(f"  [{P['accent']}]Chat name: [/{P['accent']}]").strip() or f"Chat {len(chats)+1}"
            new  = Chat.create(name)
            con.print(f"  [{P['ok']}]✓  Created '{escape(new.name)}'[/{P['ok']}]"); con.print()
            return new
        if 0 <= idx < len(chats):
            sel = chats[idx]
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  '[{P['chat']}]{escape(sel.name)}[/{P['chat']}]'"
                      f"  [{P['dim']}]{sel.turns} turns[/{P['dim']}]"); con.print()
            return sel
        con.print(f"  [{P['err']}]Out of range[/{P['err']}]"); con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  /memory
# ═══════════════════════════════════════════════════════════════════════════════
def show_memory(chat: Chat):
    msgs = [m for m in chat.messages if m["role"] in ("user", "assistant")]
    if not msgs:
        con.print(f"  [{P['dim']}]No memory yet.[/{P['dim']}]"); con.print(); return
    turns = []
    i = 0
    while i < len(msgs):
        u = msgs[i]   if msgs[i]["role"]   == "user"      else None
        a = msgs[i+1] if i+1 < len(msgs) and msgs[i+1]["role"] == "assistant" else None
        turns.append((u, a))
        i += 2 if (u and a) else 1
    con.print(Panel(
        f"[{P['mem']}]{escape(chat.name)}[/{P['mem']}]"
        f"  [{P['dim']}]· {len(turns)} turns · ~{msgs_tokens(msgs):,} tokens[/{P['dim']}]",
        border_style=P["mem"], box=box.ROUNDED, padding=(0, 2),
    ))
    con.print()
    for idx, (u, a) in enumerate(turns, 1):
        con.print(Rule(f"[{P['dim']}] Turn {idx} [/{P['dim']}]", style=P["dim"]))
        if u:
            txt = u["content"][:300] + ("…" if len(u["content"]) > 300 else "")
            con.print(Panel(f"[{P['user']}]{escape(txt)}[/{P['user']}]",
                            title=f"[{P['user']}] You [/{P['user']}]", title_align="right",
                            border_style=P["dim"], box=box.ROUNDED, padding=(0, 2)))
        if a:
            txt = a["content"][:400] + ("…" if len(a["content"]) > 400 else "")
            try:    content = Markdown(txt)
            except: content = Text(txt, style=P["ai"])
            con.print(Panel(content, title=f"[{P['ai']}] AI [/{P['ai']}]", title_align="left",
                            border_style=P["border"], box=box.ROUNDED, padding=(0, 2)))
        con.print()
    while True:
        raw = con.input(f"  [{P['mem']}]-N delete turn · Enter exit: [/{P['mem']}]").strip()
        if not raw:
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(turns):
                    u_del, a_del = turns[di]
                    chat.messages = [m for m in chat.messages if m is not u_del and m is not a_del]
                    chat.save()
                    con.print(f"  [{P['ok']}]✓  Turn {di+1} deleted[/{P['ok']}]"); con.print(); break
                con.print(f"  [{P['err']}]Invalid turn[/{P['err']}]")
            except ValueError:
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]")
        else:
            con.print(f"  [{P['err']}]Use -N to delete[/{P['err']}]")
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  /codes
# ═══════════════════════════════════════════════════════════════════════════════
def show_codes(chat: Chat):
    while True:
        files = sorted(chat.codes_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            con.print(f"  [{P['dim']}]No code files in [bold]{chat.codes_dir}[/bold][/{P['dim']}]")
            con.print(); return
        t = Table(box=box.SIMPLE_HEAD, border_style=P["code"],
                  header_style=f"bold {P['code']}", padding=(0, 2))
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
                size  = f"{len(txt.encode()):,}B"
            except Exception:
                lines = 0; size = "?"
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M")
            t.add_row(str(i), f.name, f.suffix.lstrip("."), str(lines), size, mtime)
        con.print(Panel(t, title=f"[{P['code']}]  {escape(chat.name)} · Code Files  [/{P['code']}]",
                        border_style=P["code"], box=box.ROUNDED, padding=(0, 1)))
        con.print()
        raw = con.input(f"  [{P['code']}]N view · -N delete · Enter exit: [/{P['code']}]").strip()
        con.print()
        if not raw:
            break
        if raw.startswith("-"):
            try:
                di = int(raw[1:]) - 1
                if 0 <= di < len(files):
                    if CFG.get("confirm_delete"):
                        yn = con.input(f"  [{P['warn']}]Delete {files[di].name}? (y/n): [/{P['warn']}]").strip().lower()
                        if yn not in ("y", "yes"):
                            con.print(f"  [{P['dim']}]Cancelled[/{P['dim']}]"); con.print(); continue
                    files[di].unlink()
                    con.print(f"  [{P['ok']}]✓  Deleted {files[di].name}[/{P['ok']}]"); con.print(); continue
            except (ValueError, IndexError):
                pass
            con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print(); continue
        try:
            vi = int(raw) - 1
            if 0 <= vi < len(files):
                f     = files[vi]
                lang  = f.suffix.lstrip(".")
                theme = CFG.get("code_theme")
                try:
                    code = f.read_text(encoding="utf-8")
                    con.print(Panel(
                        Syntax(code, lang, theme=theme, line_numbers=True,
                               word_wrap=False, background_color="default"),
                        title=f"[bold black on {P['code']}]  {f.name}  [/bold black on {P['code']}]",
                        title_align="left", border_style=P["code"], box=box.HEAVY, padding=(0, 1),
                    ))
                    con.print()
                except Exception as e:
                    con.print(f"  [{P['err']}]{e}[/{P['err']}]"); con.print()
            else:
                con.print(f"  [{P['err']}]Invalid[/{P['err']}]"); con.print()
        except ValueError:
            con.print(f"  [{P['err']}]N to view · -N to delete[/{P['err']}]"); con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  /info
# ═══════════════════════════════════════════════════════════════════════════════
def show_info(chat: Chat, model: dict, turn: int, session_start: float):
    codes   = list(chat.codes_dir.glob("*"))
    sess    = msgs_tokens(chat.messages)
    ctx     = model.get("ctx", 32768)
    pct     = min(100, int(sess / ctx * 100))
    elapsed = _elapsed(time.time() - session_start)
    bw      = 28
    filled  = int(bw * pct / 100)
    bc      = P["ok"] if pct < 60 else (P["warn"] if pct < 85 else P["err"])
    bar     = f"[{bc}]{'█'*filled}[/{bc}][{P['dim']}]{'░'*(bw-filled)}[/{P['dim']}]"
    g = Table.grid(padding=(0, 3))
    g.add_column(justify="right", style=P["dim"],     min_width=22)
    g.add_column(justify="left",  style="bold white", min_width=26)
    rows = [
        (f"[{P['chat']}]── CHAT[/{P['chat']}]",   ""),
        ("Name",          escape(chat.name)),
        ("Created",       chat.created[:16].replace("T", "  ")),
        ("Session time",  elapsed),
        ("Turns total",   str(chat.turns)),
        ("Turns now",     str(turn)),
        ("API calls",     str(chat.api_calls)),
        ("System prompt", f"[{P['sys']}]Active[/{P['sys']}]" if chat.custom_system else f"[{P['dim']}]Default[/{P['dim']}]"),
        ("", ""),
        (f"[{P['model']}]── MODEL[/{P['model']}]", ""),
        ("Name",          model["label"]),
        ("ID",            f"[{P['dim']}]{model['id']}[/{P['dim']}]"),
        ("Ctx window",    f"{ctx:,} tokens"),
        ("Max output",    f"{CFG.get('max_tokens'):,} tokens"),
        ("Temperature",   str(CFG.get("temperature"))),
        ("", ""),
        (f"[{P['mem']}]── TOKENS[/{P['mem']}]", ""),
        ("Session ctx",   f"~{sess:,}"),
        ("Ctx used",      f"{bar}  {pct}%"),
        ("Total in",      f"~{chat.token_in:,}"),
        ("Total out",     f"~{chat.token_out:,}"),
        ("Total",         f"~{chat.token_in+chat.token_out:,}"),
        ("Avg / call",    f"~{(chat.token_in+chat.token_out)//max(chat.api_calls,1):,}"),
        ("", ""),
        (f"[{P['code']}]── CODES[/{P['code']}]", ""),
        ("Files",         str(len(codes))),
        ("Folder",        str(chat.codes_dir)),
        ("", ""),
        (f"[{P['accent']}]── MEMORY[/{P['accent']}]", ""),
        ("Stored turns",  f"{len(chat.messages)//2} / {CFG.get('max_memory_turns')}"),
        ("Code theme",    CFG.get("code_theme")),
    ]
    for r in rows: g.add_row(*r)
    con.print(Panel(g, title=f"[{P['border']}]  Session Info  [/{P['border']}]",
                    border_style=P["border"], box=box.ROUNDED, padding=(1, 2)))
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  /search  (memory search)
# ═══════════════════════════════════════════════════════════════════════════════
def search_history(chat: Chat):
    query = con.input(f"  [{P['accent']}]Search memory: [/{P['accent']}]").strip()
    if not query: con.print(); return
    q    = query.lower()
    hits = [m for m in chat.messages
            if m.get("role") in ("user", "assistant") and q in m.get("content", "").lower()]
    if not hits:
        con.print(f"  [{P['dim']}]No results for '{escape(query)}'[/{P['dim']}]"); con.print(); return
    con.print(f"  [{P['ok']}]{len(hits)} result(s)[/{P['ok']}]"); con.print()
    for m in hits:
        role  = m["role"]
        hl    = re.sub(
            f"(?i)({re.escape(query)})",
            f"[bold {P['accent']}]\\1[/bold {P['accent']}]",
            escape(m["content"][:400]),
        )
        label = f"[{P['user']}] You [/{P['user']}]" if role == "user" else f"[{P['ai']}] AI [/{P['ai']}]"
        bc    = P["dim"] if role == "user" else P["border"]
        con.print(Panel(hl, title=label,
                        title_align="right" if role == "user" else "left",
                        border_style=bc, box=box.ROUNDED, padding=(0, 2)))
        con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  /export  /rename
# ═══════════════════════════════════════════════════════════════════════════════
def export_chat(chat: Chat):
    msgs = [m for m in chat.messages if m["role"] in ("user", "assistant")]
    if not msgs:
        con.print(f"  [{P['dim']}]Nothing to export[/{P['dim']}]"); con.print(); return
    lines = [f"# {chat.name}",
             f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  {chat.turns} turns*", ""]
    for m in msgs:
        role = "**You**" if m["role"] == "user" else "**AI**"
        lines += [f"### {role}", "", m["content"], ""]
    fname = chat.codes_dir.parent / f"{chat.safe_name}_export.md"
    fname.write_text("\n".join(lines), encoding="utf-8")
    con.print(f"  [{P['ok']}]✓  Exported →[/{P['ok']}] [bold]{fname}[/bold]"); con.print()

def rename_chat(chat: Chat):
    new = con.input(f"  [{P['chat']}]New name: [/{P['chat']}]").strip()
    if not new:
        con.print(f"  [{P['dim']}]Cancelled[/{P['dim']}]"); con.print(); return
    chat.name = new; chat.save()
    con.print(f"  [{P['ok']}]✓  Renamed → '{escape(new)}'[/{P['ok']}]"); con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGE BUILDER
# ═══════════════════════════════════════════════════════════════════════════════
_BASE_INST = (
    "Use markdown in replies: **bold**, *italic*, `code`, headers, lists. "
    "Always wrap code in fenced blocks with the correct language tag, "
    "e.g. ```python or ```javascript."
)

def build_system_content(chat: Chat, model: dict) -> str:
    base = (f"You are a highly capable AI assistant inside NVIDIA NIM, "
            f"powered by {model['label']}. Today is {_now()}.\n{_BASE_INST}")
    if chat.custom_system:
        return f"{chat.custom_system}\n\nPowered by {model['label']}. Today: {_now()}.\n{_BASE_INST}"
    return base

def build_api_messages(sys: str, history: list, model_id: str) -> list:
    no_sys = {"gemma", "falcon"}
    if any(k in model_id.lower() for k in no_sys):
        return [
            {"role": "user",      "content": f"[Instructions] {sys}"},
            {"role": "assistant", "content": "Understood."},
        ] + history
    return [{"role": "system", "content": sys}] + history

# ═══════════════════════════════════════════════════════════════════════════════
#  STREAMING PANEL
# ═══════════════════════════════════════════════════════════════════════════════
def _stream_panel(text: str, model_label: str) -> Panel:
    return Panel(
        Text(text, style=P["ai"]),
        title=f"[{P['ai']}]  {escape(model_label)}  ··· streaming[/{P['ai']}]",
        title_align="left",
        border_style=P["dim"],
        box=box.ROUNDED,
        padding=(1, 2),
    )

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER FORMATTED REPLY
#  Text   → Markdown printed directly (no wrapping panel — fixes overflow bug)
#  Code   → syntax-highlighted heavy panel + filename prompt + auto-save
#  Framed by two Rules top and bottom
# ═══════════════════════════════════════════════════════════════════════════════
def render_formatted_reply(reply: str, chat: Chat, model_label: str):
    segments = []
    cursor   = 0
    for m in CODE_FENCE.finditer(reply):
        s, e   = m.span()
        before = reply[cursor:s].strip()
        if before: segments.append(("text", before, ""))
        segments.append(("code", m.group("code"), m.group("lang").strip().lower() or "text"))
        cursor = e
    tail = reply[cursor:].strip()
    if tail: segments.append(("text", tail, ""))
    if not segments: return

    con.print(Rule(f"[{P['ai']}]  {escape(model_label)}  [/{P['ai']}]", style=P["border"]))
    con.print()

    for kind, content, lang in segments:
        if kind == "text":
            try:
                con.print(Markdown(content, code_theme=CFG.get("code_theme")))
            except Exception:
                con.print(Text(content, style=P["ai"]))
            con.print()
            continue

        # ── code block ─────────────────────────────────────────────────────
        ext       = LANG_EXT.get(lang, lang if lang else "txt")
        theme     = CFG.get("code_theme")
        skip_save = lang in NO_SAVE_LANGS and not CFG.get("save_shell_scripts")
        badge     = f"  {lang.upper() if lang else 'CODE'}  "
        sfx       = (f"  [{P['err']}]terminal · not saved[/{P['err']}]"
                     if skip_save else f"  [{P['dim']}].{ext}[/{P['dim']}]")

        con.print(Panel(
            Syntax(content, lang if lang else "text", theme=theme,
                   line_numbers=True, word_wrap=False, indent_guides=True,
                   background_color="default"),
            title=f"[bold black on {P['code']}]{badge}[/bold black on {P['code']}]{sfx}",
            title_align="left",
            border_style=P["code"], box=box.HEAVY, padding=(0, 1),
        ))

        if skip_save:
            con.print(); continue

        # ── filename prompt ────────────────────────────────────────────────
        if CFG.get("auto_name_code"):
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_name = f"{lang or 'code'}_{ts}"
        else:
            try:
                raw_name = con.input(
                    f"  [{P['accent']}]Save as[/{P['accent']}]"
                    f" [{P['dim']}](name · 0 skip · Enter auto): [/{P['dim']}]"
                ).strip()
            except Exception:
                raw_name = ""

        if raw_name == "0":
            con.print(f"  [{P['dim']}]Skipped[/{P['dim']}]"); con.print(); continue
        if not raw_name:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_name = f"{lang or 'code'}_{ts}"

        safe = re.sub(r"[^\w\-]", "_", raw_name)[:40]
        sp   = chat.codes_dir / f"{safe}.{ext}"
        n    = 1
        while sp.exists():
            sp = chat.codes_dir / f"{safe}_{n}.{ext}"; n += 1
        try:
            sp.write_text(content, encoding="utf-8")
            try:    rel = sp.relative_to(Path.cwd())
            except: rel = sp
            con.print(f"  [{P['ok']}]↓[/{P['ok']}]  [{P['saved']}]{rel}[/{P['saved']}]"
                      f"  [{P['dim']}]({len(content.splitlines())} lines)[/{P['dim']}]")
        except Exception as e:
            con.print(f"  [{P['err']}]Save failed: {escape(str(e))}[/{P['err']}]")
        con.print()

    con.print(Rule(style=P["dim"]))
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  STREAM → REPLACE
# ═══════════════════════════════════════════════════════════════════════════════
def stream_response(client: OpenAI, chat: Chat, model: dict, messages: list) -> str:
    def _attempt(msgs: list) -> tuple:
        buf = []; err = None
        with Live(
            _stream_panel("", model["label"]),
            console=con,
            refresh_per_second=CFG.get("stream_refresh"),
            vertical_overflow="ellipsis",
            transient=True,
        ) as live:
            try:
                stream = client.chat.completions.create(
                    model=model["id"], messages=msgs,
                    max_tokens=CFG.get("max_tokens"),
                    stream=True, temperature=CFG.get("temperature"),
                )
                for chunk in stream:
                    if not chunk.choices: continue
                    choice = chunk.choices[0]
                    if not choice.delta: continue
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
            time.sleep(2); reply, err = _attempt(messages)

    chat.record_usage(msgs_tokens(messages), est_tokens(reply))

    if not reply and err is not None:
        reply = f"Error: {err}"
        con.print(f"  [{P['err']}]{escape(reply)}[/{P['err']}]"); con.print(); return reply

    if CFG.get("show_tokens_per_reply"):
        con.print(f"  [{P['dim']}]~{est_tokens(reply)} tokens[/{P['dim']}]")

    con.print()
    render_formatted_reply(reply, chat, model["label"])
    return reply

# ═══════════════════════════════════════════════════════════════════════════════
#  HELP  &  HEADER
# ═══════════════════════════════════════════════════════════════════════════════
COMMANDS = {
    "/help"    : "Show commands",
    "/chat"    : "Switch · create · delete chats",
    "/model"   : "Switch AI model",
    "/system"  : "System prompt manager",
    "/settings": "Configuration options",
    "/memory"  : "View & delete conversation turns",
    "/search"  : "Search chat history",
    "/codes"   : "View · open · delete code files",
    "/export"  : "Export chat to Markdown",
    "/rename"  : "Rename current chat",
    "/info"    : "Session & token stats",
    "/forget"  : "Clear chat memory",
    "/clear"   : "Clear screen",
    "/exit"    : "Quit",
}

def show_help():
    t = Table(box=box.SIMPLE, border_style=P["dim"], show_header=False, padding=(0, 2))
    t.add_column("cmd",  style=f"bold {P['accent']}", width=12)
    t.add_column("desc", style=P["ai"])
    for cmd, desc in COMMANDS.items(): t.add_row(cmd, desc)
    con.print(Panel(t, title=f"[{P['border']}]  NIM Chat v{VERSION}  [/{P['border']}]",
                    border_style=P["border"], box=box.ROUNDED, padding=(0, 1)))
    con.print()

def _chat_header(chat: Chat, model: dict):
    sys_tag = f"  [{P['sys']}][SYS][/{P['sys']}]" if chat.custom_system else ""
    codes   = len(list(chat.codes_dir.glob("*")))
    if CFG.get("compact_header"):
        con.print(Rule(
            f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]"
            f"  [{P['dim']}]{model['label']}[/{P['dim']}]{sys_tag}",
            style=P["chat"],
        ))
    else:
        con.print(Panel(
            f"[{P['chat']}]{escape(chat.name)}[/{P['chat']}]{sys_tag}"
            f"  [{P['dim']}]·  [{P['model']}]{model['label']}[/{P['model']}]"
            f"  ·  {chat.turns} turns  ·  {codes} files  ·  /help[/{P['dim']}]",
            border_style=P["chat"], box=box.ROUNDED, padding=(0, 2),
        ))
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT LOOP
# ═══════════════════════════════════════════════════════════════════════════════
def chat_loop(client: OpenAI, model: dict, chat: Chat):
    session_start = time.time()
    turn          = 0
    _chat_header(chat, model)

    while True:
        try:
            user_input = get_input(chat.name, model["label"], turn,
                                   sys_active=bool(chat.custom_system))
        except KeyboardInterrupt:
            break
        if not user_input: continue

        cmd = user_input.lower().strip()
        if cmd == "/exit":     break
        if cmd == "/help":     show_help(); continue
        if cmd == "/clear":    con.clear(); continue
        if cmd == "/codes":    con.print(); show_codes(chat); continue
        if cmd == "/memory":   con.print(); show_memory(chat); continue
        if cmd == "/search":   con.print(); search_history(chat); continue
        if cmd == "/export":   con.print(); export_chat(chat); continue
        if cmd == "/rename":   con.print(); rename_chat(chat); _chat_header(chat, model); continue
        if cmd == "/info":     con.print(); show_info(chat, model, turn, session_start); continue
        if cmd == "/settings": con.print(); show_settings(); continue
        if cmd == "/forget":
            chat.messages.clear(); chat.save()
            con.print(f"  [{P['ok']}]✓  Memory cleared[/{P['ok']}]"); con.print(); continue
        if cmd == "/system":
            con.print(); manage_system_prompt(chat); _chat_header(chat, model); continue
        if cmd == "/chat":
            con.print(); chat = chat_manager(chat); _chat_header(chat, model); continue
        if cmd == "/model":
            con.print(); model = choose_model(current=model)
            con.print(); _chat_header(chat, model); continue

        # ── send ──────────────────────────────────────────────────────────
        turn += 1
        chat.add("user", user_input)

        con.print(Panel(
            f"[{P['user']}]{escape(user_input)}[/{P['user']}]",
            title=f"[{P['user']}] You [/{P['user']}]", title_align="right",
            border_style=P["dim"], box=box.ROUNDED, padding=(0, 2),
        ))
        con.print()

        sys_content = build_system_content(chat, model)
        msgs        = build_api_messages(sys_content, chat.messages, model["id"])
        reply       = stream_response(client, chat, model, msgs)
        chat.add("assistant", reply)
        con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  --list
# ═══════════════════════════════════════════════════════════════════════════════
def cmd_list_chats():
    chats = Chat.all_chats()
    if not chats:
        con.print(f"  [{P['dim']}]No chats found.[/{P['dim']}]"); return
    t = Table(box=box.SIMPLE_HEAD, border_style=P["chat"],
              header_style=f"bold {P['chat']}", show_lines=False, padding=(0, 2))
    t.add_column("#",      style="bold white", width=4)
    t.add_column("Name",   style=P["ai"],      min_width=22)
    t.add_column("Turns",  style=P["dim"],     width=7)
    t.add_column("Tokens", style=P["dim"],     width=10)
    t.add_column("SYS",    style=P["sys"],     width=5)
    t.add_column("Active", style=P["dim"],     width=14)
    for i, c in enumerate(chats, 1):
        t.add_row(str(i), escape(c.name), str(c.turns),
                  f"~{c.token_in+c.token_out:,}",
                  "●" if c.custom_system else "", c.last_active)
    con.print(Panel(t, title=f"[{P['chat']}]  All Chats  [/{P['chat']}]",
                    border_style=P["chat"], box=box.ROUNDED, padding=(0, 1)))
    con.print(f"  [{P['dim']}]Resume: [bold]python nim_chat.py --chat \"name\"[/bold]"
              f"  or  [bold]--chat N[/bold][/{P['dim']}]")
    con.print()

# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(prog="nim_chat.py")
    parser.add_argument("--chat", metavar="NAME_OR_N", help="Resume chat by name or index")
    parser.add_argument("--list", action="store_true",  help="List all chats and exit")
    args = parser.parse_args()

    if args.list:
        cmd_list_chats(); return

    splash()
    api_key = get_api_key()
    model   = choose_model()
    client  = OpenAI(api_key=api_key, base_url=NIM_BASE_URL)

    if not HAS_PT:
        con.print(f"  [{P['dim']}]Tip: pip install prompt_toolkit  for a styled input bar[/{P['dim']}]")
        con.print()

    if args.chat:
        found = Chat.find(args.chat)
        if found:
            con.print(f"  [{P['ok']}]✓[/{P['ok']}]  Resuming"
                      f" '[{P['chat']}]{escape(found.name)}[/{P['chat']}]'"
                      f"  [{P['dim']}]{found.turns} turns"
                      f" · ~{found.token_in+found.token_out:,} tokens[/{P['dim']}]")
            con.print()
            chat = found
        else:
            con.print(f"  [{P['warn']}]'{escape(args.chat)}' not found — creating new.[/{P['warn']}]")
            con.print()
            chat = Chat.create(args.chat)
    else:
        raw  = con.input(f"  [{P['chat']}]Chat name[/{P['chat']}]"
                         f" [{P['dim']}](Enter = 'New Chat'): [/{P['dim']}]").strip()
        chat = Chat.create(raw or "New Chat")
        con.print(f"  [{P['ok']}]✓[/{P['ok']}]"
                  f"  Started '[{P['chat']}]{escape(chat.name)}[/{P['chat']}]'")
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
