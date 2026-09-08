from fastapi import HTTPException
from pydantic import BaseModel
from uuid import uuid4
import app as pulsar
from nexus_gateway import router as nexus_router

app = pulsar.app
app.include_router(nexus_router)

class NexusAcceptance(BaseModel):
    message_id: str
    source_system: str = 'UNG-NEXUS'
    target_system: str = 'UNG-PULSAR'

@app.post('/v1/nexus/acceptance', status_code=202)
def nexus_acceptance(p: NexusAcceptance):
    if p.source_system != 'UNG-NEXUS' or p.target_system != 'UNG-PULSAR':
        raise HTTPException(422, 'acceptance_route_mismatch')
    key = 'nexus-cert:' + p.message_id
    deliveries = pulsar.DeliveryPlanner.fanout('UNG-NEXUS', ['UNG-PULSAR'], 'production_acceptance', {'certification': True, 'message_id': p.message_id}, priority=100, max_attempts=2)
    d = deliveries[0]
    d.idempotency_key = key
    created = pulsar.delivery_planner.enqueue(d)
    return {'accepted': True, 'duplicate': not created, 'message_id': p.message_id, 'queue_message_id': d.message_id if created else None, 'idempotency_key': key}

@app.get('/v1/nexus/acceptance/{message_id}')
def nexus_acceptance_status(message_id: str):
    key = 'nexus-cert:' + message_id
    rows = pulsar.delivery_store.list_queue(limit=1000)
    matches = [r for r in rows if r.get('idempotency_key') == key]
    return {'message_id': message_id, 'persisted': len(matches) == 1, 'records': len(matches), 'status': matches[0].get('status') if matches else None}
