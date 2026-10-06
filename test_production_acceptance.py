from production_acceptance import enqueue_machine_mind_acceptance


class FakePlanner:
    def __init__(self):
        self.items = []

    def enqueue(self, delivery):
        self.items.append(delivery)
        return True


def test_acceptance_flag_enqueues_exactly_one_machine_mind_delivery():
    planner = FakePlanner()

    created = enqueue_machine_mind_acceptance(planner, enabled=True, acceptance_id='cert-2026-10-06')

    assert created is True
    assert len(planner.items) == 1
    delivery = planner.items[0]
    assert delivery.source == 'UNG-PULSAR'
    assert delivery.targets == ['MACHINE-MIND']
    assert delivery.event_type == 'production_acceptance'
    assert delivery.idempotency_key == 'pulsar-machine-mind-acceptance:cert-2026-10-06'
    assert delivery.message_id == 'pulsar-machine-mind-acceptance-cert-2026-10-06'
    assert delivery.payload['body']['acceptance'] is True


def test_acceptance_flag_disabled_does_not_enqueue():
    planner = FakePlanner()

    created = enqueue_machine_mind_acceptance(planner, enabled=False, acceptance_id='cert-2026-10-06')

    assert created is False
    assert planner.items == []
