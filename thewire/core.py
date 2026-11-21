import json, os, sqlite3, subprocess, shutil
from datetime import datetime, timezone
from pathlib import Path

HOME=Path(os.environ.get('THEWIRE_HOME', str(Path.home()/'.local/share/thewire')))
MANIFESTS=HOME/'plugins'

def now(): return datetime.now(timezone.utc).isoformat()

def db():
    HOME.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(HOME/'thewire.db'); c.row_factory=sqlite3.Row
    c.executescript('''
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,client TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,project TEXT NOT NULL,task TEXT NOT NULL,start TEXT NOT NULL,end TEXT,notes TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS one_active_session ON sessions((1)) WHERE end IS NULL;
CREATE TABLE IF NOT EXISTS worklogs(id INTEGER PRIMARY KEY,project TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions(id INTEGER PRIMARY KEY,tool TEXT NOT NULL,command TEXT NOT NULL,exit_code INTEGER,created TEXT NOT NULL);
    ''')
    return c

def manifests():
    MANIFESTS.mkdir(parents=True, exist_ok=True)
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