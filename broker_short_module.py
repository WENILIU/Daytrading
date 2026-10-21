"""
Broker Short Strategy Module
Track specific brokers selling pressure as short entry trigger

Logic:
  T-2: Stock hits limit-up
  T-1: Tracked brokers buy heavily (gemingchong confirmed)
  T:   Those brokers turn sellers -> short trigger

Target: CAGR 100%, MDD < -20%
Cost: 0.198%/trade (day-trade tax halved + 1.7x commission + no borrow)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from collections import defaultdict
from enum import Enum
import warnings
warnings.filterwarnings('ignore')


class BrokerTier(Enum):
    TIER1_PURE = 'tier1_pure'
    TIER2_ACTIVE = 'tier2_active'
    TIER3_SWING = 'tier3_swing'


GEMINGCHONG_BROKERS = {
    '凱基-台北': BrokerTier.TIER1_PURE,
    '摩根大通': BrokerTier.TIER1_PURE,
    '美林': BrokerTier.TIER1_PURE,
    '元富-松德': BrokerTier.TIER1_PURE,
    '國票-敦北法人': BrokerTier.TIER1_PURE,
    '國票-安和': BrokerTier.TIER1_PURE,
    '統一-城中': BrokerTier.TIER1_PURE,
    '港商法國興業': BrokerTier.TIER1_PURE,
    '美商高盛': BrokerTier.TIER2_ACTIVE,
    '統一': BrokerTier.TIER2_ACTIVE,
    '港商野村': BrokerTier.TIER2_ACTIVE,
    '凱基-城中': BrokerTier.TIER2_ACTIVE,
    '新加坡商瑞銀': BrokerTier.TIER2_ACTIVE,
    '台灣摩根士丹利': BrokerTier.TIER2_ACTIVE,
    '元大證券': BrokerTier.TIER2_ACTIVE,
    '富邦證券': BrokerTier.TIER2_ACTIVE,
}

TRACKED_BROKER_NAMES = list(GEMINGCHONG_BROKERS.keys())
TIER1_NAMES = [b for b, t in GEMINGCHONG_BROKERS.items() if t == BrokerTier.TIER1_PURE]
TIER2_NAMES = [b for b, t in GEMINGCHONG_BROKERS.items() if t == BrokerTier.TIER2_ACTIVE]


@dataclass
class BrokerSignalParams:
    min_tier1_buyers: int = 1
    min_tier2_buyers: int = 2
    min_buy_volume: int = 200
    min_net_buy_ratio: float = 0.6
    require_tier1: bool = True
    t_day_trigger_method: str = 'price'
    price_trigger_pct: float = 0.005
    price_trigger_minutes: int = 15
    volume_surge_ratio: float = 2.0
    entry_method: str = 'trigger'
    max_entry_delay_minutes: int = 30
    stop_loss_pct: float = 0.02
    atr_multiplier: float = 1.5
    atr_period: int = 14
    time_stop_minutes: int = 235
    target_profit_pct: float = 0.04
    trailing_stop_pct: float = 0.015
    exit_method: str = 'hybrid'
    max_position_pct: float = 0.25
    max_concurrent_positions: int = 3
    daily_loss_limit_pct: float = 0.04
    max_consecutive_losses: int = 5
    cooldown_days: int = 1
    commission_rate: float = 0.000238
    tax_rate: float = 0.0015
    borrow_cost_daily: float = 0.0
    slippage_ticks: int = 1
    tick_size: float = 0.1

    @property
    def total_cost_per_trade(self) -> float:
        return self.tax_rate + self.commission_rate * 2 + self.borrow_cost_daily


@dataclass
class BrokerSignal:
    stock: str
    signal_date: str
    trade_date: str
    limit_up_date: str
    tier1_buyers: list = field(default_factory=list)
    tier2_buyers: list = field(default_factory=list)
    total_tier1_volume: int = 0
    total_tier2_volume: int = 0
    t_day_tier1_sellers: list = field(default_factory=list)
    t_day_total_sell_volume: int = 0
    signal_score: float = 0.0
    signal_grade: str = ''
    gap_pct: float = 0.0


class BrokerSignalDetector:
    def __init__(self, params: BrokerSignalParams, broker_dir: str):
        self.params = params
        self.broker_dir = Path(broker_dir)
        self._cache = {}

    def _load_broker_data(self, date: str) -> Optional[pd.DataFrame]:
        if date in self._cache:
            return self._cache[date]
        filepath = self.broker_dir / f'broker_transactions_{date}.csv'
        if not filepath.exists():
            return None
        try:
            df = pd.read_csv(filepath, dtype={'symbol': str})
            self._cache[date] = df
            if len(self._cache) > 10:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            return df
        except Exception:
            return None

    def detect_t1_signal(self, stock: str, t1_date: str,
                        limit_up_price: float) -> Optional[dict]:
        df = self._load_broker_data(t1_date)
        if df is None:
            return None
        stock_data = df[df['symbol'] == stock].copy()
        if stock_data.empty:
            return None
        stock_data['net_buy'] = stock_data['buy'] - stock_data['sell']
        stock_data['buy_ratio'] = stock_data['buy'] / (stock_data['buy'] + stock_data['sell'] + 1)
        tier1_buyers = []
        tier2_buyers = []
        for _, row in stock_data.iterrows():
            broker = row['broker']
            if broker not in GEMINGCHONG_BROKERS:
                continue
            is_big_buy = (
                row['buy'] >= self.params.min_buy_volume and
                row['buy_ratio'] >= self.params.min_net_buy_ratio and
                row['net_buy'] > 0
            )
            if not is_big_buy:
                continue
            tier = GEMINGCHONG_BROKERS[broker]
            info = {
                'broker': broker, 'buy': int(row['buy']),
                'sell': int(row['sell']), 'net_buy': int(row['net_buy']),
                'buy_ratio': float(row['buy_ratio']), 'tier': tier.value
            }
            if tier == BrokerTier.TIER1_PURE:
                tier1_buyers.append(info)
            elif tier == BrokerTier.TIER2_ACTIVE:
                tier2_buyers.append(info)
        has_valid = False
        if self.params.require_tier1:
            has_valid = len(tier1_buyers) >= self.params.min_tier1_buyers
        else:
            has_valid = (len(tier1_buyers) >= self.params.min_tier1_buyers or
                        len(tier2_buyers) >= self.params.min_tier2_buyers)
        if not has_valid:
            return None
        return {
            'tier1_buyers': tier1_buyers, 'tier2_buyers': tier2_buyers,
            'total_tier1_volume': sum(b['buy'] for b in tier1_buyers),
            'total_tier2_volume': sum(b['buy'] for b in tier2_buyers),
            'num_tier1': len(tier1_buyers), 'num_tier2': len(tier2_buyers),
        }

    def detect_t_day_selling(self, stock: str, t_date: str,
                            t1_buyers: list) -> Optional[dict]:
        df = self._load_broker_data(t_date)
        if df is None:
            return None
        stock_data = df[df['symbol'] == stock].copy()
        if stock_data.empty:
            return None
        stock_data['net_buy'] = stock_data['buy'] - stock_data['sell']
        buyer_names = [b['broker'] for b in t1_buyers]
        sellers = stock_data[
            (stock_data['broker'].isin(buyer_names)) & (stock_data['net_buy'] < 0)
        ]
        if sellers.empty:
            return None
        tier1_sellers = []
        tier2_sellers = []
        for _, row in sellers.iterrows():
            broker = row['broker']
            tier = GEMINGCHONG_BROKERS.get(broker)
            info = {'broker': broker, 'sell': int(row['sell']), 'net_sell': int(-row['net_buy'])}
            if tier == BrokerTier.TIER1_PURE:
                tier1_sellers.append(info)
            elif tier == BrokerTier.TIER2_ACTIVE:
                tier2_sellers.append(info)
        return {
            'tier1_sellers': tier1_sellers, 'tier2_sellers': tier2_sellers,
            'total_sell_volume': sum(s['net_sell'] for s in tier1_sellers + tier2_sellers),
            'num_sellers': len(tier1_sellers) + len(tier2_sellers),
        }

    def score_signal(self, t1_result: dict, t_day_result: Optional[dict],
                    gap_pct: float) -> tuple:
        score = 0.0
        score += min(t1_result['num_tier1'] / 3, 1.0) * 0.35
        total_vol = t1_result['total_tier1_volume'] + t1_result['total_tier2_volume']
        score += min(total_vol / 5000, 1.0) * 0.25
        if 0.03 <= gap_pct <= 0.08:
            gap_score = 1.0
        elif 0.02 <= gap_pct < 0.03:
            gap_score = 0.5
        elif 0.08 < gap_pct <= 0.12:
            gap_score = 0.6
        else:
            gap_score = 0.2
        score += gap_score * 0.20
        if t_day_result:
            score += min(t_day_result['num_sellers'] / 3, 1.0) * 0.20
        else:
            score += 0.10
        if score >= 0.7:
            grade = 'A'
        elif score >= 0.45:
            grade = 'B'
        else:
            grade = 'C'
        return score, grade


class LiveTrigger:
    def __init__(self, params: BrokerSignalParams):
        self.params = params

    def check_trigger(self, open_price: float, current_price: float,
                     elapsed_minutes: int, current_volume: int,
                     avg_volume: int, vwap: float) -> Optional[dict]:
        if elapsed_minutes > self.params.max_entry_delay_minutes:
            return None
        drop_pct = (open_price - current_price) / open_price
        volume_surge = current_volume / (avg_volume + 1)
        triggers = []
        if drop_pct >= self.params.price_trigger_pct:
            triggers.append({'type': 'price_drop', 'detail': f'drop {drop_pct*100:.2f}%'})
        if volume_surge >= self.params.volume_surge_ratio:
            triggers.append({'type': 'volume_surge', 'detail': f'vol {volume_surge:.1f}x'})
        if vwap > 0 and current_price < vwap:
            triggers.append({'type': 'vwap_break', 'detail': 'below vwap'})
        if len(triggers) < 2:
            return None
        return {
            'triggered': True, 'entry_price': current_price,
            'elapsed_minutes': elapsed_minutes, 'triggers': triggers,
            'confidence': min(len(triggers) / 3, 1.0)
        }


@dataclass
class TradeResult:
    date: str
    stock: str
    signal_grade: str
    signal_score: float
    entry_price: float
    exit_price: float
    exit_reason: str
    pnl_pct: float
    holding_minutes: int
    stop_loss_price: float
    tier1_buyers: list
    t_day_sellers: list


class BrokerShortBacktester:
    def __init__(self, params: BrokerSignalParams, broker_dir: str):
        self.params = params
        self.detector = BrokerSignalDetector(params, broker_dir)
        self.trades: list = []

    def run(self, daily_df: pd.DataFrame, intraday_df: pd.DataFrame,
            initial_capital: float = 1000000) -> dict:
        capital = initial_capital
        peak = capital
        max_dd = 0
        equity_curve = [capital]
        consecutive_losses = 0
        cooldown_until = -1
        dates = sorted(daily_df['date'].unique())
        for i in range(2, len(dates)):
            if i <= cooldown_until:
                equity_curve.append(capital)
                continue
            t2_date = dates[i - 2]
            t1_date = dates[i - 1]
            t_date = dates[i]
            t2_data = daily_df[daily_df['date'] == t2_date]
            limit_ups = t2_data[
                (t2_data['close'] >= t2_data['prev_close'] * 1.095) &
                (t2_data['high'] == t2_data['close'])
            ]
            if limit_ups.empty:
                equity_curve.append(capital)
                continue
            signals = []
            for _, lu in limit_ups.iterrows():
                stock = lu['stock']
                lu_price = lu['close']
                t1_result = self.detector.detect_t1_signal(stock, t1_date, lu_price)
                if t1_result is None:
                    continue
                t1_data = daily_df[(daily_df['stock'] == stock) & (daily_df['date'] == t1_date)]
                if t1_data.empty:
                    continue
                t1_row = t1_data.iloc[0]
                gap_pct = (t1_row['open'] - lu_price) / lu_price
                if gap_pct < 0.02 or gap_pct > 0.15:
                    continue
                all_buyers = t1_result['tier1_buyers'] + t1_result['tier2_buyers']
                t_day_result = self.detector.detect_t_day_selling(stock, t_date, all_buyers)
                score, grade = self.detector.score_signal(t1_result, t_day_result, gap_pct)
                if grade == 'C':
                    continue
                signals.append({
                    'stock': stock, 'score': score, 'grade': grade,
                    't1_result': t1_result, 't_day_result': t_day_result,
                    'gap_pct': gap_pct, 'lu_price': lu_price,
                })
            if not signals:
                equity_curve.append(capital)
                continue
            signals.sort(key=lambda x: x['score'], reverse=True)
            signals = signals[:self.params.max_concurrent_positions]
            daily_pnl = 0
            for sig in signals:
                if consecutive_losses >= self.params.max_consecutive_losses:
                    cooldown_until = i + self.params.cooldown_days
                    break
                stock = sig['stock']
                entry_data = intraday_df[(intraday_df['stock'] == stock) &
                                         (intraday_df['date'] == t_date)]
                if entry_data.empty:
                    continue
                entry_price = entry_data.iloc[0]['open']
                atr = self._calc_atr(daily_df, stock)
                stop_loss = min(
                    entry_price * (1 + self.params.stop_loss_pct),
                    entry_price + self.params.atr_multiplier * atr
                )
                trade = self._simulate_trade(intraday_df, stock, t_date, entry_price, stop_loss, sig)
                if trade:
                    self.trades.append(trade)
                    pos_size = capital * self.params.max_position_pct
                    daily_pnl += pos_size * trade.pnl_pct
                    if trade.pnl_pct < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
            capital += daily_pnl
            equity_curve.append(capital)
            peak = max(peak, capital)
            dd = (capital - peak) / peak
            max_dd = min(max_dd, dd)
        return self._metrics(equity_curve, max_dd, initial_capital)

    def _calc_atr(self, daily_df, stock):
        data = daily_df[daily_df['stock'] == stock].tail(self.params.atr_period)
        if len(data) < 5:
            return 0
        tr = np.maximum(
            data['high'] - data['low'],
            np.maximum(abs(data['high'] - data['prev_close']),
                       abs(data['low'] - data['prev_close']))
        )
        return tr.mean()

    def _simulate_trade(self, intraday_df, stock, date, entry_price, stop_loss, sig):
        data = intraday_df[(intraday_df['stock'] == stock) & (intraday_df['date'] == date)]
        if data.empty:
            return None
        exit_price = entry_price
        exit_reason = 'close'
        holding_min = 0
        highest = entry_price
        for i, (_, bar) in enumerate(data.iterrows()):
            holding_min = (i + 1) * 5
            if bar['high'] >= stop_loss:
                exit_price = stop_loss
                exit_reason = 'stop_loss'
                break
            if self.params.exit_method in ('target', 'hybrid'):
                target = entry_price * (1 - self.params.target_profit_pct)
                if bar['low'] <= target:
                    exit_price = target
                    exit_reason = 'target'
                    break
            if self.params.exit_method in ('trailing', 'hybrid'):
                highest = max(highest, bar['high'])
                trail = highest * (1 - self.params.trailing_stop_pct)
                if bar['high'] >= trail and holding_min > 15:
                    exit_price = trail
                    exit_reason = 'trailing'
                    break
            if holding_min >= self.params.time_stop_minutes:
                exit_price = bar['close']
                exit_reason = 'time_stop'
                break
        else:
            exit_price = data.iloc[-1]['close']
        pnl = (entry_price - exit_price) / entry_price
        pnl -= self.params.total_cost_per_trade
        return TradeResult(
            date=date, stock=stock, signal_grade=sig['grade'],
            signal_score=sig['score'], entry_price=entry_price,
            exit_price=exit_price, exit_reason=exit_reason,
            pnl_pct=pnl, holding_minutes=holding_min,
            stop_loss_price=stop_loss,
            tier1_buyers=sig['t1_result']['tier1_buyers'],
            t_day_sellers=sig.get('t_day_result', {}).get('tier1_sellers', [])
                         if sig.get('t_day_result') else []
        )

    def _metrics(self, equity_curve, max_dd, initial):
        if not self.trades:
            return {'error': 'no trades'}
        pnls = [t.pnl_pct for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        years = (len(equity_curve) - 1) / 250
        final = equity_curve[-1]
        cagr = (final / initial) ** (1 / max(years, 0.1)) - 1
        grade_stats = {}
        for grade in ['A', 'B']:
            gt = [t for t in self.trades if t.signal_grade == grade]
            if gt:
                gp = [t.pnl_pct for t in gt]
                grade_stats[grade] = {
                    'count': len(gt),
                    'win_rate': sum(1 for p in gp if p > 0) / len(gp) * 100,
                    'avg_pnl': np.mean(gp) * 100,
                }
        return {
            'total_trades': len(self.trades),
            'win_rate': len(wins) / len(pnls) * 100,
            'avg_win': np.mean(wins) * 100 if wins else 0,
            'avg_loss': np.mean(losses) * 100 if losses else 0,
            'profit_factor': abs(sum(wins) / sum(losses)) if losses else float('inf'),
            'cagr': cagr * 100,
            'max_drawdown': max_dd * 100,
            'sharpe': np.mean(pnls) / np.std(pnls) * np.sqrt(250) if np.std(pnls) > 0 else 0,
            'avg_holding_min': np.mean([t.holding_minutes for t in self.trades]),
            'grade_breakdown': grade_stats,
            'exit_reasons': pd.Series([t.exit_reason for t in self.trades]).value_counts().to_dict(),
            'equity_curve': equity_curve,
            'trades': self.trades,
        }


class DailySignalGenerator:
    def __init__(self, params: BrokerSignalParams, broker_dir: str):
        self.params = params
        self.detector = BrokerSignalDetector(params, broker_dir)
        self.trigger = LiveTrigger(params)

    def generate_signals(self, yesterday_date: str, today_date: str,
                        limit_up_stocks: list) -> list:
        candidates = []
        for lu in limit_up_stocks:
            stock = lu['stock']
            lu_price = lu['close']
            t1_result = self.detector.detect_t1_signal(stock, yesterday_date, lu_price)
            if t1_result is None:
                continue
            gap_pct = lu.get('yesterday_gap', 0.05)
            score, grade = self.detector.score_signal(t1_result, None, gap_pct)
            if grade == 'C':
                continue
            candidates.append({
                'stock': stock, 'signal_grade': grade,
                'signal_score': round(score, 3),
                'tier1_buyers': [b['broker'] for b in t1_result['tier1_buyers']],
                'tier2_buyers': [b['broker'] for b in t1_result['tier2_buyers']],
                'total_buy_volume': t1_result['total_tier1_volume'] + t1_result['total_tier2_volume'],
                'entry_conditions': {
                    'method': self.params.entry_method,
                    'price_drop_pct': self.params.price_trigger_pct,
                    'max_delay_min': self.params.max_entry_delay_minutes,
                    'volume_surge_ratio': self.params.volume_surge_ratio,
                    'require_2_conditions': True,
                },
                'stop_loss_pct': self.params.stop_loss_pct,
                'target_profit_pct': self.params.target_profit_pct,
                'max_entry_time': f'09:{self.params.max_entry_delay_minutes:02d}',
                'mandatory_exit': '13:25',
            })
        candidates.sort(key=lambda x: x['signal_score'], reverse=True)
        return candidates[:self.params.max_concurrent_positions]


if __name__ == '__main__':
    print('=' * 60)
    print('Gem-ing-chong Broker Short Strategy Module')
    print('=' * 60)
    params = BrokerSignalParams()
    print(f'Tracked brokers: {len(TRACKED_BROKER_NAMES)}')
    print(f'  Tier1: {TIER1_NAMES}')
    print(f'  Tier2: {TIER2_NAMES}')
    print(f'Cost: {params.total_cost_per_trade*100:.3f}%/trade')
    print(f'Stop: {params.stop_loss_pct*100:.1f}% | Target: {params.target_profit_pct*100:.1f}%')