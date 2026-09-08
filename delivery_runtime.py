import json, sqlite3
from dataclasses import asdict
from durable_delivery import Delivery
class SQLiteDeliveryStore:
 def __init__(self,db):self.db=db;self.init()
 def c(self):
  c=sqlite3.connect(self.db,timeout=15);c.row_factory=sqlite3.Row;return c
 def init(self):
  c=self.c();c.executescript('''CREATE TABLE IF NOT EXISTS delivery_queue(message_id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE,source TEXT NOT NULL,target TEXT NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,priority INTEGER NOT NULL,attempts INTEGER NOT NULL,max_attempts INTEGER NOT NULL,status TEXT NOT NULL,next_attempt_at TEXT,last_error TEXT);CREATE INDEX IF NOT EXISTS idx_delivery_status ON delivery_queue(status,next_attempt_at);CREATE TABLE IF NOT EXISTS delivery_dlq(message_id TEXT PRIMARY KEY,record_json TEXT NOT NULL,dead_lettered_at DATETIME DEFAULT CURRENT_TIMESTAMP);''');c.commit();c.close()
 def seen(self,key):
  c=self.c();r=c.execute('SELECT 1 FROM delivery_queue WHERE message_id=? OR idempotency_key=? UNION SELECT 1 FROM delivery_dlq WHERE message_id=? LIMIT 1',(key,key,key)).fetchone();c.close();return bool(r)
 def save(self,d:Delivery):
  target=d.targets[0] if d.targets else '';c=self.c();c.execute('''INSERT INTO delivery_queue VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET priority=excluded.priority,attempts=excluded.attempts,max_attempts=excluded.max_attempts,status=excluded.status,next_attempt_at=excluded.next_attempt_at,last_error=excluded.last_error''',(d.message_id,d.idempotency_key,d.source,target,d.event_type,json.dumps(d.payload,separators=(',',':')),d.priority,d.attempts,d.max_attempts,d.status,d.next_attempt_at,d.last_error));c.commit();c.close()
 def dead_letter(self,d:Delivery):
  c=self.c();c.execute('INSERT OR REPLACE INTO delivery_dlq(message_id,record_json) VALUES(?,?)',(d.message_id,json.dumps(asdict(d),separators=(',',':'))));c.execute('DELETE FROM delivery_queue WHERE message_id=?',(d.message_id,));c.commit();c.close()
 def list_queue(self,status=None,limit=100):
  c=self.c();q='SELECT * FROM delivery_queue';args=[]
  if status:q+=' WHERE status=?';args.append(status)
  q+=' ORDER BY priority DESC,rowid ASC LIMIT ?';args.append(limit);rows=[dict(r) for r in c.execute(q,args)];c.close();return rows
 def list_dlq(self,limit=100):
  c=self.c();rows=[dict(r) for r in c.execute('SELECT * FROM delivery_dlq ORDER BY dead_lettered_at DESC LIMIT ?',(limit,))];c.close();return rows
