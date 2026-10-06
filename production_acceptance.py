from __future__ import annotations

from durable_delivery import Delivery


def enqueue_machine_mind_acceptance(planner, *, enabled: bool, acceptance_id: str) -> bool:
    """Queue one idempotent, harmless production acceptance delivery."""
    acceptance_id = (acceptance_id or '').strip()
    if not enabled or not acceptance_id:
        return False

    key = f'pulsar-machine-mind-acceptance:{acceptance_id}'
    delivery = Delivery(
        source='UNG-PULSAR',
        targets=['MACHINE-MIND'],
        event_type='production_acceptance',
        payload={
            'body': {
                'acceptance': True,
                'acceptance_id': acceptance_id,
            },
            'classification': 'internal',
            'schema_version': '1.0',
        },
        message_id=f'pulsar-machine-mind-acceptance-{acceptance_id}',
        idempotency_key=key,
        priority=100,
        max_attempts=3,
    )
    return planner.enqueue(delivery)
