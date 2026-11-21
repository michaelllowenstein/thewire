# TheWire — BuildFromScratch Runbook

**Version:** v0.1 (with local dashboard proxy fix)  
**Target:** Linux, macOS, WSL2; Python 3.12+, Node.js 20+  
**Purpose:** Recreate TheWire one source file at a time and understand every boundary.

This document is derived from the inspected TheWire v0.1 source files. The original release lacked `web/vite.config.ts`; this edition includes a development proxy that connects the React dashboard to the FastAPI API. No official Toptal integration is present.

## 1. Architecture

```text
Terminal + zsh                           Browser
     |                                      |
     v                                      v
  tw CLI                              React + Vite :5173
     |                                      |
     v                                /api proxy (GET)
 thewire/core.py                            |
     |                                      v
     +------------------------------> FastAPI :8765
     |                                      |
     +------------+-------------------------+
                  v
            SQLite database
             /         \
    project/timer     worklogs
     and audit        and tools
                  |
            plugin manifests
                  |
          trusted subprocess CLI
```

The application has four primary boundaries. `thewire/__main__.py` parses commands; `thewire/core.py` is the single shared domain/data layer; `api/main.py` projects read-only HTTP views; `web/src/main.tsx` renders those views. JSON tool manifests are registration records, not installed packages. Python executes tools directly with `subprocess.run`, without a shell.

**Database:** `projects`, `sessions`, `worklogs`, and `executions`. UTC timestamps; one unfinished timer across all projects is enforced by a SQLite partial unique index. Only completed sessions count toward reported hours. `THEWIRE_HOME` controls the database and manifest directory, and must be set before launching the CLI or API. The original MVP has no migrations, user authentication, Toptal submission, remote execution, or role-based client isolation.

## 2. Start from an empty repository

Verify tools:

```bash
python3 --version
node --version
npm --version
git --version
```

Expected: Python >=3.12 and Node >=20. If Python cannot create a virtual environment on Debian/Ubuntu/WSL, install the matching `python3-venv` package.

```bash
mkdir -p "$HOME/develop/workspaces/thewire"
cd "$HOME/develop/workspaces/thewire"
mkdir -p thewire api tests plugins scripts docs web/src
export THEWIRE_HOME="$PWD/.demo-data"
mkdir -p "$THEWIRE_HOME"
```

The disposable `.demo-data` path prevents practice time entries from mixing with actual client records. For regular usage, omit the override and use `~/.local/share/thewire`.

## 3. BuildFromScratch — recreate the implementation

For each file below, first read its purpose, then create the file at the listed relative path using the exact contents of its fenced code block. A practical way to learn is to write each file manually and review the next dependency before proceeding. The code follows the source archive without functional refactoring, except the new Vite proxy.

### `pyproject.toml`

**Why this exists:** Package metadata and executable entry point `tw = thewire.__main__:main`. Optional `web` and `test` dependencies.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "thewire"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []
[project.optional-dependencies]
web = ["fastapi>=0.115,<1", "uvicorn>=0.30,<1"]
test = ["pytest>=8,<10", "httpx>=0.27,<1"]
[project.scripts]
tw = "thewire.__main__:main"
[tool.setuptools.packages.find]
include = ["thewire*", "api*"]
```

### `thewire/__init__.py`

**Why this exists:** Package marker and version constant.

```python
__version__='0.1.0'
```

### `thewire/core.py`

**Why this exists:** Domain services, schema initialization, manifest registration, subprocess runner and time report.

```python
import json, os, sqlite3, subprocess, shutil
from datetime import datetime, timezone
from pathlib import Path

HOME=Path(os.environ.get('THEWIRE_HOME',str(Path.home()/'.local/share/thewire')))
MANIFESTS=HOME/'plugins'
def now(): return datetime.now(timezone.utc).isoformat()
def db():
    HOME.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(HOME/'thewire.db'); c.row_factory=sqlite3.Row
    c.executescript('''CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,client TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,project TEXT NOT NULL,task TEXT NOT NULL,start TEXT NOT NULL,end TEXT,notes TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS one_active_session ON sessions((1)) WHERE end IS NULL;
CREATE TABLE IF NOT EXISTS worklogs(id INTEGER PRIMARY KEY,project TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions(id INTEGER PRIMARY KEY,tool TEXT NOT NULL,command TEXT NOT NULL,exit_code INTEGER,created TEXT NOT NULL);''')
    return c

