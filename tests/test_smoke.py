import importlib, json, os
from fastapi.testclient import TestClient


def load_app(tmp_path):
    os.environ['DRS_DB']=str(tmp_path/'relay.db')
    os.environ['DRS_API_KEY']='admin-test-key'
    os.environ['DRS_SERVICE_KEYS']=json.dumps({'ugamap':'ugamap-test','ugaship':'ugaship-test','warehouse':'warehouse-test'})
    import app, service_identity, service_registry, server_entrypoint
    importlib.reload(app); importlib.reload(service_identity); importlib.reload(service_registry); importlib.reload(server_entrypoint)
    return TestClient(server_entrypoint.app)


def test_health(tmp_path):
    c=load_app(tmp_path)
    r=c.get('/health')
    assert r.status_code==200
    assert r.json()['status']=='healthy'


def test_service_authenticated_event_and_integrity(tmp_path):
    c=load_app(tmp_path)
    r=c.post('/events',headers={'x-service-id':'ugamap','x-service-key':'ugamap-test'},json={'category':'api_call','source':'ugamap','action':'route','resource':'/route','status':'ok','payload':{'method':'GET'}})
    assert r.status_code==200
    assert r.headers.get('X-DRS-Service')=='ugamap'
    v=c.get('/integrity/verify',headers={'x-api-key':'admin-test-key'})
    assert v.status_code==200
    assert v.json()['ok'] is True


def test_audit_who_what_when_how(tmp_path):
    c=load_app(tmp_path)
    r=c.post('/audit/events',headers={'x-service-id':'warehouse','x-service-key':'warehouse-test'},json={'who':'staff-17','what':'inventory_adjustment','resource':'SKU-100','result':'success','how_method':'POST','how_channel':'warehouse-app','device_id':'device-9'})
    assert r.status_code==200
    a=c.get('/audit/events',headers={'x-api-key':'admin-test-key'})
    row=a.json()['results'][0]
    assert row['who']=='staff-17'
    assert row['what']=='inventory_adjustment'
    assert row['how_method']=='POST'
