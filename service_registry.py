from __future__ import annotations
import time
from typing import Dict,List
import app as core
from service_identity import configured_services,fingerprint

# Core services currently monitored by the independent Data Relay Server.
# Credentials remain in DRS_SERVICE_KEYS; this file contains no secrets.
SERVICE_PROFILES:Dict[str,dict]={
    'ugamap':{
        'display_name':'UGAMAP',
        'service_type':'mapping_navigation',
        'role':'National grid, mapping and routing',
        'criticality':'critical',
    },
    'ugaship':{
        'display_name':'UGASHIP',
        'service_type':'shipping_logistics',
        'role':'Shipping and logistics operations',
        'criticality':'critical',
    },
    'warehouse':{
        'display_name':'Warehouse',
        'service_type':'warehouse_operations',
        'role':'Receiving, inventory and dispatch operations',
        'criticality':'critical',
    },
}


def profiles()->List[dict]:
    configured=set(configured_services())
    out=[]
    for sid,p in SERVICE_PROFILES.items():
        out.append({'service_id':sid,**p,'credential_configured':sid in configured,'key_fingerprint':fingerprint(sid) if sid in configured else ''})
    # Preserve visibility for any future configured service not yet named above.
    for sid in sorted(configured-set(SERVICE_PROFILES)):
        out.append({'service_id':sid,'display_name':sid.upper(),'service_type':'future_service','role':'Registered future service','criticality':'standard','credential_configured':True,'key_fingerprint':fingerprint(sid)})
    return out


def live_status(stale_after_seconds:int=300)->List[dict]:
    now=time.time(); c=core.conn(); result=[]
    try:
        for p in profiles():
            sid=p['service_id']
            row=c.execute("SELECT created_at,severity,category,status FROM events WHERE source=? OR json_extract(payload_json,'$.verified_service_id')=? ORDER BY created_at DESC LIMIT 1",(sid,sid)).fetchone()
            audit=c.execute("SELECT recorded_at,result FROM audit WHERE json_extract(details_json,'$.verified_service_id')=? ORDER BY recorded_at DESC LIMIT 1",(sid,)).fetchone()
            last_event=float(row['created_at']) if row else 0.0
            last_audit=float(audit['recorded_at']) if audit else 0.0
            last_seen=max(last_event,last_audit)
            if not p['credential_configured']:
                state='not_configured'
            elif not last_seen:
                state='waiting_for_telemetry'
            elif now-last_seen>stale_after_seconds:
                state='stale'
            else:
                state='online'
            result.append({**p,'state':state,'last_seen':last_seen or None,'age_seconds':round(now-last_seen,1) if last_seen else None,'last_category':row['category'] if row else None,'last_severity':row['severity'] if row else None,'last_result':audit['result'] if audit else None})
    finally:
        c.close()
    return result