def manifests():
    MANIFESTS.mkdir(parents=True,exist_ok=True)
    out={}
    for p in sorted(MANIFESTS.glob('*.json')):
        m=json.loads(p.read_text()); out[m['name']]=m
    return out

def register(path):
    m=json.loads(Path(path).read_text())
    if not isinstance(m.get('name'),str) or not m['name'].replace('-','').replace('_','').isalnum(): raise ValueError('Invalid plugin name')
    if not isinstance(m.get('executable'),str) or not m['executable']: raise ValueError('Missing executable')
    if not isinstance(m.get('fixed_args',[]),list) or not all(isinstance(x,str) for x in m.get('fixed_args',[])): raise ValueError('Invalid fixed_args')
    MANIFESTS.mkdir(parents=True,exist_ok=True)
    target=MANIFESTS/(m['name']+'.json'); target.write_text(json.dumps(m,indent=2)+'\n'); return target

def run_tool(name,args):
    m=manifests()[name]; executable=m['executable']; resolved=shutil.which(executable)
    if not resolved: raise FileNotFoundError(f'Executable not found: {executable}')
    command=[resolved,*m.get('fixed_args',[]),*args]
    result=subprocess.run(command,check=False,timeout=int(m.get('timeout_seconds',300)))
    with db() as c: c.execute('INSERT INTO executions(tool,command,exit_code,created) VALUES(?,?,?,?)',(name,json.dumps(command),result.returncode,now()))
    return result.returncode

def rows(query,params=()):
    with db() as c: return [dict(r) for r in c.execute(query,params)]

def create_project(name,client=''):
    with db() as c: c.execute('INSERT INTO projects(name,client,created) VALUES(?,?,?)',(name,client,now()))

def start(project,task):
    with db() as c:
        if not c.execute('SELECT 1 FROM projects WHERE name=?',(project,)).fetchone(): raise ValueError('Create the project first')
        c.execute('INSERT INTO sessions(project,task,start) VALUES(?,?,?)',(project,task,now()))

def stop(notes=''):
    with db() as c:
        r=c.execute('SELECT id FROM sessions WHERE end IS NULL').fetchone()
        if not r: raise ValueError('No active session')
        c.execute('UPDATE sessions SET end=?,notes=? WHERE id=?',(now(),notes,r['id']))

def log(project,kind,body):
    with db() as c:
        if not c.execute('SELECT 1 FROM projects WHERE name=?',(project,)).fetchone(): raise ValueError('Create the project first')
        c.execute('INSERT INTO worklogs(project,kind,body,created) VALUES(?,?,?,?)',(project,kind,body,now()))

def report(project=None):
    q='SELECT * FROM sessions WHERE end IS NOT NULL'; p=()
    if project: q+=' AND project=?'; p=(project,)
    items=rows(q+' ORDER BY start',p)
    for r in items: r['hours']=round((datetime.fromisoformat(r['end'])-datetime.fromisoformat(r['start'])).total_seconds()/3600,4)
    return {'sessions':items,'total_hours':round(sum(x['hours'] for x in items),4)}
```

### `thewire/__main__.py`

**Why this exists:** CLI verbs, arguments, errors and dispatch into domain functions.

```python
import argparse, json, sys, shutil
from . import core as c

