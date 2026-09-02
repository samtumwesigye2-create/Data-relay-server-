from __future__ import annotations
import hashlib, hmac, json, os, sqlite3, time, uuid
from collections import Counter
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

APP_NAME='Data Relay Server'
DB=os.environ.get('DRS_DB','data_relay.db')
API_KEY=os.environ.get('DRS_API_KEY','')
RETENTION_DAYS=int(os.environ.get('DRS_RETENTION_DAYS','90'))
CPU_ALERT=float(os.environ.get('DRS_CPU_ALERT','90'))
MEMORY_ALERT=float(os.environ.get('DRS_MEMORY_ALERT','90'))
DISK_ALERT=float(os.environ.get('DRS_DISK_ALERT','90'))
SLOW_QUERY_MS=float(os.environ.get('DRS_SLOW_QUERY_MS','1000'))
REPLICATION_LAG_SECONDS=float(os.environ.get('DRS_REPLICATION_LAG_SECONDS','30'))
BRUTE_FORCE_ATTEMPTS=int(os.environ.get('DRS_BRUTE_FORCE_ATTEMPTS','5'))
BRUTE_FORCE_WINDOW_SECONDS=int(os.environ.get('DRS_BRUTE_FORCE_WINDOW_SECONDS','300'))
CATEGORIES={'system_metric','application_log','user_interaction','database_activity','api_call','security_event','error','communication','file_transfer','alert_prediction'}
SECRET_KEYS={'password','passwd','secret','token','access_token','refresh_token','authorization','cookie','set-cookie','api_key','apikey','private_key'}
app=FastAPI(title=APP_NAME,version='1.0.0')

def conn():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; return c

def now(): return time.time()
def auth(key:str):
 if not API_KEY: raise HTTPException(503,'DRS_API_KEY is not configured')
 if not hmac.compare_digest(key or '',API_KEY): raise HTTPException(401,'Invalid API key')

def scrub(v:Any):
 if isinstance(v,dict): return {k:('[REDACTED]' if str(k).lower() in SECRET_KEYS else scrub(x)) for k,x in v.items()}
 if isinstance(v,list): return [scrub(x) for x in v]
 if isinstance(v,str) and len(v)>12000: return v[:12000]+'…[TRUNCATED]'
 return v

def init():
 c=conn(); c.executescript('''
 CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,category TEXT NOT NULL,source TEXT NOT NULL,severity TEXT NOT NULL,actor TEXT,action TEXT,resource TEXT,status TEXT,duration_ms REAL,trace_id TEXT,payload_json TEXT NOT NULL,created_at REAL NOT NULL,prev_hash TEXT,event_hash TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at DESC);
 CREATE INDEX IF NOT EXISTS idx_events_category ON events(category,created_at DESC);
 CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor,created_at DESC);
 CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id);
 CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,who TEXT NOT NULL,what TEXT NOT NULL,resource TEXT,result TEXT,how_method TEXT,how_channel TEXT,ip_address TEXT,user_agent TEXT,device_id TEXT,session_id TEXT,trace_id TEXT,details_json TEXT NOT NULL,occurred_at REAL NOT NULL,recorded_at REAL NOT NULL,prev_hash TEXT,event_hash TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS idx_audit_when ON audit(occurred_at DESC);
 CREATE INDEX IF NOT EXISTS idx_audit_who ON audit(who,occurred_at DESC);
 CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,title TEXT NOT NULL,severity TEXT NOT NULL,status TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at REAL NOT NULL,resolved_at REAL);
 '''); c.commit(); c.close()
init()

class EventIn(BaseModel):
 category:str; source:str=Field(min_length=1,max_length=120); severity:str='info'; actor:str=''; action:str=''; resource:str=''; status:str=''; duration_ms:Optional[float]=None; trace_id:str=''; payload:Dict[str,Any]=Field(default_factory=dict)
class BatchIn(BaseModel): events:List[EventIn]=Field(min_length=1,max_length=500)
class AuditIn(BaseModel):
 who:str=Field(min_length=1,max_length=200); what:str=Field(min_length=1,max_length=300); resource:str=''; result:str=''; how_method:str=''; how_channel:str=''; ip_address:str=''; user_agent:str=''; device_id:str=''; session_id:str=''; trace_id:str=''; occurred_at:float=0; details:Dict[str,Any]=Field(default_factory=dict)

