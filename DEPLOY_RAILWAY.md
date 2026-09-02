# Railway deployment checklist

Deploy this repository as its own Railway service. Do not place it inside UGAMAP.

## Required variables

- `DRS_API_KEY` — long random administrator key.
- `DRS_SERVICE_KEYS` — JSON object containing independent keys for `ugamap`, `ugaship`, and `warehouse`.
- `DRS_RETENTION_DAYS=90`

Example shape only (never commit real values):

`{"ugamap":"<random-key>","ugaship":"<random-key>","warehouse":"<random-key>"}`

## Persistent storage

The current server defaults to SQLite (`data_relay.db`). Attach a Railway persistent volume and set:

`DRS_DB=/data/data_relay.db`

Mount the volume at `/data` so audit/event history survives redeploys.

## Deployment

Railway reads `railway.json` and starts:

`uvicorn server_entrypoint:app --host 0.0.0.0 --port $PORT`

Health check: `/health`
Dashboard: `/dashboard-ui`

## Acceptance checks

1. `/health` returns healthy.
2. `/dashboard-ui` loads the Data Relay console.
3. `/service-registry` with the admin API key shows UGAMAP, UGASHIP, and Warehouse.
4. `/integrity/verify` reports `ok: true`.
5. Send one UGAMAP event using `X-Service-ID: ugamap` and its service key.
6. Confirm UGAMAP changes from `never_seen` to an active/recent state in `/service-status`.

Do not connect production collectors until these checks pass.
