import asyncio
import json
from websockets import connect

WALLET_ADDRESS = "0x001d31846d08c23177011c6a523ed5b75823533e"
URL = "wss://api.hyperliquid.xyz/ws"
SOCKS_PROXY = "socks5://127.0.0.1:9050"  # Your Tor SOCKS5 proxy


async def debug_socks():
    print(f"[+] Starting Hyperliquid debug for wallet: {WALLET_ADDRESS}")
    print(f"[+] Using SOCKS5 proxy: {SOCKS_PROXY}")

    headers = {
        "Host": "api.hyperliquid.xyz",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://app.hyperliquid.xyz",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }

    try:
        async with connect(
            URL,
            proxy=SOCKS_PROXY,
            close_timeout=5,
        ) as ws:

            print("[✓] WebSocket connected through SOCKS5 proxy!")

            # Subscribe to wallet
            sub = {
                "method": "subscribe",
                "subscription": {"type": "webData2", "user": WALLET_ADDRESS},
            }
            await ws.send(json.dumps(sub))
            print("[+] Sent subscription")

            # Wait for messages
            print("[+] Waiting for messages...")
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                print(f"[MSG] {msg}...")  # Print first 200 chars
                print(msg)
                if "webData2" in msg:
                    print("[✓] Received target data!")
                    return

    except Exception as e:
        print(f"[ERROR] WebSocket failed: {e}")


if __name__ == "__main__":
    asyncio.run(debug_socks())
