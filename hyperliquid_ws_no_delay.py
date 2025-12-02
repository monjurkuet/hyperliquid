import asyncio
import argparse
import ssl
import base64
import os
import json
import random
import re
import time
import struct
import socket
from websockets import connect
from websockets.legacy.client import WebSocketClientProtocol
import threading
from datetime import datetime, timedelta
import pymysql
from urllib.parse import urlparse

# Import the custom break manager - REMOVED for fast version
# from break_manager import BreakManager 
from data_inserter_env import load_env_config, MySQLStealthClient 
from hyperliquid_parser import parse_hyperliquid_data

URL = "wss://api.hyperliquid.xyz/ws"
PATTERN = re.compile(r'"channel"\s*:\s*"webData2"')

with open('wallets.txt', 'r') as file:
    # Using a list comprehension for concise reading and cleaning
    wallets = [line.strip() for line in file if line.strip()]

class MultiTargetFastClient:
    def __init__(self, wallets, db_config, ssh_config, proxy_url=None):
        self.wallets = wallets
        self.current_wallet_index = 0
        self.session_id = self.generate_session_id()
        self.connection_count = 0
        self.last_activity = time.time()
        
        # Database configurations
        self.db_config = db_config  
        self.ssh_config = ssh_config
        
        # Proxy configuration
        self.proxy_url = proxy_url
        if self.proxy_url:
            self.configure_proxy()

        # Persistent DB client
        self.db_client = None

    def _ensure_db_connection(self):
        """Ensure database connection is active, reconnecting if necessary."""
        if self.db_client is None:
            try:
                self.db_client = MySQLStealthClient(self.ssh_config, self.db_config)
                self.db_client.__enter__()
            except Exception as e:
                print(f"[❌] Failed to connect to DB: {e}")
                self.db_client = None
                raise

        # Optional: Check if connection is alive (ping)
        # Note: MySQLStealthClient.conn is the pymysql connection
        try:
            if self.db_client and self.db_client.conn:
                self.db_client.conn.ping(reconnect=True)
        except Exception as e:
            print(f"[⚠️] DB Connection lost ({e}). Reconnecting...")
            self.close_db()
            try:
                self.db_client = MySQLStealthClient(self.ssh_config, self.db_config)
                self.db_client.__enter__()
            except Exception as ex:
                print(f"[❌] Reconnection failed: {ex}")
                self.db_client = None
                raise

    def close_db(self):
        """Safely close the database connection."""
        if self.db_client:
            try:
                self.db_client.__exit__(None, None, None)
            except Exception as e:
                print(f"[⚠️] Error closing DB client: {e}")
            finally:
                self.db_client = None

    def configure_proxy(self):
        """Set environment variables for proxy support."""
        print(f"[🔧] Configuring proxy: {self.proxy_url}")
        os.environ['http_proxy'] = self.proxy_url
        os.environ['https_proxy'] = self.proxy_url
        os.environ['ws_proxy'] = self.proxy_url
        os.environ['wss_proxy'] = self.proxy_url

    # --- Insertion Helper Method ---
    def insert_data_point(self, wallet_address, raw_data_json):
        """
        Parses the raw JSON string and inserts data into the three database tables 
        (snapshots, positions, orders).
        """
        try:
            # 1. Parse the JSON message string into a dict
            full_data_dict = json.loads(raw_data_json)
            raw_data_dict = full_data_dict.get("data")
            
            if not raw_data_dict:
                print("⚠️ Received JSON is missing the 'data' key.")
                return

            # 2. Extract snapshot time (needed for the snapshot table)
            # This is available in the top-level clearinghouseState dict
            clearinghouse_state = raw_data_dict.get('clearinghouseState', {})
            snapshot_time_ms = clearinghouse_state.get('time')

            if not snapshot_time_ms:
                 print("⚠️ Received JSON is missing 'clearinghouseState.time'. Cannot insert.")
                 return

            # 3. Parse and structure the data for all three tables
            parsed_data = parse_hyperliquid_data(raw_data_dict)
            
            # 4. Insert using the persistent client with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self._ensure_db_connection()
                    self.db_client.insert_hyperliquid_data(
                        wallet_address, 
                        snapshot_time_ms, 
                        parsed_data,
                        raw_data_json # Pass the full raw JSON string
                    )
                    # If successful, break the retry loop
                    break
                except Exception as e:
                    print(f"[⚠️] DB Insert Error (Attempt {attempt+1}/{max_retries}): {e}")
                    # Force reconnection on next attempt
                    self.close_db()
                    if attempt == max_retries - 1:
                        print(f"[❌] FAILED TO INSERT data for {wallet_address} after retries.")
                
        except Exception as e:
            print(f"[❌] Error processing/inserting data for {wallet_address}: {e}")

    def generate_session_id(self):
        """Generate realistic Chrome session ID"""
        return ''.join(random.choices('0123456789abcdef', k=32))
    
    def get_current_wallet(self):
        """Get current target wallet"""
        return self.wallets[self.current_wallet_index]
    
    def advance_to_next_wallet(self):
        """Move to next wallet linearly and fast"""
        self.current_wallet_index = (self.current_wallet_index + 1) % len(self.wallets)
        current_wallet = self.get_current_wallet()
        print(f"🔄 Switching to wallet: {current_wallet}")
        return current_wallet
    
    def random_key(self):
        """Generate WebSocket key"""
        return base64.b64encode(os.urandom(16)).decode()
    
    def chrome_user_agent(self):
        """Rotate between recent Chrome versions"""
        versions = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        return random.choice(versions)
    
    def realistic_headers(self):
        """Generate browser-realistic headers"""
        sec_ch_ua_versions = [
            '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
            '"Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="99"',
            '"Google Chrome";v="121", "Chromium";v="121", "Not A(Brand";v="99"'
        ]
        
        return [
            ("Host", "api.hyperliquid.xyz"),
            ("Connection", "Upgrade"),
            ("Pragma", "no-cache"),
            ("Cache-Control", "no-cache"),
            ("User-Agent", self.chrome_user_agent()),
            ("Upgrade", "websocket"),
            ("Origin", "https://app.hyperliquid.xyz"),
            ("Sec-WebSocket-Version", "13"),
            ("Accept-Encoding", "gzip, deflate, br"),
            ("Accept-Language", "en-US,en;q=0.9"),
            ("Sec-Ch-Ua", random.choice(sec_ch_ua_versions)),
            ("Sec-Ch-Ua-Mobile", "?0"),
            ("Sec-Ch-Ua-Platform", '"Windows"'),
            ("Sec-WebSocket-Key", self.random_key()),
            ("Sec-WebSocket-Extensions", "permessage-deflate; client_max_window_bits"),
            ("Sec-Fetch-Dest", "websocket"),
            ("Sec-Fetch-Mode", "websocket"),
            ("Sec-Fetch-Site", "cross-site"),
        ]
    
    def create_ssl_context(self):
        """Create SSL context"""
        context = ssl.create_default_context()
        # Keep cipher suite for compatibility/stealth but remove delays
        chrome_ciphers = [
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384", 
            "TLS_CHACHA20_POLY1305_SHA256",
            "ECDHE-ECDSA-AES128-GCM-SHA256",
            "ECDHE-RSA-AES128-GCM-SHA256",
            "ECDHE-ECDSA-AES256-GCM-SHA384",
            "ECDHE-RSA-AES256-GCM-SHA384",
            "ECDHE-ECDSA-CHACHA20-POLY1305",
            "ECDHE-RSA-CHACHA20-POLY1305",
            "ECDHE-RSA-AES128-SHA",
            "ECDHE-RSA-AES256-SHA",
            "AES128-GCM-SHA256",
            "AES256-GCM-SHA384",
            "AES128-SHA",
            "AES256-SHA"
        ]
        
        try:
            context.set_ciphers(":".join(chrome_ciphers))
        except:
            context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS")
        
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        
        return context
    
    async def connect_fast(self):
        """Establish connection immediately, ensuring proxy usage if configured."""
        self.connection_count += 1
        
        ssl_context = self.create_ssl_context()
        headers = self.realistic_headers()
        
        current_wallet = self.get_current_wallet()
        print(f"[🔗] Connecting for wallet: {current_wallet[:10]}...")

        # Parse the target URL to get host and port
        parsed_url = urlparse(URL)
        host = parsed_url.hostname
        port = parsed_url.port or 443

        # Prioritize SOCKS_PROXY env var, then configured proxy_url
        proxy_url = os.environ.get('SOCKS_PROXY') or self.proxy_url
        
        sock = None
        if proxy_url:
            try:
                # Parse proxy URL
                proxy_parsed = urlparse(proxy_url)
                proxy_host = proxy_parsed.hostname
                proxy_port = proxy_parsed.port
                proxy_scheme = proxy_parsed.scheme

                print(f"[🛡️] Connecting via {proxy_scheme.upper()} proxy: {proxy_host}:{proxy_port}")

                # 1. Establish TCP connection to the proxy
                sock = socket.create_connection((proxy_host, proxy_port), timeout=10)

                if proxy_scheme == 'socks5':
                    # --- SOCKS5 HANDSHAKE ---
                    # 1. Auth Negotiation (Method 0: No Auth)
                    # Ver=5, NMethods=1, Method=0
                    sock.sendall(b"\x05\x01\x00")
                    auth_resp = sock.recv(2)
                    if not auth_resp or auth_resp[0:2] != b"\x05\x00":
                        raise ConnectionError(f"SOCKS5 Auth failed. Response: {auth_resp}")

                    # 2. Connect Request (ATYP=3 Domain name)
                    # Ver=5, Cmd=1(Connect), Rsv=0, Atyp=3
                    # Addr = len(host) + host
                    # Port = 2 bytes big-endian
                    req = b"\x05\x01\x00\x03" + bytes([len(host)]) + host.encode() + struct.pack("!H", port)
                    sock.sendall(req)

                    # 3. Read Reply
                    # Ver, Rep, Rsv, Atyp (4 bytes)
                    resp = sock.recv(4)
                    if not resp or len(resp) < 4:
                        raise ConnectionError("SOCKS5 handshake closed prematurely")
                    
                    if resp[1] != 0x00:
                        raise ConnectionError(f"SOCKS5 Connect failed with error code: {resp[1]}")
                    
                    # Consume the bound address field to clear the buffer
                    atyp = resp[3]
                    if atyp == 1: # IPv4
                        sock.recv(4 + 2)
                    elif atyp == 3: # Domain
                        addr_len = sock.recv(1)[0]
                        sock.recv(addr_len + 2)
                    elif atyp == 4: # IPv6
                        sock.recv(16 + 2)
                        
                    print("[✅] SOCKS5 tunnel established")

                else:
                    # --- HTTP CONNECT HANDSHAKE (Fallback) ---
                    connect_msg = f"CONNECT {host}:{port} HTTP/1.1\r\n"
                    connect_msg += f"Host: {host}:{port}\r\n"
                    if proxy_parsed.username and proxy_parsed.password:
                        auth = base64.b64encode(f"{proxy_parsed.username}:{proxy_parsed.password}".encode()).decode()
                        connect_msg += f"Proxy-Authorization: Basic {auth}\r\n"
                    connect_msg += "\r\n"
                    
                    sock.sendall(connect_msg.encode())

                    response = b""
                    while b"\r\n\r\n" not in response:
                        chunk = sock.recv(4096)
                        if not chunk:
                            raise ConnectionError("Proxy closed connection during handshake")
                        response += chunk
                    
                    status_line = response.split(b"\n")[0].decode()
                    if "200" not in status_line:
                        raise ConnectionError(f"Proxy handshake failed: {status_line}")
                    
                    print("[✅] HTTP Proxy tunnel established")

            except Exception as e:
                print(f"[❌] Proxy connection failed: {e}")
                if sock:
                    sock.close()
                raise

            except Exception as e:
                print(f"[❌] Proxy connection failed: {e}")
                if sock:
                    sock.close()
                raise

        # 4. Connect via websockets
        # Prepare arguments dynamically to avoid TypeError with extra_headers + sock
        connect_args = {
            "ssl": ssl_context,
            "ping_interval": 30,
            "ping_timeout": 10,
            "close_timeout": 10
        }

        if sock:
            connect_args["sock"] = sock
            connect_args["server_hostname"] = host
            # Note: We omit extra_headers when using a pre-connected socket 
            # because it causes a TypeError in some websockets versions.
        else:
            connect_args["extra_headers"] = headers

        ws = await connect(URL, **connect_args)
        
        print("[✅] Connection established")
        return ws
    
    async def subscribe_to_wallet(self, ws, wallet_address):
        """Subscribe to specific wallet immediately"""
        # No browsing simulation delay
        
        subscribe_msg = {
            "method": "subscribe",
            "subscription": {
                "type": "webData2", 
                "user": wallet_address
            }
        }
        
        message = json.dumps(subscribe_msg)
        
        # No typing simulation delay
        
        await ws.send(message)
        print(f"[📡] Monitoring: {wallet_address}")
    
    async def collect_wallet_data(self, wallet_address, timeout_minutes=5):
        """Collect data for a specific wallet with timeout"""
        print(f"\n{'='*60}")
        print(f"🎯 COLLECTING DATA FOR: {wallet_address}")
        print(f"{'='*60}")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        data_collected = False
        
        try:
            ws = await self.connect_fast()
            await self.subscribe_to_wallet(ws, wallet_address)
            
            while time.time() - start_time < timeout_seconds:
                try:
                    # Wait for message with timeout
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    self.last_activity = time.time()
                    
                    if PATTERN.search(msg):
                        print(f"\n🎉 DATA COLLECTED FOR {wallet_address}!")
                        print("="*50)
                        
                        # --- INSERTION LOGIC ---
                        self.insert_data_point(wallet_address, msg)
                        # -----------------------

                        data_collected = True
                        
                        # No reading time delay
                        
                        break
                        
                except asyncio.TimeoutError:
                    print("[⏰] Waiting for data...")
                    # Send ping to keep connection alive
                    try:
                        await ws.ping()
                    except:
                        break
                    continue
            
            # No disconnect delay
            
            await ws.close()
            
        except Exception as e:
            print(f"[❌] Error collecting data for {wallet_address}: {e}")
        
        if not data_collected:
            print(f"[⚠️] No data received for {wallet_address} within {timeout_minutes} minutes")
        
        return data_collected
    
    def print_session_summary(self):
        """Print summary of data collection session"""
        print(f"\n{'='*60}")
        print("📊 SESSION SUMMARY")
        print(f"{'='*60}")
        print(f"Total wallets monitored: {len(self.wallets)}")
        print(f"Total connections made: {self.connection_count}")
        print(f"✅ All collected data points were inserted directly into the database.")
        print(f"{'='*60}\n")
    
    async def run_multi_target_monitor(self, cycles_per_wallet=1):
        """
        Main monitoring loop for multiple wallets, running continuously.
        """
        print("[*] Starting Multi-Target Fast Monitor")
        print(f"🎯 Monitoring {len(self.wallets)} wallets")
        print(f"🔄 {cycles_per_wallet} cycle(s) per wallet per rotation")
        print("[*] Mode: Continuous (Runs indefinitely)")
        print("="*60)
        
        total_cycles = 0
        wallet_cycle_count = {wallet: 0 for wallet in self.wallets}
        
        try:
            while True:
                current_wallet = self.get_current_wallet()
                
                # Check if a full rotation is complete
                if all(count >= cycles_per_wallet for count in wallet_cycle_count.values()):
                    # Full rotation complete. Reset counters.
                    print(f"\n=== CONTINUOUS MONITORING ROTATION COMPLETE. STARTING NEW ROTATION ===")
                    wallet_cycle_count = {wallet: 0 for wallet in self.wallets}
                    
                    # No long break
                    continue # Restart the loop iteration
                    
                # If the current wallet is done but others aren't, move on
                if wallet_cycle_count[current_wallet] >= cycles_per_wallet:
                    # print(f"[✅] Completed {cycles_per_wallet} cycles for {current_wallet}. Skipping.")
                    self.advance_to_next_wallet()
                    continue
                
                # No break manager check
                
                # Collect data for current wallet
                print(f"\n[🔍] Cycle {wallet_cycle_count[current_wallet] + 1}/{cycles_per_wallet} for {current_wallet}")
                
                data_collected = await self.collect_wallet_data(
                    current_wallet, 
                    timeout_minutes=1 # Reduced timeout for fast mode
                )
                
                wallet_cycle_count[current_wallet] += 1
                total_cycles += 1
                
                if data_collected:
                    print(f"[✅] Data successfully collected for {current_wallet}")
                else:
                    print(f"[⚠️] No data collected for {current_wallet} this cycle")
                
                # Advance to next wallet immediately
                self.advance_to_next_wallet()
                
        except KeyboardInterrupt:
            print("\n[⏹️] Monitoring stopped by user")
        except Exception as e:
            print(f"\n[💥] Unexpected error: {e}")
        finally:
            self.close_db()
            self.print_session_summary()

