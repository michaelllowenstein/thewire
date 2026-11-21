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
