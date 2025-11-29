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

URL = "wss://api.hyperliquid.xyz/ws"
PATTERN = re.compile(r'"channel"\s*:\s*"webData2"')

with open('wallets.txt', 'r') as file:
    # Using a list comprehension for concise reading and cleaning
    wallets = [line.strip() for line in file if line.strip()]

class MultiTargetStealthClient:
    def __init__(self, wallets):
        self.wallets = wallets
        self.current_wallet_index = 0
        self.session_id = self.generate_session_id()
        self.connection_count = 0
        self.last_activity = time.time()
        self.collected_data = {}
        self.wallet_visit_history = {}
        self.daily_limits = {}
        
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
        
        # Track visit history
        today = datetime.now().date()
        if current_wallet not in self.wallet_visit_history:
            self.wallet_visit_history[current_wallet] = []
        self.wallet_visit_history[current_wallet].append(datetime.now())
        
        return current_wallet
    
    def should_take_break(self):
        """Determine if we should take a longer break (human behavior)"""
        current_wallet = self.get_current_wallet()
        today = datetime.now().date()
        
        # Check daily limits
        if current_wallet in self.wallet_visit_history:
            today_visits = [v for v in self.wallet_visit_history[current_wallet] 
                          if v.date() == today]
            
            # Take break after 3-5 visits to same wallet per day
            if len(today_visits) >= random.randint(3, 5):
                return True
        
        # Random breaks (simulate human getting distracted)
        if random.random() < 0.15:  # 15% chance
            return True
            
        return False
    
    def calculate_human_break_time(self):
        """Calculate realistic break duration"""
        break_types = [
            (300, 900, 0.4),    # 5-15 min (coffee break)
            (900, 1800, 0.3),   # 15-30 min (lunch break)
            (1800, 3600, 0.2),  # 30-60 min (meeting)
            (3600, 7200, 0.1),  # 1-2 hours (long break)
        ]
        
        # Weighted random selection
        total_weight = sum(weight for _, _, weight in break_types)
        r = random.random() * total_weight
        
        cumulative = 0
        for min_time, max_time, weight in break_types:
            cumulative += weight
            if r <= cumulative:
                return random.randint(min_time, max_time)
        
        return random.randint(300, 900)  # Default
    
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
                        print(msg)
                        print("="*50)
                        
                        # Store the data
                        if wallet_address not in self.collected_data:
                            self.collected_data[wallet_address] = []

                        self.collected_data[wallet_address].append({
                            'timestamp': datetime.now().isoformat(),
                            'data': msg
                        })

                        try:
                            parsed = json.loads(msg)
                            print("📊 Formatted Data:")
                            print(json.dumps(parsed, indent=2))
                        except:
                            pass

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
    
    async def take_human_break(self):
        """Take a realistic human break"""
        break_duration = self.calculate_human_break_time()
        break_minutes = break_duration / 60
        
        break_reasons = [
            "☕ Coffee break",
            "🍽️ Lunch break", 
            "📞 Taking a call",
            "💭 Thinking break",
            "🚶 Quick walk",
            "📧 Checking emails"
        ]
        
        reason = random.choice(break_reasons)
        print(f"\n{reason} - Taking {break_minutes:.1f} minute break...")
        print(f"[😴] Break time: {break_minutes:.1f} minutes")
        print(f"[⏰] Will resume at {(datetime.now() + timedelta(seconds=break_duration)).strftime('%H:%M:%S')}")
        
        # Show countdown every minute for long breaks
        if break_duration > 300:  # 5+ minutes
            remaining = break_duration
            while remaining > 0:
                if remaining > 60:
                    print(f"[⏳] {remaining//60:.0f} minutes remaining...")
                    await asyncio.sleep(60)
                    remaining -= 60
                else:
                    await asyncio.sleep(remaining)
                    remaining = 0
        else:
            await asyncio.sleep(break_duration)
        
        print("[🔄] Break over, resuming monitoring...")
    
    def save_collected_data(self):
        """Save collected data to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hyperliquid_data_{timestamp}.json"
    
        with open(filename, 'w') as f:
            json.dump(self.collected_data, f, indent=2)

        print(f"[💾] Data saved to {filename}")
        return filename
    
    def print_session_summary(self):
        """Print summary of data collection session"""
        print(f"\n{'='*60}")
        print("📊 SESSION SUMMARY")
        print(f"{'='*60}")
        print(f"Total wallets monitored: {len(self.wallets)}")
        print(f"Data collected for: {len(self.collected_data)} wallets")
        print(f"Total connections made: {self.connection_count}")
        
        for wallet, data_list in self.collected_data.items():
            print(f"  • {wallet}: {len(data_list)} data points")
        
        if self.collected_data:
            filename = self.save_collected_data()
            print(f"📁 All data saved to: {filename}")
        
        print(f"{'='*60}\n")
    
    async def run_multi_target_monitor(self, cycles_per_wallet=1, max_total_cycles=None):
        """Main monitoring loop for multiple wallets"""
        print("🥷 Starting Multi-Target Ultra-Stealth Monitor")
        print(f"🎯 Monitoring {len(self.wallets)} wallets")
        print(f"🔄 {cycles_per_wallet} cycle(s) per wallet")
        if max_total_cycles:
            print(f"⏹️ Max total cycles: {max_total_cycles}")
        print("="*60)
        
        total_cycles = 0
        wallet_cycle_count = {wallet: 0 for wallet in self.wallets}
        
        try:
            while True:
                current_wallet = self.get_current_wallet()
                
                # Check if we've completed enough cycles for this wallet
                if wallet_cycle_count[current_wallet] >= cycles_per_wallet:
                    print(f"[✅] Completed {cycles_per_wallet} cycles for {current_wallet}")
                    
                    # Check if all wallets are done
                    if all(count >= cycles_per_wallet for count in wallet_cycle_count.values()):
                        print("🎉 All wallets completed!")
                        break
                    
                    # Move to next wallet that needs monitoring
                    self.advance_to_next_wallet()
                    continue
                
                # Check total cycle limit
                if max_total_cycles and total_cycles >= max_total_cycles:
                    print(f"[⏹️] Reached maximum cycles limit: {max_total_cycles}")
                    break
                
                # Check if we should take a break
                if self.should_take_break():
                    await self.take_human_break()
                
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
                
                # Inter-wallet delay (human browsing behavior)
                if wallet_cycle_count[current_wallet] < cycles_per_wallet:
                    # Same wallet, shorter delay
                    delay = random.uniform(10, 30)
                    print(f"[⏸️] Same wallet cooldown: {delay:.1f}s...")
                else:
                    # Different wallet, longer delay
                    delay = random.uniform(30, 90)
                    print(f"[⏸️] Wallet switch cooldown: {delay:.1f}s...")
                
                await asyncio.sleep(delay)
                
                # Advance to next wallet
                self.advance_to_next_wallet()
                
        except KeyboardInterrupt:
            print("\n[⏹️] Monitoring stopped by user")
        except Exception as e:
            print(f"\n[💥] Unexpected error: {e}")
        finally:
            self.print_session_summary()

# 🎯 Configuration and Usage
async def main():
    """Main function with configuration"""
    
    # 📝 CONFIGURATION - Modify these settings
    wallets_to_monitor = [
        "0x9eec98d048d06d9cd75318fffa3f3960e081daab",
        "0x1234567890123456789012345678901234567890",  # Replace with real addresses
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        "0x9876543210987654321098765432109876543210",
        # Add more wallet addresses here...
    ]
    
    # How many times to collect data from each wallet
    cycles_per_wallet = 2
    
    # Maximum total cycles (optional limit)
    max_total_cycles = 20  # Set to None for unlimited
    
    # Create and run the stealth client
    client = MultiTargetStealthClient(wallets_to_monitor)
    
    await client.run_multi_target_monitor(
        cycles_per_wallet=cycles_per_wallet,
        max_total_cycles=max_total_cycles
    )

# 🚀 Advanced Usage Examples
async def continuous_monitoring():
    """Example: Continuous monitoring with breaks"""  
    client = MultiTargetStealthClient(wallets)
    
    # Run indefinitely with 1 cycle per wallet, then repeat
    await client.run_multi_target_monitor(
        cycles_per_wallet=1,
        max_total_cycles=None  # Infinite
    )

async def quick_scan():
    """Example: Quick scan of all wallets once"""
    wallets = [
        "0x9eec98d048d06d9cd75318fffa3f3960e081daab",
        # Add your wallets...
    ]
    
    client = MultiTargetStealthClient(wallets)
    
    # Scan each wallet once
    await client.run_multi_target_monitor(
        cycles_per_wallet=1,
        max_total_cycles=len(wallets)
    )

async def intensive_monitoring():
    """Example: Intensive monitoring of specific wallets"""
    high_priority_wallets = [
        "0x9eec98d048d06d9cd75318fffa3f3960e081daab",
        # Add high-priority wallets...
    ]
    
    client = MultiTargetStealthClient(high_priority_wallets)
    
    # Monitor each wallet 5 times
    await client.run_multi_target_monitor(
        cycles_per_wallet=5,
        max_total_cycles=None
    )

if __name__ == "__main__":
    print("🥷 Multi-Target Hyperliquid Stealth Monitor")
    print("=" * 50)
    
    # Choose your monitoring mode:
    
    # 1. Standard monitoring
    #asyncio.run(main())
    
    # 2. Continuous monitoring (uncomment to use)
    asyncio.run(continuous_monitoring())
    
    # 3. Quick scan (uncomment to use)
    # asyncio.run(quick_scan())
    
    # 4. Intensive monitoring (uncomment to use)
    # asyncio.run(intensive_monitoring())
