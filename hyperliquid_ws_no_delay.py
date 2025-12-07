import argparse
import ssl
import base64
import os
import json
import random
import re
import time
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlparse

import socks
import socket
from websocket import create_connection, WebSocket
import pymysql

# Your custom imports
from data_inserter_env import load_env_config, MySQLStealthClient
from hyperliquid_parser import parse_hyperliquid_data

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Constants ---
URL = "wss://api.hyperliquid.xyz/ws"
PATTERN = re.compile(r'"channel"\s*:\s*"webData2"')

# Rotation intervals
SSL_ROTATE_INTERVAL = 10      # Rotate SSL context every N wallets
TOR_ROTATE_INTERVAL = 20      # Rotate Tor identity every N wallets


def load_wallets(filepath: str = 'wallets.txt') -> List[str]:
    """Load wallets from file."""
    try:
        with open(filepath, 'r') as f:
            wallets = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(wallets)} wallets from {filepath}")
        return wallets
    except FileNotFoundError:
        logger.error(f"Wallet file not found: {filepath}")
        raise


@dataclass
class ProxyConfig:
    """SOCKS5 proxy configuration."""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    
    @classmethod
    def from_url(cls, url: str) -> 'ProxyConfig':
        parsed = urlparse(url)
        if not parsed.hostname or not parsed.port:
            raise ValueError(f"Invalid proxy URL: {url}")
        return cls(
            host=parsed.hostname,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password
        )


@dataclass
class TorControlConfig:
    """Tor control port configuration."""
    host: str = "127.0.0.1"
    port: int = 9051
    password: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'TorControlConfig':
        return cls(
            host=os.getenv('TOR_CONTROL_HOST', '127.0.0.1'),
            port=int(os.getenv('TOR_CONTROL_PORT', '9051')),
            password=os.getenv('TOR_CONTROL_PASSWORD')
        )


class TorController:
    """Manages Tor identity changes via control port."""
    
    def __init__(self, config: TorControlConfig):
        self.config = config
        self._identity_count = 0
        self._last_change_time = 0
        self._min_interval = 10  # Tor recommends waiting 10s between NEWNYM
    
    def change_identity(self, reason: str = "scheduled") -> bool:
        """
        Send NEWNYM signal to Tor to get a new identity/circuit.
        
        Args:
            reason: Why identity is being changed (for logging)
        
        Returns:
            True if successful, False otherwise
        """
        # Respect Tor's rate limit
        elapsed = time.time() - self._last_change_time
        if elapsed < self._min_interval:
            wait_time = self._min_interval - elapsed
            logger.debug(f"Waiting {wait_time:.1f}s before Tor identity change...")
            time.sleep(wait_time)
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((self.config.host, self.config.port))
                
                # Authenticate
                if self.config.password:
                    auth_cmd = f'AUTHENTICATE "{self.config.password}"\r\n'
                else:
                    auth_cmd = 'AUTHENTICATE\r\n'
                
                sock.send(auth_cmd.encode())
                response = sock.recv(1024).decode()
                
                if "250" not in response:
                    logger.error(f"Tor auth failed: {response.strip()}")
                    return False
                
                # Send NEWNYM signal
                sock.send(b'SIGNAL NEWNYM\r\n')
                response = sock.recv(1024).decode()
                
                if "250" in response:
                    self._identity_count += 1
                    self._last_change_time = time.time()
                    logger.info(f"🧅 Tor identity changed [{reason}] (#{self._identity_count})")
                    
                    # Wait for new circuit to be established
                    time.sleep(2)
                    return True
                else:
                    logger.error(f"Tor NEWNYM failed: {response.strip()}")
                    return False
                    
        except ConnectionRefusedError:
            logger.error(
                f"Cannot connect to Tor control port {self.config.host}:{self.config.port}. "
                "Make sure Tor is running and ControlPort is enabled."
            )
            return False
        except Exception as e:
            logger.error(f"Tor identity change failed: {e}")
            return False
    
    @property
    def identity_changes(self) -> int:
        """Number of identity changes performed."""
        return self._identity_count


