import acceptance_entrypoint as pulsar
from ung_lagrange_adapter import create_lagrange_router

app = pulsar.app
app.include_router(create_lagrange_router('UNG-PULSAR', ['message_relay']))
