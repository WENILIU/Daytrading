"""
Gap Fade v3 LIVE - 最終實戰執行腳本
====================================
策略：Market-adjusted gap > 5% + 15-min confirmation + Tiered sizing
資金：500 萬
每日操作：9:00 掃描 → 9:15 確認進場 → 13:25 平倉

Version: 2026-10-17
"""

import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

class Config:
    # Capital
    capital = 5_000_000
    
    # Signal detection (at 9:00)
    gap_threshold = 0.05          # Market-adjusted gap > 5%
    min_price = 30
    max_price = 250               # Zhang constraint: 5% of 500wan / 1000 shares
    min_volume_t1 = 5_000_000     # TWD
    
    # Confirmation (at 9:15)
    confirm_wait_minutes = 15
    confirm_drop_min = 0.0        # Any drop = confirmed (Tier 2+)
    
    # Tiered position sizing (based on 15-min drop magnitude)
    tiers = [
        # (min_drop, max_drop, multiplier, label)
        (0.03, 999, 2.0, "T5"),    # drop >3%: 2x
        (0.015, 0.03, 1.5, "T4"),  # drop 1.5-3%: 1.5x
        (0.005, 0.015, 1.0, "T3"), # drop 0.5-1.5%: 1x
        (0.0, 0.005, 0.5, "T2"),   # drop 0-0.5%: 0.5x
    ]
    
    # Base position
    base_position_pct = 0.05      # 5% per trade (SHORT)
    long_position_pct = 0.025     # 2.5% per trade (LONG)
    
    # Exit
    stop_loss_pct = 0.06          # -6% hard stop
    take_profit_pct = 0.04        # +4% target
    force_exit_time = "13:25"
    
    # Limits
    max_daily_positions = 8       # Top 8 signals per day
    max_daily_exposure = 1.0      # 100% max
    
    # Cost
    cost_per_trade = 0.0023       # 0.23% (2.8 zhe)
    
    # Data source
    fugle_api_key = 'MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=='


# ============================================================
# STEP 1: 9:00 - Scan for signals
# ============================================================

def scan_signals(config: Config):
    """
    At market open, scan all stocks for market-adjusted gap signals.
    Returns list of candidate signals (not yet entered).
    """
    from fugle_marketdata import RestClient
    
    client = RestClient(api_key=config.fugle_api_key)
    stock = client.stock
    
    # Get all tickers with current data
    tickers = stock.intraday.tickers(type='EQUITY', exchange='TWSE', isNormal=True)
    
    # Get TAIEX for market adjustment
    # Use the index open vs previous close
    index_data = stock.intraday.current(symbol='0000')  # TAIEX
    market_gap = index_data.get('changePercent', 0) / 100  # as decimal
    
    signals = []
    
    for ticker in tickers['data']:
        symbol = ticker['symbol']
        name = ticker['name']
        open_price = ticker.get('open', 0)
        prev_close = ticker.get('previousClose', 0)
        change_pct = ticker.get('changePercent', 0) / 100
        
        # Filters
        if prev_close < config.min_price or prev_close > config.max_price:
            continue
        
        # Calculate market-adjusted gap
        raw_gap = (open_price - prev_close) / prev_close if prev_close > 0 else 0
        adj_gap = raw_gap - market_gap
        
        # Signal detection
        direction = None
        if adj_gap > config.gap_threshold:
            direction = 'SHORT'
        elif adj_gap < -config.gap_threshold:
            direction = 'LONG'
        
        if direction is None:
            continue
        
        # Volume check (use previous day volume from ticker data if available)
        volume = ticker.get('volume', 0) * open_price  # rough estimate
        
        signals.append({
            'symbol': symbol,
            'name': name,
            'direction': direction,
            'open_price': open_price,
            'prev_close': prev_close,
            'raw_gap': raw_gap,
            'adj_gap': adj_gap,
        })
    
    # Sort by |adj_gap| descending, take top N
    signals.sort(key=lambda x: abs(x['adj_gap']), reverse=True)
    signals = signals[:config.max_daily_positions]
    
    return signals, market_gap


# ============================================================
# STEP 2: 9:15 - Confirm and determine position size
# ============================================================