def main():
 p=argparse.ArgumentParser(prog='tw',description='TheWire unified operations CLI'); sub=p.add_subparsers(dest='cmd',required=True)
 sub.add_parser('version'); sub.add_parser('doctor')
 t=sub.add_parser('tool'); ts=t.add_subparsers(dest='action',required=True);ts.add_parser('list');r=ts.add_parser('register');r.add_argument('manifest');r=ts.add_parser('inspect');r.add_argument('name');r=ts.add_parser('run');r.add_argument('name');r.add_argument('args',nargs=argparse.REMAINDER)
 pr=sub.add_parser('project'); ps=pr.add_subparsers(dest='action',required=True);ps.add_parser('list');r=ps.add_parser('create');r.add_argument('name');r.add_argument('--client',default='')
 tm=sub.add_parser('time'); tms=tm.add_subparsers(dest='action',required=True);r=tms.add_parser('start');r.add_argument('project');r.add_argument('task');r=tms.add_parser('stop');r.add_argument('--notes',default='');tms.add_parser('status');r=tms.add_parser('report');r.add_argument('--project')
 w=sub.add_parser('worklog');ws=w.add_subparsers(dest='action',required=True);r=ws.add_parser('add');r.add_argument('project');r.add_argument('kind',choices=['work','insight','technical','decision']);r.add_argument('body');r=ws.add_parser('list');r.add_argument('--project');r=ws.add_parser('export');r.add_argument('--project')
 sub.add_parser('dashboard')
 a=p.parse_args()
 try:
  if a.cmd=='version': print('TheWire 0.1.0')
  elif a.cmd=='doctor': print(json.dumps({'python':sys.version.split()[0],'database':str(c.HOME/'thewire.db'),'plugins':len(c.manifests()),'git':bool(shutil.which('git'))},indent=2))
  elif a.cmd=='tool':
   if a.action=='list': print(json.dumps(c.manifests(),indent=2))
   elif a.action=='register': print(c.register(a.manifest))
   elif a.action=='inspect': print(json.dumps(c.manifests()[a.name],indent=2))
   else: return c.run_tool(a.name,a.args[1:] if a.args[:1]==['--'] else a.args)
  elif a.cmd=='project':
   if a.action=='create': c.create_project(a.name,a.client);print('Project created')
   else: print(json.dumps(c.rows('SELECT * FROM projects ORDER BY name'),indent=2))
  elif a.cmd=='time':
   if a.action=='start': c.start(a.project,a.task);print('Timer started')
   elif a.action=='stop': c.stop(a.notes);print('Timer stopped')
   elif a.action=='status': print(json.dumps(c.rows('SELECT * FROM sessions WHERE end IS NULL'),indent=2))
   else: print(json.dumps(c.report(a.project),indent=2))
  elif a.cmd=='worklog':
   if a.action=='add': c.log(a.project,a.kind,a.body);print('Worklog saved')
   else:
    records=c.rows('SELECT * FROM worklogs'+(' WHERE project=?' if a.project else '')+' ORDER BY created', (a.project,) if a.project else ())
    if a.action=='list': print(json.dumps(records,indent=2))
    else:
     print('# Worklogs\n');[print(f"## {r['created']} — {r['project']} — {r['kind']}\n\n{r['body']}\n") for r in records]
  elif a.cmd=='dashboard':
   import uvicorn;uvicorn.run('api.main:app',host='127.0.0.1',port=8765)
 except (ValueError,KeyError,FileNotFoundError,TimeoutError) as e: print(f'ERROR: {e}',file=sys.stderr);return 1
 return 0
if __name__=='__main__': raise SystemExit(main())
```

### `api/main.py`

**Why this exists:** Read-only local HTTP endpoints for health, projects, tools, sessions, reports and worklogs.

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from thewire import core
app=FastAPI(title='TheWire API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET'],allow_headers=['*'])
@app.get('/api/health')
def health():return {'status':'ok'}
@app.get('/api/projects')
def projects():return core.rows('SELECT * FROM projects ORDER BY name')
@app.get('/api/tools')
def tools():return core.manifests()
@app.get('/api/sessions')
def sessions():return core.rows('SELECT * FROM sessions ORDER BY start DESC LIMIT 100')
@app.get('/api/report')
def report(project:str|None=None):return core.report(project)
@app.get('/api/worklogs')
def worklogs():return core.rows('SELECT * FROM worklogs ORDER BY created DESC LIMIT 100')
```

### `tests/test_core.py`

**Why this exists:** Baseline lifecycle and manifest tests using temporary storage.

```python
import pytest
from thewire import core

def test_workflow(tmp_path,monkeypatch):
 monkeypatch.setattr(core,'HOME',tmp_path)
 core.create_project('demo','Client A');core.start('demo','Implement API')
 assert len(core.rows('SELECT * FROM sessions WHERE end IS NULL'))==1
 with pytest.raises(Exception):core.start('demo','Overlapping timer')
 core.stop('Done');core.log('demo','insight','Integration test passed')
 assert len(core.report('demo')['sessions'])==1
 assert core.rows('SELECT body FROM worklogs')[0]['body']=='Integration test passed'

def test_plugin_validation(tmp_path,monkeypatch):
 monkeypatch.setattr(core,'MANIFESTS',tmp_path/'plugins')
 p=tmp_path/'plugin.json';p.write_text('{"name":"test-tool","executable":"echo"}')
 core.register(p)
 assert core.manifests()['test-tool']['executable']=='echo'
```

