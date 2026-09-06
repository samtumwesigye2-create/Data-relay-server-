from __future__ import annotations
import json, os, threading, time, urllib.request
import app as core

TARGETS={
    'atlas':('ATLAS_BASE_URL','UNG-ATLAS'),
    'core':('CORE_BASE_URL','UNG-CORE'),
    'iam':('IAM_BASE_URL','UNG-IAM'),
    'mdm':('MDM_BASE_URL','UNG-MDM'),
    'noc':('NOC_BASE_URL','UNG-NOC'),
}


def poll_service(service_id:str,env_name:str,display_name:str):
    base=os.getenv(env_name,'').rstrip('/')
    if not base:
        return False
    started=time.perf_counter()
    with urllib.request.urlopen(base+'/health',timeout=5) as r:
        data=json.loads(r.read().decode())
    latency=round((time.perf_counter()-started)*1000,2)
    event=core.EventIn(
        category='system_metric',
        source=service_id,
        severity='info',
        actor='UNG-PULSAR',
        action='health_poll',
        resource=display_name,
        status='online',
        duration_ms=latency,
        trace_id='',
        payload={'service':display_name,'health':data,'verified_service_id':service_id}
    )
    c=core.conn()
    try:
        core.insert_event(c,event)
        c.commit()
    finally:
        c.close()
    return True


def poll_all():
    results={}
    for service_id,(env_name,display_name) in TARGETS.items():
        try:
            results[service_id]=poll_service(service_id,env_name,display_name)
        except Exception:
            results[service_id]=False
    return results


def _loop():
    while True:
        poll_all()
        time.sleep(60)


def start():
    threading.Thread(target=_loop,name='ung-service-monitor',daemon=True).start()
