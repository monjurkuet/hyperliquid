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
