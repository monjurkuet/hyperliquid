-- Schema for normalized wallet pnl data
CREATE TABLE IF NOT EXISTS wallets (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  address VARCHAR(128) NOT NULL,
  wallet_type VARCHAR(64),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_wallet_address (address)
);

CREATE TABLE IF NOT EXISTS wallet_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  wallet_id BIGINT UNSIGNED NOT NULL,
  margin_usd DECIMAL(30,2),
  wallet_bias VARCHAR(64),
  position_usd DECIMAL(30,2),
  upnl_usd DECIMAL(30,2),
  -- removed page_url and page per user request
  snapshot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_wallet_id (wallet_id),
  CONSTRAINT fk_wallet_snapshots_wallet FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
);


#############
-- ===================================================================
-- Database Schema for Hyperliquid Stealth Monitor
-- Target: MySQL / MariaDB
-- ===================================================================

-- -------------------------------------------------------------------
-- Table: hyperliquid_snapshots
-- Stores account-level summary data captured at a specific time.
-- This table serves as the primary data point for a 'snapshot'.
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `hyperliquid_snapshots` (
    -- Primary Key: Unique ID for this specific data capture event
    `snapshot_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,

    -- Identifying the target wallet
    `wallet_address` CHAR(42) NOT NULL COMMENT 'Ethereum wallet address that was monitored (e.g., 0x...)',

    -- Timestamp from the Hyperliquid system (in milliseconds)
    `snapshot_time_ms` BIGINT UNSIGNED NOT NULL,

    -- Converted timestamp for human-readable querying (UNIX_TIMESTAMP(snapshot_time_ms / 1000))
    `snapshot_datetime` DATETIME NOT NULL,

    -- Account Summary Metrics (from clearinghouseState.marginSummary)
    `account_value` DECIMAL(30, 18) NOT NULL,
    `total_ntl_pos` DECIMAL(30, 18) NOT NULL COMMENT 'Total Notional Position',
    `total_raw_usd` DECIMAL(30, 18) NOT NULL,
    `total_margin_used` DECIMAL(30, 18) NOT NULL,
    `withdrawable` DECIMAL(30, 18) NOT NULL,
    `cross_maintenance_margin_used` DECIMAL(30, 18) NULL,

    -- Audit/Debugging Field: Stores the complete raw JSON message
    -- raw_json column removed as per new requirement

    PRIMARY KEY (`snapshot_id`),
    -- Indexing for quick lookups by wallet and time
    INDEX `idx_wallet_time` (`wallet_address`, `snapshot_datetime`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------
-- Table: hyperliquid_positions
-- Stores individual asset positions linked back to a hyperliquid_snapshot.
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `hyperliquid_positions` (
    `position_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,

    -- Foreign Key linking back to the account snapshot
    `snapshot_id` INT UNSIGNED NOT NULL,

    -- Position Details (from assetPositions array)
    `coin` VARCHAR(16) NOT NULL,
    `type` VARCHAR(16) NOT NULL COMMENT 'Position type: e.g., oneWay',
    `size` DECIMAL(30, 18) NOT NULL COMMENT 'Position size (szi)',
    
    -- Leverage Details (from position.leverage)
    `leverage_type` VARCHAR(16) NOT NULL,
    `leverage_value` INT NOT NULL,

    -- Financial Metrics
    `entry_price` DECIMAL(30, 18) NULL,
    `position_value` DECIMAL(30, 18) NOT NULL,
    `unrealized_pnl` DECIMAL(30, 18) NOT NULL,
    `return_on_equity` DECIMAL(30, 18) NOT NULL,

    PRIMARY KEY (`position_id`),
    
    -- Foreign Key constraint
    CONSTRAINT `fk_position_snapshot_id`
        FOREIGN KEY (`snapshot_id`)
        REFERENCES `hyperliquid_snapshots` (`snapshot_id`)
        ON DELETE CASCADE,
        
    INDEX `idx_position_snapshot_id` (`snapshot_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -------------------------------------------------------------------
-- Table: hyperliquid_open_orders
-- Stores individual open orders linked back to a hyperliquid_snapshot.
-- Mapped to the 'openOrders' array in the raw data.
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `hyperliquid_open_orders` (
    -- Unique Order ID from Hyperliquid (oid)
    `order_id` BIGINT UNSIGNED NOT NULL,
    
    -- Foreign Key linking back to the account snapshot
    `snapshot_id` INT UNSIGNED NOT NULL,

    -- Order Details
    `coin` VARCHAR(16) NOT NULL,
    `side` CHAR(1) NOT NULL COMMENT 'Order side (e.g., A for Ask/Sell, B for Bid/Buy)',
    `limit_price` DECIMAL(30, 18) NOT NULL COMMENT 'Price at which the order is placed (limitPx)',
    `quantity` DECIMAL(30, 18) NOT NULL COMMENT 'Order size (sz)',
    `timestamp_ms` BIGINT UNSIGNED NOT NULL COMMENT 'Order timestamp (timestamp)',
    `order_type` VARCHAR(16) NOT NULL COMMENT 'Order type (e.g., Limit, Market)',
    `reduce_only` BOOLEAN NOT NULL,
    `time_in_force` VARCHAR(16) NOT NULL COMMENT 'Time In Force (tif)',
    
    -- We use a composite key since the 'oid' is the unique identifier for the order itself
    PRIMARY KEY (`order_id`, `snapshot_id`),
    
    -- Foreign Key constraint
    CONSTRAINT `fk_order_snapshot_id`
        FOREIGN KEY (`snapshot_id`)
        REFERENCES `hyperliquid_snapshots` (`snapshot_id`)
        ON DELETE CASCADE,
        
    INDEX `idx_order_snapshot_id` (`snapshot_id`),
    INDEX `idx_order_coin` (`coin`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;