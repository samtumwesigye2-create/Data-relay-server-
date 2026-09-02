from __future__ import annotations
import hashlib,json,os
from fastapi import Header,HTTPException,Request
from fastapi.responses import HTMLResponse
import app as core
from service_identity import authenticate_service,configured_services,fingerprint

app=core.app


def require_key(key:str):
    core.auth(key)


async def _bind_verified_service(request:Request,sid:str):
    """Inject the authenticated submitter into the signed/hashed event payload before storage."""
    raw=await request.body()
    if not raw:return
    try:
        data=json.loads(raw.decode('utf-8'))
    except Exception:
        return
    path=request.url.path
    if path=='/events' and isinstance(data,dict):
        payload=data.get('payload') if isinstance(data.get('payload'),dict) else {}
        payload['_drs_verified_service_id']=sid
        data['payload']=payload
    elif path=='/events/batch' and isinstance(data,dict) and isinstance(data.get('events'),list):
        for event in data['events']:
            if not isinstance(event,dict):continue
            payload=event.get('payload') if isinstance(event.get('payload'),dict) else {}
            payload['_drs_verified_service_id']=sid
            event['payload']=payload
    elif path=='/audit/events' and isinstance(data,dict):
        details=data.get('details') if isinstance(data.get('details'),dict) else {}
        details['_drs_verified_service_id']=sid
        data['details']=details
    new_body=json.dumps(data,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    request._body=new_body
    sent=False
    async def receive():
        nonlocal sent
        if sent:return {'type':'http.request','body':b'','more_body':False}
        sent=True
        return {'type':'http.request','body':new_body,'more_body':False}
    request._receive=receive
    headers=[(k,v) for (k,v) in request.scope['headers'] if k.lower()!=b'content-length']
    headers.append((b'content-length',str(len(new_body)).encode()))
    request.scope['headers']=headers


@app.middleware('http')
async def service_identity_middleware(request:Request,call_next):
    path=request.url.path
    ingest_path=path in {'/events','/events/batch','/audit/events'} and request.method.upper()=='POST'
    if ingest_path:
        sid=request.headers.get('x-service-id','')
        skey=request.headers.get('x-service-key','')
        if sid or skey:
            sid=authenticate_service(sid,skey)
            await _bind_verified_service(request,sid)
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


@app.get('/dashboard-ui',response_class=HTMLResponse)
def dashboard_ui():
    path=os.path.join(os.path.dirname(__file__),'dashboard.html')
    if not os.path.exists(path): raise HTTPException(404,'dashboard.html missing')
    with open(path,'r',encoding='utf-8') as f: return HTMLResponse(f.read(),headers={'Cache-Control':'no-store'})
