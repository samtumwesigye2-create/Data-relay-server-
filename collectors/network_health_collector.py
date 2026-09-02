from __future__ import annotations
import os,socket,time
from urllib.parse import urlparse
import httpx
from relay_queue import enqueue,flush_once

SOURCE=os.environ.get('DRS_SOURCE','network-health')
TARGETS=[x.strip() for x in os.environ.get('DRS_HEALTH_TARGETS','').split(',') if x.strip()]
INTERVAL=float(os.environ.get('DRS_HEALTH_INTERVAL','30'))
TIMEOUT=float(os.environ.get('DRS_HEALTH_TIMEOUT','3'))


def emit(target:str,ok:bool,latency_ms:float,status_code:int=0,error:str='',resolved_ip:str=''):
    enqueue({
        'category':'system_metric',
        'source':SOURCE,
        'severity':'info' if ok else 'critical',
        'actor':'collector',
        'action':'health_check',
        'resource':target,
        'status':'up' if ok else 'down',
        'duration_ms':latency_ms,
        'trace_id':'',
        'payload':{
            'target':target,
            'reachable':ok,
            'latency_ms':round(latency_ms,3),
            'status_code':status_code,
            'resolved_ip':resolved_ip,
            'error':error,
        }
    })


def check_http(target:str):
    parsed=urlparse(target)
    host=parsed.hostname or ''
    resolved=''
    try:
        if host: resolved=socket.gethostbyname(host)
    except Exception: pass
    t=time.perf_counter()
    try:
        r=httpx.get(target,timeout=TIMEOUT,follow_redirects=True)
        ms=(time.perf_counter()-t)*1000
        ok=r.status_code<500
        emit(target,ok,ms,r.status_code,'' if ok else f'HTTP {r.status_code}',resolved)
    except Exception as exc:
        emit(target,False,(time.perf_counter()-t)*1000,0,type(exc).__name__,resolved)


def run_once():
    for target in TARGETS:
        if target.startswith('http://') or target.startswith('https://'):
            check_http(target)
    flush_once()


def run_forever():
    while True:
        run_once(); time.sleep(INTERVAL)


if __name__=='__main__': run_forever()
