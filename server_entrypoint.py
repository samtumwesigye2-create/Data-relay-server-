from __future__ import annotations
import hashlib,json,os
from fastapi import Header,HTTPException,Request,Query
from fastapi.responses import HTMLResponse
import app as core
from service_identity import authenticate_service,configured_services,fingerprint
from service_registry import profiles,live_status

app=core.app


def require_key(key:str):
    core.auth(key)


@app.middleware('http')
async def service_identity_middleware(request:Request,call_next):
    path=request.url.path
    ingest_path=path in {'/events','/events/batch','/audit/events'} and request.method.upper()=='POST'
    if ingest_path:
        sid=request.headers.get('x-service-id','')
        skey=request.headers.get('x-service-key','')
        if sid or skey:
            sid=authenticate_service(sid,skey)
            request.scope['headers']=[
                (k,v) for (k,v) in request.scope['headers']
                if k.lower()!=b'x-api-key'
            ]+[(b'x-api-key',core.API_KEY.encode())]
            request.state.drs_service_id=sid
        else:
            core.auth(request.headers.get('x-api-key',''))
    response=await call_next(request)
    if ingest_path and getattr(request.state,'drs_service_id',None):
        response.headers['X-DRS-Service']=request.state.drs_service_id
    return response


def verify_table(table:str,payload_builder):
    c=core.conn()
    rows=c.execute(f'SELECT * FROM {table} ORDER BY rowid ASC').fetchall()
    prev=''
    checked=0
    for row in rows:
        d=dict(row)
        payload=payload_builder(d)
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        expected=hashlib.sha256((prev+'|'+raw).encode()).hexdigest()
        if d.get('prev_hash','')!=prev or d.get('event_hash','')!=expected:
            c.close()
            return {'ok':False,'table':table,'checked':checked,'failed_id':d.get('id')}
        prev=d['event_hash']; checked+=1
    c.close()
    return {'ok':True,'table':table,'checked':checked,'head_hash':prev}


def event_payload(d):
    return {'id':d['id'],'category':d['category'],'source':d['source'],'severity':d['severity'],'actor':d['actor'],'action':d['action'],'resource':d['resource'],'status':d['status'],'duration_ms':d['duration_ms'],'trace_id':d['trace_id'],'payload':json.loads(d['payload_json'] or '{}'),'created_at':d['created_at']}


def audit_payload(d):
    return {'id':d['id'],'who':d['who'],'what':d['what'],'resource':d['resource'],'result':d['result'],'how_method':d['how_method'],'how_channel':d['how_channel'],'ip_address':d['ip_address'],'user_agent':d['user_agent'],'device_id':d['device_id'],'session_id':d['session_id'],'trace_id':d['trace_id'],'details':json.loads(d['details_json'] or '{}'),'occurred_at':d['occurred_at'],'recorded_at':d['recorded_at']}


@app.get('/integrity/verify')
def integrity_verify(x_api_key:str=Header(default='')):
    require_key(x_api_key)
    e=verify_table('events',event_payload)
    a=verify_table('audit',audit_payload)
    return {'ok':bool(e['ok'] and a['ok']),'events':e,'audit':a}


@app.get('/services')
def services(x_api_key:str=Header(default='')):
    require_key(x_api_key)
    return {'services':[{'service_id':sid,'key_fingerprint':fingerprint(sid)} for sid in configured_services()]}


@app.get('/service-registry')
def service_registry(x_api_key:str=Header(default='')):
    require_key(x_api_key)
    return {'services':profiles()}


@app.get('/service-status')
def service_status(stale_after_seconds:int=Query(300,ge=30,le=86400),x_api_key:str=Header(default='')):
    require_key(x_api_key)
    return {'services':live_status(stale_after_seconds)}


@app.get('/dashboard-ui',response_class=HTMLResponse)
def dashboard_ui():
    path=os.path.join(os.path.dirname(__file__),'dashboard.html')
    if not os.path.exists(path): raise HTTPException(404,'dashboard.html missing')
    with open(path,'r',encoding='utf-8') as f: return HTMLResponse(f.read(),headers={'Cache-Control':'no-store'})
