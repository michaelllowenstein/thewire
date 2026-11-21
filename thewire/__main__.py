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
