# Walkthrough - Fast Proxy Hyperliquid Script

I have created a new script [hyperliquid_ws_no_delay.py](file:///d:/githubrepose/hyperliquid/hyperliquid_ws_no_delay.py) that removes all artificial delays and adds proxy support, while maintaining the existing data collection and database insertion logic.

## Changes

### New Script: [hyperliquid_ws_no_delay.py](file:///d:/githubrepose/hyperliquid/hyperliquid_ws_no_delay.py)

This script is a modified version of [hyperliquid_ws_stealthy.py](file:///d:/githubrepose/hyperliquid/hyperliquid_ws_stealthy.py) with the following changes:

1.  **Removed Delays**:
    - Removed `BreakManager` usage.
    - Removed [human_delay()](file:///d:/githubrepose/hyperliquid/hyperliquid_ws_stealthy.py#380-390) function and all calls to it.
    - Removed `asyncio.sleep()` calls used for stealth (browsing simulation, typing simulation, reading time).
    - Reduced timeouts to make the script fail faster if no data is received.

2.  **Added Proxy Support**:
    - The script now checks for a `PROXY_URL` in the [.env](file:///d:/githubrepose/hyperliquid/.env) file or environment variables.
    - If found, it sets `http_proxy`, `https_proxy`, `ws_proxy`, and `wss_proxy` environment variables, which the `websockets` library uses for connection routing.

3.  **Preserved Features**:
    - Database insertion logic ([insert_data_point](file:///d:/githubrepose/hyperliquid/hyperliquid_ws_no_delay.py#55-92)) is identical.
    - Wallet rotation logic is preserved but runs immediately without pauses.
    - Headers and SSL context generation are kept to ensure connection stability and basic stealth (avoiding immediate bot detection by headers).

## How to Run

1.  **Configure Proxy (Optional)**:
    Add `PROXY_URL` to your [.env](file:///d:/githubrepose/hyperliquid/.env) file:
    ```env
    PROXY_URL=http://user:pass@host:port
    ```

2.  **Run the Script**:
    ```bash
    python hyperliquid_ws_no_delay.py
    ```

3.  **Local Mode**:
    To run without SSH tunnel (if DB is local):
    ```bash
    python hyperliquid_ws_no_delay.py --local
    ```

## Verification

I ran a dry run of the script to ensure it parses arguments correctly:
```powershell
python hyperliquid_ws_no_delay.py --help
```
Output:
```
usage: hyperliquid_ws_no_delay.py [-h] [--local]

Hyperliquid Fast Monitor

options:
  -h, --help  show this help message and exit
  --local     Use local database connection without SSH tunnel
```
