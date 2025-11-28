# wallet_pnl Importer

This repository includes `wallet_pnl_importer.py` — a small, production-oriented importer that
normalizes `wallet_pnl.xlsx` and inserts the data into MySQL. Key characteristics:

- Uses `PyMySQL` and `sshtunnel` for SSH-tunneled connections.
- Parameterized queries and transactions.
- Idempotent wallet upserts via `ON DUPLICATE KEY UPDATE ... LAST_INSERT_ID(id)`.
- Batched snapshot inserts for efficiency.

Prerequisites
- Python 3.8+
- MySQL server reachable from the SSH host (if using SSH) or directly
- Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Environment
Copy `.env.example` to `.env` and edit the values. This project expects the following env vars (matching your final setup):

- `USE_SSH_TUNNEL` (optional): `true` or `false` (script uses `--ssh` flag; this is informational)
- `SSH_HOST`, `SSH_PORT`, `SSH_USER`, `SSH_KEY_PATH`
- `REMOTE_DB_HOST`, `REMOTE_DB_PORT`, `LOCAL_BIND_PORT`
- `DB_USER`, `DB_PASSWORD`, `DB_NAME`

Usage (Windows `cmd.exe`)

Create schema (optional) using SSH tunnel:

```
python wallet_pnl_importer.py wallet_pnl.xlsx --create-schema --ssh
```

Run import using SSH tunnel:

```
python wallet_pnl_importer.py wallet_pnl.xlsx --ssh
```

Run import directly (no tunnel):

```
python wallet_pnl_importer.py wallet_pnl.xlsx
```

Notes
- The importer uses a minimal dependency set (`PyMySQL`, `sshtunnel`, `pandas`, `python-dotenv`).
- Use a dedicated DB user with least privileges required for INSERT/SELECT.
- For higher-scale ingestion, consider parallelizing reads and chunked batch inserts and adding monitoring/metrics.

If you'd like, I can add:
- A dry-run mode that writes the normalized CSV to disk.
- Chunked processing for very large files and progress reporting.
