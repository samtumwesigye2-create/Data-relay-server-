import json, os, platform, socket, time, urllib.request
try:
 import psutil
except Exception:
 psutil=None
SERVER=os.environ.get('DRS_URL','').rstrip('/')
KEY=os.environ.get('DRS_API_KEY','')
INTERVAL=int(os.environ.get('DRS_INTERVAL','30'))
SOURCE=os.environ.get('DRS_SOURCE',socket.gethostname())
def send(payload):
 if not SERVER or not KEY:return
 data=json.dumps(payload).encode();req=urllib.request.Request(SERVER+'/events',data=data,headers={'Content-Type':'application/json','X-API-Key':KEY},method='POST')
 try: urllib.request.urlopen(req,timeout=3).read()
 except Exception: pass
while True:
 p={'category':'system_metric','source':SOURCE,'severity':'info','action':'sample','resource':'host','payload':{'platform':platform.platform()}}
 if psutil:
  p['payload'].update({'cpu_percent':psutil.cpu_percent(interval=None),'memory_percent':psutil.virtual_memory().percent,'disk_percent':psutil.disk_usage('/').percent,'network_bytes_sent':psutil.net_io_counters().bytes_sent,'network_bytes_recv':psutil.net_io_counters().bytes_recv})
 send(p);time.sleep(INTERVAL)
