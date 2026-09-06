from __future__ import annotations
import json, os, threading, time, urllib.request
import app as core


def poll_atlas():
    base=os.getenv('ATLAS_BASE_URL','').rstrip('/')
    if not base: return False
    with urllib.request.urlopen(base+'/health',timeout=5) as r:
        data=json.loads(r.read().decode())
    now=time.time(); c=core.conn()
    try:
        payload={'service':'UNG-ATLAS','health':data,'verified_service_id':'atlas'}
        core.insert_event(c,{'category':'system_metric','source':'atlas','severity':'info','actor':'UNG-PULSAR','action':'health_poll','resource':'UNG-ATLAS','status':'online','duration_ms':None,'trace_id':'','payload':payload,'created_at':now})
        c.commit()
    finally: c.close()
    return True


def _loop():
    while True:
        try: poll_atlas()
        except Exception: pass
        time.sleep(60)


def start():
    threading.Thread(target=_loop,name='atlas-monitor',daemon=True).start()
