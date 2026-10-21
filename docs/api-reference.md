# API Reference

Interactive OpenAPI docs: `/api/docs` (schema at `/api/openapi.json`). All routes are under
`/api/v1`. User routes use the browser session cookie (or no auth on loopback-only installs);
collector routes use a per-account bearer token. All endpoints are read-only with respect to
trading — none can place, modify or close orders.

| Method & path | Auth | Purpose |
| --- | --- | --- |
| `GET /health` | none | Liveness + database status |
| `GET/POST /accounts`, `PATCH /accounts/{id}` | session | List / create (returns token once) / update accounts |
| `POST /accounts/demo` | session | Create SIMULATED demo account |
| `POST /accounts/{id}/token` | session | Rotate collector token (revokes previous) |
| `GET /accounts/{id}/sync-runs` | session | Sync history |
| `POST /accounts/{id}/sync-runs/{run}/retry` | session | Re-ingest stored payload of a failed run |
| `POST /accounts/{id}/import/csv` | session | Upload MT4/MT5 history CSV (≤5 MB) |
| `POST /accounts/{id}/rebuild` | session | Rebuild derived positions from raw deals |
| `GET /accounts/{id}/reconciliation` | session | Deal vs position totals check |
| `POST /ingest` | bearer | Normalized batch from MT5 collector (rate limited) |
| `POST /ingest/mt4` | bearer | Ticket batch from the MT4 EA |
| `GET /analytics/summary\|equity\|daily\|periods\|breakdown\|calendar` | session | Metrics (filters below) |
| `GET /trades`, `GET /trades/{id}` | session | Paginated journal / trade detail |
| `PUT /trades/{id}/annotation` | session | Partial annotation update (tags replace per kind) |
| `GET /trades/export.csv` | session | CSV export (formula-injection safe) |
| `GET /tags` | session | User tags by kind |
| `GET/PUT /reviews/weekly?week=YYYY-MM-DD` | session | Weekly review data / save reflection |
| `POST /reviews/weekly/llm-summary` | session | Optional LLM narrative (409 when disabled) |

Common analytics filters: `account_id` (repeatable), `date_from`, `date_to` (local dates in the
display timezone, by close time), `symbol`, `direction`, `session`, `setup`, `tag`,
`outcome=WIN|LOSS|BREAKEVEN`. Amounts are grouped per account currency (`by_currency`).
