**Purpose**
- **Repo:**: Provide concise guidance so AI coding agents can be immediately productive in this repository.

**Quick Context**
- **What it is:**: A small Python project that normalizes `wallet_pnl.xlsx` and inserts records into MySQL (`wallet_pnl_importer.py`).
- **Other tools:**: `toptraders.py` is an async browser script (uses `nodriver`) and is separate from the importer.

**Key Files**
- **`wallet_pnl_importer.py`:**: Core importer. Important functions: `parse_money`, `normalize_bias`, `normalize_wallet_type`, `prepare_row`, `get_db_connection_via_ssh`, `get_db_connection_direct`, `ensure_schema`, `run_import`.
- **`schema.sql`:**: DB schema used by `ensure_schema()`; creating or modifying schema should keep `wallets` and `wallet_snapshots` table shapes in mind.
- **`README.md`:**: Usage examples and environment variable list (copy `.env.example` -> `.env`).
- **`requirements.txt`:**: Declares runtime deps: `pandas`, `sshtunnel`, `PyMySQL`, `python-dotenv`, `openpyxl`.

**Project-specific patterns & constraints**
- **SSH tunnel support:**: Importer optionally establishes an SSH tunnel via `sshtunnel.SSHTunnelForwarder` and then connects to MySQL via PyMySQL on the bound local port. Env names: `SSH_HOST`, `SSH_PORT`, `SSH_USER`, `SSH_KEY_PATH`, `REMOTE_DB_HOST`, `REMOTE_DB_PORT`, `LOCAL_BIND_PORT`.
- **Two connection modes:**: `get_db_connection_via_ssh(...)` (tunnel + PyMySQL) and `get_db_connection_direct(...)` (direct PyMySQL). Use the same `DB_USER`, `DB_PASSWORD`, `DB_NAME` env vars either way.
- **Idempotent wallet upsert:**: Uses SQL pattern: `INSERT ... ON DUPLICATE KEY UPDATE wallet_type=VALUES(wallet_type), id=LAST_INSERT_ID(id)` so callers rely on `cursor.lastrowid` to obtain `wallet_id`. If changing this logic, preserve how wallet id is retrieved (LAST_INSERT_ID semantics).
- **Per-row commits:**: The importer currently commits after each row's snapshot insert. If you change to batched commits, ensure error handling and rollback semantics remain correct.
- **Normalization functions:**: `parse_money()` accepts strings like `$39.18M` and returns `Decimal`. Tests/changes should preserve decimal precision and suffix handling.

**Commands / Workflows**
- **Install deps:**: `python -m pip install -r requirements.txt`
- **Run importer (SSH tunnel):**: `python wallet_pnl_importer.py wallet_pnl.xlsx --ssh`
- **Run importer (create schema then import):**: `python wallet_pnl_importer.py wallet_pnl.xlsx --create-schema --ssh`
- **Run importer (direct DB):**: `python wallet_pnl_importer.py wallet_pnl.xlsx`

**Editing guidance for AI agents**
- **When editing DB logic:**: Preserve `ON DUPLICATE KEY ... LAST_INSERT_ID(id)` or replace with tests that confirm behavior; otherwise `cursor.lastrowid` semantics break.
- **When changing commit frequency:**: Tests or a small local MySQL run are recommended because current code commits per-row.
- **Env usage:**: The code uses `python-dotenv` (`load_dotenv()`), so prefer modifying `.env` for local runs rather than hardcoding secrets.
- **Logging & errors:**: The module uses `logging` at INFO level; keep messages helpful and idempotent-friendly.
- **Toptraders script:**: `toptraders.py` uses `nodriver` and async patterns; it's UI-scraping/automation code and not tied to importer DB logic.

**Integration points / external dependencies**
- **MySQL:**: Accessed via `PyMySQL`. Ensure compatible server versions and authentication method.
- **SSH host (optional):**: `sshtunnel` is used for tunneling. The project expects SSH key auth (see `SSH_KEY_PATH`).
- **Pandas/openpyxl:**: Used to read Excel files; large files may require chunked processing (not implemented).

**What an AI agent should do first when changing code**
- **Read:**: `wallet_pnl_importer.py` top-to-bottom and `schema.sql` to understand table shapes.
- **Run:**: `python -m pip install -r requirements.txt` then run `python wallet_pnl_importer.py wallet_pnl.xlsx --ssh` (or without `--ssh`) with a small test Excel file.
- **Preserve invariants:**: `LAST_INSERT_ID` upsert, per-row commit behavior, `parse_money` numeric semantics.

**Missing / not present**
- **No tests present:**: There are no automated tests—add unit tests for `parse_money`, `prepare_row`, and DB upsert behavior when refactoring.
- **No CI config:**: No GitHub Actions or similar configured.

If anything in this file is unclear or you'd like the instructions expanded (examples, a test scaffold, or CI steps), tell me which area to expand.
