#!/usr/bin/env python3

import argparse
import os
import sys
import time
from datetime import datetime

import requests

BASE_URL = "https://api.nonkyc.io/api/v2"

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def supports_color():
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"

USE_COLOR = supports_color()

def c(text, color):
    return f"{color}{text}{RESET}" if USE_COLOR else text

def clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

def fmt(x, d=8):
    s = f"{x:,.{d}f}"
    return s.rstrip("0").rstrip(".")

def fetch_orderbook(symbol, limit):
    r = requests.get(
        f"{BASE_URL}/market/orderbook",
        params={"symbol": symbol, "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

def fetch_ticker(symbol):
    try:
        r = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {}

# ✅ fixed widths (key to clean layout)
IDX_W = 3
PRICE_W = 14
QTY_W = 14
TOTAL_W = 16
SIDE_W = 48
FULL_W = SIDE_W * 2 + 3

def format_row(i, price, qty, side):
    total = price * qty

    price_s = fmt(price)
    qty_s = fmt(qty, 6)
    total_s = fmt(total, 4)

    if side == "bid":
        price_s = c(f"{price_s:>{PRICE_W}}", GREEN)
    else:
        price_s = c(f"{price_s:>{PRICE_W}}", RED)

    return (
        f"{i:>{IDX_W}} "
        f"{price_s} "
        f"{qty_s:>{QTY_W}} "
        f"{total_s:>{TOTAL_W}}"
    )

def render(base, quote, symbol, book, ticker, depth, refresh):
    bids = [(float(x["price"]), float(x["quantity"])) for x in book["bids"]]
    asks = [(float(x["price"]), float(x["quantity"])) for x in book["asks"]]

    bids.sort(key=lambda x: x[0], reverse=True)
    asks.sort(key=lambda x: x[0])

    bids = bids[:depth]
    asks = asks[:depth]

    best_bid = bids[0][0] if bids else 0
    best_ask = asks[0][0] if asks else 0
    spread = best_ask - best_bid if best_bid and best_ask else 0
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
    spread_pct = (spread / mid * 100) if mid else 0

    total_bid_qty = sum(q for _, q in bids)
    total_ask_qty = sum(q for _, q in asks)
    total_bid_val = sum(p * q for p, q in bids)
    total_ask_val = sum(p * q for p, q in asks)

    title = f"NonKYC Order Book — {base}/{quote} ({symbol})"
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if refresh:
        ts += f" • refresh {refresh}s • Ctrl+C to exit"

    print(c("=" * FULL_W, CYAN))
    print(c(title.center(FULL_W), BOLD))
    print(c(ts.center(FULL_W), DIM))
    print(c("=" * FULL_W, CYAN))

    # ticker
    if ticker:
        last = float(ticker.get("lastPrice", 0))
        change = float(ticker.get("priceChangePercent", 0))
        high = float(ticker.get("highPrice", 0))
        low = float(ticker.get("lowPrice", 0))

        col = GREEN if change >= 0 else RED

        print("\n" + c("24h Ticker Stats:", BOLD))
        print(f" Last Price : {fmt(last)} {quote}")
        print(f" Change     : {c(f'{change:+.2f}%', col)}")
        print(f" High       : {fmt(high)}")
        print(f" Low        : {fmt(low)}")

    print("\n" + c("Market Snapshot:", BOLD))
    print(f" Best Bid   : {c(fmt(best_bid), GREEN)}")
    print(f" Best Ask   : {c(fmt(best_ask), RED)}")
    print(f" Mid        : {fmt(mid)}")
    print(f" Spread     : {fmt(spread)} ({spread_pct:.4f}%)")

    print("\n" + c("-" * FULL_W, CYAN))

    print(
        c("BIDS".center(SIDE_W), GREEN + BOLD)
        + c(" | ", CYAN)
        + c("ASKS".center(SIDE_W), RED + BOLD)
    )

    print(c("-" * FULL_W, CYAN))

    header = (
        f"{'#':>{IDX_W}} "
        f"{'Price':>{PRICE_W}} "
        f"{'Qty':>{QTY_W}} "
        f"{'Total':>{TOTAL_W}}"
    )

    print(header.ljust(SIDE_W) + " | " + header.ljust(SIDE_W))
    print(c("-" * FULL_W, CYAN))

    rows = max(len(bids), len(asks))

    for i in range(rows):
        left = ""
        right = ""

        if i < len(bids):
            p, q = bids[i]
            left = format_row(i + 1, p, q, "bid")

        if i < len(asks):
            p, q = asks[i]
            right = format_row(i + 1, p, q, "ask")

        print(f"{left:<{SIDE_W}} | {right:<{SIDE_W}}")

    print(c("-" * FULL_W, CYAN))

    left_tot = f"Totals: qty={fmt(total_bid_qty,6)} val={fmt(total_bid_val,4)}"
    right_tot = f"Totals: qty={fmt(total_ask_qty,6)} val={fmt(total_ask_val,4)}"

    print(
        f"{c(left_tot, GREEN):<{SIDE_W}} | {c(right_tot, RED):<{SIDE_W}}"
    )

    print("\n" + c("Order Book Imbalance:", BOLD))

    total = total_bid_qty + total_ask_qty
    if total > 0:
        bid_pct = total_bid_qty / total * 100
        ask_pct = total_ask_qty / total * 100

        skew = "BUY pressure" if bid_pct > ask_pct else "SELL pressure"

        bar_len = 60
        bid_bar = int(bar_len * bid_pct / 100)
        ask_bar = bar_len - bid_bar

        bar = c("█" * bid_bar, GREEN) + c("█" * ask_bar, RED)

        print(f" Bid: {c(f'{bid_pct:.2f}%', GREEN)}")
        print(f" Ask: {c(f'{ask_pct:.2f}%', RED)}")
        print(f" Skew: {c(skew, GREEN if bid_pct > ask_pct else RED)}")
        print(f" [{bar}]")

    print("\n" + c("=" * FULL_W, CYAN))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("quote")
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("-t", "--refresh", type=int, default=0)
    args = parser.parse_args()

    base = args.base.upper()
    quote = args.quote.upper()
    symbol = f"{base}_{quote}"

    try:
        if args.refresh:
            while True:
                try:
                    book = fetch_orderbook(symbol, args.depth)
                    ticker = fetch_ticker(symbol)
                    clear()
                    render(base, quote, symbol, book, ticker, args.depth, args.refresh)
                except Exception as e:
                    print(c(f"[warn] {e}", YELLOW))
                time.sleep(args.refresh)
        else:
            book = fetch_orderbook(symbol, args.depth)
            ticker = fetch_ticker(symbol)
            render(base, quote, symbol, book, ticker, args.depth, 0)

    except KeyboardInterrupt:
        print("\nExiting")

if __name__ == "__main__":
    main()