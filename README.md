# Hyperliquid Stealth Monitor & Data Tools

This repository contains a suite of tools for monitoring Hyperliquid wallet activity via WebSocket and importing PnL data, with support for secure database insertion.

## Components

### 1. Hyperliquid Stealth Monitor (`hyperliquid_ws_stealthy.py`)
A sophisticated WebSocket client designed to mimic human browser behavior while collecting real-time data from Hyperliquid.

**Features:**
- **Stealth Mode:** Mimics Chrome TLS fingerprint, headers, and behavior to avoid detection.
- **Multi-Target Monitoring:** Rotates through a list of wallets (`wallets.txt`).
- **Human-like Behavior:** Implements random delays, breaks, and browsing simulation.
- **Secure Insertion:** Inserts data into a MySQL database, optionally via SSH tunnel.
- **Resilience:** Handles connection drops and timeouts gracefully.

### 2. Wallet PnL Importer (`wallet_pnl_importer.py`)
A tool to normalize and import wallet PnL data from Excel files (`wallet_pnl.xlsx`) into the database.

**Features:**
- **Normalization:** Cleans and formats data (e.g., parsing money strings like `$1.5M`).
- **Idempotency:** Uses `ON DUPLICATE KEY UPDATE` to prevent duplicate wallet entries.
- **SSH Tunneling:** Supports secure remote database connections.

## Setup

### Prerequisites
- Python 3.8+
- MySQL Database

### Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

1.  Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
2.  Edit `.env` with your database and SSH credentials:
    ```ini
    # Database
    DB_HOST=localhost
    DB_PORT=3306
    DB_USER=root
    DB_PASSWORD=your_password
    DB_NAME=hyperliquid

    # SSH Tunnel (Optional)
    SSH_HOST=your.ssh.server.com
    SSH_PORT=22
    SSH_USER=ssh_user
    SSH_KEY_PATH=/path/to/private/key
    REMOTE_DB_HOST=127.0.0.1
    REMOTE_DB_PORT=3306
    ```
3.  Create a `wallets.txt` file with one wallet address per line for the monitor to track.

## Usage

### Running the Stealth Monitor

**Standard Mode (SSH Tunnel enabled by default if configured):**
```bash
python hyperliquid_ws_stealthy.py
```

**Local Mode (Disable SSH Tunnel):**
Use this flag if you are running the script on the same machine as the database or have a direct connection.
```bash
python hyperliquid_ws_stealthy.py --local
```

### Running the Importer

**Import from Excel:**
```bash
python wallet_pnl_importer.py wallet_pnl.xlsx
```

**Import with SSH Tunnel:**
```bash
python wallet_pnl_importer.py wallet_pnl.xlsx --ssh
```

**Create Schema:**
```bash
python wallet_pnl_importer.py --create-schema
```

## Project Structure

- `hyperliquid_ws_stealthy.py`: Main WebSocket monitor script.
- `wallet_pnl_importer.py`: Excel data importer script.
- `data_inserter_env.py`: Database connection and insertion logic.
- `hyperliquid_parser.py`: Parser for WebSocket JSON messages.
- `break_manager.py`: Logic for simulating human breaks.
- `schema.sql`: Database schema definition.
- `wallets.txt`: List of target wallets.
