import os
import re
import logging
import argparse
from datetime import datetime
from decimal import Decimal

import pandas as pd
from sshtunnel import SSHTunnelForwarder
import pymysql
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# multipliers for common money suffixes
MUL = {'': 1, 'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}

def parse_money(s):
    """Parse strings like '$39.18M', '+$151.97K', '-$15.36M' -> Decimal(39180000)
    Returns None if input is empty/NaN.
    """
    if pd.isna(s):
        return None
    if isinstance(s, (int, float, Decimal)):
        return Decimal(str(s))
    s = str(s).strip()
    if s == '':
        return None

    s = s.replace(',', '')
    m = re.match(r"^([+-])?\s*\$?\s*([0-9]*\.?[0-9]+)\s*([KMBkmb]?)$", s)
    if not m:
        try:
            return Decimal(re.sub(r'[^0-9.-]', '', s))
        except Exception:
            logger.warning('Unparseable money string: %s', s)
            return None

    sign, num, suffix = m.groups()
    num = Decimal(num)
    mult = MUL.get(suffix.upper(), 1)
    value = num * mult
    if sign == '-':
        value = -value
    return value

def normalize_bias(bias):
    if pd.isna(bias):
        return None
    val = str(bias).strip().lower()
    mapping = {
        'very bullish': 'very_bullish',
        'bullish': 'bullish',
        'slightly bullish': 'slightly_bullish',
        'slightly bearish': 'slightly_bearish',
        'bearish': 'bearish',
        'very bearish': 'very_bearish',
        'neutral': 'neutral'
    }
    if val in mapping:
        return mapping[val]
    return re.sub(r'[^a-z0-9]+', '_', val).strip('_')

def normalize_wallet_type(t):
    if pd.isna(t):
        return None
    val = str(t).strip().lower()
    if 'money printer' in val:
        return 'money_printer'
    if 'exchange' in val:
        return 'exchange'
    return re.sub(r'[^a-z0-9]+', '_', val).strip('_')

def prepare_row(row):
    return {
        'wallet_address': row.get('walletAddress') or row.get('wallet_address') or row.get('wallet'),
        'margin_usd': parse_money(row.get('margin')),
        'wallet_bias': normalize_bias(row.get('wallet_bias')),
        'position_usd': parse_money(row.get('position')),
        'upnl_usd': parse_money(row.get('upnl')),
        'wallet_type': normalize_wallet_type(row.get('wallet_type'))
    }

def get_db_connection_via_ssh(ssh_config, db_config):
    ssh_host = ssh_config.get('SSH_HOST')
    if not ssh_host:
        raise ValueError('SSH_HOST not provided for SSH tunnel')
    ssh_port = int(ssh_config.get('SSH_PORT', 22))
    ssh_user = ssh_config.get('SSH_USER')
    ssh_pkey = ssh_config.get('SSH_KEY_PATH') or None

    remote_db_host = ssh_config.get('REMOTE_DB_HOST') or db_config.get('DB_HOST', '127.0.0.1')
    remote_db_port = int(ssh_config.get('REMOTE_DB_PORT') or db_config.get('DB_PORT', 3306))
    remote_bind_address = (remote_db_host, remote_db_port)

    t_kwargs = dict(
        ssh_address_or_host=(ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_pkey=ssh_pkey,
        remote_bind_address=remote_bind_address,
    )
    if ssh_config.get('LOCAL_BIND_PORT'):
        t_kwargs['local_bind_address'] = ('127.0.0.1', int(ssh_config['LOCAL_BIND_PORT']))

    t = SSHTunnelForwarder(**t_kwargs)
    t.start()
    local_port = t.local_bind_port
    logger.info('SSH tunnel established: localhost:%s -> %s:%s via %s', local_port, remote_bind_address[0], remote_bind_address[1], ssh_host)

    try:
        conn = pymysql.connect(host='127.0.0.1', port=local_port, user=db_config.get('DB_USER'),
                               password=db_config.get('DB_PASSWORD'), db=db_config.get('DB_NAME'),
                               connect_timeout=8, read_timeout=15, write_timeout=15,
                               cursorclass=pymysql.cursors.Cursor)
    except Exception:
        t.stop()
        raise
    return conn, t

def get_db_connection_direct(db_config):
    host = db_config.get('DB_HOST', '127.0.0.1')
    port = int(db_config.get('DB_PORT', 3306))
    logger.info('Attempting direct MySQL connection to %s:%s', host, port)
    conn = pymysql.connect(host=host, port=port, user=db_config.get('DB_USER'),
                           password=db_config.get('DB_PASSWORD'), db=db_config.get('DB_NAME'),
                           connect_timeout=8, read_timeout=15, write_timeout=15,
                           cursorclass=pymysql.cursors.Cursor)
    return conn


# removed threaded connector logic and mysql-connector; using PyMySQL only for simplicity and reliability

def ensure_schema(conn):
    path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    if not os.path.exists(path):
        logger.warning('schema.sql not found at %s', path)
        return
    with open(path, 'r', encoding='utf8') as f:
        sql = f.read()
    cursor = conn.cursor()
    for stmt in sql.split(';'):
        stmt = stmt.strip()
        if not stmt:
            continue
        cursor.execute(stmt)
    conn.commit()
    cursor.close()

def run_import(file_path, create_schema=False, use_ssh=False):
    # Only use the env variables present in your final .env
    db_config = {
        'DB_USER': os.getenv('DB_USER'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD'),
        'DB_NAME': os.getenv('DB_NAME'),
        'DB_HOST': os.getenv('REMOTE_DB_HOST') or os.getenv('DB_HOST'),
        'DB_PORT': os.getenv('REMOTE_DB_PORT') or os.getenv('DB_PORT', '3306'),
    }
    ssh_config = {
        'SSH_HOST': os.getenv('SSH_HOST'),
        'SSH_PORT': os.getenv('SSH_PORT', '22'),
        'SSH_USER': os.getenv('SSH_USER'),
        'SSH_KEY_PATH': os.getenv('SSH_KEY_PATH'),
        'REMOTE_DB_HOST': os.getenv('REMOTE_DB_HOST'),
        'REMOTE_DB_PORT': os.getenv('REMOTE_DB_PORT'),
        'LOCAL_BIND_PORT': os.getenv('LOCAL_BIND_PORT'),
    }

    conn = None
    tunnel = None
    try:
        if use_ssh:
            conn, tunnel = get_db_connection_via_ssh(ssh_config, db_config)
        else:
            conn = get_db_connection_direct(db_config)

        logger.info('Connection object: %s', getattr(conn, '__class__', str(conn)))
        try:
            connected = conn.is_connected() if hasattr(conn, 'is_connected') else True
        except Exception:
            connected = False
        logger.info('conn.is_connected -> %s', connected)

        if create_schema:
            logger.info('Creating schema (create_schema=True)')
            try:
                ensure_schema(conn)
                logger.info('Schema creation completed')
            except Exception as e:
                logger.exception('Schema creation failed: %s', e)
                raise

        logger.info('Reading Excel file: %s', file_path)
        df = pd.read_excel(file_path)
        logger.info('Read %d rows from %s', len(df), file_path)

        records = []
        for _, r in df.iterrows():
            rec = {
                'walletAddress': r.get('walletAddress') if 'walletAddress' in r.index else r.get('wallet_address'),
                'margin': r.get('margin'),
                'wallet_bias': r.get('wallet_bias') if 'wallet_bias' in r.index else r.get('wallet_bias'),
                'position': r.get('position'),
                'upnl': r.get('upnl'),
                'wallet_type': r.get('wallet_type') if 'wallet_type' in r.index else r.get('wallet_type')
            }
            records.append(prepare_row(rec))

        cursor = conn.cursor()

        # Process records one-by-one (no batching) as requested.
        upsert_wallet_sql = (
            "INSERT INTO wallets (address, wallet_type, created_at) "
            "VALUES (%s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE wallet_type=VALUES(wallet_type), id=LAST_INSERT_ID(id)"
        )
        insert_sql = (
            "INSERT INTO wallet_snapshots "
            "(wallet_id, margin_usd, wallet_bias, position_usd, upnl_usd, snapshot_time) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )

        total = len(records)
        for idx, r in enumerate(records, start=1):
            addr = r['wallet_address']
            if not addr:
                logger.warning('Skipping row %d with empty address', idx)
                continue

            # upsert wallet and get id via LAST_INSERT_ID
            cursor.execute(upsert_wallet_sql, (addr, r.get('wallet_type')))
            wallet_id = cursor.lastrowid
            if not wallet_id:
                # attempt a direct select as fallback
                cursor.execute("SELECT id FROM wallets WHERE address = %s", (addr,))
                row = cursor.fetchone()
                if row:
                    wallet_id = row[0]
                else:
                    logger.warning('Could not obtain wallet id for %s at row %d', addr, idx)
                    continue

            # insert snapshot for this single row
            cursor.execute(insert_sql, (
                wallet_id,
                r['margin_usd'],
                r['wallet_bias'],
                r['position_usd'],
                r['upnl_usd'],
                datetime.utcnow()
            ))
            conn.commit()

            if idx % 50 == 0 or idx == total:
                logger.info('Processed %d/%d rows', idx, total)
    except Exception as err:
        logger.exception('DB error: %s', err)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
        if tunnel:
            tunnel.stop()

def main():
    parser = argparse.ArgumentParser(description='Import and normalize wallet_pnl.xlsx into MySQL.')
    parser.add_argument('file', nargs='?', default='wallet_pnl.xlsx')
    parser.add_argument('--ssh', action='store_true', help='Use SSH tunnel (reads SSH_* env vars)')
    parser.add_argument('--create-schema', action='store_true', help='Create DB schema before inserting')
    args = parser.parse_args()

    run_import(args.file, create_schema=args.create_schema, use_ssh=args.ssh)

if __name__ == '__main__':
    main()