class SSLContextFactory:
    """SSL context factory with rotation support."""
    
    CIPHERS = [
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
    ]
    
    @classmethod
    def create(cls) -> ssl.SSLContext:
        """Create a fresh SSL context."""
        context = ssl.create_default_context()
        try:
            context.set_ciphers(":".join(cls.CIPHERS))
        except ssl.SSLError:
            context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5")
        
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
        
        logger.debug("New SSL context created")
        return context


class HeaderGenerator:
    """Generate realistic browser headers."""
    
    USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    )
    
    SEC_CH_UA_CHROME = (
        '"Google Chrome";v="121", "Chromium";v="121", "Not A(Brand";v="99"',
        '"Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="99"',
        '"Google Chrome";v="122", "Chromium";v="122", "Not(A:Brand";v="24"',
    )
    
    PLATFORMS = ('"Windows"', '"macOS"', '"Linux"')
    
    @classmethod
    def generate(cls) -> Dict[str, str]:
        """Generate new random headers."""
        ua = random.choice(cls.USER_AGENTS)
        is_chrome = "Chrome" in ua and "Firefox" not in ua
        
        headers = {
            "Host": "api.hyperliquid.xyz",
            "User-Agent": ua,
            "Origin": "https://app.hyperliquid.xyz",
            "Sec-WebSocket-Version": "13",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "websocket",
            "Sec-Fetch-Mode": "websocket",
            "Sec-Fetch-Site": "cross-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
        
        # Chrome-specific headers
        if is_chrome:
            headers.update({
                "Sec-Ch-Ua": random.choice(cls.SEC_CH_UA_CHROME),
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": random.choice(cls.PLATFORMS),
            })
        
        return headers


class DatabaseManager:
    """Manages database connection with auto-reconnect."""
    
    # Errors that should NOT be retried (data issues, not connection issues)
    DATA_ERRORS = (1406, 1048, 1062, 1264, 1265, 1366)
    
    def __init__(self, db_config: Dict, ssh_config: Dict):
        self.db_config = db_config
        self.ssh_config = ssh_config
        self._client: Optional[MySQLStealthClient] = None
    
    def _ensure_connection(self):
        """Ensure database connection is active."""
        if self._client is None:
            self._connect()
            return
        
        try:
            self._client.conn.ping(reconnect=True)
        except Exception as e:
            logger.warning(f"DB connection lost: {e}. Reconnecting...")
            self.close()
            self._connect()
    
    def _connect(self):
        """Establish database connection."""
        try:
            self._client = MySQLStealthClient(self.ssh_config, self.db_config)
            self._client.__enter__()
            logger.info("Database connected")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self._client = None
            raise
    
    def insert(self, wallet: str, snapshot_time: int, 
               parsed_data: Dict, max_retries: int = 3) -> bool:
        """Insert data with retry logic (only for connection errors)."""
        
        for attempt in range(max_retries):
            try:
                self._ensure_connection()
                self._client.insert_hyperliquid_data(
                    wallet, snapshot_time, parsed_data
                )
                return True
                
            except Exception as e:
                error_code = e.args[0] if hasattr(e, 'args') and e.args else None
                
                # Data error - don't retry, it will always fail
                if isinstance(error_code, int) and error_code in self.DATA_ERRORS:
                    logger.error(f"❌ Data error (code {error_code}), skipping wallet: {e}")
                    return False  # Exit immediately, no retry
                
                # Connection error - retry
                logger.warning(f"Insert failed (attempt {attempt + 1}/{max_retries}): {e}")
                self.close()
                
                if attempt == max_retries - 1:
                    logger.error(f"Failed to insert data for {wallet}")
                    return False
                
                time.sleep(1)
        
        return False
    
    def close(self):
        """Close database connection."""
        if self._client:
            try:
                self._client.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing DB: {e}")
            finally:
                self._client = None


class HyperliquidMonitor:
    """
    Synchronous WebSocket monitor for Hyperliquid wallets.
    Runs indefinitely, connecting via Tor SOCKS5 proxy.
    Changes Tor identity on errors and every N wallets.
    """
    
    def __init__(
        self,
        wallets: List[str],
        proxy_config: ProxyConfig,
        tor_control: TorControlConfig,
        db_config: Dict,
        ssh_config: Dict,
        timeout_seconds: int = 60,
        ssl_rotate_interval: int = SSL_ROTATE_INTERVAL,
        tor_rotate_interval: int = TOR_ROTATE_INTERVAL,
    ):
        self.wallets = wallets
        self.proxy = proxy_config
        self.tor = TorController(tor_control)
        self.timeout = timeout_seconds
        self.ssl_rotate_interval = ssl_rotate_interval
        self.tor_rotate_interval = tor_rotate_interval
        
        # SSL context and headers (will be rotated)
        self._ssl_context = SSLContextFactory.create()
        self._headers = HeaderGenerator.generate()
        
        # Database manager
        self.db = DatabaseManager(db_config, ssh_config)
        
        # Stats
        self.wallets_processed = 0
        self.successful = 0
        self.failed = 0
        self.connection_errors = 0
        self.start_time = None
    
    def _rotate_full_identity(self, reason: str = "scheduled"):
        """Change Tor identity, SSL context, and headers."""
        logger.info(f"🔄 Full rotation [{reason}]: Tor + SSL + Headers")
        
        # Change Tor circuit
        self.tor.change_identity(reason)
        
        # New SSL context
        self._ssl_context = SSLContextFactory.create()
        
        # New headers
        self._headers = HeaderGenerator.generate()
        
        logger.debug(f"New User-Agent: {self._headers.get('User-Agent', '')[:50]}...")
    
    def _rotate_ssl_only(self):
        """Rotate only SSL context and headers (no Tor change)."""
        logger.info(f"🔒 SSL rotation (every {self.ssl_rotate_interval} wallets)")
        self._ssl_context = SSLContextFactory.create()
        self._headers = HeaderGenerator.generate()
    
    def _check_scheduled_rotations(self):
        """Check and perform scheduled rotations based on wallet count."""
        if self.wallets_processed == 0:
            return
        
        # Tor rotation takes priority (includes SSL rotation)
        if self.wallets_processed % self.tor_rotate_interval == 0:
            self._rotate_full_identity(f"every {self.tor_rotate_interval} wallets")
        # SSL-only rotation (if not already doing Tor rotation)
        elif self.wallets_processed % self.ssl_rotate_interval == 0:
            self._rotate_ssl_only()
    
    def _create_socks_socket(self, host: str, port: int) -> socket.socket:
        """Create a socket connected through SOCKS5 proxy."""
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5,
            self.proxy.host,
            self.proxy.port,
            username=self.proxy.username,
            password=self.proxy.password
        )
        sock.settimeout(10)
        sock.connect((host, port))
        return sock
    
    def _connect_websocket(self) -> WebSocket:
        """Create WebSocket connection via SOCKS5 proxy."""
        parsed = urlparse(URL)
        host = parsed.hostname
        port = parsed.port or 443
        
        # Create SOCKS5 socket
        sock = self._create_socks_socket(host, port)
        
        # Wrap with SSL
        ssl_sock = self._ssl_context.wrap_socket(sock, server_hostname=host)
        
        # Create WebSocket connection
        ws = create_connection(
            URL,
            socket=ssl_sock,
            header=self._headers,
            timeout=self.timeout
        )
        
        logger.debug("WebSocket connected")
        return ws
    
    def _subscribe(self, ws: WebSocket, wallet: str):
        """Subscribe to wallet updates."""
        msg = json.dumps({
            "method": "subscribe",
            "subscription": {"type": "webData2", "user": wallet}
        })
        ws.send(msg)
        logger.debug(f"Subscribed to: {wallet[:16]}...")
    
    def _process_message(self, wallet: str, msg: str) -> Optional[bool]:
        """
        Process message and insert to database.
        
        Returns:
            True: Success
            False: Data error (don't retry)
            None: Not the right message, keep waiting
        """
        if not PATTERN.search(msg):
            return None  # Not our message, keep waiting
        
        try:
            data = json.loads(msg)
            raw_data = data.get("data", {})
            
            if not raw_data:
                logger.warning("Message missing 'data' key")
                return None
            
            clearinghouse = raw_data.get('clearinghouseState', {})
            snapshot_time = clearinghouse.get('time')
            
            if not snapshot_time:
                logger.warning("Message missing 'clearinghouseState.time'")
                return None
            
            # Parse data
            parsed_data = parse_hyperliquid_data(raw_data)
            
            # Insert to database
            success = self.db.insert(wallet, snapshot_time, parsed_data)
            return success  # True or False, we're done with this wallet
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None  # Keep waiting for valid JSON
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return False  # Stop processing this wallet
    
    def collect_wallet_data(self, wallet: str) -> bool:
        """
        Collect data for a single wallet.
        On any connection/receive error, change Tor identity and move to next wallet.
        """
        ws = None
        try:
            ws = self._connect_websocket()
            self._subscribe(ws, wallet)
            
            deadline = time.time() + self.timeout
            
            while time.time() < deadline:
                ws.settimeout(15)
                
                try:
                    msg = ws.recv()
                    
                    result = self._process_message(wallet, msg)
                    
                    # None = keep waiting for right message
                    # True/False = we're done with this wallet
                    if result is not None:
                        return result
                        
                except Exception as recv_error:
                    # Any receive error: change identity and move on
                    logger.warning(f"⚠️ Receive error: {recv_error}")
                    self.connection_errors += 1
                    self._rotate_full_identity("receive error")
                    return False  # Move to next wallet
            
            # Timeout reached
            logger.warning(f"⏱️ Timeout for {wallet[:16]}...")
            return False
            
        except Exception as conn_error:
            # Connection error: change identity and move on
            logger.error(f"🔌 Connection error: {conn_error}")
            self.connection_errors += 1
            self._rotate_full_identity("connection error")
            return False  # Move to next wallet
            
        finally:
            if ws:
                try:
                    ws.close()
                except:
                    pass
    
    def _log_progress(self, wallet: str, success: bool):
        """Log current progress."""
        status = "✅" if success else "❌"
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        
        success_rate = (self.successful / self.wallets_processed * 100) if self.wallets_processed > 0 else 0
        
        # Show next rotation countdown
        next_tor = self.tor_rotate_interval - (self.wallets_processed % self.tor_rotate_interval)
        next_ssl = self.ssl_rotate_interval - (self.wallets_processed % self.ssl_rotate_interval)
        
        logger.info(
            f"{status} [{self.wallets_processed}] {wallet[:20]}... | "
            f"✓{self.successful} ✗{self.failed} | "
            f"{success_rate:.1f}% | "
            f"🧅{self.tor.identity_changes}(→{next_tor}) | "
            f"⏱️{elapsed_str}"
        )
    
    def run(self):
        """Main infinite monitoring loop."""
        logger.info("=" * 70)
        logger.info("🚀 Starting Hyperliquid Monitor (Tor Mode)")
        logger.info(f"📋 Wallets: {len(self.wallets)}")
        logger.info(f"🔒 SSL rotation: Every {self.ssl_rotate_interval} wallets")
        logger.info(f"🧅 Tor rotation: Every {self.tor_rotate_interval} wallets")
        logger.info(f"🧅 Tor proxy: {self.proxy.host}:{self.proxy.port}")
        logger.info(f"🎛️  Tor control: {self.tor.config.host}:{self.tor.config.port}")
        logger.info(f"⏱️  Timeout: {self.timeout}s per wallet")
        logger.info("=" * 70)
        
        self.start_time = time.time()
        wallet_index = 0
        
        try:
            while True:
                # Get current wallet (loop through list)
                wallet = self.wallets[wallet_index]
                wallet_index = (wallet_index + 1) % len(self.wallets)
                
                # Check scheduled rotations BEFORE processing
                self._check_scheduled_rotations()
                
                # Collect data (errors trigger identity change internally)
                success = self.collect_wallet_data(wallet)
                
                # Update stats
                self.wallets_processed += 1
                if success:
                    self.successful += 1
                else:
                    self.failed += 1
                
                # Log progress
                self._log_progress(wallet, success)
                
                # Log rotation completion
                if wallet_index == 0:
                    logger.info(f"🔄 Completed full wallet rotation. Starting again...")
                
        except KeyboardInterrupt:
            logger.info("\n⏹️  Stopped by user")
        finally:
            self.db.close()
            self._print_summary()
    
    def _print_summary(self):
        """Print session summary."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        
        success_rate = (self.successful / self.wallets_processed * 100) if self.wallets_processed > 0 else 0
        avg_time = elapsed / self.wallets_processed if self.wallets_processed > 0 else 0
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 SESSION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"⏱️  Total runtime:        {elapsed_str}")
        logger.info(f"📋 Wallets in list:      {len(self.wallets)}")
        logger.info(f"🔄 Total processed:      {self.wallets_processed}")
        logger.info(f"✅ Successful:           {self.successful}")
        logger.info(f"❌ Failed:               {self.failed}")
        logger.info(f"📈 Success rate:         {success_rate:.1f}%")
        logger.info(f"⚡ Avg time per wallet:  {avg_time:.2f}s")
        logger.info(f"🧅 Tor identity changes: {self.tor.identity_changes}")
        logger.info(f"🔌 Connection errors:    {self.connection_errors}")
        logger.info("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Hyperliquid Tor Monitor')
    parser.add_argument('--local', action='store_true', 
                        help='Use local database (no SSH tunnel)')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Timeout per wallet in seconds (default: 10)')
    parser.add_argument('--tor-control-port', type=int, default=9051,
                        help='Tor control port (default: 9051)')
    parser.add_argument('--tor-control-password', type=str, default=None,
                        help='Tor control password (or set TOR_CONTROL_PASSWORD env)')
    parser.add_argument('--ssl-rotate', type=int, default=SSL_ROTATE_INTERVAL,
                        help=f'Rotate SSL every N wallets (default: {SSL_ROTATE_INTERVAL})')
    parser.add_argument('--tor-rotate', type=int, default=TOR_ROTATE_INTERVAL,
                        help=f'Rotate Tor identity every N wallets (default: {TOR_ROTATE_INTERVAL})')
    args = parser.parse_args()
    
    # Load configuration
    config = load_env_config()
    
    if args.local:
        config['SSH_CONFIG']['use_tunnel'] = False
        logger.info("🔧 Local mode: SSH tunnel disabled")
    
    # Get proxy URL (required)
    proxy_url = config.get('SOCKS5_PROXY') or os.getenv('SOCKS5_PROXY')
    if not proxy_url:
        raise ValueError(
            "SOCKS5_PROXY is required.\n"
            "For Tor, set: export SOCKS5_PROXY=socks5://127.0.0.1:9050"
        )
    
    # Tor control configuration
    tor_control = TorControlConfig(
        host=os.getenv('TOR_CONTROL_HOST', '127.0.0.1'),
        port=args.tor_control_port,
        password=args.tor_control_password or os.getenv('TOR_CONTROL_PASSWORD')
    )
    
    # Load wallets
    wallets = load_wallets()
    
    if not wallets:
        raise ValueError("No wallets found in wallets.txt")
    
    # Create and run monitor
    monitor = HyperliquidMonitor(
        wallets=wallets,
        proxy_config=ProxyConfig.from_url(proxy_url),
        tor_control=tor_control,
        db_config=config['DB_CONFIG'],
        ssh_config=config['SSH_CONFIG'],
        timeout_seconds=args.timeout,
        ssl_rotate_interval=args.ssl_rotate,
        tor_rotate_interval=args.tor_rotate,
    )
    
    monitor.run()


if __name__ == "__main__":
    main()