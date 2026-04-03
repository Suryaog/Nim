#!/usr/bin/env node
'use strict';
/**
 * NVIDIA NIM · Terminal AI Client · v7.2 (JavaScript Port)
 *   node nim_chat.js                 → new chat
 *   node nim_chat.js --chat NAME/N   → resume chat
 *   node nim_chat.js --list          → list all chats
 */

// ═══════════════════════════════════════════════════════════════════════════════
//  DEPENDENCY CHECK
// ═══════════════════════════════════════════════════════════════════════════════
const MISSING = [];
let OpenAI, chalk, boxen, Table, hljs, marked, TermRenderer, minimist;

try { ({ OpenAI } = require('openai')); }           catch { MISSING.push('openai'); }
try { chalk        = require('chalk'); }             catch { MISSING.push('chalk@4'); }
try { boxen        = require('boxen'); }             catch { MISSING.push('boxen@5'); }
try { Table        = require('cli-table3'); }        catch { MISSING.push('cli-table3'); }
try { ({ highlight: hljs } = require('cli-highlight')); } catch { MISSING.push('cli-highlight'); }
try { ({ marked }  = require('marked')); }           catch { MISSING.push('marked@4'); }
try { TermRenderer = require('marked-terminal'); }   catch { MISSING.push('marked-terminal'); }
try { minimist     = require('minimist'); }          catch { MISSING.push('minimist'); }

if (MISSING.length) {
  console.error(`\n[ SETUP ]  npm install ${MISSING.join(' ')}`);
  process.exit(1);
}

marked.setOptions({ renderer: new TermRenderer() });

const os        = require('os');
const fs        = require('fs');
const path      = require('path');
const readline  = require('readline');

// ═══════════════════════════════════════════════════════════════════════════════
//  PATHS & CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════
const BASE_DIR   = path.join(os.homedir(), '.nim_chat');
const CHATS_DIR  = path.join(BASE_DIR, 'chats');
const ENV_FILE   = path.join(BASE_DIR, '.env');
const SYS_FILE   = path.join(BASE_DIR, 'system_prompts.json');
const CFG_FILE   = path.join(BASE_DIR, 'settings.json');
const CODES_ROOT = path.join(process.cwd(), 'codes');

for (const d of [BASE_DIR, CHATS_DIR]) {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
}

const NIM_BASE_URL = 'https://integrate.api.nvidia.com/v1';
const VERSION      = '7.2';

const MODELS = [
  { id: 'meta/llama-3.1-70b-instruct',        label: 'Llama 3.1 70B',    ctx: 131072 },
  { id: 'qwen/qwen3-coder-480b-a35b-instruct', label: 'Qwen3 Coder 480B', ctx: 32768  },
];

const NO_SAVE_LANGS = new Set(['bash','shell','sh','zsh','fish','powershell','ps1','cmd','batch']);

const LANG_EXT = {
  python:'py',py:'py',javascript:'js',js:'js',typescript:'ts',ts:'ts',
  jsx:'jsx',tsx:'tsx',html:'html',css:'css',scss:'scss',sass:'sass',
  java:'java',kotlin:'kt',c:'c',cpp:'cpp','c++':'cpp',csharp:'cs',
  cs:'cs',rust:'rs',go:'go',ruby:'rb',rb:'rb',php:'php',
  swift:'swift',r:'r',sql:'sql',json:'json',yaml:'yaml',yml:'yaml',
  toml:'toml',xml:'xml',md:'md',markdown:'md',dockerfile:'dockerfile',
  makefile:'makefile',nginx:'conf',text:'txt',txt:'txt',lua:'lua',
  perl:'pl',scala:'scala',dart:'dart',vue:'vue',svelte:'svelte',
};

const CODE_FENCE = /```(?<lang>[a-zA-Z0-9+\-#._]*)\n(?<code>[\s\S]*?)```/g;

// ═══════════════════════════════════════════════════════════════════════════════
//  PALETTE
// ═══════════════════════════════════════════════════════════════════════════════
const P = {
  border: '#4fc3f7', ai:    '#80deea', user:  '#e0e0e0', dim:   '#455a64',
  accent: '#ffd54f', ok:    '#69f0ae', err:   '#ef5350', code:  '#a5d6a7',
  model:  '#ce93d8', saved: '#69f0ae', chat:  '#ffb74d', mem:   '#4dd0e1',
  sys:    '#f48fb1', warn:  '#ff8a65',
};

const c  = (col) => chalk.hex(col);
const cb = (col) => chalk.bold.hex(col);
const W  = () => process.stdout.columns || 80;

// ═══════════════════════════════════════════════════════════════════════════════
//  SETTINGS  (mirrors Python Settings class + SETTING_DEFS)
// ═══════════════════════════════════════════════════════════════════════════════
const SETTING_DEFS = {
  max_tokens:            ['Max output tokens',          'int',   2048,      [512,1024,2048,4096]],
  temperature:           ['Temperature',                'float', 0.7,       null],
  max_memory_turns:      ['Memory turns kept',          'int',   40,        [10,20,40,60,80]],
  stream_refresh:        ['Stream refresh rate (fps)',  'int',   6,         [4,6,8,12]],
  code_theme:            ['Code syntax theme',          'str',   'one-dark', ['one-dark','monokai','dracula','github-dark','solarized-dark']],
  auto_name_code:        ['Auto-name code files',       'bool',  false,     null],
  show_tokens_per_reply: ['Show token count per reply', 'bool',  true,      null],
  confirm_delete:        ['Confirm before deleting',    'bool',  true,      null],
  compact_header:        ['Compact chat header',        'bool',  false,     null],
  save_shell_scripts:    ['Save bash/shell blocks',     'bool',  false,     null],
};

class Settings {
  constructor() {
    this._data = {};
    this._load();
  }
  _load() {
    const base = {};
    for (const [k, v] of Object.entries(SETTING_DEFS)) base[k] = v[2];
    if (fs.existsSync(CFG_FILE)) {
      try {
        const stored = JSON.parse(fs.readFileSync(CFG_FILE, 'utf8'));
        for (const [k, v] of Object.entries(stored)) if (k in base) base[k] = v;
      } catch {}
    }
    this._data = base;
  }
  save() {
    try { fs.writeFileSync(CFG_FILE, JSON.stringify(this._data, null, 2)); } catch {}
  }
  get(key) { return this._data[key] ?? SETTING_DEFS[key][2]; }
  set(key, value) { this._data[key] = value; this.save(); }
  toggle(key) { this._data[key] = !this._data[key]; this.save(); return this._data[key]; }
}

const CFG = new Settings();