def chain_hash(c,table,payload:dict):
 row=c.execute(f'SELECT event_hash FROM {table} ORDER BY rowid DESC LIMIT 1').fetchone(); prev=row['event_hash'] if row else ''
 raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False)
 return prev,hashlib.sha256((prev+'|'+raw).encode()).hexdigest()

def open_alert(c,title,severity,evidence,dedupe=300):
 cutoff=now()-dedupe; prior=c.execute("SELECT id FROM alerts WHERE title=? AND status='open' AND created_at>=? LIMIT 1",(title,cutoff)).fetchone()
 if prior:return None
 aid='ALT-'+uuid.uuid4().hex[:12].upper(); c.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?)',(aid,title,severity,'open',json.dumps(scrub(evidence)),now(),None)); return aid

def auto_alerts(c,eid,p:EventIn):
 out=[]; pay=p.payload or {}; sev=p.severity.lower(); evidence={'event_id':eid,'source':p.source,'trace_id':p.trace_id}
 if p.category=='error' and sev in {'critical','fatal','emergency'}:
  a=open_alert(c,f'Critical error: {p.source}','critical',evidence); out += [a] if a else []
 if p.category=='system_metric':
  for label,key,limit in [('CPU','cpu_percent',CPU_ALERT),('Memory','memory_percent',MEMORY_ALERT),('Disk','disk_percent',DISK_ALERT)]:
   v=pay.get(key)
   if isinstance(v,(int,float)) and v>=limit:
    a=open_alert(c,f'High {label}: {p.source}','critical',{**evidence,'value':v,'threshold':limit}); out += [a] if a else []
 if p.category=='database_activity':
  qms=p.duration_ms if p.duration_ms is not None else pay.get('query_ms')
  if isinstance(qms,(int,float)) and qms>=SLOW_QUERY_MS:
   a=open_alert(c,f'Slow database query: {p.source}','warning',{**evidence,'query_ms':qms}); out += [a] if a else []
  lag=pay.get('replication_lag_seconds')
  if isinstance(lag,(int,float)) and lag>=REPLICATION_LAG_SECONDS:
   a=open_alert(c,f'Replication lag: {p.source}','critical',{**evidence,'lag_seconds':lag}); out += [a] if a else []
 if p.category=='security_event' and p.action.lower() in {'failed_login','login_failed','authentication_failed'}:
  since=now()-BRUTE_FORCE_WINDOW_SECONDS; args=[since]; q="SELECT COUNT(*) n FROM events WHERE category='security_event' AND created_at>=? AND action IN ('failed_login','login_failed','authentication_failed')"
  if p.actor:q+=' AND actor=?';args.append(p.actor)
  count=c.execute(q,args).fetchone()['n']
  if count>=BRUTE_FORCE_ATTEMPTS:
   a=open_alert(c,f'Brute force login attempts: {p.actor or p.source}','critical',{**evidence,'failed_attempts':count},BRUTE_FORCE_WINDOW_SECONDS); out += [a] if a else []
 return out

def insert_event(c,p:EventIn):
 if p.category not in CATEGORIES: raise HTTPException(422,{'allowed':sorted(CATEGORIES)})
 eid='EVT-'+uuid.uuid4().hex[:16].upper(); t=now(); clean=scrub(p.payload)
 integrity={'id':eid,'category':p.category,'source':p.source,'severity':p.severity.lower(),'actor':p.actor,'action':p.action,'resource':p.resource,'status':p.status,'duration_ms':p.duration_ms,'trace_id':p.trace_id,'payload':clean,'created_at':t}
 prev,eh=chain_hash(c,'events',integrity)
 c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,p.category,p.source,p.severity.lower(),p.actor,p.action,p.resource,p.status,p.duration_ms,p.trace_id,json.dumps(clean,separators=(',',':'),ensure_ascii=False),t,prev,eh)); return eid

@app.get('/health')
def health(): return {'status':'healthy','service':APP_NAME,'timestamp':now(),'retention_days':RETENTION_DAYS}
@app.post('/events')
def ingest(p:EventIn,x_api_key:str=Header(default='')):
 auth(x_api_key); c=conn(); eid=insert_event(c,p); alerts=auto_alerts(c,eid,p); c.commit(); c.close(); return {'accepted':True,'event_id':eid,'alerts':alerts}
@app.post('/events/batch')
def ingest_batch(p:BatchIn,x_api_key:str=Header(default='')):
 auth(x_api_key); c=conn(); ids=[];alerts=[]
 for e in p.events:
  eid=insert_event(c,e);ids.append(eid);alerts.extend(auto_alerts(c,eid,e))
 c.commit();c.close();return {'accepted':len(ids),'event_ids':ids,'alerts':alerts}
