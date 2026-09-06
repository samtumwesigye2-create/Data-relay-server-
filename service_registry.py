from __future__ import annotations
import os,time
from typing import Dict,List
import app as core
from service_identity import configured_services,fingerprint

SERVICE_PROFILES:Dict[str,dict]={
    'atlas':{'display_name':'UNG-ATLAS','service_type':'control_infrastructure','role':'Enterprise control infrastructure and system orchestration','criticality':'critical','env':'ATLAS_BASE_URL'},
    'core':{'display_name':'UNG-CORE','service_type':'core_platform','role':'Shared national grid core services','criticality':'critical','env':'CORE_BASE_URL'},
    'iam':{'display_name':'UNG-IAM','service_type':'identity_access','role':'Identity, access and authentication services','criticality':'critical','env':'IAM_BASE_URL'},
    'mdm':{'display_name':'UNG-MDM','service_type':'master_data','role':'Master data and reference data management','criticality':'critical','env':'MDM_BASE_URL'},
    'noc':{'display_name':'UNG-NOC','service_type':'operations_command','role':'National operations command and coordination','criticality':'critical','env':'NOC_BASE_URL'},
    'ugamap':{'display_name':'UGAMAP','service_type':'mapping_navigation','role':'National grid, mapping and routing','criticality':'critical'},
    'ugaship':{'display_name':'UGASHIP','service_type':'shipping_logistics','role':'Shipping and logistics operations','criticality':'critical'},
    'warehouse':{'display_name':'Warehouse','service_type':'warehouse_operations','role':'Receiving, inventory and dispatch operations','criticality':'critical'},
    'backup':{'display_name':'Backup','service_type':'backup_recovery','role':'Backup health, availability and recovery telemetry','criticality':'critical'},
}


def profiles()->List[dict]:
    configured=set(configured_services())
    out=[]
    for sid,p0 in SERVICE_PROFILES.items():
        p=dict(p0); env_name=p.pop('env',None)
        monitored=bool(env_name and os.getenv(env_name,''))
        api_key_mode=(sid=='atlas' and bool(core.API_KEY))
        credential_configured=sid in configured or monitored or api_key_mode
        fp=fingerprint(sid) if sid in configured else ('internal-monitor' if monitored else ('api-key' if api_key_mode else ''))
        out.append({'service_id':sid,**p,'credential_configured':credential_configured,'key_fingerprint':fp})
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
