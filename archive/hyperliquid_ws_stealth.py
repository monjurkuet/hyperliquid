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

URL = "wss://api.hyperliquid.xyz/ws"
TARGET_USER = "0x9eec98d048d06d9cd75318fffa3f3960e081daab"
PATTERN = re.compile(r'"channel"\s*:\s*"webData2"')

class StealthWebSocket:
    def __init__(self):
        self.session_id = self.generate_session_id()
        self.connection_count = 0
        self.last_activity = time.time()
        
    def generate_session_id(self):
        """Generate realistic Chrome session ID"""
        return ''.join(random.choices('0123456789abcdef', k=32))
    
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
        
        # Chrome-like cipher suites (ordered by preference)
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
            # Fallback to default if specific ciphers fail
            context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS")
        
        # Chrome-like settings
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        
        return context
    
    async def human_delay(self):
        """Simulate human-like delays"""
        delays = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 1.0]
        weights = [20, 15, 15, 12, 10, 8, 6, 5, 4, 5]  # More likely to be quick
        delay = random.choices(delays, weights=weights)[0]
        
        # Add micro-jitter
        jitter = random.uniform(-0.05, 0.05)
        total_delay = max(0.05, delay + jitter)
        
        await asyncio.sleep(total_delay)
    
    async def split_message(self, ws, message):
        """Split large messages to avoid detection"""
        if len(message) < 100:
            await ws.send(message)
            return
        
        # Split into realistic chunks
        chunk_size = random.randint(50, 150)
        chunks = [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(random.uniform(0.001, 0.005))  # Tiny delay between chunks
            await ws.send(chunk)
    
    async def heartbeat_simulation(self, ws):
        """Send periodic heartbeats like a real browser"""
        while True:
            try:
                await asyncio.sleep(random.uniform(25, 35))  # Chrome-like ping interval
                if ws.open:
                    await ws.ping()
                    print("[♥] Heartbeat sent")
            except:
                break
    
    async def connect_with_stealth(self):
        """Establish connection with maximum stealth"""
        self.connection_count += 1
        
        # Human-like connection timing
        if self.connection_count > 1:
            reconnect_delay = random.uniform(2, 8)
            print(f"[⏳] Waiting {reconnect_delay:.1f}s before reconnecting...")
            await asyncio.sleep(reconnect_delay)
        
        ssl_context = self.create_stealth_ssl_context()
        headers = self.realistic_headers()
        
        print(f"[🔗] Establishing connection #{self.connection_count}...")
        
        # Add connection jitter
        await self.human_delay()
        
        ws = await connect(
            URL, 
            ssl=ssl_context, 
            extra_headers=headers,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10
        )
        
        print("[✅] Connected with stealth profile")
        
        # Start heartbeat in background
        asyncio.create_task(self.heartbeat_simulation(ws))
        
        return ws
    
    async def subscribe_with_timing(self, ws):
        """Subscribe with realistic human timing"""
        # Wait a bit after connection (like a human would)
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
        subscribe_msg = {
            "method": "subscribe",
            "subscription": {
                "type": "webData2", 
                "user": TARGET_USER
            }
        }
        
        message = json.dumps(subscribe_msg)
        
        # Add realistic typing simulation
        typing_delay = len(message) * random.uniform(0.001, 0.003)
        await asyncio.sleep(typing_delay)
        
        await self.split_message(ws, message)
        print(f"[📡] Subscribed to webData2 for {TARGET_USER}")
    
    async def process_message(self, msg):
        """Process incoming messages with human-like behavior"""
        self.last_activity = time.time()
        
        if PATTERN.search(msg):
            print("\n" + "="*50)
            print("🎯 WEBDATA2 MATCH DETECTED")
            print("="*50)
            print(msg)
            print("="*50 + "\n")
            
            try:
                parsed = json.loads(msg)
                print("📊 Formatted Data:")
                print(json.dumps(parsed, indent=2))
                print("\n" + "="*50 + "\n")
            except:
                pass
        
        # Simulate human reading time
        reading_time = min(len(msg) * 0.0001, 0.1)
        await asyncio.sleep(reading_time)
    
    async def monitor_connection_health(self, ws):
        """Monitor and maintain connection health"""
        while ws.open:
            await asyncio.sleep(10)
            
            # Check if we've been idle too long
            if time.time() - self.last_activity > 300:  # 5 minutes
                print("[⚠️] Connection seems idle, sending keep-alive...")
                try:
                    await ws.ping()
                    self.last_activity = time.time()
                except:
                    break
    
    async def run_stealth_client(self):
        """Main stealth client loop"""
        print("🥷 Starting Ultra-Stealth Hyperliquid Monitor")
        print(f"🎯 Target: {TARGET_USER}")
        print("🔍 Monitoring for webData2 messages...\n")
        
        while True:
            try:
                ws = await self.connect_with_stealth()
                
                # Start health monitoring
                health_task = asyncio.create_task(self.monitor_connection_health(ws))
                
                await self.subscribe_with_timing(ws)
                
                # Main message loop
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60)
                        await self.process_message(msg)
                        
                    except asyncio.TimeoutError:
                        print("[⏰] No messages for 60s, checking connection...")
                        await ws.ping()
                        continue
                        
            except Exception as e:
                print(f"[❌] Connection error: {e}")
                
                # Exponential backoff with jitter
                base_delay = min(2 ** min(self.connection_count, 6), 60)
                jitter = random.uniform(0.5, 1.5)
                delay = base_delay * jitter
                
                print(f"[⏳] Reconnecting in {delay:.1f}s...")
                await asyncio.sleep(delay)

# Additional stealth features
class NetworkStealth:
    @staticmethod
    def randomize_tcp_options():
        """Randomize TCP options to avoid fingerprinting"""
        # This would require raw socket access, simplified here
        pass
    
    @staticmethod
    def simulate_browser_dns():
        """Simulate browser DNS resolution patterns"""
        # Pre-resolve DNS with realistic timing
        import socket
        try:
            socket.gethostbyname("api.hyperliquid.xyz")
        except:
            pass

# Run the ultra-stealth client
async def main():
    stealth_client = StealthWebSocket()
    await stealth_client.run_stealth_client()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[👋] Stealth client stopped by user")
    except Exception as e:
        print(f"\n[💥] Fatal error: {e}")