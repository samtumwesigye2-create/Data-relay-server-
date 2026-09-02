from __future__ import annotations
import os,time,uuid
from typing import Any,Dict,Optional
import httpx
from relay_queue import enqueue,flush_once

SERVICE_NAME=os.environ.get('DRS_SOURCE','application')
DEFAULT_TIMEOUT=float(os.environ.get('DRS_COLLECTOR_TIMEOUT','3'))


def _event(category:str,action:str='',actor:str='',resource:str='',status:str='',duration_ms:Optional[float]=None,trace_id:str='',severity:str='info',payload:Optional[Dict[str,Any]]=None):
    return {
        'category':category,
        'source':SERVICE_NAME,
        'severity':severity,
        'actor':actor or '',
        'action':action or '',
        'resource':resource or '',
        'status':status or '',
        'duration_ms':duration_ms,
        'trace_id':trace_id or uuid.uuid4().hex,
        'payload':payload or {},
    }


def emit_application_log(message:str,severity:str='info',**fields):
    enqueue(_event('application_log',severity=severity,payload={'message':message,**fields}))


def emit_user_action(who:str,what:str,resource:str='',result:str='',how:Optional[Dict[str,Any]]=None,trace_id:str=''):
    how=how or {}
    enqueue(_event('user_interaction',action=what,actor=who,resource=resource,status=result,trace_id=trace_id,payload={'how':how}))


def emit_security_event(action:str,actor:str='',resource:str='',severity:str='warning',trace_id:str='',**fields):
    enqueue(_event('security_event',action=action,actor=actor,resource=resource,severity=severity,trace_id=trace_id,payload=fields))


def emit_file_transfer(action:str,actor:str='',resource:str='',status:str='',bytes_count:int=0,trace_id:str='',**fields):
    enqueue(_event('file_transfer',action=action,actor=actor,resource=resource,status=status,trace_id=trace_id,payload={'bytes':bytes_count,**fields}))


def emit_communication(action:str,actor:str='',resource:str='',status:str='',trace_id:str='',**fields):
    enqueue(_event('communication',action=action,actor=actor,resource=resource,status=status,trace_id=trace_id,payload=fields))


def record_api_call(method:str,url_or_path:str,status_code:int,duration_ms:float,actor:str='',trace_id:str='',request_bytes:int=0,response_bytes:int=0,remote_ip:str='',user_agent:str=''):
    sev='error' if status_code>=500 else ('warning' if status_code>=400 else 'info')
    enqueue(_event('api_call',action=method.upper(),actor=actor,resource=url_or_path,status=str(status_code),duration_ms=duration_ms,trace_id=trace_id,severity=sev,payload={'request_bytes':request_bytes,'response_bytes':response_bytes,'remote_ip':remote_ip,'user_agent':user_agent}))


def monitored_request(method:str,url:str,*,actor:str='',trace_id:str='',timeout:float=DEFAULT_TIMEOUT,**kwargs):
    t=time.perf_counter(); status=0; response=None
    try:
        response=httpx.request(method,url,timeout=timeout,**kwargs)
        status=response.status_code
        return response
    except Exception:
        status=599
        raise
    finally:
        record_api_call(method,url,status,(time.perf_counter()-t)*1000,actor=actor,trace_id=trace_id)
        flush_once()
