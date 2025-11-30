import asyncio
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
# Import the custom break manager
from break_manager import BreakManager 
from data_inserter_env import load_env_config, MySQLStealthClient 
from hyperliquid_parser import parse_hyperliquid_data

URL = "wss://api.hyperliquid.xyz/ws"
PATTERN = re.compile(r'"channel"\s*:\s*"webData2"')

with open('wallets.txt', 'r') as file:
    # Using a list comprehension for concise reading and cleaning
    wallets = [line.strip() for line in file if line.strip()]

# Load configuration once globally
config = load_env_config()
db_config = config['DB_CONFIG']
ssh_config = config['SSH_CONFIG']

class MultiTargetStealthClient:
    def __init__(self, wallets, break_manager):
        self.wallets = wallets
        self.current_wallet_index = 0
        self.session_id = self.generate_session_id()
        self.connection_count = 0
        self.last_activity = time.time()
        
        # Database configurations
        self.db_config = db_config  
        self.ssh_config = ssh_config

        # Store the BreakManager instance
        self.break_manager = break_manager 

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
            
            # 4. Insert using the secure client
            with MySQLStealthClient(self.ssh_config, self.db_config) as client:
                client.insert_hyperliquid_data(
                    wallet_address, 
                    snapshot_time_ms, 
                    parsed_data,
                    raw_data_json # Pass the full raw JSON string
                )
                
        except Exception as e:
            print(f"[❌] FAILED TO INSERT data for {wallet_address}: {e}")

    def generate_session_id(self):
        """Generate realistic Chrome session ID"""
        return ''.join(random.choices('0123456789abcdef', k=32))
    
    def get_current_wallet(self):
        """Get current target wallet"""
        return self.wallets[self.current_wallet_index]
    
    def advance_to_next_wallet(self):
        """Move to next wallet with human-like selection"""
        # Sometimes skip wallets or go back (human behavior)
        if random.random() < 0.1:  # 10% chance to skip
            self.current_wallet_index = (self.current_wallet_index + 2) % len(self.wallets)
        elif random.random() < 0.05:  # 5% chance to go back
            self.current_wallet_index = (self.current_wallet_index - 1) % len(self.wallets)
        else:
            self.current_wallet_index = (self.current_wallet_index + 1) % len(self.wallets)
        
        current_wallet = self.get_current_wallet()
        print(f"🔄 Switching to wallet: {current_wallet}")
        
        return current_wallet
    
    def random_key(self):
        """Generate WebSocket key with realistic entropy"""
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
        """Generate browser-realistic headers with proper ordering"""
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
            ("Origin", "https://www.coinglass.com"),
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
    
    def create_stealth_ssl_context(self):
        """Create SSL context that mimics Chrome's TLS fingerprint"""
        context = ssl.create_default_context()
        
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
    
    async def human_delay(self):
        """Simulate human-like delays"""
        delays = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 1.0]
        weights = [20, 15, 15, 12, 10, 8, 6, 5, 4, 5]
        delay = random.choices(delays, weights=weights)[0]
        
        jitter = random.uniform(-0.05, 0.05)
        total_delay = max(0.05, delay + jitter)
        
        await asyncio.sleep(total_delay)
    
    async def connect_with_stealth(self):
        """Establish connection with maximum stealth"""
        self.connection_count += 1
        
        if self.connection_count > 1:
            reconnect_delay = random.uniform(3, 12)
            print(f"[⏳] Human-like pause: {reconnect_delay:.1f}s...")
            await asyncio.sleep(reconnect_delay)
        
        ssl_context = self.create_stealth_ssl_context()
        headers = self.realistic_headers()
        
        current_wallet = self.get_current_wallet()
        print(f"[🔗] Connecting for wallet: {current_wallet[:10]}...")
        
        await self.human_delay()
        
        ws = await connect(
            URL, 
            ssl=ssl_context, 
            extra_headers=headers,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10
        )
        
        print("[✅] Stealth connection established")
        return ws
    
    async def subscribe_to_wallet(self, ws, wallet_address):
        """Subscribe to specific wallet with realistic timing"""
        # Human browsing simulation - wait before subscribing
        browse_delay = random.uniform(1.0, 4.0)
        print(f"[👀] Browsing simulation: {browse_delay:.1f}s...")
        await asyncio.sleep(browse_delay)
        
        subscribe_msg = {
            "method": "subscribe",
            "subscription": {
                "type": "webData2", 
                "user": wallet_address
            }
        }
        
        message = json.dumps(subscribe_msg)
        
        # Typing simulation
        typing_delay = len(message) * random.uniform(0.002, 0.005)
        await asyncio.sleep(typing_delay)
        
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
            ws = await self.connect_with_stealth()
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
                        
                        # Human-like "reading" time after getting data
                        reading_time = random.uniform(2, 8)
                        print(f"[📖] Processing data: {reading_time:.1f}s...")
                        await asyncio.sleep(reading_time)
                        
                        break
                        
                except asyncio.TimeoutError:
                    print("[⏰] Waiting for data...")
                    # Send ping to keep connection alive
                    try:
                        await ws.ping()
                    except:
                        break
                    continue
            
            # Graceful disconnect simulation
            disconnect_delay = random.uniform(1, 3)
            print(f"[👋] Graceful disconnect in {disconnect_delay:.1f}s...")
            await asyncio.sleep(disconnect_delay)
            
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
        print("🥷 Starting Multi-Target Ultra-Stealth Monitor")
        print(f"🎯 Monitoring {len(self.wallets)} wallets")
        print(f"🔄 {cycles_per_wallet} cycle(s) per wallet per rotation")
        print("♾️ Mode: Continuous (Runs indefinitely)")
        print("="*60)
        
        total_cycles = 0
        wallet_cycle_count = {wallet: 0 for wallet in self.wallets}
        
        try:
            while True:
                current_wallet = self.get_current_wallet()
                
                # Check if a full rotation is complete
                if all(count >= cycles_per_wallet for count in wallet_cycle_count.values()):
                    # Full rotation complete. Reset counters and take a long break.
                    print(f"\n=== CONTINUOUS MONITORING ROTATION COMPLETE. STARTING NEW ROTATION ===")
                    wallet_cycle_count = {wallet: 0 for wallet in self.wallets}
                    
                    # Apply a long human break between full rotations
                    await self.break_manager.take_human_break(is_long_rotation_break=True)
                    continue # Restart the loop iteration
                    
                # If the current wallet is done but others aren't, move on
                if wallet_cycle_count[current_wallet] >= cycles_per_wallet:
                    print(f"[✅] Completed {cycles_per_wallet} cycles for {current_wallet}. Skipping.")
                    self.advance_to_next_wallet()
                    continue
                
                # Check if we should take a break 
                if self.break_manager.should_take_break():
                    await self.break_manager.take_human_break(is_long_rotation_break=False)
                
                # Collect data for current wallet
                print(f"\n[🔍] Cycle {wallet_cycle_count[current_wallet] + 1}/{cycles_per_wallet} for {current_wallet}")
                
                data_collected = await self.collect_wallet_data(
                    current_wallet, 
                    timeout_minutes=random.randint(3, 8)  # Vary timeout
                )
                
                wallet_cycle_count[current_wallet] += 1
                total_cycles += 1
                
                if data_collected:
                    print(f"[✅] Data successfully collected for {current_wallet}")
                else:
                    print(f"[⚠️] No data collected for {current_wallet} this cycle")
                
                # Inter-wallet delay removed - script moves immediately to advance_to_next_wallet
                
                # Advance to next wallet
                self.advance_to_next_wallet()
                
        except KeyboardInterrupt:
            print("\n[⏹️] Monitoring stopped by user")
        except Exception as e:
            print(f"\n[💥] Unexpected error: {e}")
        finally:
            self.print_session_summary()

