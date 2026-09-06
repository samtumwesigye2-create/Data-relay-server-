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
    'titan':{'display_name':'UNG-TITAN','service_type':'asset_management','role':'Enterprise asset and heavy equipment management','criticality':'critical','env':'TITAN_BASE_URL'},
    'midas':{'display_name':'UNG-MIDAS','service_type':'finance','role':'Finance and financial operations','criticality':'critical','env':'MIDAS_BASE_URL'},
    'nova':{'display_name':'UNG-NOVA','service_type':'data_analytics','role':'Enterprise data and analytics','criticality':'critical','env':'NOVA_BASE_URL'},
    'hermes':{'display_name':'UNG-HERMES','service_type':'communications','role':'Enterprise communications services','criticality':'critical','env':'HERMES_BASE_URL'},
    'nemsis':{'display_name':'UNG-NEMSIS','service_type':'emergency_management','role':'National emergency management services','criticality':'critical','env':'NEMSIS_BASE_URL'},
    'horus':{'display_name':'UNG-HORUS','service_type':'uas_operations','role':'UAS and aerial operations','criticality':'critical','env':'HORUS_BASE_URL'},
    'sentinel':{'display_name':'UNG-SENTINEL','service_type':'security_operations','role':'Security operations center','criticality':'critical','env':'SENTINEL_BASE_URL'},
    'vector':{'display_name':'UNG-VECTOR','service_type':'warehouse_logistics','role':'Warehouse and logistics operations','criticality':'critical','env':'VECTOR_BASE_URL'},
    'aegis':{'display_name':'UNG-AEGIS','service_type':'protection_security','role':'Protection and security platform','criticality':'critical','env':'AEGIS_BASE_URL'},
    'nexus':{'display_name':'UNG-NEXUS','service_type':'integration','role':'Integration and interoperability services','criticality':'critical','env':'NEXUS_BASE_URL'},
    'apollo':{'display_name':'UNG-APOLLO','service_type':'planning_intelligence','role':'Planning and intelligence services','criticality':'critical','env':'APOLLO_BASE_URL'},
    'orion':{'display_name':'UNG-ORION','service_type':'national_operations','role':'National operations command','criticality':'critical','env':'ORION_BASE_URL'},
    'docs':{'display_name':'UNG-DOCS','service_type':'document_management','role':'Document and records services','criticality':'standard','env':'DOCS_BASE_URL'},
    'procure':{'display_name':'UNG-PROCURE','service_type':'procurement','role':'Procurement and sourcing services','criticality':'standard','env':'PROCURE_BASE_URL'},
    'infra25':{'display_name':'UNG-INFRA-25','service_type':'infrastructure','role':'Infrastructure services','criticality':'standard','env':'INFRA25_BASE_URL'},
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