# 🎯 Main function (Continuous Monitoring)
async def main():
    """Main entry point for continuous monitoring."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Hyperliquid Fast Monitor')
    parser.add_argument('--local', action='store_true', help='Use local database connection without SSH tunnel')
    args = parser.parse_args()

    # Load configuration
    config = load_env_config()
    
    # Override SSH tunnel setting if --local is provided
    if args.local:
        config['SSH_CONFIG']['use_tunnel'] = False
        print("🔧 Local mode enabled: SSH tunnel disabled.")

    # Proxy URL from config or env
    PROXY_URL = config.get('PROXY_URL') or os.getenv('PROXY_URL')
    
    # wallets is loaded globally from wallets.txt
    wallets_to_monitor = wallets 
    
    # How many times to collect data from each wallet before moving to the next rotation
    cycles_per_wallet = int(config.get('CYCLES_PER_WALLET', 1))
    
    # Create and run the fast client
    client = MultiTargetFastClient(
        wallets_to_monitor, 
        config['DB_CONFIG'], 
        config['SSH_CONFIG'],
        proxy_url=PROXY_URL
    )
    
    # Run indefinitely
    await client.run_multi_target_monitor(
        cycles_per_wallet=cycles_per_wallet
    )


if __name__ == "__main__":
    print("[*] Multi-Target Hyperliquid Fast Monitor")
    print("=" * 50)
    
    # Run continuous monitoring
    asyncio.run(main())
