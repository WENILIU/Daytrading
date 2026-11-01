"""收盤後把「最近一個交易日」的完整逐筆成交存成檔案。

为什么要这个：策略 75% 的损益来自 13:25 强制平仓，而 13:25 之后只剩收盘竞价。
只有逐笔成交能回答"那个价位有几张"——1 分 K 只能回答"价格有没有到过"。

两个实测过的事实，写在这里免得以后又踩：
  1. intraday.trades 的 limit 上限是 500，offset 有效，可以往前翻到 09:00:08
     （2026-11-01 实测 2330 共 15 页 7,428 笔 / 4.0 秒）。之前那批 241,404 个档案
     每档只有 50 笔，是因为没带 limit，吃到了 API 预设值。
  2. date= 参数被忽略，永远回最近一个交易日。所以历史补不回来，只能每天收。

用法：
  python collect_ticks.py                # 今天日志里实际下单的股票
  python collect_ticks.py 2330 2395      # 指定代码
"""
import sys, os, json, time, glob, datetime, warnings; warnings.filterwarnings("ignore")
from fugle_marketdata import RestClient

API_KEY = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="
OUT = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票成交明細_full"
PAGE = 500
MAX_PAGES = 60
PAUSE = 0.35  # between pages; the free key throttles well before 60 requests
client = RestClient(api_key=API_KEY).stock


def from_log():
    """今天 live/paper 日志里真的下过单的股票。"""
    today = datetime.date.today().isoformat()
    codes = []
    for p in sorted(glob.glob(os.path.join("trading_logs", "*.log"))):
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if today not in txt:
            continue
        for line in txt.splitlines():
            if "ORDER" in line or "SUBMIT" in line:
                for tok in line.replace(",", " ").split():
                    if len(tok) == 4 and tok.isdigit():
                        codes.append(tok)
    return sorted(set(codes)), today


def get_page(symbol, off):
    """一页逐笔。Fugle 有 rate limit（实测 2026-11-01：连发约 20 页就 429），
    所以退避重试而不是直接放弃。"""
    delay = 1.0
    for attempt in range(6):
        try:
            return client.intraday.trades(symbol=symbol, limit=PAGE, offset=off)
        except Exception as e:
            if "Rate limit" not in str(e) and "429" not in str(e):
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError("rate limit: still blocked after retries")


def fetch(symbol):
    """整天逐笔（升序），回 (date, rows, pages)。翻到空或回到 09:00 之前为止。"""
    rows, off, pages = [], 0, 0
    day = None
    while pages < MAX_PAGES:
        r = get_page(symbol, off)
        d = r.get("data") or []
        if not d:
            break
        if day is None:
            day = r.get("date")
        rows.extend(d)
        pages += 1
        off += PAGE
        ts = [x.get("time") for x in d if x.get("time")]
        if not ts:
            break
        hhmm = datetime.datetime.fromtimestamp(min(ts) / 1e6,
                                              datetime.timezone(datetime.timedelta(hours=8))).strftime("%H:%M:%S")
        if hhmm <= "09:00:10":
            break
        time.sleep(PAUSE)
    seen = {}
    for x in rows:
        seen[x.get("serial", x.get("time"))] = x
    return day, sorted(seen.values(), key=lambda x: x.get("time") or 0), pages


def main():
    args = [a for a in sys.argv[1:] if a.isdigit()]
    if args:
        codes, day_hint = sorted(set(a.zfill(4) for a in args)), None
    else:
        codes, day_hint = from_log()
    if not codes:
        print("没有代码可收。日志里找不到今天的下单记录，或直接给代码：python collect_ticks.py 2330")
        return 1
    print("收集 %d 档" % len(codes))
    t0 = time.time()
    ok = 0
    got_day = None
    for i, c in enumerate(codes, 1):
        try:
            day, rows, pages = fetch(c)
        except Exception as e:
            print("  [%2d/%d] %s ERR %s %s" % (i, len(codes), c, type(e).__name__, str(e)[:80]))
            continue
        if not rows:
            print("  [%2d/%d] %s 无成交" % (i, len(codes), c))
            continue
        got_day = got_day or day
        d = os.path.join(OUT, c)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "%s_%s.json" % (c, day))
        json.dump({"date": day, "symbol": c, "pages": pages, "count": len(rows), "data": rows},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)
        ok += 1
        time.sleep(PAUSE)
        if i <= 5 or i == len(codes):
            print("  [%2d/%d] %s n=%6d pages=%2d -> %s" % (i, len(codes), c, len(rows), pages, p))
    print("\n完成 %d/%d 档，日期 %s，耗时 %.1fs（%.2fs/档）" %
          (ok, len(codes), got_day or day_hint, time.time() - t0, (time.time() - t0) / max(1, len(codes))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