# 🎯 Main function (Continuous Monitoring)
async def main():
    """Main entry point for continuous monitoring."""
    
    # 1. Initialize the Break Manager with configuration from env
    BREAK_PROBABILITY = float(config.get('BREAK_PROBABILITY', 0.15))
    LONG_BREAK_MIN = int(config.get('LONG_BREAK_MIN_SECONDS', 180)) 
    LONG_BREAK_MAX = int(config.get('LONG_BREAK_MAX_SECONDS', 420))
    
    # Removed SAME_DELAY and SWITCH_DELAY configurations as they are no longer used
    break_manager = BreakManager(
        BREAK_PROBABILITY, LONG_BREAK_MIN, LONG_BREAK_MAX
    )
    
    # wallets is loaded globally from wallets.txt
    wallets_to_monitor = wallets 
    
    # How many times to collect data from each wallet before moving to the next rotation
    cycles_per_wallet = int(config.get('CYCLES_PER_WALLET', 1))
    
    # Create and run the stealth client, passing the manager
    client = MultiTargetStealthClient(wallets_to_monitor, break_manager)
    
    # Run indefinitely
    await client.run_multi_target_monitor(
        cycles_per_wallet=cycles_per_wallet
    )


if __name__ == "__main__":
    print("🥷 Multi-Target Hyperliquid Stealth Monitor")
    print("=" * 50)
    
    # Run continuous monitoring
    asyncio.run(main())