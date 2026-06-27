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
    r = requests.get(
        f"{BASE_URL}/market/orderbook",
        params={"symbol": symbol, "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

def fetch_market_info(symbol):
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

# ── column widths ─────────────────────────────────────────────────────────────
IDX_W    = 3
PRICE_W  = 14
QTY_W    = 14
TOTAL_W  = 14
CQTY_W   = 16   # cumulative qty
CTOTAL_W = 18   # cumulative total (USD)
CAVG_W   = 14   # cumulative avg price

# one full side = all columns + spaces between them
SIDE_W = (
    IDX_W + 1
    + PRICE_W + 1
    + QTY_W + 1
    + TOTAL_W + 1
    + CQTY_W + 1
    + CTOTAL_W + 1
    + CAVG_W
)

SEP    = " | "
FULL_W = SIDE_W * 2 + len(SEP)

def build_levels(raw):
    """Parse raw [{price, quantity}] list into (price, qty) tuples."""
    return [(float(x["price"]), float(x["quantity"])) for x in raw]

def cumulative(levels):
    """
    Given a list of (price, qty) levels already sorted in display order,
    return a list of (cum_qty, cum_total, cum_avg) per row.

    cum_avg is the quantity-weighted average price:
        cum_avg = sum(price_i * qty_i) / sum(qty_i)
    which gives heavier weight to levels with larger quantity.
    """
    rows = []
    cum_qty   = 0.0
    cum_total = 0.0
    for price, qty in levels:
        cum_qty   += qty
        cum_total += price * qty
        cum_avg    = cum_total / cum_qty if cum_qty else 0.0
        rows.append((cum_qty, cum_total, cum_avg))
    return rows

def visible_row(i, price, qty, cum_qty, cum_total, cum_avg):
    """Return the plain (no ANSI) string for a row — used for length calc."""
    total = price * qty
    return (
        f"{i:>{IDX_W}} "
        f"{fmt(price):>{PRICE_W}} "
        f"{fmt(qty, 6):>{QTY_W}} "
        f"{fmt(total, 4):>{TOTAL_W}} "
        f"{fmt(cum_qty, 4):>{CQTY_W}} "
        f"{fmt(cum_total, 4):>{CTOTAL_W}} "
        f"{fmt(cum_avg):>{CAVG_W}}"
    )

def format_row(i, price, qty, cum_qty, cum_total, cum_avg, side):
    """Return the ANSI-colored string for a row."""
    total      = price * qty
    price_col  = GREEN if side == "bid" else RED
    cum_col    = GREEN if side == "bid" else RED

    return (
        f"{i:>{IDX_W}} "
        f"{c(f'{fmt(price):>{PRICE_W}}', price_col)} "
        f"{fmt(qty, 6):>{QTY_W}} "
        f"{fmt(total, 4):>{TOTAL_W}} "
        f"{c(f'{fmt(cum_qty, 4):>{CQTY_W}}', DIM + cum_col)} "
        f"{c(f'{fmt(cum_total, 4):>{CTOTAL_W}}', DIM + cum_col)} "
        f"{c(f'{fmt(cum_avg):>{CAVG_W}}', DIM + cum_col)}"
    )

def header_row():
    """Return the plain header string (no ANSI)."""
    return (
        f"{'#':>{IDX_W}} "
        f"{'Price':>{PRICE_W}} "
        f"{'Qty':>{QTY_W}} "
        f"{'Total':>{TOTAL_W}} "
        f"{'Cum Qty':>{CQTY_W}} "
        f"{'Cum Total':>{CTOTAL_W}} "
        f"{'Cum Avg':>{CAVG_W}}"
    )

def render(base, quote, symbol, book, market_info, depth, refresh):
    bids = build_levels(book.get("bids", []))
    asks = build_levels(book.get("asks", []))

    bids.sort(key=lambda x: x[0], reverse=True)
    asks.sort(key=lambda x: x[0])

    bids = bids[:depth]
    asks = asks[:depth]

    bid_cum = cumulative(bids)
    ask_cum = cumulative(asks)

    best_bid   = bids[0][0] if bids else 0.0
    best_ask   = asks[0][0] if asks else 0.0
    spread     = best_ask - best_bid if best_bid and best_ask else 0.0
    mid        = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_pct = (spread / mid * 100) if mid else 0.0

    total_bid_qty = bid_cum[-1][0] if bid_cum else 0.0
    total_ask_qty = ask_cum[-1][0] if ask_cum else 0.0
    total_bid_val = bid_cum[-1][1] if bid_cum else 0.0
    total_ask_val = ask_cum[-1][1] if ask_cum else 0.0
    total_bid_avg = bid_cum[-1][2] if bid_cum else 0.0
    total_ask_avg = ask_cum[-1][2] if ask_cum else 0.0

    # ── header ────────────────────────────────────────────────────────────────
    title = f"NonKYC Order Book — {base}/{quote} ({symbol})"
    ts    = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if refresh:
        ts += f"  •  refresh {refresh}s  •  Ctrl+C to exit"

    print(c("=" * FULL_W, CYAN))
    print(c(title.center(FULL_W), BOLD))
    print(c(ts.center(FULL_W), DIM))
    print(c("=" * FULL_W, CYAN))

    # ── market info ───────────────────────────────────────────────────────────
    if market_info:
        last = float(market_info.get("lastPrice", 0) or 0)
        high = float(market_info.get("highPrice",  0) or 0)
        low  = float(market_info.get("lowPrice",   0) or 0)
        vol  = float(market_info.get("volume",     0) or 0)

        print("\n" + c("24h Market Stats:", BOLD))
        print(f"  Last Price : {c(fmt(last), CYAN)} {quote}")
        print(f"  24h High   : {fmt(high)} {quote}")
        print(f"  24h Low    : {fmt(low)} {quote}")
        print(f"  24h Volume : {fmt(vol, 4)} {base}")

    # ── snapshot ──────────────────────────────────────────────────────────────
    print("\n" + c("Market Snapshot:", BOLD))
    print(f"  Best Bid   : {c(fmt(best_bid), GREEN)} {quote}")
    print(f"  Best Ask   : {c(fmt(best_ask), RED)} {quote}")
    print(f"  Mid Price  : {fmt(mid)} {quote}")
    print(f"  Spread     : {fmt(spread)} {quote}  ({spread_pct:.4f}%)")

    # ── column headers ────────────────────────────────────────────────────────
    hdr = header_row()

    print("\n" + c("-" * FULL_W, CYAN))
    print(
        c(f"BIDS (buyers) — top {len(bids)}".center(SIDE_W),  BOLD + GREEN)
        + c(SEP, CYAN)
        + c(f"ASKS (sellers) — top {len(asks)}".center(SIDE_W), BOLD + RED)
    )
    print(c("-" * FULL_W, CYAN))
    print(c(hdr.ljust(SIDE_W), DIM) + c(SEP, CYAN) + c(hdr.ljust(SIDE_W), DIM))
    print(c("-" * FULL_W, CYAN))

    # ── rows ──────────────────────────────────────────────────────────────────
    rows = max(len(bids), len(asks))

    for i in range(rows):
        # left (bid) side
        if i < len(bids):
            p, q           = bids[i]
            cq, ct, ca     = bid_cum[i]
            left_plain     = visible_row(i + 1, p, q, cq, ct, ca)
            left_colored   = format_row(i + 1, p, q, cq, ct, ca, "bid")
            left_pad       = max(0, SIDE_W - len(left_plain))
        else:
            left_colored   = ""
            left_pad       = SIDE_W

        # right (ask) side
        if i < len(asks):
            p, q           = asks[i]
            cq, ct, ca     = ask_cum[i]
            right_colored  = format_row(i + 1, p, q, cq, ct, ca, "ask")
        else:
            right_colored  = ""

        print(left_colored + " " * left_pad + c(SEP, CYAN) + right_colored)

    print(c("-" * FULL_W, CYAN))

    # ── totals ────────────────────────────────────────────────────────────────
    left_tot = (
        f"  Totals:"
        f"  qty={fmt(total_bid_qty, 4)} {base}"
        f"  val={fmt(total_bid_val, 4)} {quote}"
        f"  wavg={fmt(total_bid_avg)}"
    )
    right_tot = (
        f"  Totals:"
        f"  qty={fmt(total_ask_qty, 4)} {base}"
        f"  val={fmt(total_ask_val, 4)} {quote}"
        f"  wavg={fmt(total_ask_avg)}"
    )
    print(c(left_tot.ljust(SIDE_W),  GREEN) + c(SEP, CYAN) + c(right_tot.ljust(SIDE_W), RED))

    # ── imbalance ─────────────────────────────────────────────────────────────
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
    parser = argparse.ArgumentParser(description="NonKYC.io order book viewer")
    parser.add_argument("base",  help="Base asset ticker,  e.g. BTC")
    parser.add_argument("quote", help="Quote asset ticker, e.g. USDT")
    parser.add_argument("--depth",   type=int, default=20,
                        help="Levels per side (default 20)")
    parser.add_argument("-t", "--refresh", type=int, default=0,
                        help="Auto-refresh every N seconds (0 = one shot)")
    args = parser.parse_args()

    base    = args.base.upper()
    quote   = args.quote.upper()
    symbol  = f"{base}_{quote}"
    depth   = max(1, args.depth)
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