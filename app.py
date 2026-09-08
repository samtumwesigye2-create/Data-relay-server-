from __future__ import annotations
import hashlib,hmac,json,os,sqlite3,time,uuid
from collections import Counter
from typing import Any,Dict,List,Optional
from fastapi import FastAPI,Header,HTTPException,Query
from pydantic import BaseModel,Field
from durable_delivery import Delivery,DeliveryPlanner
from delivery_runtime import SQLiteDeliveryStore
APP_NAME='UNG-PULSAR Data Relay';DB=os.environ.get('DRS_DB','data_relay.db');API_KEY=os.environ.get('DRS_API_KEY','');RETENTION_DAYS=int(os.environ.get('DRS_RETENTION_DAYS','90'));CATEGORIES={'system_metric','application_log','user_interaction','database_activity','api_call','security_event','error','communication','file_transfer','alert_prediction'};SECRET_KEYS={'password','passwd','secret','token','access_token','refresh_token','authorization','cookie','set-cookie','api_key','apikey','private_key'}
app=FastAPI(title=APP_NAME,version='1.1.0')
def conn():c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;return c
def now():return time.time()
def auth(key):
 if not API_KEY:raise HTTPException(503,'DRS_API_KEY is not configured')
 if not hmac.compare_digest(key or '',API_KEY):raise HTTPException(401,'Invalid API key')
def scrub(v):
 if isinstance(v,dict):return {k:('[REDACTED]' if str(k).lower() in SECRET_KEYS else scrub(x)) for k,x in v.items()}
 if isinstance(v,list):return [scrub(x) for x in v]
 if isinstance(v,str) and len(v)>12000:return v[:12000]+'…[TRUNCATED]'
 return v
def init():
 c=conn();c.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,category TEXT NOT NULL,source TEXT NOT NULL,severity TEXT NOT NULL,actor TEXT,action TEXT,resource TEXT,status TEXT,duration_ms REAL,trace_id TEXT,payload_json TEXT NOT NULL,created_at REAL NOT NULL,prev_hash TEXT,event_hash TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at DESC);CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,who TEXT NOT NULL,what TEXT NOT NULL,resource TEXT,result TEXT,how_method TEXT,how_channel TEXT,ip_address TEXT,user_agent TEXT,device_id TEXT,session_id TEXT,trace_id TEXT,details_json TEXT NOT NULL,occurred_at REAL NOT NULL,recorded_at REAL NOT NULL,prev_hash TEXT,event_hash TEXT NOT NULL);CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,title TEXT NOT NULL,severity TEXT NOT NULL,status TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at REAL NOT NULL,resolved_at REAL);''');c.commit();c.close()
init();delivery_store=SQLiteDeliveryStore(DB);delivery_planner=DeliveryPlanner(delivery_store)
class EventIn(BaseModel):category:str;source:str=Field(min_length=1,max_length=120);severity:str='info';actor:str='';action:str='';resource:str='';status:str='';duration_ms:Optional[float]=None;trace_id:str='';payload:Dict[str,Any]=Field(default_factory=dict)
class BatchIn(BaseModel):events:List[EventIn]=Field(min_length=1,max_length=500)
class DeliveryIn(BaseModel):source:str;targets:list[str]=Field(min_length=1,max_length=100);event_type:str;payload:Dict[str,Any]=Field(default_factory=dict);idempotency_key:str|None=None;priority:int=50;max_attempts:int=5
def chain_hash(c,table,payload):
 row=c.execute(f'SELECT event_hash FROM {table} ORDER BY rowid DESC LIMIT 1').fetchone();prev=row['event_hash'] if row else '';raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False);return prev,hashlib.sha256((prev+'|'+raw).encode()).hexdigest()
def insert_event(c,p):
 if p.category not in CATEGORIES:raise HTTPException(422,{'allowed':sorted(CATEGORIES)})
 eid='EVT-'+uuid.uuid4().hex[:16].upper();t=now();clean=scrub(p.payload);integrity={'id':eid,'category':p.category,'source':p.source,'severity':p.severity.lower(),'actor':p.actor,'action':p.action,'resource':p.resource,'status':p.status,'duration_ms':p.duration_ms,'trace_id':p.trace_id,'payload':clean,'created_at':t};prev,eh=chain_hash(c,'events',integrity);c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,p.category,p.source,p.severity.lower(),p.actor,p.action,p.resource,p.status,p.duration_ms,p.trace_id,json.dumps(clean,separators=(',',':'),ensure_ascii=False),t,prev,eh));return eid
@app.get('/health')
def health():return {'status':'healthy','service':APP_NAME,'version':'1.1.0','timestamp':now(),'retention_days':RETENTION_DAYS,'delivery_queue':len(delivery_store.list_queue(limit=1000))}
@app.post('/events')
def ingest(p:EventIn,x_api_key:str=Header(default='')):
 auth(x_api_key);c=conn();eid=insert_event(c,p);c.commit();c.close();return {'accepted':True,'event_id':eid}
@app.post('/events/batch')
def ingest_batch(p:BatchIn,x_api_key:str=Header(default='')):
 auth(x_api_key);c=conn();ids=[insert_event(c,e) for e in p.events];c.commit();c.close();return {'accepted':len(ids),'event_ids':ids}
@app.get('/events')
def events(category:str='',source:str='',trace_id:str='',limit:int=Query(100,ge=1,le=1000),x_api_key:str=Header(default='')):
 auth(x_api_key);clauses=[];args=[]
 for col,val in [('category',category),('source',source),('trace_id',trace_id)]:
  if val:clauses.append(f'{col}=?');args.append(val)
 q='SELECT * FROM events'+((' WHERE '+' AND '.join(clauses)) if clauses else '')+' ORDER BY created_at DESC LIMIT ?';args.append(limit);c=conn();rows=[]
 for r in c.execute(q,args):d=dict(r);d['payload']=json.loads(d.pop('payload_json'));rows.append(d)
 c.close();return {'results':rows}
@app.post('/v1/deliveries',status_code=202)
def enqueue_delivery(p:DeliveryIn,x_api_key:str=Header(default='')):
 auth(x_api_key);created=[];duplicates=[]
 for d in DeliveryPlanner.fanout(p.source,p.targets,p.event_type,scrub(p.payload),priority=p.priority,max_attempts=p.max_attempts):
  d.idempotency_key=(f'{p.idempotency_key}:{d.targets[0]}' if p.idempotency_key and len(p.targets)>1 else p.idempotency_key)
  (created if delivery_planner.enqueue(d) else duplicates).append(d.message_id)
 return {'accepted':len(created),'message_ids':created,'duplicates':duplicates,'fanout_targets':len(set(p.targets))}
@app.get('/v1/deliveries')
def deliveries(status:str|None=None,limit:int=Query(100,ge=1,le=1000),x_api_key:str=Header(default='')):
 auth(x_api_key);return {'results':delivery_store.list_queue(status,limit)}
@app.get('/v1/dlq')
def dlq(limit:int=Query(100,ge=1,le=1000),x_api_key:str=Header(default='')):
 auth(x_api_key);return {'results':delivery_store.list_dlq(limit)}
@app.get('/dashboard')
def dashboard(x_api_key:str=Header(default='')):
 auth(x_api_key);c=conn();n=c.execute('SELECT COUNT(*) n FROM events').fetchone()['n'];c.close();return {'service':APP_NAME,'events':n,'queued':len(delivery_store.list_queue(limit=1000)),'dead_letters':len(delivery_store.list_dlq(limit=1000)),'timestamp':now()}