### `web/package.json`

**Why this exists:** Dashboard runtime and build dependencies.

```json
{"name":"thewire-dashboard","private":true,"version":"0.1.0","type":"module","scripts":{"dev":"vite --host 127.0.0.1","build":"tsc -b && vite build"},"dependencies":{"react":"^19.0.0","react-dom":"^19.0.0"},"devDependencies":{"@types/react":"^19.0.0","@types/react-dom":"^19.0.0","typescript":"~5.7.0","vite":"^6.0.0"}}
```

### `web/tsconfig.json`

**Why this exists:** TypeScript compile settings.

```json
{"compilerOptions":{"target":"ES2022","lib":["ES2022","DOM"],"module":"ESNext","moduleResolution":"Bundler","jsx":"react-jsx","strict":true,"skipLibCheck":true,"noEmit":true},"include":["src"]}
```

### `web/index.html`

**Why this exists:** Document and root element.

```html
<!doctype html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>TheWire</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>
```

### `web/vite.config.ts`

**Why this exists:** Added integration fix: proxy `/api` on Vite port 5173 to FastAPI port 8765.

```typescript
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
});
```

### `web/src/main.tsx`

**Why this exists:** Typed React views for projects, sessions, worklogs and tools.

```tsx
import React,{useEffect,useState} from 'react';import{createRoot}from'react-dom/client';import './style.css';
type Project={id:number;name:string;client:string};type Session={id:number;project:string;task:string;start:string;end:string|null};type Log={id:number;project:string;kind:string;body:string;created:string};
function App(){const[projects,setProjects]=useState<Project[]>([]),[sessions,setSessions]=useState<Session[]>([]),[logs,setLogs]=useState<Log[]>([]),[tools,setTools]=useState<Record<string,unknown>>({}),[hours,setHours]=useState(0),[error,setError]=useState('');useEffect(()=>{Promise.all(['/api/projects','/api/sessions','/api/worklogs','/api/tools','/api/report'].map(async p=>{const r=await fetch(p);if(!r.ok)throw Error(p+' '+r.status);return r.json()})).then(([p,s,l,t,r])=>{setProjects(p);setSessions(s);setLogs(l);setTools(t);setHours(r.total_hours)}).catch(e=>setError(String(e)))},[]);return <main><header><span className="logo">TW</span><div><h1>TheWire</h1><p>Unified developer operations · v0.1</p></div></header>{error&&<p className="error">API unavailable: {error}. Start the API on port 8765.</p>}<section className="stats"><article><small>Projects</small><strong>{projects.length}</strong></article><article><small>Completed hours</small><strong>{hours.toFixed(2)}</strong></article><article><small>Active sessions</small><strong>{sessions.filter(s=>!s.end).length}</strong></article><article><small>Registered tools</small><strong>{Object.keys(tools).length}</strong></article></section><div className="cols"><section><h2>Projects</h2>{projects.map(p=><article key={p.id}><b>{p.name}</b><small>{p.client||'Personal'}</small></article>)}<h2>Recent sessions</h2>{sessions.slice(0,10).map(s=><article key={s.id}><b>{s.project}</b><p>{s.task}</p><small>{s.start} · {s.end?'Completed':'Running'}</small></article>)}</section><section><h2>Worklogs and insights</h2>{logs.slice(0,10).map(l=><article key={l.id}><b>{l.project} · {l.kind}</b><p>{l.body}</p><small>{l.created}</small></article>)}<h2>Tool registry</h2>{Object.keys(tools).map(name=><article key={name}><b>{name}</b></article>)}</section></div><footer>Local read-only dashboard. Use the tw CLI to modify records.</footer></main>};createRoot(document.getElementById('root')!).render(<App/>);
```

### `web/src/style.css`

**Why this exists:** Dashboard layout and responsive styles.

