from __future__ import annotations
import json, os, urllib.error, urllib.request
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
import app as core
from durable_delivery import Delivery

router = APIRouter(prefix='/v1/nexus', tags=['NEXUS Relay'])
JANUS_BASE_URL = os.getenv('IAM_BASE_URL', os.getenv('JANUS_BASE_URL','https://ung-iam-production.up.railway.app')).rstrip('/')

class NexusEnvelopeIn(BaseModel):
    message_id: str = Field(min_length=2,max_length=160)
    source_system: str = Field(min_length=2,max_length=120)
    target_system: str = Field(min_length=2,max_length=120)
    message_type: str = Field(min_length=2,max_length=160)
    payload: dict = Field(default_factory=dict)
    correlation_id: str | None = None
    trace_id: str | None = None
    schema_version: str = '1.0'
    priority: int = 50
    classification: str = 'internal'

def janus_auth(authorization: str | None):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401,'JANUS bearer token required')
    req=urllib.request.Request(JANUS_BASE_URL+'/v1/auth/introspect',data=b'',method='POST',headers={'Authorization':authorization,'User-Agent':'UNG-PULSAR/1.2.0'})
    try:
        with urllib.request.urlopen(req,timeout=5) as r:data=json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        if e.code in (401,403): raise HTTPException(401,'JANUS token invalid or expired')
        raise HTTPException(503,'JANUS authorization unavailable')
    except Exception: raise HTTPException(503,'JANUS authorization unavailable')
    principal=data.get('principal') or {}; perms=set(principal.get('permissions') or [])
    if 'nexus.messages.write' not in perms and 'ung.admin' not in perms and 'platform:service' not in perms:
        raise HTTPException(403,'Missing JANUS permission: nexus.messages.write')
    return principal

@router.post('/inbound',status_code=202)
def nexus_inbound(body:NexusEnvelopeIn,authorization:str|None=Header(None)):
    principal=janus_auth(authorization)
    delivery=Delivery(source=body.source_system,targets=[body.target_system],event_type=body.message_type,payload={'message_id':body.message_id,'correlation_id':body.correlation_id,'trace_id':body.trace_id,'schema_version':body.schema_version,'classification':body.classification,'principal_id':str(principal.get('id') or ''),'body':core.scrub(body.payload)},message_id=body.message_id,idempotency_key=body.message_id,priority=body.priority)
    created=core.delivery_planner.enqueue(delivery)
    return {'accepted':True,'duplicate':not created,'message_id':body.message_id,'status':'queued' if created else 'duplicate','target':body.target_system}

@router.get('/status/{message_id}')
def nexus_status(message_id:str,authorization:str|None=Header(None)):
    janus_auth(authorization)
    for row in core.delivery_store.list_queue(limit=1000):
        if row.get('message_id')==message_id:return {'found':True,'store':'queue','delivery':row}
    for row in core.delivery_store.list_dlq(limit=1000):
        if row.get('message_id')==message_id:return {'found':True,'store':'dlq','delivery':row}
    raise HTTPException(404,'message_not_found')
