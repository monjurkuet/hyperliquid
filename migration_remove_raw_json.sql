-- Migration to remove raw_json column from hyperliquid_snapshots table
-- Run this if you have an existing database and want to apply the new changes.

ALTER TABLE hyperliquid_snapshots DROP COLUMN raw_json;