```css
:root{font-family:Inter,system-ui,sans-serif;background:#0b1220;color:#e5edf8}*{box-sizing:border-box}body{margin:0}main{max-width:1150px;margin:auto;padding:36px 24px}header{display:flex;gap:18px;align-items:center;margin-bottom:36px}.logo{background:#467de5;color:white;padding:16px;border-radius:14px;font-weight:800}h1{margin:0;font-size:32px}header p,small,footer{color:#93a4bc}header p{margin:4px 0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.stats article{background:#152238;padding:20px;border-radius:12px;display:grid;gap:12px}.stats strong{font-size:32px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:30px}h2{font-size:19px;margin:24px 0 14px}section article{background:#152238;border:1px solid #263750;border-radius:10px;padding:15px;margin-bottom:10px}section article b{display:block;margin-bottom:7px}section article p{color:#c2d1e4;white-space:pre-wrap}.error{color:#ffb4b4}footer{margin-top:40px}@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}}
```

### `scripts/thewire.zsh`

**Why this exists:** Thin zsh wrappers for registered tool names.

```bash
# Source this file after activating the TheWire virtual environment or installing tw.
function twc(){ tw tool run clc -- "$@"; }
function two(){ tw tool run onboarded -- "$@"; }
function twdb(){ tw tool run dbscaffold -- "$@"; }
function twrw(){ tw tool run reworked -- "$@"; }
function twstatus(){ tw time status; }
```

### `plugins/clc.json`

**Why this exists:** CLC adapter.

```json
{"name":"clc","description":"cl-commons toolkit adapter","executable":"clc","timeout_seconds":300}
```

### `plugins/onboarded.json`

**Why this exists:** Onboarded `ob` executable adapter.

```json
{"name":"onboarded","description":"Onboarded CLI adapter; adjust executable to local command","executable":"ob","timeout_seconds":300}
```

### `plugins/dbscaffold.json`

**Why this exists:** DBScaffold adapter; may require executable-name correction.

```json
{"name":"dbscaffold","description":"DBScaffold adapter; adjust executable to local command","executable":"dbscaffold","timeout_seconds":300}
```

### `plugins/reworked.json`

**Why this exists:** Reworked adapter; may require executable-name correction.

```json
{"name":"reworked","description":"Reworked adapter; adjust executable to local command","executable":"reworked","timeout_seconds":300}
```

### `plugins/terminal-workflow.json`

**Why this exists:** Terminal Workflow Kit adapter; may require executable-name correction.

```json
{"name":"terminal-workflow","description":"Terminal workflow kit adapter; replace executable with installed binary","executable":"terminal-workflow","timeout_seconds":300}
```

### `.gitignore`

**Why this exists:** Local build/data exclusions.

```text
.venv/
__pycache__/
.pytest_cache/
web/node_modules/
web/dist/
*.db
.env
```

## 4. Understand execution and data storage

**CLI command sequence:** `tw time start demo "Task"` -> `argparse` in `__main__.py` -> `core.start()` -> SQLite validates project and inserts session -> active timer unique index blocks a second active session. `tw time stop` writes the end timestamp. `core.report()` calculates duration from saved UTC timestamps and rounds each completed session to four decimal hours.

**Dashboard sequence:** the browser requests `/api/projects` from Vite -> Vite proxy forwards to `127.0.0.1:8765` -> `api.main.projects()` calls `core.rows()` -> JSON returns -> React stores the data and renders it. The UI is read-only and fetches once on mount; refresh the page to see later CLI writes.

**Tool sequence:** `tw tool register plugins/clc.json` saves a manifest under `$THEWIRE_HOME/plugins/`; `tw tool run clc -- help` resolves the actual `clc` binary, passes arguments without a shell, waits for completion, and writes an execution record on normal exit. The adapter does not install CLC and does not isolate its privileges. Command arguments appear in the SQLite execution log: do not pass secrets.

## 5. Install the Python CLI and run tests

