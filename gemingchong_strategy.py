"""
隔日沖放空策略回測框架
========================
策略邏輯:
  T-2: 個股觸及漲停 (收盤=漲停價)
  T-1: 個股出現隔日沖 (開高 + 分點大量買進)
  T:   放空進場 -> 開高走低獲利

目標: CAGR 100%, MDD < -20%

使用方式:
  1. 準備數據: 個股日線 + 5分鐘K線 (或分點數據)
  2. 設定參數
  3. 執行回測
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from itertools import product
import warnings
warnings.filterwarnings("ignore")


# ============================================================
# 1. 參數定義
# ============================================================
@dataclass
class StrategyParams:
    # === 漲停篩選 (T-2) ===
    limit_up_pct: float = 0.10
    min_volume_ratio: float = 2.0
    max_price: float = 200
    min_price: float = 15
    exclude_st: bool = True

    # === 隔日沖確認 (T-1) ===
    min_open_gap_pct: float = 0.03
    max_open_gap_pct: float = 0.15
    min_tick_volume: int = 500
    tick_window_minutes: int = 5
    require_high_volume_open: bool = True

    # === 放空進場 (T日) ===
    entry_method: str = "open"
    entry_delay_minutes: int = 0
    entry_above_vwap: bool = False

    # === 停損設計 ===
    stop_loss_method: str = "hybrid"
    stop_loss_pct: float = 0.03
    atr_multiplier: float = 1.5
    atr_period: int = 14
    vwap_stop: bool = False
    time_stop_minutes: int = 240

    # === 出場設計 ===
    exit_method: str = "close"
    target_profit_pct: float = 0.05
    trailing_stop_pct: float = 0.02
    exit_before_close_minutes: int = 5

    # === 風控 ===
    max_position_pct: float = 0.25
    max_concurrent_positions: int = 3
    daily_loss_limit_pct: float = 0.05
    max_consecutive_losses: int = 5

    # === 成本 (當沖稅率減半 + 手續費1.7折 + 無借券費) ===
    commission_rate: float = 0.000238  # 0.14% x 1.7折 = 0.0238%
    tax_rate: float = 0.0015  # 0.3% / 2 = 0.15% (當沖減半)
    borrow_cost_daily: float = 0.0  # 無借券費用
    slippage_ticks: int = 1
    tick_size: float = 0.1


# ============================================================
# 2. 數據結構
# ============================================================
@dataclass
class Trade:
    date: str
    stock: str
    entry_price: float
    exit_price: float
    exit_reason: str
    pnl_pct: float
    holding_minutes: int
    stop_loss_price: float
    signal_strength: float


# ============================================================
# 3. 核心策略邏輯
# ============================================================
class GeMingChongStrategy:
    def __init__(self, params: StrategyParams):
        self.params = params
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = []

    def screen_limit_up_stocks(self, daily_df: pd.DataFrame, date: str) -> list:
        """T-2: 篩選漲停股"""
        candidates = []
        df = daily_df[daily_df["date"] == date].copy()

        for _, row in df.iterrows():
            if row["close"] >= row["prev_close"] * (1 + self.params.limit_up_pct - 0.001):
                if row["high"] == row["close"]:
                    vol_ma20 = row.get("volume_ma20", row["volume"])
                    if vol_ma20 > 0 and row["volume"] / vol_ma20 >= self.params.min_volume_ratio:
                        if self.params.min_price <= row["close"] <= self.params.max_price:
                            candidates.append(row["stock"])
        return candidates

    def detect_gemingchong(self, tick_df: pd.DataFrame, stock: str, date: str) -> Optional[dict]:
        """T-1: 檢測隔日沖信號, 回傳信號強度評分 (0-1) 或 None"""
        stock_ticks = tick_df[(tick_df["stock"] == stock) & (tick_df["date"] == date)]
        if stock_ticks.empty:
            return None

        open_price = stock_ticks.iloc[0]["price"]
        prev_close = stock_ticks.iloc[0]["prev_close"]
        gap_pct = (open_price - prev_close) / prev_close

        if gap_pct < self.params.min_open_gap_pct:
            return None
        if gap_pct > self.params.max_open_gap_pct:
            return None

        window = stock_ticks.head(self.params.tick_window_minutes * 60)
        large_buys = window[window["volume"] >= self.params.min_tick_volume]

        if len(large_buys) == 0:
            return None

        score = 0.0
        score += min(gap_pct / 0.10, 1.0) * 0.3
        score += min(len(large_buys) / 10, 1.0) * 0.3
        yesterday_vol = stock_ticks.iloc[0].get("yesterday_volume", 1)
        if yesterday_vol and yesterday_vol > 0:
            score += min(window["volume"].sum() / (yesterday_vol * 0.3), 1.0) * 0.4
        else:
            score += 0.2

        return {
            "signal_strength": score,
            "gap_pct": gap_pct,
            "large_buy_count": len(large_buys),
            "open_volume": window["volume"].sum()
        }

    def calculate_stop_loss(self, entry_price: float, atr: float,
                           vwap: float = None, method: str = None) -> float:
        """計算停損價位"""
        method = method or self.params.stop_loss_method

        if method == "fixed_pct":
            return entry_price * (1 + self.params.stop_loss_pct)
        elif method == "atr":
            return entry_price + self.params.atr_multiplier * atr
        elif method == "vwap":
            if vwap and vwap > entry_price:
                return vwap * 1.005
            return entry_price * (1 + self.params.stop_loss_pct)
        elif method == "hybrid":
            atr_stop = entry_price + self.params.atr_multiplier * atr
            pct_stop = entry_price * (1 + self.params.stop_loss_pct)
            return min(atr_stop, pct_stop)
        return entry_price * (1 + self.params.stop_loss_pct)

    def simulate_trade(self, intraday_df: pd.DataFrame, stock: str, date: str,
                      entry_price: float, stop_loss: float,
                      signal_strength: float) -> Optional[Trade]:
        """模擬單筆交易 (使用5分鐘K線)"""
        data = intraday_df[(intraday_df["stock"] == stock) & (intraday_df["date"] == date)]
        if data.empty:
            return None

        exit_price = entry_price
        exit_reason = "unknown"
        holding_minutes = 0
        highest_since_entry = entry_price

        for i, (_, bar) in enumerate(data.iterrows()):
            holding_minutes = (i + 1) * 5

            if bar["high"] >= stop_loss:
                exit_price = stop_loss
                exit_reason = "stop_loss"
                break

            if self.params.exit_method == "target_pct":
                target = entry_price * (1 - self.params.target_profit_pct)
                if bar["low"] <= target:
                    exit_price = target
                    exit_reason = "target"
                    break

            if self.params.exit_method == "trailing":
                highest_since_entry = max(highest_since_entry, bar["high"])
                trail_stop = highest_since_entry * (1 - self.params.trailing_stop_pct)
                if bar["high"] >= trail_stop:
                    exit_price = trail_stop
                    exit_reason = "trailing_stop"
                    break

            if holding_minutes >= self.params.time_stop_minutes - self.params.exit_before_close_minutes:
                exit_price = bar["close"]
                exit_reason = "time_stop"
                break
        else:
            exit_price = data.iloc[-1]["close"]
            exit_reason = "close"

        pnl_pct = (entry_price - exit_price) / entry_price

        cost = (self.params.commission_rate * 2 + self.params.tax_rate +
                self.params.borrow_cost_daily +
                self.params.slippage_ticks * self.params.tick_size / entry_price * 2)
        pnl_pct -= cost

        return Trade(
            date=date, stock=stock,
            entry_price=entry_price, exit_price=exit_price,
            exit_reason=exit_reason, pnl_pct=pnl_pct,
            holding_minutes=holding_minutes,
            stop_loss_price=stop_loss,
            signal_strength=signal_strength
        )


# ============================================================
# 4. 回測引擎
# ============================================================
class Backtester:
    def __init__(self, params: StrategyParams):
        self.params = params
        self.strategy = GeMingChongStrategy(params)

    def run(self, daily_df: pd.DataFrame, tick_df: pd.DataFrame,
            intraday_df: pd.DataFrame, initial_capital: float = 1000000) -> dict:
        """
        執行回測

        Parameters:
            daily_df: 日線 (date, stock, open, high, low, close, volume, prev_close, volume_ma20)
            tick_df: 分點 (date, stock, time, price, volume, prev_close, yesterday_volume)
            intraday_df: 5分鐘K線 (date, stock, time, open, high, low, close, volume)
        """
        capital = initial_capital
        peak = capital
        max_drawdown = 0
        equity_curve = [capital]
        trades = []
        consecutive_losses = 0

        dates = sorted(daily_df["date"].unique())

        for i in range(2, len(dates)):
            t_date = dates[i]
            t1_date = dates[i - 1]
            t2_date = dates[i - 2]

            limit_up_stocks = self.strategy.screen_limit_up_stocks(daily_df, t2_date)
            if not limit_up_stocks:
                equity_curve.append(capital)
                continue

            signals = []
            for stock in limit_up_stocks:
                signal = self.strategy.detect_gemingchong(tick_df, stock, t1_date)
                if signal and signal["signal_strength"] >= 0.4:
                    signals.append((stock, signal))

            if not signals:
                equity_curve.append(capital)
                continue

            signals.sort(key=lambda x: x[1]["signal_strength"], reverse=True)
            signals = signals[:self.params.max_concurrent_positions]

            daily_pnl = 0
            for stock, signal in signals:
                if consecutive_losses >= self.params.max_consecutive_losses:
                    break

                entry_data = intraday_df[(intraday_df["stock"] == stock) &
                                         (intraday_df["date"] == t_date)]
                if entry_data.empty:
                    continue

                delay_bars = self.params.entry_delay_minutes // 5
                if delay_bars >= len(entry_data):
                    continue
                entry_price = entry_data.iloc[delay_bars]["open"]

                stock_daily = daily_df[daily_df["stock"] == stock].tail(self.params.atr_period)
                if len(stock_daily) < self.params.atr_period:
                    atr = entry_price * 0.03
                else:
                    tr = np.maximum(
                        stock_daily["high"] - stock_daily["low"],
                        np.maximum(
                            abs(stock_daily["high"] - stock_daily["prev_close"]),
                            abs(stock_daily["low"] - stock_daily["prev_close"])
                        )
                    )
                    atr = tr.mean()

                stop_loss = self.strategy.calculate_stop_loss(entry_price, atr)

                trade = self.strategy.simulate_trade(
                    intraday_df, stock, t_date, entry_price, stop_loss,
                    signal["signal_strength"]
                )

                if trade:
                    trades.append(trade)
                    position_size = capital * self.params.max_position_pct
                    daily_pnl += position_size * trade.pnl_pct

                    if trade.pnl_pct < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0

            capital += daily_pnl

            if daily_pnl < -capital * self.params.daily_loss_limit_pct:
                capital -= (daily_pnl + capital * self.params.daily_loss_limit_pct)

            equity_curve.append(capital)
            peak = max(peak, capital)
            dd = (capital - peak) / peak
            max_drawdown = min(max_drawdown, dd)

        return self._calculate_metrics(trades, equity_curve, max_drawdown, initial_capital)

    def _calculate_metrics(self, trades, equity_curve, max_dd, initial_capital):
        if not trades:
            return {"error": "無交易產生"}

        pnls = [t.pnl_pct for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_days = len(equity_curve) - 1
        years = total_days / 250
        final_capital = equity_curve[-1]
        cagr = (final_capital / initial_capital) ** (1 / max(years, 0.1)) - 1

        return {
            "total_trades": len(trades),
            "win_rate": len(wins) / len(pnls) * 100,
            "avg_win": np.mean(wins) * 100 if wins else 0,
            "avg_loss": np.mean(losses) * 100 if losses else 0,
            "profit_factor": abs(sum(wins) / sum(losses)) if losses else float("inf"),
            "sharpe_ratio": np.mean(pnls) / np.std(pnls) * np.sqrt(250) if np.std(pnls) > 0 else 0,
            "cagr": cagr * 100,
            "max_drawdown": max_dd * 100,
            "avg_holding_minutes": np.mean([t.holding_minutes for t in trades]),
            "exit_reasons": pd.Series([t.exit_reason for t in trades]).value_counts().to_dict(),
            "best_trade": max(pnls) * 100,
            "worst_trade": min(pnls) * 100,
            "trades": trades,
            "equity_curve": equity_curve
        }


# ============================================================
# 5. 參數優化
# ============================================================
def optimize_parameters(daily_df, tick_df, intraday_df,
                        target_cagr=100, max_mdd=-20):
    """
    網格搜索找最佳參數
    目標: CAGR >= 100%, MDD > -20%
    """
    param_grid = {
        "min_open_gap_pct": [0.02, 0.03, 0.05],
        "max_open_gap_pct": [0.10, 0.15, 0.20],
        "min_tick_volume": [300, 500, 1000],
        "stop_loss_method": ["fixed_pct", "atr", "hybrid"],
        "stop_loss_pct": [0.02, 0.03, 0.05],
        "atr_multiplier": [1.0, 1.5, 2.0],
        "exit_method": ["close", "target_pct", "trailing"],
        "target_profit_pct": [0.03, 0.05, 0.08],
        "entry_delay_minutes": [0, 5, 15],
        "min_volume_ratio": [1.5, 2.0, 3.0],
    }

    best_result = None
    best_score = -float("inf")
    best_params = None

    keys = list(param_grid.keys())
    values = list(param_grid.values())

    results = []
    for combo in product(*values):
        params = StrategyParams(**dict(zip(keys, combo)))
        bt = Backtester(params)
        result = bt.run(daily_df, tick_df, intraday_df)

        if "error" in result:
            continue

        if result["max_drawdown"] > max_mdd:
            score = result["cagr"]
        else:
            score = -1000

        results.append({
            "params": dict(zip(keys, combo)),
            "cagr": result["cagr"],
            "mdd": result["max_drawdown"],
            "win_rate": result["win_rate"],
            "sharpe": result["sharpe_ratio"],
            "score": score
        })

        if score > best_score:
            best_score = score
            best_result = result
            best_params = params

    return best_params, best_result, pd.DataFrame(results)


# ============================================================
# 6. 日線近似估算 (無分點數據時的替代方案)
# ============================================================
def estimate_edge_from_daily_only(daily_df: pd.DataFrame, params: StrategyParams):
    """
    僅用日線數據估算策略邊際 (Edge)

    邏輯:
    - 找到所有漲停股 (T-2)
    - 看T-1的開盤跳空 (近似隔日沖)
    - 看T日的開盤到收盤跌幅 (近似開高走低)

    注意: 這是粗略估算, 無法精確模擬分點進出場
    """
    results = []
    dates = sorted(daily_df["date"].unique())

    for i in range(2, len(dates)):
        t2 = dates[i - 2]
        t1 = dates[i - 1]
        t0 = dates[i]

        t2_data = daily_df[daily_df["date"] == t2]
        limit_ups = t2_data[
            (t2_data["close"] >= t2_data["prev_close"] * (1 + params.limit_up_pct - 0.001)) &
            (t2_data["high"] == t2_data["close"])
        ]

        for _, lu in limit_ups.iterrows():
            stock = lu["stock"]

            t1_data = daily_df[(daily_df["stock"] == stock) & (daily_df["date"] == t1)]
            if t1_data.empty:
                continue
            t1_row = t1_data.iloc[0]
            gap = (t1_row["open"] - lu["close"]) / lu["close"]

            if gap < params.min_open_gap_pct or gap > params.max_open_gap_pct:
                continue

            t0_data = daily_df[(daily_df["stock"] == stock) & (daily_df["date"] == t0)]
            if t0_data.empty:
                continue
            t0_row = t0_data.iloc[0]

            entry = t0_row["open"]
            exit_close = t0_row["close"]
            pnl = (entry - exit_close) / entry

            stop = entry * (1 + params.stop_loss_pct)
            if t0_row["high"] >= stop:
                pnl = (entry - stop) / entry

            results.append({
                "date": t0, "stock": stock,
                "gap_pct": gap, "pnl": pnl,
                "t1_high": t1_row["high"], "t1_close": t1_row["close"]
            })

    df = pd.DataFrame(results)
    if df.empty:
        return {"error": "無符合條件的交易"}

    return {
        "total_signals": len(df),
        "win_rate": (df["pnl"] > 0).mean() * 100,
        "avg_pnl": df["pnl"].mean() * 100,
        "median_pnl": df["pnl"].median() * 100,
        "p5": df["pnl"].quantile(0.05) * 100,
        "p95": df["pnl"].quantile(0.95) * 100,
        "raw_data": df
    }


# ============================================================
# 7. 使用範例
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("隔日沖放空策略回測框架")
    print("=" * 60)
    print()
    print("使用步驟:")
    print("  1. 準備數據 (見下方格式要求)")
    print("  2. 設定 StrategyParams")
    print("  3. 執行回測或參數優化")
    print()
    print("數據格式要求:")
    print("  daily_df: date, stock, open, high, low, close, volume, prev_close, volume_ma20")
    print("  tick_df:  date, stock, time, price, volume, prev_close, yesterday_volume")
    print("  intraday_df: date, stock, time, open, high, low, close, volume")
    print()
    print("快速估算 (僅日線):")
    print("  result = estimate_edge_from_daily_only(daily_df, params)")
    print()
    print("完整回測:")
    print("  params = StrategyParams(...)")
    print("  bt = Backtester(params)")
    print("  result = bt.run(daily_df, tick_df, intraday_df)")
    print()
    print("參數優化:")
    print("  best_params, best_result, all_results = optimize_parameters(...)")
