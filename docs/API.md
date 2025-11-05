# API

Base URL: `http://<host>:8080`

## Endpoints
- POST /api/dedup/start
- GET  /api/dedup/status
- POST /api/batch/create
- GET  /api/batch/list
- POST /api/sync/start/{batch_id}
- GET  /api/sync/status/{batch_id}
- POST /api/sort/start/{batch_id}
- GET  /api/sort/status/{batch_id}
- POST /api/workflow/run
- GET  /api/config
- PUT  /api/config
- GET  /api/dashboard
- POST /api/cleanup/run
- GET  /dbui  (sqlite-web separate process; see scripts/run.sh)
