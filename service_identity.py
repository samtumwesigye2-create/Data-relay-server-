from __future__ import annotations
import hashlib,hmac,json,os
from typing import Dict
from fastapi import HTTPException

# JSON map, e.g. {"ugamap":"secret1","ugaship":"secret2"}
_RAW=os.environ.get('DRS_SERVICE_KEYS','{}')
try:
    SERVICE_KEYS:Dict[str,str]=json.loads(_RAW) if _RAW else {}
except Exception:
    SERVICE_KEYS={}


def configured_services():
    return sorted(k for k,v in SERVICE_KEYS.items() if isinstance(k,str) and isinstance(v,str) and v)


def authenticate_service(service_id:str,service_key:str)->str:
    sid=(service_id or '').strip().lower()
    if not sid:
        raise HTTPException(401,'Missing service identity')
    expected=SERVICE_KEYS.get(sid)
    if not expected:
        raise HTTPException(401,'Unknown service identity')
    if not hmac.compare_digest(service_key or '',expected):
        raise HTTPException(401,'Invalid service key')
    return sid


def fingerprint(service_id:str)->str:
    value=SERVICE_KEYS.get((service_id or '').strip().lower(),'')
    if not value:return ''
    return hashlib.sha256(value.encode()).hexdigest()[:12]
