# MT5 collector (Windows)

Separate process that runs on the same Windows machine as the MetaTrader 5 terminal,
reads closed-deal history through the official `MetaTrader5` Python package, normalizes it,
and pushes batches to the web app's authenticated ingest API.

Read-only: it never calls `order_send` or any other trading function.

Implemented in TASK-003. See `docs/metatrader-integration.md`.
