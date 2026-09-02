from __future__ import annotations
import os,time,json
import httpx

DRS_URL=os.environ.get('DRS_URL','').rstrip('/')
DRS_API_KEY=os.environ.get('DRS_API_KEY','')
DB_KIND=os.environ.get('DB_KIND','postgres').lower()
INTERVAL=int(os.environ.get('DB_COLLECT_INTERVAL','30'))
SOURCE=os.environ.get('DRS_SOURCE','database')


def send(payload):
    if not DRS_URL or not DRS_API_KEY:
        return False
    try:
        r=httpx.post(DRS_URL+'/events',headers={'x-api-key':DRS_API_KEY},json=payload,timeout=5)
        return r.status_code<300
    except Exception:
        return False


def postgres_metrics():
    import psycopg
    url=os.environ['DATABASE_URL']
    with psycopg.connect(url,connect_timeout=5) as c:
        with c.cursor() as cur:
            cur.execute("select count(*) from pg_stat_activity")
            connections=cur.fetchone()[0]
            cur.execute("select coalesce(max(extract(epoch from (now()-query_start))),0) from pg_stat_activity where state<>'idle'")
            longest=float(cur.fetchone()[0] or 0)
            lag=0.0
            try:
                cur.execute("select coalesce(max(extract(epoch from (now()-pg_last_xact_replay_timestamp()))),0)")
                lag=float(cur.fetchone()[0] or 0)
            except Exception:
                c.rollback()
        return {'connections':connections,'longest_active_query_seconds':longest,'replication_lag_seconds':lag}


def mysql_metrics():
    import pymysql
    c=pymysql.connect(host=os.environ['MYSQL_HOST'],user=os.environ['MYSQL_USER'],password=os.environ['MYSQL_PASSWORD'],database=os.environ.get('MYSQL_DATABASE'),port=int(os.environ.get('MYSQL_PORT','3306')),connect_timeout=5)
    try:
        with c.cursor() as cur:
            cur.execute("SHOW STATUS LIKE 'Threads_connected'")
            row=cur.fetchone(); connections=int(row[1]) if row else 0
            cur.execute("SHOW PROCESSLIST")
            rows=cur.fetchall(); longest=max([int(r[5] or 0) for r in rows],default=0)
            lag=0
            try:
                cur.execute('SHOW REPLICA STATUS')
                r=cur.fetchone()
                if r and len(r)>32 and r[32] is not None: lag=float(r[32])
            except Exception:
                pass
        return {'connections':connections,'longest_active_query_seconds':longest,'replication_lag_seconds':lag}
    finally:
        c.close()


def collect_once():
    started=time.perf_counter()
    metrics=postgres_metrics() if DB_KIND=='postgres' else mysql_metrics()
    duration_ms=(time.perf_counter()-started)*1000
    payload={'category':'database_activity','source':SOURCE,'severity':'info','action':'database_health_sample','status':'ok','duration_ms':duration_ms,'payload':metrics}
    if metrics.get('longest_active_query_seconds',0)*1000>=1000:
        payload['severity']='warning'; payload['payload']['query_ms']=metrics['longest_active_query_seconds']*1000
    send(payload)


if __name__=='__main__':
    while True:
        try: collect_once()
        except Exception as e:
            send({'category':'error','source':SOURCE,'severity':'critical','action':'db_collector_failure','status':'failed','payload':{'error':str(e)}})
        time.sleep(INTERVAL)
