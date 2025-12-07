import pymysql
import os
from dotenv import load_dotenv 
from sshtunnel import SSHTunnelForwarder
from typing import Dict, List, Any, Tuple
from hyperliquid_parser import parse_hyperliquid_data 
import datetime
import json 

# --- Configuration Loading Function ---

def load_env_config() -> Dict[str, Any]:
    """Loads all necessary configuration from environment variables (using .env)."""
    
    # Load environment variables from the .env file
    load_dotenv()
    
    try:
        # SSH Configuration
        ssh_config = {
            'use_tunnel': os.environ.get('USE_SSH_TUNNEL', 'false').lower() == 'true',
            'ssh_address_or_host': os.environ['SSH_HOST'],
            'ssh_username': os.environ['SSH_USER'],
            'ssh_port': int(os.environ.get('SSH_PORT', 22)),
            'ssh_pkey': os.environ.get('SSH_KEY_PATH'), 
            'remote_bind_address': (
                os.environ['REMOTE_DB_HOST'], 
                int(os.environ['REMOTE_DB_PORT'])
            ),
            'local_bind_address': ('127.0.0.1', int(os.environ.get('LOCAL_BIND_PORT', 0))) 
        }
        
        # DB Configuration
        db_config = {
            'database': os.environ['DB_NAME'],
            'user': os.environ['DB_USER'],
            'password': os.environ.get('DB_PASSWORD'), 
        }
        
        return {
            "SSH_CONFIG": ssh_config, 
            "DB_CONFIG": db_config
        }
    except KeyError as e:
        print(f"Error: Missing environment variable: {e}. Check your .env file.")
        raise
    except ValueError as e:
        print(f"Error: Invalid value for port variable (must be integer): {e}.")
        raise


class MySQLStealthClient:
    """Handles secure data insertion into MySQL, conditionally using SSH tunnel."""

    def __init__(self, ssh_config: Dict[str, Any], db_config: Dict[str, str]):
        self.ssh_config = ssh_config
        self.db_config = db_config
        self.tunnel: SSHTunnelForwarder = None
        self.conn: pymysql.connections.Connection = None

    def __enter__(self) -> 'MySQLStealthClient':
        """Context manager entry point: sets up connection."""
        
        if self.ssh_config['use_tunnel']:
            # --- 1. SSH TUNNEL SETUP ---
            print("Starting SSH tunnel...")
            
            # Prepare optional key/password arguments for SSHTunnelForwarder
            tunnel_kwargs = {}
            if self.ssh_config['ssh_pkey']:
                tunnel_kwargs['ssh_pkey'] = self.ssh_config['ssh_pkey']
            else:
                print("[⚠️] SSH_KEY_PATH is empty. Ensure you are using SSH Agent or password auth.")

            self.tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(self.ssh_config['ssh_address_or_host'], self.ssh_config['ssh_port']),
                ssh_username=self.ssh_config['ssh_username'],
                remote_bind_address=self.ssh_config['remote_bind_address'],
                local_bind_address=self.ssh_config['local_bind_address'],
                **tunnel_kwargs
            )
            self.tunnel.start()

            # Connection parameters point to the local side of the tunnel
            db_host = '127.0.0.1'
            db_port = self.tunnel.local_bind_port
            print(f"SSH Tunnel running on port {db_port}.")

        else:
            # --- 2. DIRECT CONNECTION ---
            print("SSH tunnel disabled. Connecting directly to database...")
            db_host = self.ssh_config['remote_bind_address'][0]
            db_port = self.ssh_config['remote_bind_address'][1]
        
        # --- 3. MYSQL CONNECTION ---
        self.conn = pymysql.connect(
            host=db_host, 
            port=db_port,
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            cursorclass=pymysql.cursors.DictCursor
        )
        print("Database connected.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point: closes DB connection and SSH tunnel (if used)."""
        if self.conn:
            self.conn.close()
        if self.tunnel:
            self.tunnel.stop()
            print("SSH tunnel and DB connection closed.")

    def _execute_batch_insert(self, cursor: pymysql.cursors.DictCursor, sql: str, data: List[Tuple]):
        """Helper for batch execution."""
        if data:
            cursor.executemany(sql, data)

    def insert_hyperliquid_data(self, wallet_address: str, snapshot_time_ms: int, parsed_data: Dict):
        """
        Main method to orchestrate the insertion of all structured data into three tables 
        (snapshots, positions, orders) using a transaction.
        """
        if not self.conn:
            raise ConnectionError("Database connection not established. Use 'with MySQLStealthClient(...) as client:'")
            
        try:
            with self.conn.cursor() as cursor:
                
                # Convert time_ms to DATETIME for the snapshot table
                snapshot_datetime = datetime.datetime.fromtimestamp(snapshot_time_ms / 1000.0)
                
                # --- 1. Insert Summary into hyperliquid_snapshots (Header) ---
                summary = parsed_data['summary']
                
                summary_sql = f"""
                    INSERT INTO hyperliquid_snapshots (
                        wallet_address, snapshot_time_ms, snapshot_datetime, 
                        account_value, total_ntl_pos, total_raw_usd, total_margin_used,
                        withdrawable, cross_maintenance_margin_used
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(summary_sql, (
                    wallet_address, snapshot_time_ms, snapshot_datetime,
                    summary['account_value'], summary['total_ntl_pos'], 
                    summary['total_raw_usd'], summary['total_margin_used'],
                    summary['withdrawable'], summary['cross_maintenance_margin_used']
                ))
                
                # Get the ID of the newly inserted snapshot record
                snapshot_id = cursor.lastrowid
                
                if snapshot_id is None:
                    raise Exception("Failed to retrieve snapshot_id after insertion.")

                # --- 2. Insert Asset Positions into hyperliquid_positions ---
                position_data = [
                    (
                        snapshot_id, p['coin'], p['type'], p['size'], 
                        p['leverage_type'], p['leverage_value'], p['entry_price'], 
                        p['position_value'], p['unrealized_pnl'], p['return_on_equity']
                    )
                    for p in parsed_data['asset_positions']
                ]
                position_sql = """
                    INSERT INTO hyperliquid_positions (
                        snapshot_id, coin, type, size, leverage_type, 
                        leverage_value, entry_price, position_value, 
                        unrealized_pnl, return_on_equity
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                self._execute_batch_insert(cursor, position_sql, position_data)

                # --- 3. Insert Open Orders into hyperliquid_open_orders ---
                order_data = [
                    (
                        o['order_id'], snapshot_id, o['coin'], o['side'], 
                        o['limit_price'], o['quantity'], o['timestamp_ms'], 
                        o['order_type'], o['reduce_only'], o['time_in_force']
                    )
                    for o in parsed_data['open_orders']
                ]
                order_sql = """
                    INSERT INTO hyperliquid_open_orders (
                        order_id, snapshot_id, coin, side, limit_price, 
                        quantity, timestamp_ms, order_type, reduce_only, time_in_force
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                self._execute_batch_insert(cursor, order_sql, order_data)

            self.conn.commit()
            print(f"✅ Successfully inserted snapshot (ID: {snapshot_id}) for wallet {wallet_address}.")
            
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Database error during insertion. Rolled back transaction. Error: {e}")
            raise