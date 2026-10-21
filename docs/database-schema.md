# Database Schema (proposed)

Types: `money` = `Numeric(18,2)`, `price` = `Numeric(20,10)`, `volume` = `Numeric(14,4)`,
`ts` = timezone-aware timestamp stored in UTC. All tables have `id` (PK) and `created_at`/`updated_at`.

## Entities

### user
`username` (unique), `password_hash`, `display_timezone` (default `Asia/Jakarta`), `week_start` (default `MONDAY`).

### trading_account
| column | type | notes |
| --- | --- | --- |
| user_id | FK user | data isolation |
| account_name | text | user label |
| broker_name, broker_server | text | from terminal |
| platform | enum `MT4`,`MT5`,`CSV`,`MOCK` | |
| login_hash | text | SHA-256 of `platform:server:login`; raw login not stored |
| account_currency | char(3) | |
| account_type | enum `REAL`,`DEMO`,`CONTEST`,`UNKNOWN` | |
| margin_mode | enum `HEDGING`,`NETTING`,`UNKNOWN` | MT5 only |
| server_utc_offset_mode | enum `AUTO`,`FIXED`,`NY_CLOSE` | how server time → UTC (`NY_CLOSE` = New York time + 7h) |
| server_utc_offset_minutes | int null | when FIXED |
| initial_balance | money null | |
| is_simulated | bool | true for mock data, shown in UI |
| last_synced_at | ts null | last successful sync |

Unique: `(user_id, platform, login_hash)`.

### ingest_token
`account_id` FK, `token_hash`, `label`, `last_used_at`, `revoked_at`. Plain token shown once.

### symbol_spec
`account_id` FK, `symbol` (broker name, e.g. `XAUUSD.m`), `base_symbol` (normalized, optional),
`digits`, `point`, `contract_size`, `tick_size`, `tick_value`, `profit_currency`,
`asset_class` (`FX`,`METAL`,`INDEX`,`CRYPTO`,`OTHER`), `pip_size` (effective), `pip_size_source`
(`DERIVED`,`USER`), `pip_unit_label`. Unique `(account_id, symbol)`.

### trade_deal (raw, source of truth)
| column | notes |
| --- | --- |
| account_id | FK |
| sync_run_id | FK, first run that inserted it |
| external_deal_id | MT5 deal ticket; MT4 synthetic `<ticket>:open` / `<ticket>:close` |
| external_order_id, external_position_id | |
| symbol | |
| deal_type | `BUY`,`SELL`,`BALANCE`,`CREDIT`,`COMMISSION`,`OTHER` |
| entry | `IN`,`OUT`,`INOUT`,`OUT_BY`,`NONE` |
| time_server_raw | broker server time as reported |
| time_utc | normalized |
| price, volume | |
| profit, commission, swap, fee | money, signed, as reported |
| sl_price, tp_price | null when unknown |
| magic, comment, reason | |
| raw_payload | JSON, original record for audit |

Unique: `(account_id, external_deal_id)`. Indexes: `(account_id, external_position_id)`, `(account_id, time_utc)`.
Non-trade deals (balance, credit) are stored for balance series but excluded from trade analytics.

### trade_order (raw)
`account_id`, `external_order_id` (unique per account), `external_position_id`, `symbol`, `order_type`,
`time_setup_utc`, `time_done_utc`, `volume_initial`, `price_open`, `sl_price`, `tp_price`, `raw_payload`.
Used to obtain the SL/TP set on the order that opened a position.

### trade_position (derived, rebuildable)
| column | notes |
| --- | --- |
| account_id, external_position_id | unique together |
| symbol, direction (`BUY`/`SELL`) | |
| volume_lots | max open volume |
| open_time, close_time | UTC; `close_time` = last exit deal |
| open_price | volume-weighted entry |
| close_price | volume-weighted exit |
| realized_gross_profit | Σ deal profit |
| commission, swap, fees | Σ over all deals of the position |
| realized_net_profit | gross + commission + swap + fees |
| initial_sl_price, initial_tp_price | from opening order/deal; null if unknown |
| sl_tp_source | `OPEN_ORDER`,`OPEN_DEAL`,`LAST_KNOWN`,`NONE` |
| exit_count | number of exit deals (partial closes) |
| status | `CLOSED`,`OPEN` (open ones excluded from analytics) |
| trading_session | computed from open_time + session config |
| account_currency | copied for safety |
| source_metadata | JSON |

Indexes: `(account_id, close_time)`, `(account_id, symbol, close_time)`.

### trade_annotation (1:1 with position, user-owned, never touched by sync)
`trade_position_id` (unique), `setup_name`, `trading_session_override`, `market_condition`,
`entry_timeframe`, `higher_timeframe_context`, `entry_reason`, `exit_reason`, `rule_followed` (bool null),
`emotional_state`, `screenshot_ref`, `personal_notes`. Tags via `annotation_tag` (M:N to `tag`).

### tag
`user_id`, `name`, `kind` (`MISTAKE`,`ICT`,`SETUP`,`CUSTOM`). Unique `(user_id, kind, name)`.
Seeded ICT tags: Liquidity Sweep, FVG, CISD, PDH/PDL, Asia H/L, London H/L, New York H/L.

### trade_review
`user_id`, `account_id` null (all accounts), `review_period` (`WEEK`,`MONTH`,`CUSTOM`),
`period_start`, `period_end` (dates in user TZ), `timezone`, `metrics_snapshot` JSON,
`performance_summary`, `strengths`, `mistakes`, `lessons_learned`, `improvement_plan`,
`stop_doing`, `continue_doing`, `next_week_goals`, `auto_summary`, `llm_summary` null.
Unique `(user_id, account_id, review_period, period_start)`.

### sync_run
`account_id`, `source` (`MT5_COLLECTOR`,`MT4_EA`,`CSV`,`MOCK`), `started_at`, `finished_at`,
`range_from`, `range_to`, `status` (`RUNNING`,`SUCCESS`,`FAILED`,`PARTIAL`), `deals_received`,
`deals_inserted`, `deals_duplicate`, `positions_rebuilt`, `error_code`, `error_message` (sanitized),
`deals_updated`, `retry_of_id`, `failed_payload` (JSON batch kept only for failed runs so they can be retried).

## Idempotency

- Insert deals with `ON CONFLICT (account_id, external_deal_id) DO NOTHING` (or compare-and-update
  when the broker corrects a record; differences are logged on the sync run).
- After insert, rebuild only positions whose `external_position_id` received new deals.
- A batch may overlap previous ranges; the overlap window is intentional (late deals, server-time skew).
