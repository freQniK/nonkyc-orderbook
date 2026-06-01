#!/usr/bin/env python3

import argparse
import os
import sys
import time
from datetime import datetime

import requests

BASE_URL = "https://api.nonkyc.io/api/v2"

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def supports_color():
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"

USE_COLOR = supports_color()

def c(text, color):
    return f"{color}{text}{RESET}" if USE_COLOR else text

def clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

def fmt(x, d=8):
    try:
        s = f"{float(x):,.{d}f}"
        return s.rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "0"

def fetch_orderbook(symbol, limit):
    """
    GET /market/orderbook
    params: symbol (BTC_USDT format), limit
    returns: { bids: [{price, quantity}], asks: [{price, quantity}] }
    """
    r = requests.get(
        f"{BASE_URL}/market/orderbook",
        params={"symbol": symbol, "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

def fetch_market_info(symbol):
    """
    GET /market/info
    params: symbol (BTC_USDT format)
    returns: { lastPrice, highPrice, lowPrice, volume, primaryAsset, secondaryAsset, ... }
    Per the API docs this is the correct endpoint for price/volume stats.
    """
    try:
        r = requests.get(
            f"{BASE_URL}/market/info",
            params={"symbol": symbol},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

# fixed column widths
IDX_W   = 3
PRICE_W = 14
QTY_W   = 14
TOTAL_W = 16
SIDE_W  = IDX_W + 1 + PRICE_W + 1 + QTY_W + 1 + TOTAL_W   # = 50
SEP     = " | "
FULL_W  = SIDE_W * 2 + len(SEP)                             # = 103

def format_row(i, price, qty, side):
    price_s = fmt(price)
    qty_s   = fmt(qty, 6)
    total_s = fmt(price * qty, 4)

    colored_price = c(f"{price_s:>{PRICE_W}}", GREEN if side == "bid" else RED)

    return (
        f"{i:>{IDX_W}} "
        f"{colored_price} "
        f"{qty_s:>{QTY_W}} "
        f"{total_s:>{TOTAL_W}}"
    )

def render(base, quote, symbol, book, market_info, depth, refresh):
    bids = [(float(x["price"]), float(x["quantity"])) for x in book.get("bids", [])]
    asks = [(float(x["price"]), float(x["quantity"])) for x in book.get("asks", [])]

    bids.sort(key=lambda x: x[0], reverse=True)
    asks.sort(key=lambda x: x[0])

    bids = bids[:depth]
    asks = asks[:depth]

    best_bid  = bids[0][0] if bids else 0.0
    best_ask  = asks[0][0] if asks else 0.0
    spread    = best_ask - best_bid if best_bid and best_ask else 0.0
    mid       = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_pct = (spread / mid * 100) if mid else 0.0

    total_bid_qty = sum(q for _, q in bids)
    total_ask_qty = sum(q for _, q in asks)
    total_bid_val = sum(p * q for p, q in bids)
    total_ask_val = sum(p * q for p, q in asks)

    # ── header ────────────────────────────────────────────────────────────────
    title = f"NonKYC Order Book — {base}/{quote} ({symbol})"
    ts    = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if refresh:
        ts += f"  •  refresh {refresh}s  •  Ctrl+C to exit"

    print(c("=" * FULL_W, CYAN))
    print(c(title.center(FULL_W), BOLD))
    print(c(ts.center(FULL_W), DIM))
    print(c("=" * FULL_W, CYAN))

    # ── 24h stats from /market/info ───────────────────────────────────────────
    if market_info:
        last   = float(market_info.get("lastPrice", 0) or 0)
        high   = float(market_info.get("highPrice",  0) or 0)
        low    = float(market_info.get("lowPrice",   0) or 0)
        vol    = float(market_info.get("volume",     0) or 0)

        # /market/info does not return a change %; calculate from lastPrice vs
        # lowPrice as a rough proxy, or just omit if we don't have open price.
        # NonKYC does not expose openPrice in this endpoint, so we skip change%.
        print("\n" + c("24h Market Stats:", BOLD))
        print(f"  Last Price : {c(fmt(last), CYAN)} {quote}")
        print(f"  24h High   : {fmt(high)} {quote}")
        print(f"  24h Low    : {fmt(low)} {quote}")
        print(f"  24h Volume : {fmt(vol, 4)} {base}")

    # ── market snapshot ───────────────────────────────────────────────────────
    print("\n" + c("Market Snapshot:", BOLD))
    print(f"  Best Bid   : {c(fmt(best_bid), GREEN)} {quote}")
    print(f"  Best Ask   : {c(fmt(best_ask), RED)} {quote}")
    print(f"  Mid Price  : {fmt(mid)} {quote}")
    print(f"  Spread     : {fmt(spread)} {quote}  ({spread_pct:.4f}%)")

    # ── side-by-side order book ───────────────────────────────────────────────
    print("\n" + c("-" * FULL_W, CYAN))
    print(
        c(f"BIDS (buyers) — top {len(bids)}".center(SIDE_W),  BOLD + GREEN)
        + c(SEP, CYAN)
        + c(f"ASKS (sellers) — top {len(asks)}".center(SIDE_W), BOLD + RED)
    )
    print(c("-" * FULL_W, CYAN))

    header = (
        f"{'#':>{IDX_W}} "
        f"{'Price':>{PRICE_W}} "
        f"{'Qty':>{QTY_W}} "
        f"{'Total':>{TOTAL_W}}"
    )
    print(c(header.ljust(SIDE_W), DIM) + c(SEP, CYAN) + c(header.ljust(SIDE_W), DIM))
    print(c("-" * FULL_W, CYAN))

    rows = max(len(bids), len(asks))
    for i in range(rows):
        left  = format_row(i + 1, *bids[i], "bid") if i < len(bids) else ""
        right = format_row(i + 1, *asks[i], "ask") if i < len(asks) else ""

        # pad left side to SIDE_W visible chars (ANSI codes add invisible bytes
        # so we can't use plain ljust on the colored string — pad before coloring)
        left_pad  = SIDE_W - len(
            f"{i+1:>{IDX_W}} {fmt(bids[i][0]):>{PRICE_W}} {fmt(bids[i][1], 6):>{QTY_W}} {fmt(bids[i][0]*bids[i][1], 4):>{TOTAL_W}}"
        ) if i < len(bids) else SIDE_W
        right_pad = SIDE_W - len(
            f"{i+1:>{IDX_W}} {fmt(asks[i][0]):>{PRICE_W}} {fmt(asks[i][1], 6):>{QTY_W}} {fmt(asks[i][0]*asks[i][1], 4):>{TOTAL_W}}"
        ) if i < len(asks) else SIDE_W

        print(
            left  + " " * max(0, left_pad)
            + c(SEP, CYAN)
            + right + " " * max(0, right_pad)
        )

    print(c("-" * FULL_W, CYAN))

    # ── totals ────────────────────────────────────────────────────────────────
    left_tot  = f"  Totals: qty={fmt(total_bid_qty, 6)} {base}  val={fmt(total_bid_val, 4)} {quote}"
    right_tot = f"  Totals: qty={fmt(total_ask_qty, 6)} {base}  val={fmt(total_ask_val, 4)} {quote}"
    print(c(left_tot.ljust(SIDE_W),  GREEN) + c(SEP, CYAN) + c(right_tot.ljust(SIDE_W), RED))

    # ── imbalance bar ─────────────────────────────────────────────────────────
    print("\n" + c("Order Book Imbalance:", BOLD))
    total = total_bid_qty + total_ask_qty
    if total > 0:
        bid_pct = total_bid_qty / total * 100
        ask_pct = total_ask_qty / total * 100
        skew    = "BUY pressure" if bid_pct > ask_pct else "SELL pressure"
        bid_bar = int(60 * bid_pct / 100)
        bar     = c("█" * bid_bar, GREEN) + c("█" * (60 - bid_bar), RED)
        print(f"  Bid share  : {c(f'{bid_pct:.2f}%', GREEN)}")
        print(f"  Ask share  : {c(f'{ask_pct:.2f}%', RED)}")
        print(f"  Skew       : {c(skew, GREEN if bid_pct > ask_pct else RED)}")
        print(f"  [{bar}]")
    else:
        print(c("  No liquidity on either side.", YELLOW))

    print("\n" + c("=" * FULL_W, CYAN))

def main():
    parser = argparse.ArgumentParser(
        description="NonKYC.io order book viewer"
    )
    parser.add_argument("base",  help="Base asset ticker  e.g. BTC")
    parser.add_argument("quote", help="Quote asset ticker e.g. USDT")
    parser.add_argument("--depth",   type=int, default=20,
                        help="Levels per side (default 20)")
    parser.add_argument("-t", "--refresh", type=int, default=0,
                        help="Auto-refresh every N seconds (0 = single snapshot)")
    args = parser.parse_args()

    base   = args.base.upper()
    quote  = args.quote.upper()
    symbol = f"{base}_{quote}"      # NonKYC expects BTC_USDT format
    depth  = max(1, args.depth)
    refresh = max(0, args.refresh)

    def render_once():
        book        = fetch_orderbook(symbol, depth)
        market_info = fetch_market_info(symbol)
        if refresh:
            clear()
        render(base, quote, symbol, book, market_info, depth, refresh)

    try:
        if refresh:
            while True:
                try:
                    render_once()
                except requests.RequestException as e:
                    print(c(f"[warn] {e} — retrying in {refresh}s", YELLOW))
                time.sleep(refresh)
        else:
            render_once()
    except KeyboardInterrupt:
        print("\nExiting.")

if __name__ == "__main__":
    main()