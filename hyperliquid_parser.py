import json
from typing import Dict, List, Any
import datetime

def safe_get(data: dict, key: str, default: Any):
    """Safely retrieves a key, returning default if None or missing."""
    # Check for both missing key and explicit None value
    return data.get(key) if data.get(key) is not None else default

def parse_hyperliquid_data(data: dict) -> dict:
    """
    Parses the raw Hyperliquid WebSocket data structure (received under the 'data' key) 
    into a simplified, structured dictionary suitable for database insertion.
    
    This function uses robust defaults for fields determined to be NOT NULL in the database
    schema, preventing insertion errors.
    """
    clearinghouse_state = data.get("clearinghouseState", {})
    margin_summary = clearinghouse_state.get("marginSummary", {})
    
    # 1. Extract Global Summary (hyperliquid_snapshots)
    
    # Get time from 'clearinghouseState' (or use current timestamp as fallback)
    snapshot_time_ms = safe_get(clearinghouse_state, "time", int(datetime.datetime.now().timestamp() * 1000))

    summary = {
        "snapshot_time_ms": snapshot_time_ms, 
        
        # Core margin summary fields are expected to be NOT NULL, must have defaults
        "account_value": safe_get(margin_summary, "accountValue", "0.0"),
        "total_ntl_pos": safe_get(margin_summary, "totalNtlPos", "0.0"),
        "total_raw_usd": safe_get(margin_summary, "totalRawUsd", "0.0"),
        "total_margin_used": safe_get(margin_summary, "totalMarginUsed", "0.0"),
        
        # FIX: Correctly locate 'withdrawable' at clearinghouseState level and provide non-null default.
        # It was causing the (1048, "Column 'withdrawable' cannot be null") error.
        "withdrawable": safe_get(clearinghouse_state, "withdrawable", "0.0"), 
        
        # 'cross_maintenance_margin_used' is treated as nullable (can be None)
        "cross_maintenance_margin_used": clearinghouse_state.get("crossMaintenanceMarginUsed"),
    }

    # 2. Extract Asset Positions (hyperliquid_positions)
    asset_positions = []
    raw_positions = clearinghouse_state.get("assetPositions", [])
    
    for asset_data in raw_positions:
        position = asset_data.get("position", {})
        leverage = position.get("leverage", {})
        
        size_str = safe_get(position, "szi", "0")
        coin = safe_get(position, "coin", "")
        
        # Only process positions with non-zero size and a valid coin name
        if size_str != "0" and coin:
            
            asset_positions.append({
                "coin": coin,
                # Correct location for 'type' (fixes previous issue)
                "type": safe_get(asset_data, "type", "oneWay"), 
                "size": size_str, 
                "leverage_type": safe_get(leverage, "type", "cross"), 
                "leverage_value": safe_get(leverage, "value", 1), 
                
                # entry_price can be null
                "entry_price": position.get("entryPx"), 
                
                # These fields are NOT NULL
                "position_value": safe_get(position, "positionValue", "0.0"), 
                "unrealized_pnl": safe_get(position, "unrealizedPnl", "0.0"),
                "return_on_equity": safe_get(position, "returnOnEquity", "0.0"),
            })

    # 3. Extract Open Orders (hyperliquid_open_orders)
    open_orders = []
    raw_orders = data.get("openOrders", [])

    for order in raw_orders:
        if order.get("oid") is not None:
            open_orders.append({
                "order_id": order.get("oid"),
                "coin": safe_get(order, "coin", ""),
                "side": safe_get(order, "side", ""),
                "limit_price": safe_get(order, "limitPx", "0.0"), 
                "quantity": safe_get(order, "sz", "0.0"), 
                "timestamp_ms": safe_get(order, "timestamp", 0),
                "order_type": safe_get(order, "orderType", "Limit"),
                "reduce_only": safe_get(order, "reduceOnly", False),
                "time_in_force": safe_get(order, "tif", "Gtc"),
            })

    # 4. Combine and Return
    return {
        "summary": summary,
        "asset_positions": asset_positions,
        "open_orders": open_orders,
        "snapshot_time_ms": snapshot_time_ms
    }