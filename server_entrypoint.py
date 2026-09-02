from __future__ import annotations
import hashlib,json,os
from fastapi import Header,HTTPException
from fastapi.responses import HTMLResponse
import app as core

app=core.app


def require_key(key:str):
    core.auth(key)


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


@app.get('/dashboard-ui',response_class=HTMLResponse)
def dashboard_ui():
    path=os.path.join(os.path.dirname(__file__),'dashboard.html')
    if not os.path.exists(path): raise HTTPException(404,'dashboard.html missing')
    with open(path,'r',encoding='utf-8') as f: return HTMLResponse(f.read(),headers={'Cache-Control':'no-store'})
