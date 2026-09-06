from __future__ import annotations
import json, os, threading, time, urllib.request
import app as core

TARGETS={
    'atlas':('ATLAS_BASE_URL','UNG-ATLAS'),
    'core':('CORE_BASE_URL','UNG-CORE'),
    'iam':('IAM_BASE_URL','UNG-IAM'),
    'mdm':('MDM_BASE_URL','UNG-MDM'),
    'noc':('NOC_BASE_URL','UNG-NOC'),
    'titan':('TITAN_BASE_URL','UNG-TITAN'),
    'midas':('MIDAS_BASE_URL','UNG-MIDAS'),
    'nova':('NOVA_BASE_URL','UNG-NOVA'),
    'hermes':('HERMES_BASE_URL','UNG-HERMES'),
    'nemsis':('NEMSIS_BASE_URL','UNG-NEMSIS'),
    'horus':('HORUS_BASE_URL','UNG-HORUS'),
    'sentinel':('SENTINEL_BASE_URL','UNG-SENTINEL'),
    'vector':('VECTOR_BASE_URL','UNG-VECTOR'),
    'aegis':('AEGIS_BASE_URL','UNG-AEGIS'),
    'nexus':('NEXUS_BASE_URL','UNG-NEXUS'),
    'apollo':('APOLLO_BASE_URL','UNG-APOLLO'),
    'orion':('ORION_BASE_URL','UNG-ORION'),
    'docs':('DOCS_BASE_URL','UNG-DOCS'),
    'procure':('PROCURE_BASE_URL','UNG-PROCURE'),
    'infra25':('INFRA25_BASE_URL','UNG-INFRA-25'),
}


def poll_service(service_id:str,env_name:str,display_name:str):
    base=os.getenv(env_name,'').rstrip('/')
    if not base:
        print(f'[PULSAR-MONITOR] {service_id} NOT_CONFIGURED', flush=True)
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
    print(f'[PULSAR-MONITOR] {service_id} ONLINE {latency}ms', flush=True)
    return True


def poll_all():
    results={}
    for service_id,(env_name,display_name) in TARGETS.items():
        try:
            results[service_id]=poll_service(service_id,env_name,display_name)
        except Exception as exc:
            results[service_id]=False
            print(f'[PULSAR-MONITOR] {service_id} FAILED {type(exc).__name__}: {exc}', flush=True)
    return results


def _loop():
    while True:
        poll_all()
        time.sleep(60)


def start():
    threading.Thread(target=_loop,name='ung-service-monitor',daemon=True).start()
