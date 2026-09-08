from durable_delivery import Delivery, DeliveryPlanner

class Store:
    def __init__(self): self.keys=set(); self.saved=[]; self.dlq=[]
    def seen(self,key): return key in self.keys
    def save(self,d): self.keys.add(d.idempotency_key or d.message_id); self.saved.append(d)
    def dead_letter(self,d): self.dlq.append(d)

def test_idempotency_and_fanout():
    s=Store(); p=DeliveryPlanner(s)
    d=Delivery('UNG-NEXUS',['UNG-ZEUS'],'object.created',{},idempotency_key='same')
    assert p.enqueue(d) is True
    assert p.enqueue(Delivery('UNG-NEXUS',['UNG-ZEUS'],'object.created',{},idempotency_key='same')) is False
    f=p.fanout('UNG-NEXUS',['UNG-ZEUS','UNG-ZEUS','UNG-NOVA'],'x',{})
    assert [x.targets[0] for x in f]==['UNG-ZEUS','UNG-NOVA']

def test_retry_to_dead_letter():
    s=Store(); p=DeliveryPlanner(s); d=Delivery('A',['B'],'x',{},max_attempts=2)
    p.retry(d,'timeout'); assert d.status=='retry'
    p.retry(d,'timeout'); assert d.status=='dead-letter' and s.dlq==[d]