def confirm_and_size(signals, config: Config):
    """
    At 9:15, check if price has moved in our direction.
    Determine tier and position size.
    Returns list of orders to place.
    """
    from fugle_marketdata import RestClient
    
    client = RestClient(api_key=config.fugle_api_key)
    stock = client.stock
    
    orders = []
    
    for sig in signals:
        symbol = sig['symbol']
        direction = sig['direction']
        entry_price = sig['open_price']
        
        # Get current price at 9:15
        try:
            current = stock.intraday.current(symbol=symbol)
            current_price = current.get('close', entry_price)
        except:
            continue
        
        # Calculate 15-min move
        if direction == 'SHORT':
            drop_pct = (entry_price - current_price) / entry_price  # positive = dropped = good
        else:
            drop_pct = (current_price - entry_price) / entry_price  # positive = rose = good
        
        # Check confirmation
        if drop_pct <= config.confirm_drop_min:
            # Not confirmed - skip
            continue
        
        # Determine tier
        pos_mult = 0
        tier_label = "SKIP"
        for min_drop, max_drop, mult, label in config.tiers:
            if min_drop <= drop_pct < max_drop:
                pos_mult = mult
                tier_label = label
                break
        
        if pos_mult == 0:
            continue
        
        # Calculate position
        if direction == 'SHORT':
            base_value = config.capital * config.base_position_pct
        else:
            base_value = config.capital * config.long_position_pct
        
        position_value = base_value * pos_mult
        shares = int(position_value / entry_price / 1000) * 1000  # Round to zhang
        
        if shares < 1000:
            continue  # Can't trade less than 1 zhang
        
        actual_value = shares * entry_price
        
        # Calculate SL/TP prices
        if direction == 'SHORT':
            sl_price = round(entry_price * (1 + config.stop_loss_pct), 1)
            tp_price = round(entry_price * (1 - config.take_profit_pct), 1)
        else:
            sl_price = round(entry_price * (1 - config.stop_loss_pct), 1)
            tp_price = round(entry_price * (1 + config.take_profit_pct), 1)
        
        orders.append({
            'symbol': symbol,
            'name': sig['name'],
            'direction': direction,
            'tier': tier_label,
            'drop_pct': drop_pct,
            'entry_price': entry_price,
            'current_price': current_price,
            'shares': shares,
            'position_value': actual_value,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'risk': actual_value * config.stop_loss_pct,
        })
    
    return orders


# ============================================================
# STEP 3: Print order sheet
# ============================================================

def print_orders(orders, config: Config):
    """Print the order sheet for manual execution."""
    
    print(f"\n{'='*80}")
    print(f"  GAP FADE v3 - ORDER SHEET")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Capital: {config.capital:,.0f}")
    print(f"{'='*80}")
    
    if not orders:
        print("\n  NO SIGNALS TODAY. No action needed.")
        return
    
    print(f"\n  {'#':<3} {'Code':<6} {'Name':<8} {'Dir':<5} {'Tier':<5} "
          f"{'Drop%':>6} {'Price':>8} {'Shares':>7} {'Value':>10} "
          f"{'SL':>8} {'TP':>8} {'Risk':>8}")
    print(f"  {'-'*95}")
    
    total_exposure = 0
    total_risk = 0
    
    for i, o in enumerate(orders, 1):
        total_exposure += o['position_value']
        total_risk += o['risk']
        
        print(f"  {i:<3} {o['symbol']:<6} {o['name']:<8.8} {o['direction']:<5} {o['tier']:<5} "
              f"{o['drop_pct']*100:>6.1f} {o['entry_price']:>8.1f} {o['shares']:>7,} "
              f"{o['position_value']:>10,.0f} {o['sl_price']:>8.1f} {o['tp_price']:>8.1f} {o['risk']:>8,.0f}")
    
    print(f"  {'-'*95}")
    print(f"  TOTAL: {len(orders)} orders | Exposure: {total_exposure:,.0f} "
          f"({total_exposure/config.capital*100:.0f}%) | Max Risk: {total_risk:,.0f} "
          f"({total_risk/config.capital*100:.2f}%)")
    
    print(f"\n  INSTRUCTIONS:")
    print(f"  1. Place market orders for each stock above")
    print(f"  2. Immediately set conditional orders (停損停利):")
    for o in orders:
        dir_text = "放空" if o['direction'] == 'SHORT' else "買進"
        print(f"     {o['symbol']} {dir_text} {o['shares']:,}股: 停損 {o['sl_price']} / 停利 {o['tp_price']}")
    print(f"  3. At 13:25, force-close any remaining positions")


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    config = Config()
    
    print(f"\nGAP FADE v3 LIVE TRADER")
    print(f"Capital: {config.capital:,.0f}")
    print(f"Mode: 9:00 scan -> 9:15 confirm -> Execute")
    
    # Step 1: Scan (run at 9:00-9:01)
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning signals...")
    signals, market_gap = scan_signals(config)
    print(f"  Market gap: {market_gap*100:+.2f}%")
    print(f"  Candidates found: {len(signals)}")
    
    if not signals:
        print("  No signals. Done for today.")
        return
    
    for s in signals:
        print(f"    {s['symbol']} {s['name']:<8} {s['direction']:<5} adj_gap={s['adj_gap']*100:+.1f}%")
    
    # Step 2: Wait for confirmation (until 9:15)
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Waiting {config.confirm_wait_minutes} min for confirmation...")
    print("  (Set an alarm for 9:15 and come back)")
    
    # In live trading, you would wait here. For testing, skip wait:
    # time.sleep(config.confirm_wait_minutes * 60)
    
    input("\n  >>> Press ENTER after 9:15 to confirm and generate orders...")
    
    # Step 3: Confirm and generate orders
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Confirming signals...")
    orders = confirm_and_size(signals, config)
    
    # Step 4: Print orders
    print_orders(orders, config)
    
    # Save to file
    output_path = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs")
    today = datetime.now().strftime('%Y-%m-%d')
    
    if orders:
        pd.DataFrame(orders).to_csv(output_path / f"orders_{today}.csv", index=False, encoding='utf-8-sig')
        print(f"\n  Orders saved to orders_{today}.csv")


if __name__ == '__main__':
    main()
