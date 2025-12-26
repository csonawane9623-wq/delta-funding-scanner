import requests
import urllib.parse
import os

# ================= CONFIG =================
BASE_URL = "https://api.india.delta.exchange"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Alert threshold in PERCENT (800 hundred = 0.8%)
ALERT_THRESHOLD = 0.0800

session = requests.Session()
session.headers.update({
    "User-Agent": "delta-funding-scanner",
    "Accept": "application/json"
})

# ================= TELEGRAM =================
def send_telegram(message):
    try:
        text = urllib.parse.quote(message)
        url = (
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
            f"/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={text}"
        )
        r = requests.get(url, timeout=20)
        if r.ok:
            print("📨 Telegram alert sent")
            return True
    except Exception as e:
        print("Telegram error:", e)

    print("⚠️ Telegram alert failed")
    return False


# ================= FUNDING INTERVAL =================
_interval_cache = {}

def get_funding_interval(symbol):
    if symbol in _interval_cache:
        return _interval_cache[symbol]

    try:
        r = session.get(f"{BASE_URL}/v2/products/{symbol}", timeout=10)
        if r.ok and r.json().get("success"):
            secs = (
                r.json()["result"]
                .get("product_specs", {})
                .get("rate_exchange_interval")
            )
            if secs:
                hours = int(secs / 3600)
                _interval_cache[symbol] = hours
                return hours
    except:
        pass

    return None


# ================= MAIN =================
def main():
    print("Delta Exchange – Funding Rate Scanner")
    print("=" * 70)
    print("Fetching perpetual futures data from Delta Exchange...\n")

    r = session.get(
        f"{BASE_URL}/v2/tickers",
        params={"contract_types": "perpetual_futures"},
        timeout=20
    )
    r.raise_for_status()

    tickers = r.json()["result"]
    funding_data = []

    for t in tickers:
        try:
            rate = float(t.get("funding_rate"))
        except:
            continue

        funding_data.append({
            "symbol": t["symbol"],
            "rate": rate,                 # already in %
            "mark": t.get("mark_price"),
            "volume": t.get("volume")
        })

    funding_data.sort(key=lambda x: abs(x["rate"]), reverse=True)
    top3 = funding_data[:3]

    print("TOP 3 HIGHEST FUNDING CONTRACTS")
    print("=" * 70)

    alert_candidates = []

    for c in top3:
        interval = get_funding_interval(c["symbol"])
        interval_str = f"/{interval}h" if interval else ""

        rate = c["rate"]
        direction = "Shorts pay Longs" if rate < 0 else "Longs pay Shorts"

        print(
            f"Symbol: {c['symbol']:<10} | "
            f"Funding: {rate:.4f}% {interval_str} | "
            f"Mark: {c['mark']}"
        )

        if abs(rate) >= ALERT_THRESHOLD:
            alert_candidates.append({
                **c,
                "interval": interval_str,
                "direction": direction
            })

    if alert_candidates:
        msg = "🚨 DELTA FUNDING ALERT 🚨\n\n"

        for c in alert_candidates:
            msg += (
                f"{c['symbol']}\n"
                f"Funding: {c['rate']:.4f}% {c['interval']}\n"
                f"Direction: {c['direction']}\n"
                f"Mark: {c['mark']}\n"
                f"Volume: {c['volume']}\n"
                f"https://www.delta.exchange/app/perpetual_futures/{c['symbol']}\n\n"
            )

        send_telegram(msg)
    else:
        print(
            f"\nℹ️ No funding rate crossed ±{ALERT_THRESHOLD:.2f}% "
            f"(Telegram alert skipped)"
        )

    print("\n✓ Bot execution completed")


if __name__ == "__main__":
    main()