@app.get('/events')
def events(category:str='',source:str='',actor:str='',trace_id:str='',since:float=0,limit:int=Query(100,ge=1,le=1000),x_api_key:str=Header(default='')):
 auth(x_api_key); clauses=[];args=[]
 for col,val in [('category',category),('source',source),('actor',actor),('trace_id',trace_id)]:
  if val:clauses.append(f'{col}=?');args.append(val)
 if since:clauses.append('created_at>=?');args.append(since)
 q='SELECT * FROM events'+((' WHERE '+' AND '.join(clauses)) if clauses else '')+' ORDER BY created_at DESC LIMIT ?';args.append(limit);c=conn();rows=[]
 for r in c.execute(q,args):d=dict(r);d['payload']=json.loads(d.pop('payload_json'));rows.append(d)
 c.close();return {'results':rows}
@app.post('/audit/events')
def audit_write(p:AuditIn,x_api_key:str=Header(default='')):
 auth(x_api_key); t=now();occur=p.occurred_at or t;clean=scrub(p.details);aid='AUD-'+uuid.uuid4().hex[:16].upper();c=conn();integrity={'id':aid,'who':p.who,'what':p.what,'resource':p.resource,'result':p.result,'how_method':p.how_method,'how_channel':p.how_channel,'ip_address':p.ip_address,'user_agent':p.user_agent,'device_id':p.device_id,'session_id':p.session_id,'trace_id':p.trace_id,'details':clean,'occurred_at':occur,'recorded_at':t};prev,eh=chain_hash(c,'audit',integrity);c.execute('INSERT INTO audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(aid,p.who,p.what,p.resource,p.result,p.how_method,p.how_channel,p.ip_address,p.user_agent,p.device_id,p.session_id,p.trace_id,json.dumps(clean,separators=(',',':'),ensure_ascii=False),occur,t,prev,eh));c.commit();c.close();return {'recorded':True,'audit_id':aid,'who':p.who,'what':p.what,'when':occur,'how':{'method':p.how_method,'channel':p.how_channel,'ip_address':p.ip_address,'user_agent':p.user_agent,'device_id':p.device_id,'session_id':p.session_id},'hash':eh}
@app.get('/audit/events')
def audit_read(who:str='',what:str='',trace_id:str='',since:float=0,limit:int=Query(100,ge=1,le=1000),x_api_key:str=Header(default='')):
 auth(x_api_key); clauses=[];args=[]
 for col,val in [('who',who),('what',what),('trace_id',trace_id)]:
  if val:clauses.append(f'{col}=?');args.append(val)
 if since:clauses.append('occurred_at>=?');args.append(since)
 q='SELECT * FROM audit'+((' WHERE '+' AND '.join(clauses)) if clauses else '')+' ORDER BY occurred_at DESC LIMIT ?';args.append(limit);c=conn();rows=[dict(r) for r in c.execute(q,args)];c.close();return {'results':rows}
@app.get('/alerts')
def alerts(x_api_key:str=Header(default='')):
 auth(x_api_key);c=conn();rows=[dict(r) for r in c.execute('SELECT * FROM alerts ORDER BY created_at DESC LIMIT 500')];c.close();return {'results':rows}
@app.post('/alerts/{alert_id}/resolve')
def resolve(alert_id:str,x_api_key:str=Header(default='')):
 auth(x_api_key);c=conn();n=c.execute("UPDATE alerts SET status='resolved',resolved_at=? WHERE id=?",(now(),alert_id)).rowcount;c.commit();c.close();return {'resolved':bool(n)}
@app.get('/dashboard')
def dashboard(window_seconds:int=Query(3600,ge=60,le=604800),x_api_key:str=Header(default='')):
 auth(x_api_key);since=now()-window_seconds;c=conn();rows=[dict(r) for r in c.execute('SELECT category,severity,source FROM events WHERE created_at>=?',(since,))];open_alerts=c.execute("SELECT COUNT(*) n FROM alerts WHERE status='open'").fetchone()['n'];c.close();return {'service':APP_NAME,'events_in_window':len(rows),'open_alerts':open_alerts,'by_category':dict(Counter(r['category'] for r in rows)),'by_source':dict(Counter(r['source'] for r in rows).most_common(20)),'timestamp':now()}
