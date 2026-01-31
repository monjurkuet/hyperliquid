import asyncio
import ssl
import json
import os
import socket
import base64
import struct
import argparse
from urllib.parse import urlparse
from websockets import connect

# Configuration
WALLET_ADDRESS = "0x001d31846d08c23177011c6a523ed5b75823533e"
URL = "wss://api.hyperliquid.xyz/ws"

async def debug_connection(proxy_url):
    print(f"[*] Starting Debug for Wallet: {WALLET_ADDRESS}")
    print(f"[*] Target URL: {URL}")
    print(f"[*] Proxy: {proxy_url}")

    # --- 1. Headers Setup ---
    headers = {
        "Host": "api.hyperliquid.xyz",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://app.hyperliquid.xyz",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Upgrade": "websocket",
        "Sec-WebSocket-Version": "13",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # --- 2. SSL Context ---
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    
    # --- 3. Proxy Connection ---
    parsed_url = urlparse(URL)
    host = parsed_url.hostname
    port = parsed_url.port or 443

    sock = None
    if proxy_url:
        try:
            proxy_parsed = urlparse(proxy_url)
            proxy_host = proxy_parsed.hostname
            proxy_port = proxy_parsed.port
            proxy_scheme = proxy_parsed.scheme
            
            print(f"\n[2] Connecting to {proxy_scheme.upper()} Proxy: {proxy_host}:{proxy_port}")
            sock = socket.create_connection((proxy_host, proxy_port), timeout=10)

            if proxy_scheme == 'socks5':
                print("    Performing SOCKS5 Handshake...")
                # 1. Auth Negotiation (No Auth)
                sock.sendall(b"\x05\x01\x00")
                auth_resp = sock.recv(2)
                if not auth_resp or auth_resp[0:2] != b"\x05\x00":
                    raise ConnectionError(f"SOCKS5 Auth failed: {auth_resp}")

                # 2. Connect Request
                req = b"\x05\x01\x00\x03" + bytes([len(host)]) + host.encode() + struct.pack("!H", port)
                sock.sendall(req)

                # 3. Reply
                resp = sock.recv(4)
                if not resp or len(resp) < 4:
                    raise ConnectionError("SOCKS5 handshake closed prematurely")
                
                if resp[1] != 0x00:
                    raise ConnectionError(f"SOCKS5 Connect failed code: {resp[1]}")
                
                # Consume address
                atyp = resp[3]
                if atyp == 1: sock.recv(6)
                elif atyp == 3: sock.recv(sock.recv(1)[0] + 2)
                elif atyp == 4: sock.recv(18)
                
                print("    [?] SOCKS5 tunnel established")
            
            else:
                # HTTP CONNECT
                print("    Performing HTTP CONNECT...")
                connect_msg = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n"
                sock.sendall(connect_msg.encode())
                
                response = b""
                while b"\r\n\r\n" not in response:
                    chunk = sock.recv(4096)
                    if not chunk: raise ConnectionError("Proxy closed")
                    response += chunk
                
                if "200" not in response.split(b"\n")[0].decode():
                    raise ConnectionError(f"HTTP Proxy failed: {response}")
                print("    [?] HTTP Tunnel established")

        except Exception as e:
            print(f"[?] Proxy Error: {e}")
            return

    # --- 4. WebSocket Handshake ---
    print(f"\n[3] Initiating WebSocket Handshake...")
    try:
        async with connect(
            URL,
            ssl=context,
            sock=sock,
            server_hostname=host,
            close_timeout=5
        ) as ws:
            print("[?] WebSocket Connected Successfully!")
            
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "webData2", 
                    "user": WALLET_ADDRESS
                }
            }
            print(f"    Sending subscription...")
            await ws.send(json.dumps(subscribe_msg))
            
            print("    Waiting for data...")
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                if "webData2" in msg:
                    print(f"    [??] Received Data! Length: {len(msg)}")
		    print(msg)
                    break
                    
    except Exception as e:
        print(f"[?] WebSocket Error: {e}")

if __name__ == "__main__":
    # Default to SOCKS5 for testing as requested
    proxy = os.environ.get("SOCKS_PROXY") or "socks5://127.0.0.1:9050"
    asyncio.run(debug_connection(proxy))
