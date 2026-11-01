"""盘前指示价探测：08:45-09:01 每 2 秒记录 referencePrice 与 openPrice。

要回答的问题只有一个：集合竞价期间 referencePrice 会不会跟着变动。
  会 -> 策略能在 08:59 前看到"大概开在哪"，于是能在竞价结束前选股、算张数、送单，
        成交价就是开盘价，回测的进场价假设字面上成立，10/30 测到的 LONG +1.6% 滑价消失。
  不会（referencePrice 一直等于前收）-> 只能等 09:00 出价格，那就必然错过竞价，
        进场只能用 09:01，代价已经量过（10/30 那天多付 1.32% 净值）。

不下任何单。收盘后看 trading_logs/preopen_*.csv。
用法：python preopen_probe.py            # 自己等到 08:44 开始
      python preopen_probe.py --now      # 立刻跑一轮（盘后也能跑，用来看字段长什么样）
"""
import sys, time, csv, json, datetime, warnings; warnings.filterwarnings("ignore")
from fugle_marketdata import RestClient

KEY = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="
client = RestClient(api_key=KEY).stock
# 混合：大型股、中型股、策略常挑的低价股，还有当天可能跳空的族群
SYMS = ["2330", "2454", "2395", "3189", "2426", "5284", "6547", "9938", "2409", "6741"]
INTERVAL = 2.0
START = (8, 44, 0)
STOP = (9, 1, 30)


def main():
    now = datetime.datetime.now()
    if "--now" not in sys.argv:
        target = now.replace(hour=START[0], minute=START[1], second=0, microsecond=0)
        if now > target:
            target = target + datetime.timedelta(days=1)
        print("等到 %s 开始轮询" % target)
        while datetime.datetime.now() < target:
            time.sleep(min(10, (target - datetime.datetime.now()).total_seconds()))
    out = "trading_logs/preopen_%s.csv" % datetime.date.today().isoformat()
    import os
    os.makedirs("trading_logs", exist_ok=True)
    f = open(out, "w", newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    w.writerow(["wall_clock", "symbol", "previousClose", "referencePrice", "openPrice",
                "openTime", "lastPrice", "ref_vs_prev_pct", "total"])
    print("写 %s" % out)
    if "--now" in sys.argv:
        # one round only; after hours the clock has already passed 09:01
        stop = datetime.datetime.now() + datetime.timedelta(seconds=5)
    else:
        stop = datetime.datetime.now().replace(hour=STOP[0], minute=STOP[1], second=STOP[2], microsecond=0)
    n = 0
    while datetime.datetime.now() < stop:
        t0 = time.time()
        for s in SYMS:
            try:
                q = client.intraday.quote(symbol=s)
            except Exception as e:
                w.writerow([datetime.datetime.now().isoformat(), s, "ERR", type(e).__name__])
                continue
            pc = q.get("previousClose"); rp = q.get("referencePrice")
            delta = (100.0 * (rp - pc) / pc) if (rp and pc) else ""
            ot = q.get("openTime")
            ots = ""
            if ot:
                ots = datetime.datetime.fromtimestamp(ot / 1e6,
                        datetime.timezone(datetime.timedelta(hours=8))).strftime("%H:%M:%S.%f")[:12]
            w.writerow([datetime.datetime.now().isoformat(), s, pc, rp, q.get("openPrice"),
                        ots, q.get("lastPrice"), delta, (q.get("total") or {}).get("tradeVolume")])
            n += 1
        f.flush()
        el = time.time() - t0
        if n <= len(SYMS) * 3:
            q = client.intraday.quote(symbol=SYMS[0])
            print("  %s  2330 ref=%s prev=%s open=%s delta=%s" %
                  (datetime.datetime.now().strftime("%H:%M:%S"), q.get("referencePrice"),
                   q.get("previousClose"), q.get("openPrice"),
                   ("%.2f%%" % (100.0 * (q["referencePrice"] - q["previousClose"]) / q["previousClose"]))
                   if q.get("referencePrice") and q.get("previousClose") else "-"))
        time.sleep(max(0.5, INTERVAL - el))
    f.close()
    print("完成，%d 行 -> %s" % (n, out))


if __name__ == "__main__":
    main()
