import os

os.environ.setdefault('LAGRANGE_INBOUND_SECRET', 'test-inbound-secret')
os.environ.setdefault('LAGRANGE_INBOUND_KEY_ID', 'primary')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lagrange_entrypoint import app
from ung_lagrange_adapter import create_lagrange_router


def test_lagrange_routes_are_mounted_on_pulsar():
    routes = {route.path for route in app.routes}
    assert '/v1/lagrange/capabilities' in routes
    assert '/v1/lagrange/inbound' in routes


def test_lagrange_capabilities_report_pulsar_identity_without_starting_shared_app():
    route = next(route for route in app.routes if route.path == '/v1/lagrange/capabilities')
    data = route.endpoint()
    assert data['system'] == 'UNG-PULSAR'
    assert 'lagrange_inbound' in data['capabilities']
    assert 'message_relay' in data['capabilities']


def test_unsigned_lagrange_inbound_is_rejected_on_isolated_adapter():
    isolated = FastAPI()
    isolated.include_router(
        create_lagrange_router(
            'UNG-PULSAR',
            ['message_relay'],
            secret='test-inbound-secret',
            key_id='primary',
        )
    )
    response = TestClient(isolated).post(
        '/v1/lagrange/inbound',
        json={
            'message_id': 'probe-1',
            'source_system': 'UNG-LAGRANGE',
            'target_system': 'UNG-PULSAR',
            'message_type': 'acceptance.probe',
            'payload': {'probe': True},
            'schema_version': '1.0',
        },
    )
    assert response.status_code == 401