From the new repository root, with `$THEWIRE_HOME` set to `.demo-data`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web,test]'
tw version
tw doctor
pytest -q
```

Expected: `TheWire 0.1.0`, JSON with Python version/database path/plugin count/Git availability, then **two passing tests**. Python can be installed via `pip` in an isolated venv; do not use `sudo pip`.

## 6. Compile the dashboard and verify the proxy

```bash
cd web
npm install
npm run build
cd ..
```

Expected: TypeScript compiler succeeds and Vite produces `web/dist`. Commit `web/package-lock.json` for repeatable future installs; do not commit `node_modules` or the compiled output.

Open two shells, using the same repo and `THEWIRE_HOME`:

**Shell A — API**

```bash
cd "$HOME/develop/workspaces/thewire"
export THEWIRE_HOME="$PWD/.demo-data"
source .venv/bin/activate
tw dashboard
```

**Shell B — web development server**

```bash
cd "$HOME/develop/workspaces/thewire/web"
npm run dev
```

A third shell can confirm both paths:

```bash
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:5173/api/projects
```

Expected: `{"status":"ok"}` and `[]` for an empty demo database. The second call checks the development proxy. Open `http://127.0.0.1:5173` in a browser. Do not bind the unauthenticated API to `0.0.0.0`.

## 7. End-to-end consulting demonstration

Execute in a terminal with venv active and `THEWIRE_HOME` set:

```bash
# 1. Project and client
tw project create toptal-practice --client 'Training Client'
tw project list

# 2. One measured work session
tw time start toptal-practice 'Implement example API endpoint'
tw time status
# Carry out a small task before you stop the timer.
tw time stop --notes 'Reviewed example endpoint and tests'
tw time report --project toptal-practice

# 3. Four distinct writing record types
tw worklog add toptal-practice work 'Completed a sample endpoint and tested its response.'
tw worklog add toptal-practice insight 'Validate inputs at API boundaries.'
tw worklog add toptal-practice technical 'GET /api/health returns a JSON object with status=ok.'
tw worklog add toptal-practice decision 'Use a loopback-only API for the single-user MVP.'
tw worklog list --project toptal-practice

# 4. Client-readable draft worklog
tw worklog export --project toptal-practice > practice-worklogs.md
cat practice-worklogs.md
```

Expected: one project, one completed session, four worklogs and a Markdown export. Elapsed hours depend on actual runtime and can round to zero if you stop immediately. The completed time record is not an official Toptal submission. Consult the applicable engagement policy before using real client data.

Check API projection and dashboard to confirm the CLI and browser observe the same records:

```bash
curl -fsS 'http://127.0.0.1:8765/api/report?project=toptal-practice'
curl -fsS http://127.0.0.1:8765/api/worklogs
```

## 8. Integrate CLC, Onboarded, DBScaffold, Reworked and Terminal Workflow Kit

The shipped adapters are **examples**, not proof that a particular executable exists. Verify installed binaries first:

```bash
for cmd in clc ob dbscaffold reworked terminal-workflow; do
  command -v "$cmd" || echo "Not installed: $cmd"
done
```

Inspect the `executable` field in each JSON manifest and correct any mismatch. Then register them:

```bash
tw tool register plugins/clc.json
tw tool register plugins/onboarded.json
tw tool register plugins/dbscaffold.json
tw tool register plugins/reworked.json
tw tool register plugins/terminal-workflow.json
tw tool list
tw tool inspect onboarded
```

For a verified and trusted binary with a known help command:

```bash
tw tool run clc -- help
tw tool run onboarded -- --help
```

Existing zsh aliases or functions are not directly executable from Python. Convert each to a trusted, explicit executable wrapper (not a dynamically constructed shell command), or keep the original function and have it call `tw`. For optional zsh helpers:

```zsh
source scripts/thewire.zsh
twstatus
```

To persist, add an absolute `source /your/actual/path/thewire/scripts/thewire.zsh` line to `.zshrc` without overwriting existing alias files.

## 9. Hands-on exercise: integrate a new executable

This exercise creates a safe local CLI called `tw-hello` and registers it through the same manifest contract as CLC.

```bash
mkdir -p scripts/bin
cat > scripts/bin/tw-hello <<'HELLO_SCRIPT_END'
#!/usr/bin/env bash
printf 'hello from tool adapter: %s\n' "$*"
HELLO_SCRIPT_END
chmod +x scripts/bin/tw-hello
python3 - <<'MANIFEST_SCRIPT_END'
import json
from pathlib import Path
manifest = {
    'name': 'hello',
    'description': 'Small integration exercise',
    'executable': str((Path.cwd() / 'scripts/bin/tw-hello').resolve()),
    'timeout_seconds': 30,
}
Path('plugins/hello.json').write_text(json.dumps(manifest, indent=2) + '\n')
MANIFEST_SCRIPT_END
tw tool register plugins/hello.json
tw tool inspect hello
tw tool run hello -- --help
```

