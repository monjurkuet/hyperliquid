import json

def parse_hyperliquid_data(data: dict) -> dict:
    """
    Parses the raw Hyperliquid WebSocket data structure into a simplified,
    structured dictionary suitable for database insertion.

    Args:
        data: The dict containing 'clearinghouseState' and 'openOrders'.

    Returns:
        A dictionary containing 'summary', 'asset_positions', and 'open_orders'.
    """
    # 1. Extract Global Summary
    margin_summary = data.get("clearinghouseState", {}).get("marginSummary", {})
    summary = {
        "account_value": margin_summary.get("accountValue"),
        "total_ntl_pos": margin_summary.get("totalNtlPos"),
        "total_raw_usd": margin_summary.get("totalRawUsd"),
        "total_margin_used": margin_summary.get("totalMarginUsed"),
    }

    # 2. Extract Asset Positions
    asset_positions = []
    raw_positions = data.get("clearinghouseState", {}).get("assetPositions", [])
    
    for asset_data in raw_positions:
        position = asset_data.get("position", {})
        if position:
            asset_positions.append({
                "coin": position.get("coin"),
                "size": position.get("szi"),
                "value": position.get("positionValue"),
                "pnl": position.get("unrealizedPnl"),
            })

    # 3. Extract Open Orders
    open_orders = []
    raw_orders = data.get("openOrders", [])

    for order in raw_orders:
        open_orders.append({
            "coin": order.get("coin"),
            "side": order.get("side"),
            "price": order.get("limitPx"),
            "size": order.get("sz"),
            "timestamp": order.get("timestamp"),
        })

    # 4. Combine and Return
    return {
        "summary": summary,
        "asset_positions": asset_positions,
        "open_orders": open_orders,
    }

# --- Demonstration using the user-provided data snippet ---
# NOTE: This snippet assumes the data received is at the level immediately
# below the top-level 'data' key from the Hyperliquid API response.
SAMPLE_RAW_DATA = {
    "clearinghouseState": {
        "marginSummary": {
            "accountValue": "40522414.6792389974",
            "totalNtlPos": "242594315.540809989",
            "totalRawUsd": "-202071900.8615710139",
            "totalMarginUsed": "19009551.0888400003"
        },
        "assetPositions": [
            {
                "type": "oneWay",
                "position": {
                    "coin": "ETH",
                    "szi": "52353.9587",
                    "leverage": {"type": "cross", "value": 15},
                    "entryPx": "3201.03",
                    "positionValue": "157496413.9572100043",
                    "unrealizedPnl": "-10090518.7028960008",
                    "returnOnEquity": "-0.9031597998",
                    "liquidationPx": "2349.3048283219",
                    "marginUsed": "10499760.9304799996",
                    "maxLeverage": 15,
                    "cumFunding": {"allTime": "259013.72305", "sinceOpen": "878727.9058750001", "sinceChange": "340584.837313"}
                }
            },
            {
                "type": "oneWay",
                "position": {
                    "coin": "XRP",
                    "szi": "38829121.0",
                    "leverage": {"type": "cross", "value": 10},
                    "entryPx": "2.292413",
                    "positionValue": "85097901.5835999995",
                    "unrealizedPnl": "-3914502.250852",
                    "returnOnEquity": "-0.4397704232",
                    "liquidationPx": "1.2874773749",
                    "marginUsed": "8509790.1583600007",
                    "maxLeverage": 10,
                    "cumFunding": {"allTime": "293843.805473", "sinceOpen": "487582.455385", "sinceChange": "219050.96129"}
                }
            }
        ],
        "time": 1764506145684
    },
    "openOrders": [
        {
            "coin": "ETH",
            "side": "A",
            "limitPx": "3778.0",
            "sz": "22000.0",
            "oid": 250816029404,
            "timestamp": 1764268400229,
            "triggerCondition": "N/A",
            "isTrigger": False,
            "triggerPx": "0.0",
            "children": [],
            "isPositionTpsl": False,
            "reduceOnly": False,
            "orderType": "Limit",
            "origSz": "22000.0",
            "tif": "Gtc",
            "cloid": None
        },
        {
            "coin": "XRP",
            "side": "A",
            "limitPx": "3.178",
            "sz": "6593604.0",
            "oid": 249899272852,
            "timestamp": 1764186802979,
            "triggerCondition": "N/A",
            "isTrigger": False,
            "triggerPx": "0.0",
            "children": [],
            "isPositionTpsl": False,
            "reduceOnly": False,
            "orderType": "Limit",
            "origSz": "6593604.0",
            "tif": "Gtc",
            "cloid": None
        },
        # Including only the first two orders for demonstration clarity
    ]
}

# Run the parser on the sample data
parsed_data = parse_hyperliquid_data(SAMPLE_RAW_DATA)

# Print the output in the requested format
print("# Clearinghouse State Summary (Global)")
for k, v in parsed_data['summary'].items():
    print(f"{k}: {v}")

print("\n# Asset Positions")
print(json.dumps(parsed_data['asset_positions'], indent=4))

print("\n# Open Orders")
print(json.dumps(parsed_data['open_orders'], indent=4))

# This structured object is what you will pass to your MySQL connector
# print(parsed_data)