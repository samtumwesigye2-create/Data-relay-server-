from __future__ import annotations
import json,os,sqlite3,time
import httpx

QUEUE_DB=os.environ.get('DRS_QUEUE_DB','drs_queue.db')
DRS_URL=os.environ.get('DRS_URL','').rstrip('/')
DRS_API_KEY=os.environ.get('DRS_API_KEY','')
MAX_BATCH=int(os.environ.get('DRS_QUEUE_BATCH','100'))


def conn():
    c=sqlite3.connect(QUEUE_DB,timeout=5)
    c.execute('CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL,created_at REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0)')
    c.commit(); return c


def enqueue(event:dict):
    c=conn(); c.execute('INSERT INTO queue(payload,created_at,attempts) VALUES(?,?,0)',(json.dumps(event,separators=(",",":"),ensure_ascii=False),time.time())); c.commit(); c.close()


def flush_once():
    if not DRS_URL or not DRS_API_KEY: return 0
    c=conn(); rows=c.execute('SELECT id,payload FROM queue ORDER BY id LIMIT ?',(MAX_BATCH,)).fetchall()
    if not rows: c.close(); return 0
    events=[json.loads(r[1]) for r in rows]
    try:
        r=httpx.post(DRS_URL+'/events/batch',headers={'x-api-key':DRS_API_KEY},json={'events':events},timeout=8)
        if r.status_code<300:
            ids=[r[0] for r in rows]; c.executemany('DELETE FROM queue WHERE id=?',[(x,) for x in ids]); c.commit(); n=len(ids); c.close(); return n
    except Exception:
        pass
    c.executemany('UPDATE queue SET attempts=attempts+1 WHERE id=?',[(r[0],) for r in rows]); c.commit(); c.close(); return 0


def run_forever(interval=5):
    while True:
        flush_once(); time.sleep(interval)


if __name__=='__main__': run_forever()