Expected: `hello from tool adapter: --help`. This proves resolution, argument passing and tool invocation without a shell. If you run it from the repository root, the absolute executable path is valid. A malicious or destructive executable remains malicious even when wrapped by TheWire; use only trusted commands.

## 10. Proper design for adding a native feature

An adapter is correct when external software already owns the behavior. A native module is correct when the capability needs shared domain state, API projections or dashboard interaction. For a planned `tw artifact attach` feature:

1. Define contract: project, input file, output record, validation, failure behavior and maximum size.
2. Add a **versioned database migration** for an `artifacts` table. Preserve existing user data and define rollback.
3. Implement domain logic in a new `thewire/artifacts.py` module; separate validation, hashing and persistence.
4. Add `tw artifact attach <project> <path>` and `tw artifact list --project <project>` to CLI argument parsing.
5. Write tests for missing files, duplicates, database failure and export behavior.
6. Add an authenticated/authorized write API only after security controls exist; until then, expose GET projections only.
7. Create a typed React display with loading, empty and error states.
8. Update this runbook, add integration tests, and issue a versioned release.

This is a **design walkthrough**, not a claim the artifact feature is implemented in v0.1.

## 11. Backup, restore and maintenance

Use the SQLite online backup API for a consistent database snapshot even if the API is running:

```bash
python3 - <<'BACKUP_SCRIPT_END'
import os, sqlite3
from pathlib import Path
home = Path(os.environ.get('THEWIRE_HOME', str(Path.home() / '.local/share/thewire')))
source = home / 'thewire.db'
target = home / 'thewire-backup.db'
if not source.exists():
    raise SystemExit('Database does not exist')
with sqlite3.connect(source) as db, sqlite3.connect(target) as backup:
    db.backup(backup)
print(target)
BACKUP_SCRIPT_END
```

A full restore must also include the `$THEWIRE_HOME/plugins` directory. To rehearse a restore, stop API/CLI, create a **separate** test directory, copy the backup database and manifests, set `THEWIRE_HOME` to that new directory, then run `tw project list` and `tw time report`. Never overwrite active client records without a verified independent backup.

## 12. Common failures

| Problem | Cause to check | Action |
|---|---|---|
| `tw` not found | Venv inactive or package not installed | Activate `.venv`; `python -m pip install -e '.[web,test]'` |
| API not available | `tw dashboard` not running | Start it; `curl -fsS 127.0.0.1:8765/api/health` |
| Dashboard `/api` 404 | Missing Vite proxy | Add `web/vite.config.ts`; restart Vite |
| Tool not found | Manifest binary not installed or incorrect path | `command -v <binary>`; fix trusted manifest |
| Timer already active | Global single-active-session rule | Inspect `tw time status`; stop the active timer |
| Empty dashboard | Different `THEWIRE_HOME` for CLI and API | Set environment before starting each process |
| Frontend build failure | Unsupported Node or TypeScript compile error | Check versions and run `npm run build` |

## 13. Release gates and limitations

- [ ] `tw version`, `tw doctor`, `pytest -q` succeed.
- [ ] `npm run build` succeeds.
- [ ] API `/api/health` returns JSON and Vite `/api/projects` returns an array.
- [ ] Project + completed timer + report + four worklog types + Markdown export succeed.
- [ ] `tw tool run hello -- --help` succeeds.
- [ ] Restore a backup into a disposable directory and inspect records.
- [ ] Check no secrets or real client data entered demo files.

**v0.1 technical debt:** no migrations, no auth, no multi-client authorization, no write UI, no Toptal API, no reliable crash/timeout execution audit, limited manifest validation, no live UI refresh, no actual migration of existing CLC/Onboarded/DBScaffold source. Prioritize these before production use or billing-grade reporting.

## 14. Suggested build sequence for the next iteration

Build v0.2 in this order: migration framework -> timezone-safe correction/audit for timers -> CSV/JSON weekly reporting -> backup/restore tests -> typed tool capability contract -> worklog templates -> integration tests. Then introduce consulting-specific report formats and stronger client isolation. Keep external tools independently runnable until their full contract and tests are verified.