// ═══════════════════════════════════════════════════════════════════════════════
//  UTILS
// ═══════════════════════════════════════════════════════════════════════════════
const estTokens  = (text) => Math.max(1, Math.floor(text.length / 4));
const msgsTokens = (msgs) => msgs.reduce((s, m) => s + estTokens(m.content || ''), 0);
const safeName   = (text, n = 30) => (text.trim().replace(/[^\w\-]/g, '_') || 'chat').slice(0, n);
const nowStr     = () => new Date().toLocaleString('en-US', { weekday:'long', year:'numeric', month:'long', day:'numeric', hour:'2-digit', minute:'2-digit' });
const elapsed    = (s) => {
  s = Math.floor(s);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${s%60}s`;
  return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;
};

// ═══════════════════════════════════════════════════════════════════════════════
//  READLINE INTERFACE
// ═══════════════════════════════════════════════════════════════════════════════
const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });

let _exiting = false;
rl.on('SIGINT', () => { _exiting = true; rl.close(); process.stdout.write('\n'); });

const ask = (prompt) => new Promise((resolve) => {
  if (_exiting) return resolve('');
  rl.question(prompt, (a) => resolve((a || '').trim()));
});

const nl  = () => console.log('');
const log = (str = '') => console.log(str);

// ═══════════════════════════════════════════════════════════════════════════════
//  UI PRIMITIVES  (Panel, Rule, Table wrappers)
// ═══════════════════════════════════════════════════════════════════════════════
function panel(content, {
  title = '', titleAlign = 'left', borderColor = P.border,
  style = 'round', pad = [0, 2]
} = {}) {
  const opts = {
    borderColor,
    borderStyle: style,
    padding: { top: pad[0], bottom: pad[0], left: pad[1], right: pad[1] },
  };
  if (title) { opts.title = title; opts.titleAlignment = titleAlign; }
  return boxen(content, opts);
}

function rule(title = '', col = P.dim) {
  const w     = W();
  const line  = c(col)('─'.repeat(w));
  if (!title) { log(line); return; }
  const bare  = title.replace(/\x1b\[[0-9;]*m/g, '');
  const side  = Math.max(0, Math.floor((w - bare.length - 2) / 2));
  const left  = c(col)('─'.repeat(side));
  const right = c(col)('─'.repeat(Math.max(0, w - side - bare.length - 2)));
  log(`${left} ${title} ${right}`);
}

function makeTable(columns, { borderColor = P.dim, headerColor = P.border } = {}) {
  const chars = {
    'top':'─','top-mid':'┬','top-left':'┌','top-right':'┐',
    'bottom':'─','bottom-mid':'┴','bottom-left':'└','bottom-right':'┘',
    'left':'│','left-mid':'├','mid':'─','mid-mid':'┼',
    'right':'│','right-mid':'┤','middle':'│'
  };
  const heads  = columns.map(col => cb(headerColor)(col.label || col));
  const widths = columns.map(col => col.width || undefined);
  return new Table({
    head: heads,
    chars,
    style: { head: [], border: [], 'padding-left': 1, 'padding-right': 1 },
    colWidths: widths.every(w => w === undefined) ? undefined : widths,
  });
}

function gridRow(...items) {
  return items.join('  ');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  SPLASH
// ═══════════════════════════════════════════════════════════════════════════════
async function splash() {
  process.stdout.write('\x1b[2J\x1b[H'); // clear screen
  const chats = Chat.allChats();
  const total = chats.reduce((s, c) => s + c.tokenIn + c.tokenOut, 0);
  const art = [
    c(P.border)  ('███╗   ██╗██╗███╗   ███╗'),
    c('#4dd0e1') ('████╗  ██║██║████╗ ████║'),
    c(P.ai)      ('██╔██╗ ██║██║██╔████╔██║'),
    c(P.ok)      ('██║╚██╗██║██║██║╚██╔╝██║'),
    c(P.code)    ('██║ ╚████║██║██║ ╚═╝ ██║'),
    c(P.dim)     ('╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝'),
    '',
    chalk.bold.white(`NVIDIA NIM  ·  Terminal AI  ·  v${VERSION}`),
    c(P.dim)(`${chats.length} chats  ·  ~${total.toLocaleString()} tokens`),
  ].join('\n');
  log(panel(art, { borderColor: P.border, style: 'double', pad: [1, 6] }));
  nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  ENV / API KEY
// ═══════════════════════════════════════════════════════════════════════════════
function loadEnv() {
  if (fs.existsSync(ENV_FILE)) {
    require('dotenv').config({ path: ENV_FILE });
  } else {
    require('dotenv').config();
  }
}

function setEnvKey(file, key, value) {
  let content = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
  const regex = new RegExp(`^${key}=.*$`, 'm');
  const line  = `${key}=${value}`;
  content = regex.test(content) ? content.replace(regex, line) : content + (content.endsWith('\n') ? '' : '\n') + line + '\n';
  fs.writeFileSync(file, content);
}

async function getApiKey() {
  loadEnv();
  let key = process.env.NVIDIA_API_KEY || '';
  if (key) {
    try {
      const client = new OpenAI({ apiKey: key, baseURL: NIM_BASE_URL });
      await client.models.list();
      log(`  ${c(P.ok)('✓')}  ${c(P.dim)(`API connected · ${key.slice(0,8)}…${key.slice(-4)}`)}`);
    } catch (e) {
      log(`  ${c(P.warn)('!')}  ${c(P.dim)(String(e).slice(0, 80))}`);
    }
    nl(); return key;
  }
  log(`  ${c(P.err)('No NVIDIA API key found.')}`); nl();
  key        = await ask(`  ${c(P.accent)('API key:')} `);
  const save = await ask(`  ${c(P.dim)('Save? (y/n):')} `);
  if (['y','yes'].includes(save.toLowerCase())) {
    if (!fs.existsSync(ENV_FILE)) fs.writeFileSync(ENV_FILE, '');
    setEnvKey(ENV_FILE, 'NVIDIA_API_KEY', key);
    log(`  ${c(P.ok)('✓  Saved')}`);
  }
  nl(); return key;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MODEL PICKER
// ═══════════════════════════════════════════════════════════════════════════════
async function chooseModel(current = null) {
  const t = makeTable([
    { label: '#', width: 5 }, { label: 'Model', width: 26 }, { label: 'Ctx', width: 10 }
  ], { headerColor: P.model });
  for (let i = 0; i < MODELS.length; i++) {
    const m  = MODELS[i];
    const mk = (current && m.id === current.id) ? c(P.ok)('▶ ') : '  ';
    const ctx = typeof m.ctx === 'number' ? m.ctx.toLocaleString() : '?';
    t.push([`${mk}${i+1}`, c(P.ai)(m.label), c(P.model)(ctx)]);
  }
  log(panel(t.toString(), { title: cb(P.model)('  Choose Model  '), borderColor: P.model, style: 'round', pad: [0,1] }));
  while (true) {
    const raw = await ask(`  ${c(P.model)('Select')} ${c(P.dim)('(Enter=1):')} `) || '1';
    const idx = parseInt(raw) - 1;
    if (!isNaN(idx) && idx >= 0 && idx < MODELS.length) {
      const sel = MODELS[idx];
      log(`  ${c(P.ok)('✓  ' + sel.label)}`); nl();
      return sel;
    }
    log(`  ${c(P.err)('Invalid')}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  SYSTEM PROMPT PRESETS
// ═══════════════════════════════════════════════════════════════════════════════
function loadPresets() {
  if (fs.existsSync(SYS_FILE)) {
    try { return JSON.parse(fs.readFileSync(SYS_FILE, 'utf8')); } catch {}
  }
  return [];
}

function savePresets(presets) {
  fs.writeFileSync(SYS_FILE, JSON.stringify(presets, null, 2));
}

async function multilineInput(promptText) {
  log(`  ${c(P.sys)(promptText + '  (blank line to finish):')}`);
  const lines = [];
  while (true) {
    const line = await ask('  ');
    if (line === '' && lines.length > 0) break;
    lines.push(line);
  }
  return lines.join('\n').trim();
}

async function manageSystemPrompt(chat) {
  let presets = loadPresets();
  while (true) {
    const cur = chat.customSystem || '';
    if (cur) {
      log(panel(c(P.sys)(cur.slice(0, 300) + (cur.length > 300 ? '…' : '')),
        { title: cb(P.sys)('  Active System Prompt  '), borderColor: P.sys, style: 'round', pad: [0,2] }));
    } else {
      log(`  ${c(P.dim)('No custom prompt — using default.')}`);
    }
    nl();

    if (presets.length) {
      const t = makeTable([
        { label: '#', width: 4 }, { label: 'Name', width: 20 }, { label: 'Preview', width: 32 }
      ], { headerColor: P.sys });
      presets.forEach((p, i) => {
        const prev = p.prompt.slice(0, 50).replace(/\n/g,' ') + (p.prompt.length > 50 ? '…' : '');
        t.push([c('white')(i+1), c(P.ai)(p.name), c(P.dim)(prev)]);
      });
      log(panel(t.toString(), { title: cb(P.sys)('  Presets  '), borderColor: P.sys, style: 'round', pad: [0,1] }));
      nl();
    }

    const lines = [
      `${cb(P.accent)('n')}   Write new prompt for this chat`,
      `${cb(P.accent)('s')}   Write & save as preset`,
      ...(presets.length ? [
        `${cb(P.accent)('N')}   Apply preset N`,
        `${cb(P.accent)('-N')}  Delete preset N`,
      ] : []),
      `${cb(P.accent)('r')}   Reset / remove custom prompt`,
      `${cb(P.accent)('q')}   Back`,
    ];
    log(lines.join('\n')); nl();

    const raw = (await ask(`  ${c(P.sys)('Action:')} `)).toLowerCase().trim();
    nl();

    if (raw === 'q' || raw === '') break;
    if (raw === 'r') {
      chat.customSystem = ''; chat.save();
      log(`  ${c(P.ok)('✓  Cleared')}`); nl(); break;
    }
    if (raw === 'n') {
      const txt = await multilineInput('System prompt');
      if (txt) { chat.customSystem = txt; chat.save(); log(`  ${c(P.ok)('✓  Applied')}`); nl(); }
      break;
    }
    if (raw === 's') {
      const pname = await ask(`  ${c(P.sys)('Preset name:')} `);
      if (!pname) { log(`  ${c(P.err)('Name required')}`); nl(); continue; }
      const txt = await multilineInput('Prompt');
      if (txt) {
        presets.push({ name: pname, prompt: txt }); savePresets(presets);
        chat.customSystem = txt; chat.save();
        log(`  ${c(P.ok)('✓  Preset \'' + pname + '\' saved')}`); nl();
      }
      break;
    }
    if (raw.startsWith('-')) {
      const di = parseInt(raw.slice(1)) - 1;
      if (!isNaN(di) && di >= 0 && di < presets.length) {
        const gone = presets.splice(di, 1)[0]; savePresets(presets);
        log(`  ${c(P.ok)('✓  Deleted \'' + gone.name + '\'')}`); nl(); continue;
      }
      log(`  ${c(P.err)('Invalid')}`); nl(); continue;
    }
    const pi = parseInt(raw) - 1;
    if (!isNaN(pi) && pi >= 0 && pi < presets.length) {
      chat.customSystem = presets[pi].prompt; chat.save();
      log(`  ${c(P.ok)('✓  Applied \'' + presets[pi].name + '\'')}`); nl(); break;
    } else {
      log(`  ${c(P.err)('Invalid')}`); nl();
    }
  }
  return chat.customSystem;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /settings
// ═══════════════════════════════════════════════════════════════════════════════
async function showSettings() {
  const keys = Object.keys(SETTING_DEFS);
  while (true) {
    const t = makeTable([
      { label: '#', width: 4 }, { label: 'Setting', width: 28 },
      { label: 'Value', width: 14 }, { label: 'Options', width: 24 }
    ], { headerColor: P.accent });

    keys.forEach((k, i) => {
      const [label, typ, , choices] = SETTING_DEFS[k];
      const val = CFG.get(k);
      let vstr, opts;
      if (typ === 'bool') {
        vstr = val ? c(P.ok)('ON') : c(P.err)('OFF');
        opts = 'toggle';
      } else if (choices) {
        vstr = String(val); opts = choices.join(' / ');
      } else {
        vstr = String(val); opts = 'free value';
      }
      t.push([c('white')(i+1), c(P.ai)(label), vstr, c(P.dim)(opts)]);
    });

    log(panel(t.toString(), {
      title: cb(P.accent)('  Settings  ·  N to edit  ·  Enter exit  '),
      borderColor: P.accent, style: 'round', pad: [0,1]
    }));
    nl();

    const raw = await ask(`  ${c(P.accent)('Edit #')} ${c(P.dim)('(Enter exit):')} `);
    nl();
    if (!raw) break;

    const si = parseInt(raw) - 1;
    if (isNaN(si) || si < 0 || si >= keys.length) { log(`  ${c(P.err)('Invalid')}`); nl(); continue; }

    const k                        = keys[si];
    const [label, typ, , choices]  = SETTING_DEFS[k];
    const cur                      = CFG.get(k);

    if (typ === 'bool') {
      const nv = CFG.toggle(k);
      log(`  ${c(P.ok)('✓')}  ${label} → ${nv ? c(P.ok)('ON') : c(P.err)('OFF')}`); nl(); continue;
    }
    if (choices) {
      const ci  = choices.indexOf(cur);
      const nxt = choices[(ci + 1) % choices.length] ?? choices[0];
      CFG.set(k, nxt); log(`  ${c(P.ok)('✓')}  ${label} → ${chalk.bold(nxt)}`); nl(); continue;
    }
    const nv = await ask(`  ${c(P.accent)(label)} ${c(P.dim)('(current: ' + cur + '):')} `);
    if (!nv) { log(`  ${c(P.dim)('Unchanged')}`); nl(); continue; }
    try {
      if      (typ === 'int')   CFG.set(k, parseInt(nv));
      else if (typ === 'float') CFG.set(k, parseFloat(nv));
      else                      CFG.set(k, nv);
      log(`  ${c(P.ok)('✓  Saved')}`);
    } catch { log(`  ${c(P.err)('Invalid value for ' + typ)}`); }
    nl();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CHAT CLASS  (mirrors Python Chat class 1:1)
// ═══════════════════════════════════════════════════════════════════════════════
class Chat {
  constructor(filePath) {
    this.path = filePath;
    let d = {};
    if (fs.existsSync(filePath)) {
      try { d = JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch {}
    }
    this.name         = d.name          ?? 'Chat';
    this.created      = d.created       ?? new Date().toISOString();
    this.messages     = d.messages      ?? [];
    this.tokenIn      = d.token_in      ?? 0;
    this.tokenOut     = d.token_out     ?? 0;
    this.apiCalls     = d.api_calls     ?? 0;
    this.customSystem = d.custom_system ?? '';
  }

  get safeName() { return safeName(this.name); }

  get codesDir() {
    const d = path.join(CODES_ROOT, this.safeName);
    if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
    return d;
  }

  get turns() { return this.messages.filter(m => m.role === 'assistant').length; }

  get lastActive() {
    if (fs.existsSync(this.path)) {
      return new Date(fs.statSync(this.path).mtimeMs).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
    }
    return 'new';
  }

  save() {
    try {
      fs.writeFileSync(this.path, JSON.stringify({
        name: this.name, created: this.created, messages: this.messages,
        token_in: this.tokenIn, token_out: this.tokenOut,
        api_calls: this.apiCalls, custom_system: this.customSystem,
      }, null, 2));
    } catch {}
  }

  add(role, content) {
    this.messages.push({ role, content });
    const mt = CFG.get('max_memory_turns');
    if (this.messages.length > mt * 2) this.messages = this.messages.slice(-(mt * 2));
    this.save();
  }

  recordUsage(pi, ri) {
    this.tokenIn  += pi; this.tokenOut += ri; this.apiCalls += 1; this.save();
  }

  static create(name) {
    if (!fs.existsSync(CHATS_DIR)) fs.mkdirSync(CHATS_DIR, { recursive: true });
    const safe = safeName(name);
    const ts   = new Date().toISOString().replace(/[:.]/g,'').slice(0,15).replace('T','_');
    const p    = path.join(CHATS_DIR, `${ts}_${safe}.json`);
    const ch   = new Chat(p);
    ch.name    = name.trim() || 'New Chat';
    ch.created = new Date().toISOString();
    ch.save();
    return ch;
  }

  static allChats() {
    if (!fs.existsSync(CHATS_DIR)) return [];
    return fs.readdirSync(CHATS_DIR)
      .filter(f => f.endsWith('.json'))
      .map(f => path.join(CHATS_DIR, f))
      .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)
      .map(p => new Chat(p));
  }

  static find(query) {
    const chats = Chat.allChats();
    if (!chats.length) return null;
    const idx = parseInt(query) - 1;
    if (!isNaN(idx) && idx >= 0 && idx < chats.length) return chats[idx];
    const q = query.toLowerCase();
    return chats.find(ch => ch.name.toLowerCase().includes(q)) || null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /chat MANAGER
// ═══════════════════════════════════════════════════════════════════════════════
async function chatManager(current) {
  while (true) {
    const chats = Chat.allChats();
    const t     = makeTable([
      { label: '#', width: 6 }, { label: 'Name', width: 22 },
      { label: 'Turns', width: 7 }, { label: 'Tokens', width: 10 }, { label: 'Active', width: 14 }
    ], { headerColor: P.chat });
    chats.forEach((ch, i) => {
      const mk  = ch.path === current.path ? c(P.ok)('▶ ') : '  ';
      const dot = ch.customSystem ? c(P.sys)('● ') : '  ';
      t.push([`${mk}${i+1}`, `${dot}${c(P.ai)(ch.name)}`, c(P.dim)(ch.turns),
              c(P.dim)(`~${(ch.tokenIn+ch.tokenOut).toLocaleString()}`), c(P.dim)(ch.lastActive)]);
    });
    t.push([`  ${chats.length+1}`, cb(P.accent)('+ New chat'), '', '', '']);
    log(panel(t.toString(), { title: cb(P.chat)('  Chats  '), borderColor: P.chat, style: 'round', pad: [0,1] }));
    nl();

    const raw = await ask(`  ${c(P.chat)(`-N delete · N switch · ${chats.length+1} new · Enter cancel:`)} `);
    nl();
    if (!raw) return current;

    if (raw.startsWith('-')) {
      const di = parseInt(raw.slice(1)) - 1;
      if (!isNaN(di) && di >= 0 && di < chats.length) {
        const gone = chats[di];
        if (gone.path === current.path) { log(`  ${c(P.err)('Cannot delete active chat')}`); nl(); continue; }
        if (CFG.get('confirm_delete')) {
          const yn = (await ask(`  ${c(P.warn)('Delete \'' + gone.name + '\'? (y/n):')} `)).toLowerCase();
          if (!['y','yes'].includes(yn)) { log(`  ${c(P.dim)('Cancelled')}`); nl(); continue; }
        }
        fs.unlinkSync(gone.path);
        log(`  ${c(P.ok)('✓  Deleted \'' + gone.name + '\'')}`); nl(); continue;
      }
      log(`  ${c(P.err)('Invalid')}`); nl(); continue;
    }

    const idx = parseInt(raw) - 1;
    if (isNaN(idx)) { log(`  ${c(P.err)('Invalid')}`); nl(); continue; }

    if (idx === chats.length) {
      const name = (await ask(`  ${c(P.accent)('Chat name:')} `)) || `Chat ${chats.length+1}`;
      const neo  = Chat.create(name);
      log(`  ${c(P.ok)('✓  Created \'' + neo.name + '\'')}`); nl();
      return neo;
    }
    if (idx >= 0 && idx < chats.length) {
      const sel = chats[idx];
      log(`  ${c(P.ok)('✓')}  '${c(P.chat)(sel.name)}'  ${c(P.dim)(sel.turns + ' turns')}`); nl();
      return sel;
    }
    log(`  ${c(P.err)('Out of range')}`); nl();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /memory
// ═══════════════════════════════════════════════════════════════════════════════
async function showMemory(chat) {
  const msgs = chat.messages.filter(m => ['user','assistant'].includes(m.role));
  if (!msgs.length) { log(`  ${c(P.dim)('No memory yet.')}`); nl(); return; }

  const turns = [];
  let i = 0;
  while (i < msgs.length) {
    const u = msgs[i]?.role === 'user'      ? msgs[i]   : null;
    const a = msgs[i+1]?.role === 'assistant' ? msgs[i+1] : null;
    turns.push([u, a]);
    i += (u && a) ? 2 : 1;
  }

  log(panel(
    `${c(P.mem)(chat.name)}  ${c(P.dim)('· ' + turns.length + ' turns · ~' + msgsTokens(msgs).toLocaleString() + ' tokens')}`,
    { borderColor: P.mem, style: 'round', pad: [0,2] }
  ));
  nl();

  turns.forEach(([u, a], idx) => {
    rule(c(P.dim)(` Turn ${idx+1} `), P.dim);
    if (u) {
      const txt = u.content.slice(0, 300) + (u.content.length > 300 ? '…' : '');
      log(panel(c(P.user)(txt), { title: c(P.user)(' You '), titleAlign:'right', borderColor: P.dim, style:'round', pad:[0,2] }));
    }
    if (a) {
      const txt = a.content.slice(0, 400) + (a.content.length > 400 ? '…' : '');
      let content;
      try { content = marked(txt).trim(); } catch { content = c(P.ai)(txt); }
      log(panel(content, { title: c(P.ai)(' AI '), borderColor: P.border, style:'round', pad:[0,2] }));
    }
    nl();
  });

  while (true) {
    const raw = await ask(`  ${c(P.mem)('-N delete turn · Enter exit:')} `);
    if (!raw) break;
    if (raw.startsWith('-')) {
      const di = parseInt(raw.slice(1)) - 1;
      if (!isNaN(di) && di >= 0 && di < turns.length) {
        const [uDel, aDel] = turns[di];
        chat.messages = chat.messages.filter(m => m !== uDel && m !== aDel);
        chat.save(); log(`  ${c(P.ok)('✓  Turn ' + (di+1) + ' deleted')}`); nl(); break;
      }
      log(`  ${c(P.err)('Invalid turn')}`);
    } else {
      log(`  ${c(P.err)('Use -N to delete')}`);
    }
  }
  nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /codes
// ═══════════════════════════════════════════════════════════════════════════════
async function showCodes(chat) {
  while (true) {
    const dir   = chat.codesDir;
    const files = fs.existsSync(dir)
      ? fs.readdirSync(dir).map(f => path.join(dir, f))
          .filter(f => fs.statSync(f).isFile())
          .sort((a,b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)
      : [];

    if (!files.length) {
      log(`  ${c(P.dim)('No code files in ' + chalk.bold(dir))}`); nl(); return;
    }

    const t = makeTable([
      { label: '#', width: 4 }, { label: 'File', width: 30 }, { label: 'Ext', width: 7 },
      { label: 'Lines', width: 7 }, { label: 'Size', width: 8 }, { label: 'When', width: 14 }
    ], { headerColor: P.code });

    files.forEach((f, i) => {
      let lines = 0, size = '?';
      try { const txt = fs.readFileSync(f, 'utf8'); lines = txt.split('\n').length; size = txt.length + 'B'; } catch {}
      const mtime = new Date(fs.statSync(f).mtimeMs).toLocaleString('en-US',{ month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
      t.push([c('white')(i+1), c(P.saved)(path.basename(f)), c(P.accent)(path.extname(f).slice(1)),
              c(P.dim)(lines), c(P.dim)(size), c(P.dim)(mtime)]);
    });

    log(panel(t.toString(), { title: cb(P.code)(`  ${chat.name} · Code Files  `), borderColor: P.code, style:'round', pad:[0,1] }));
    nl();

    const raw = await ask(`  ${c(P.code)('N view · -N delete · Enter exit:')} `);
    nl();
    if (!raw) break;

    if (raw.startsWith('-')) {
      const di = parseInt(raw.slice(1)) - 1;
      if (!isNaN(di) && di >= 0 && di < files.length) {
        if (CFG.get('confirm_delete')) {
          const yn = (await ask(`  ${c(P.warn)('Delete ' + path.basename(files[di]) + '? (y/n):')} `)).toLowerCase();
          if (!['y','yes'].includes(yn)) { log(`  ${c(P.dim)('Cancelled')}`); nl(); continue; }
        }
        fs.unlinkSync(files[di]);
        log(`  ${c(P.ok)('✓  Deleted ' + path.basename(files[di]))}`); nl(); continue;
      }
      log(`  ${c(P.err)('Invalid')}`); nl(); continue;
    }

    const vi = parseInt(raw) - 1;
    if (!isNaN(vi) && vi >= 0 && vi < files.length) {
      const f    = files[vi];
      const lang = path.extname(f).slice(1);
      try {
        const code = fs.readFileSync(f, 'utf8');
        const hl   = renderCodeBlock(code, lang);
        log(panel(hl, {
          title: `${chalk.bold.black.bgHex(P.code)('  ' + path.basename(f) + '  ')}`,
          titleAlign: 'left', borderColor: P.code, style:'bold', pad:[0,1]
        }));
        nl();
      } catch (e) { log(`  ${c(P.err)(e.message)}`); nl(); }
    } else {
      log(`  ${c(P.err)('N to view, -N to delete')}`); nl();
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /info
// ═══════════════════════════════════════════════════════════════════════════════
function showInfo(chat, model, turn, sessionStart) {
  const codes   = fs.existsSync(chat.codesDir) ? fs.readdirSync(chat.codesDir).length : 0;
  const sess    = msgsTokens(chat.messages);
  const ctx     = model.ctx || 32768;
  const pct     = Math.min(100, Math.floor(sess / ctx * 100));
  const el      = elapsed((Date.now() - sessionStart) / 1000);
  const bw      = 28;
  const filled  = Math.floor(bw * pct / 100);
  const bc      = pct < 60 ? P.ok : (pct < 85 ? P.warn : P.err);
  const bar     = c(bc)('█'.repeat(filled)) + c(P.dim)('░'.repeat(bw - filled));
  const total   = chat.tokenIn + chat.tokenOut;

  const rows = [
    [c(P.chat)('── CHAT'), ''],
    [c(P.dim)('Name'),         chat.name],
    [c(P.dim)('Created'),      chat.created.slice(0,16).replace('T','  ')],
    [c(P.dim)('Session time'), el],
    [c(P.dim)('Turns total'),  String(chat.turns)],
    [c(P.dim)('Turns now'),    String(turn)],
    [c(P.dim)('API calls'),    String(chat.apiCalls)],
    [c(P.dim)('System prompt'),chat.customSystem ? c(P.sys)('Active') : c(P.dim)('Default')],
    ['',''],
    [c(P.model)('── MODEL'), ''],
    [c(P.dim)('Name'),         model.label],
    [c(P.dim)('ID'),           c(P.dim)(model.id)],
    [c(P.dim)('Ctx window'),   ctx.toLocaleString() + ' tokens'],
    [c(P.dim)('Max output'),   CFG.get('max_tokens').toLocaleString() + ' tokens'],
    [c(P.dim)('Temperature'),  String(CFG.get('temperature'))],
    ['',''],
    [c(P.mem)('── TOKENS'), ''],
    [c(P.dim)('Session ctx'),  '~' + sess.toLocaleString()],
    [c(P.dim)('Ctx used'),     `${bar}  ${pct}%`],
    [c(P.dim)('Total in'),     '~' + chat.tokenIn.toLocaleString()],
    [c(P.dim)('Total out'),    '~' + chat.tokenOut.toLocaleString()],
    [c(P.dim)('Total'),        '~' + total.toLocaleString()],
    [c(P.dim)('Avg / call'),   '~' + Math.floor(total / Math.max(chat.apiCalls, 1)).toLocaleString()],
    ['',''],
    [c(P.code)('── CODES'), ''],
    [c(P.dim)('Files'),        String(codes)],
    [c(P.dim)('Folder'),       chat.codesDir],
    ['',''],
    [c(P.accent)('── MEMORY'), ''],
    [c(P.dim)('Stored turns'), `${Math.floor(chat.messages.length/2)} / ${CFG.get('max_memory_turns')}`],
    [c(P.dim)('Code theme'),   CFG.get('code_theme')],
  ];

  const maxLeft = Math.max(...rows.map(r => r[0].replace(/\x1b\[[0-9;]*m/g,'').length));
  const content = rows.map(([l, r]) => {
    const bare = l.replace(/\x1b\[[0-9;]*m/g,'');
    return `${l}${' '.repeat(Math.max(0, maxLeft - bare.length + 4))}${chalk.bold.white(r)}`;
  }).join('\n');

  log(panel(content, { title: cb(P.border)('  Session Info  '), borderColor: P.border, style:'round', pad:[1,2] }));
  nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /search  (memory)
// ═══════════════════════════════════════════════════════════════════════════════
async function searchHistory(chat) {
  const query = await ask(`  ${c(P.accent)('Search memory:')} `);
  if (!query) { nl(); return; }
  const q    = query.toLowerCase();
  const hits = chat.messages.filter(m => ['user','assistant'].includes(m.role) && m.content.toLowerCase().includes(q));
  if (!hits.length) { log(`  ${c(P.dim)('No results for \'' + query + '\'')}`); nl(); return; }
  log(`  ${c(P.ok)(hits.length + ' result(s)')}`); nl();
  hits.forEach(m => {
    const hl    = m.content.slice(0, 400).replace(new RegExp(`(${query})`, 'gi'), chalk.bold.hex(P.accent)('$1'));
    const label = m.role === 'user' ? c(P.user)(' You ') : c(P.ai)(' AI ');
    const bc    = m.role === 'user' ? P.dim : P.border;
    const align = m.role === 'user' ? 'right' : 'left';
    log(panel(hl, { title: label, titleAlign: align, borderColor: bc, style:'round', pad:[0,2] })); nl();
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
//  /export  /rename
// ═══════════════════════════════════════════════════════════════════════════════
async function exportChat(chat) {
  const msgs = chat.messages.filter(m => ['user','assistant'].includes(m.role));
  if (!msgs.length) { log(`  ${c(P.dim)('Nothing to export')}`); nl(); return; }
  const lines = [
    `# ${chat.name}`,
    `*${new Date().toLocaleString()}  ·  ${chat.turns} turns*`, '',
  ];
  msgs.forEach(m => {
    lines.push(`### ${m.role === 'user' ? '**You**' : '**AI**'}`, '', m.content, '');
  });
  const fname = path.join(path.dirname(chat.codesDir), `${chat.safeName}_export.md`);
  fs.writeFileSync(fname, lines.join('\n'), 'utf8');
  log(`  ${c(P.ok)('✓  Exported →')} ${chalk.bold(fname)}`); nl();
}

async function renameChat(chat) {
  const neo = await ask(`  ${c(P.chat)('New name:')} `);
  if (!neo) { log(`  ${c(P.dim)('Cancelled')}`); nl(); return; }
  chat.name = neo; chat.save();
  log(`  ${c(P.ok)('✓  Renamed → \'' + neo + '\'')}`); nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MESSAGE BUILDER
// ═══════════════════════════════════════════════════════════════════════════════
const BASE_INST = (
  'Use markdown in replies: **bold**, *italic*, `code`, headers, lists. ' +
  'Always wrap code in fenced blocks with the correct language tag, ' +
  'e.g. ```python or ```javascript.'
);

function buildSystemContent(chat, model) {
  const base = `You are a highly capable AI assistant inside NVIDIA NIM, powered by ${model.label}. Today is ${nowStr()}.\n${BASE_INST}`;
  if (chat.customSystem) return `${chat.customSystem}\n\nPowered by ${model.label}. Today: ${nowStr()}.\n${BASE_INST}`;
  return base;
}

function buildApiMessages(sysContent, history, modelId) {
  const noSys = ['gemma','falcon'];
  if (noSys.some(k => modelId.toLowerCase().includes(k))) {
    return [
      { role: 'user',      content: `[Instructions] ${sysContent}` },
      { role: 'assistant', content: 'Understood.' },
      ...history,
    ];
  }
  return [{ role: 'system', content: sysContent }, ...history];
}

// ═══════════════════════════════════════════════════════════════════════════════
//  LIVE STREAMING PANEL  (transient — disappears when done)
// ═══════════════════════════════════════════════════════════════════════════════
class LivePanel {
  constructor() { this._lineCount = 0; }

  _render(text, modelLabel) {
    const w = Math.min(W() - 4, 120);
    return boxen(c(P.ai)(text || ' '), {
      title:          c(P.ai)(` ${modelLabel} ··· streaming`),
      titleAlignment: 'left',
      borderColor:    P.dim,
      borderStyle:    'round',
      padding:        { top: 1, right: 2, bottom: 1, left: 2 },
      width:          w,
    });
  }

  update(text, modelLabel) {
    const rendered = this._render(text, modelLabel);
    if (this._lineCount > 0) {
      process.stdout.write(`\x1b[${this._lineCount}A\x1b[0J`);
    }
    process.stdout.write(rendered + '\n');
    this._lineCount = rendered.split('\n').length + 1;
  }

  clear() {
    if (this._lineCount > 0) {
      process.stdout.write(`\x1b[${this._lineCount}A\x1b[0J`);
      this._lineCount = 0;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CODE BLOCK RENDERING  (syntax highlight + line numbers)
// ═══════════════════════════════════════════════════════════════════════════════
function renderCodeBlock(code, lang) {
  let highlighted;
  try {
    highlighted = hljs(code, { language: lang || 'text', ignoreIllegals: true });
  } catch { highlighted = code; }

  const lines  = highlighted.split('\n');
  const padW   = String(lines.length).length;
  return lines.map((line, i) => `${c(P.dim)(String(i+1).padStart(padW))}  ${line}`).join('\n');
}

// ═══════════════════════════════════════════════════════════════════════════════
//  RENDER FORMATTED REPLY
//  Text   → Markdown rendered directly
//  Code   → syntax-highlighted heavy panel + filename prompt + save
//  Framed by two Rules (mirrors Python render_formatted_reply exactly)
// ═══════════════════════════════════════════════════════════════════════════════
async function renderFormattedReply(reply, chat, modelLabel) {
  const segments = [];
  let cursor = 0;
  const regex = new RegExp(CODE_FENCE.source, 'gs');
  let m;
  while ((m = regex.exec(reply)) !== null) {
    const before = reply.slice(cursor, m.index).trim();
    if (before) segments.push({ kind:'text', content: before, lang:'' });
    segments.push({ kind:'code', content: m.groups.code, lang: (m.groups.lang || 'text').toLowerCase().trim() });
    cursor = m.index + m[0].length;
  }
  const tail = reply.slice(cursor).trim();
  if (tail) segments.push({ kind:'text', content: tail, lang:'' });
  if (!segments.length) return;

  rule(c(P.ai)(`  ${modelLabel}  `), P.border);
  nl();

  for (const seg of segments) {
    if (seg.kind === 'text') {
      try { log(marked(seg.content).trim()); }
      catch { log(c(P.ai)(seg.content)); }
      nl();
      continue;
    }

    // code block
    const lang      = seg.lang;
    const ext       = LANG_EXT[lang] || (lang || 'txt');
    const skipSave  = NO_SAVE_LANGS.has(lang) && !CFG.get('save_shell_scripts');
    const badge     = `  ${(lang || 'CODE').toUpperCase()}  `;
    const badgeStr  = chalk.bold.black.bgHex(P.code)(badge);
    const sfxStr    = skipSave ? `  ${c(P.err)('terminal · not saved')}` : `  ${c(P.dim)('.' + ext)}`;

    const hl = renderCodeBlock(seg.content, lang);
    log(panel(hl, {
      title:     `${badgeStr}${sfxStr}`,
      titleAlign:'left',
      borderColor: P.code,
      style:     'bold',
      pad:       [0, 1],
    }));

    if (skipSave) { nl(); continue; }

    let rawName;
    if (CFG.get('auto_name_code')) {
      const ts = new Date().toISOString().replace(/[:.]/g,'').slice(0,15).replace('T','_');
      rawName  = `${lang || 'code'}_${ts}`;
    } else {
      rawName = await ask(`  ${c(P.accent)('Save as')} ${c(P.dim)('(name · 0 skip · Enter auto):')} `);
    }

    if (rawName === '0') { log(`  ${c(P.dim)('Skipped')}`); nl(); continue; }
    if (!rawName) {
      const ts = new Date().toISOString().replace(/[:.]/g,'').slice(0,15).replace('T','_');
      rawName  = `${lang || 'code'}_${ts}`;
    }

    const safe = rawName.replace(/[^\w\-]/g,'_').slice(0, 40);
    let sp     = path.join(chat.codesDir, `${safe}.${ext}`);
    let n      = 1;
    while (fs.existsSync(sp)) { sp = path.join(chat.codesDir, `${safe}_${n}.${ext}`); n++; }

    try {
      fs.writeFileSync(sp, seg.content, 'utf8');
      const rel = path.relative(process.cwd(), sp);
      const lc  = seg.content.split('\n').length;
      log(`  ${c(P.ok)('↓')}  ${c(P.saved)(rel)}  ${c(P.dim)('(' + lc + ' lines)')}`);
    } catch (e) {
      log(`  ${c(P.err)('Save failed: ' + e.message)}`);
    }
    nl();
  }

  rule('', P.dim); nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  STREAM RESPONSE  (with retry logic — mirrors Python stream_response)
// ═══════════════════════════════════════════════════════════════════════════════
async function streamResponse(client, chat, model, messages) {
  const live = new LivePanel();

  async function attempt(msgs) {
    const buf = [];
    let   err = null;
    try {
      const stream = await client.chat.completions.create({
        model:       model.id,
        messages:    msgs,
        max_tokens:  CFG.get('max_tokens'),
        temperature: CFG.get('temperature'),
        stream:      true,
      });
      for await (const chunk of stream) {
        if (!chunk.choices?.length)    continue;
        const choice = chunk.choices[0];
        if (!choice.delta)             continue;
        const delta = choice.delta.content || '';
        if (delta) {
          buf.push(delta);
          live.update(buf.join(''), model.label);
        }
      }
    } catch (e) { err = e; }
    live.clear();  // transient — remove streaming panel
    return [buf.join(''), err];
  }

  let [reply, err] = await attempt(messages);

  if (err) {
    const s = err.message?.toLowerCase() || '';
    if (s.includes('system') && (s.includes('support') || s.includes('not allowed'))) {
      log(`  ${c(P.dim)('Retrying without system role…')}`);
      [reply, err] = await attempt(messages.filter(m => m.role !== 'system'));
    }
    if (err && !reply) {
      log(`  ${c(P.dim)('Retrying in 2 s…')}`);
      await new Promise(r => setTimeout(r, 2000));
      [reply, err] = await attempt(messages);
    }
  }

  chat.recordUsage(msgsTokens(messages), estTokens(reply));

  if (!reply && err) {
    reply = `Error: ${err.message || err}`;
    log(`  ${c(P.err)(reply)}`); nl(); return reply;
  }

  if (CFG.get('show_tokens_per_reply')) {
    log(`  ${c(P.dim)('~' + estTokens(reply) + ' tokens')}`);
  }

  nl();
  await renderFormattedReply(reply, chat, model.label);
  return reply;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  HELP  &  CHAT HEADER
// ═══════════════════════════════════════════════════════════════════════════════
const COMMANDS = {
  '/help'    : 'Show commands',
  '/chat'    : 'Switch · create · delete chats',
  '/model'   : 'Switch AI model',
  '/system'  : 'System prompt manager',
  '/settings': 'Configuration options',
  '/memory'  : 'View & delete conversation turns',
  '/search'  : 'Search chat history',
  '/codes'   : 'View · open · delete code files',
  '/export'  : 'Export chat to Markdown',
  '/rename'  : 'Rename current chat',
  '/info'    : 'Session & token stats',
  '/forget'  : 'Clear chat memory',
  '/clear'   : 'Clear screen',
  '/exit'    : 'Quit',
};

function showHelp() {
  const t = makeTable([{ label: 'Command', width: 12 }, { label: 'Description', width: 36 }]);
  for (const [cmd, desc] of Object.entries(COMMANDS)) {
    t.push([cb(P.accent)(cmd), c(P.ai)(desc)]);
  }
  log(panel(t.toString(), { title: cb(P.border)(`  NIM Chat v${VERSION}  `), borderColor: P.border, style:'round', pad:[0,1] }));
  nl();
}

function chatHeader(chat, model) {
  const sysTag = chat.customSystem ? `  ${c(P.sys)('[SYS]')}` : '';
  const codes  = fs.existsSync(chat.codesDir) ? fs.readdirSync(chat.codesDir).length : 0;
  if (CFG.get('compact_header')) {
    rule(`${c(P.chat)(chat.name)}  ${c(P.dim)(model.label)}${sysTag}`, P.chat);
  } else {
    log(panel(
      `${c(P.chat)(chat.name)}${sysTag}  ${c(P.dim)('·  ')}${c(P.model)(model.label)}${c(P.dim)(`  ·  ${chat.turns} turns  ·  ${codes} files  ·  /help`)}`,
      { borderColor: P.chat, style:'round', pad:[0,2] }
    ));
  }
  nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  INPUT  (prompt-toolkit equivalent — styled prompt)
// ═══════════════════════════════════════════════════════════════════════════════
async function getInput(chatName, modelLabel, turn, sysActive = false) {
  const sysTag = sysActive ? '  [SYS]' : '';
  // Write a styled status line above the prompt (simulates bottom toolbar)
  process.stdout.write(c(P.dim)(`  ${chatName}  ·  ${modelLabel}  ·  turn ${turn}${sysTag}  ·  /help\n`));
  const ans = await ask(c(P.border)('  ❯  '));
  // Clear the status line
  process.stdout.write(`\x1b[2A\x1b[0J`);
  return ans;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CHAT LOOP
// ═══════════════════════════════════════════════════════════════════════════════
async function chatLoop(client, model, chat) {
  const sessionStart = Date.now();
  let   turn         = 0;
  chatHeader(chat, model);

  while (!_exiting) {
    let userInput;
    try {
      userInput = await getInput(chat.name, model.label, turn, !!chat.customSystem);
    } catch { break; }
    if (_exiting) break;
    if (!userInput) continue;

    const cmd = userInput.toLowerCase().trim();
    if (cmd === '/exit')    { break; }
    if (cmd === '/help')    { showHelp(); continue; }
    if (cmd === '/clear')   { process.stdout.write('\x1b[2J\x1b[H'); continue; }
    if (cmd === '/codes')   { nl(); await showCodes(chat); continue; }
    if (cmd === '/memory')  { nl(); await showMemory(chat); continue; }
    if (cmd === '/search')  { nl(); await searchHistory(chat); continue; }
    if (cmd === '/export')  { nl(); await exportChat(chat); continue; }
    if (cmd === '/rename')  { nl(); await renameChat(chat); chatHeader(chat, model); continue; }
    if (cmd === '/info')    { nl(); showInfo(chat, model, turn, sessionStart); continue; }
    if (cmd === '/settings'){ nl(); await showSettings(); continue; }
    if (cmd === '/forget')  {
      chat.messages = []; chat.save();
      log(`  ${c(P.ok)('✓  Memory cleared')}`); nl(); continue;
    }
    if (cmd === '/system') {
      nl(); await manageSystemPrompt(chat); chatHeader(chat, model); continue;
    }
    if (cmd === '/chat') {
      nl(); chat = await chatManager(chat); chatHeader(chat, model); continue;
    }
    if (cmd === '/model') {
      nl(); model = await chooseModel(model); nl(); chatHeader(chat, model); continue;
    }

    // ── send ────────────────────────────────────────────────────────────────
    turn++;
    chat.add('user', userInput);

    log(panel(c(P.user)(userInput), {
      title: c(P.user)(' You '), titleAlign:'right',
      borderColor: P.dim, style:'round', pad:[0,2]
    }));
    nl();

    const sysContent = buildSystemContent(chat, model);
    const msgs       = buildApiMessages(sysContent, chat.messages, model.id);
    const reply      = await streamResponse(client, chat, model, msgs);
    chat.add('assistant', reply);
    nl();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
//  --list
// ═══════════════════════════════════════════════════════════════════════════════
function cmdListChats() {
  const chats = Chat.allChats();
  if (!chats.length) { log(`  ${c(P.dim)('No chats found.')}`); return; }
  const t = makeTable([
    { label:'#',width:4 },{ label:'Name',width:24 },{ label:'Turns',width:7 },
    { label:'Tokens',width:10 },{ label:'SYS',width:5 },{ label:'Active',width:14 }
  ], { headerColor: P.chat });
  chats.forEach((ch, i) => {
    t.push([c('white')(i+1), c(P.ai)(ch.name), c(P.dim)(ch.turns),
            c(P.dim)(`~${(ch.tokenIn+ch.tokenOut).toLocaleString()}`),
            ch.customSystem ? c(P.sys)('●') : '', c(P.dim)(ch.lastActive)]);
  });
  log(panel(t.toString(), { title: cb(P.chat)('  All Chats  '), borderColor: P.chat, style:'round', pad:[0,1] }));
  log(`  ${c(P.dim)('Resume: ')}${chalk.bold('node nim_chat.js --chat "name"')}${c(P.dim)('  or  ')}${chalk.bold('--chat N')}`);
  nl();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MAIN
// ═══════════════════════════════════════════════════════════════════════════════
async function main() {
  const args = minimist(process.argv.slice(2), { string:['chat'], boolean:['list'] });

  if (args.list) { cmdListChats(); rl.close(); return; }

  await splash();
  const apiKey = await getApiKey();
  const model  = await chooseModel();
  const client = new OpenAI({ apiKey, baseURL: NIM_BASE_URL });

  let chat;
  if (args.chat) {
    const found = Chat.find(args.chat);
    if (found) {
      log(`  ${c(P.ok)('✓')}  Resuming '${c(P.chat)(found.name)}'  ${c(P.dim)(found.turns + ' turns · ~' + (found.tokenIn+found.tokenOut).toLocaleString() + ' tokens')}`);
      nl(); chat = found;
    } else {
      log(`  ${c(P.warn)('\'' + args.chat + '\' not found — creating new.')}`); nl();
      chat = Chat.create(args.chat);
    }
  } else {
    const raw = await ask(`  ${c(P.chat)('Chat name')} ${c(P.dim)('(Enter = \'New Chat\'):')} `);
    chat      = Chat.create(raw || 'New Chat');
    log(`  ${c(P.ok)('✓')}  Started '${c(P.chat)(chat.name)}'`); nl();
  }

  try { await chatLoop(client, model, chat); } catch {}

  nl();
  const codes = fs.existsSync(chat.codesDir) ? fs.readdirSync(chat.codesDir).length : 0;
  log(panel(
    `${c(P.dim)(chat.name + '  ·  ' + chat.turns + ' turns  ·  ')}${c(P.code)(codes + ' code files')}${c(P.dim)('  ·  ~' + (chat.tokenIn+chat.tokenOut).toLocaleString() + ' tokens  ·  Goodbye 👋')}`,
    { borderColor: P.border, style:'double', pad:[0,2] }
  ));
  nl();
  rl.close();
}

main().catch(e => { console.error(e); rl.close(); process.exit(1); });
