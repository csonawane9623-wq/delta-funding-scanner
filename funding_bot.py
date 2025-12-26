import requests
import json
import time
import os
from datetime import datetime

# =============================================================================
# CONFIG
# =============================================================================
BASE_URL = "https://api.india.delta.exchange"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ALERT_THRESHOLD = 0.0800       # percentage (±0.8000%)
COOLDOWN_FILE = "last_alerts.json"

session = requests.Session()
session.headers.update({
    "User-Agent": "delta-funding-scanner",
    "Accept": "application/json"
})

# =============================================================================
# UTILITIES
# =============================================================================
def format_ts(ts):
    try:
        return datetime.fromtimestamp(ts / 1_000_000).strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return "N/A"

def get_funding_interval(symbol):
    try:
        r = session.get(f"{BASE_URL}/v2/products/{symbol}", timeout=10)
        if r.ok and r.json().get("success"):
            sec = r.json()["result"]["product_specs"].get("rate_exchange_interval")
            return sec / 3600 if sec else None
    except:
        pass
    return None

# =============================================================================
# COOLDOWN LOGIC
# =============================================================================
def load_last_alerts():
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_last_alerts(data):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f)

def can_send(symbol, interval_hours, last_alerts):
    now = time.time()
    last = last_alerts.get(symbol, 0)
    return (now - last) >= (interval_hours * 3600)

# =============================================================================
# TELEGRAM
# =============================================================================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
        r.raise_for_status()
        print("📨 Telegram alert sent")
        return True
    except Exception as e:
        print(f"⚠️ Telegram skipped (network issue): {e}")
        return False

# =============================================================================
# CORE LOGIC
# =============================================================================
def run():
    print("Delta Exchange – Funding Rate Scanner")
    print("=" * 70)
    print("Fetching perpetual futures data from Delta Exchange...\n")

    r = session.get(
        f"{BASE_URL}/v2/tickers",
        params={"contract_types": "perpetual_futures"},
        timeout=10
    )

    if not r.ok or not r.json().get("success"):
        print("❌ Failed to fetch funding data")
        return

    tickers = r.json()["result"]

    contracts = []
    for t in tickers:
        try:
            rate = float(t["funding_rate"])
        except:
            continue

        contracts.append({
            "symbol": t["symbol"],
            "funding_rate": rate,
            "mark": t.get("mark_price"),
            "volume": t.get("volume", 0),
            "timestamp": t.get("timestamp")
        })

    contracts.sort(key=lambda x: abs(x["funding_rate"]), reverse=True)
    top3 = contracts[:3]

    print("\nTOP 3 HIGHEST FUNDING CONTRACTS")
    print("=" * 70)

    for c in top3:
        interval = get_funding_interval(c["symbol"])
        interval_str = f"/{int(interval)}h" if interval else ""
        print(
            f"Symbol: {c['symbol']:<10} | "
            f"Funding: {c['funding_rate']:+.4f}% {interval_str} | "
            f"Mark: {c['mark']}"
        )

    # =============================================================================
    # ALERT FILTER
    # =============================================================================
    alert_candidates = [
        c for c in top3 if abs(c["funding_rate"]) >= ALERT_THRESHOLD
    ]

    if not alert_candidates:
        print(f"\nℹ️ No funding rate crossed ±{ALERT_THRESHOLD:.4f}% (Telegram alert skipped)")
        return

    last_alerts = load_last_alerts()
    final_alerts = []

    for c in alert_candidates:
        interval = get_funding_interval(c["symbol"])
        if not interval:
            continue

        if can_send(c["symbol"], interval, last_alerts):
            final_alerts.append((c, interval))
            last_alerts[c["symbol"]] = time.time()

    if not final_alerts:
        print("\nℹ️ Alert-worthy contracts are in cooldown period")
        return

    # =============================================================================
    # BUILD MESSAGE
    # =============================================================================
    msg = "🚨 DELTA FUNDING ALERT 🚨\n\n"

    for c, interval in final_alerts:
        direction = "Shorts pay Longs" if c["funding_rate"] < 0 else "Longs pay Shorts"
        msg += (
            f"{c['symbol']}\n"
            f"Funding: {c['funding_rate']:+.4f}% /{int(interval)}h\n"
            f"Direction: {direction}\n"
            f"Mark: {c['mark']}\n"
            f"Volume: {c['volume']}\n"
            f"https://www.delta.exchange/app/perpetual_futures/{c['symbol']}\n\n"
        )

    if send_telegram(msg):
        save_last_alerts(last_alerts)

# =============================================================================
# ENTRY
# =============================================================================
if __name__ == "__main__":
    run()
    print("\n✓ Bot execution completed")
