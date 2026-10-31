"""Drawing helpers for v13_audit_day.py. Panels show entry, exit, TP/SL, price limits."""
import os
import numpy as np, pandas as pd
import matplotlib.pyplot as plt

COST = 0.00111  # same as v13_engine.COST


def panel(ax, r):
    e = float(r["進場價"]); hi = float(r["日高"]); lo = float(r["日低"]); cl = float(r["收盤"])
    lu = float(r["漲停價"]); ld = float(r["跌停價"]); pc = float(r["前收"])
    slp = float(r["停損價"]); tpp = float(r["停利價"]); ex = float(r["出場價"])
    col = "crimson" if cl >= e else "seagreen"
    ax.vlines(0.5, lo, hi, color=col, lw=1.4)
    ax.add_patch(plt.Rectangle((0.45, min(e, cl)), 0.10, max(abs(cl - e), (hi - lo) * 0.004),
                               color=col, alpha=0.9, zorder=3))
    ylo = min(lo, e, ex, slp) * 0.994
    yhi = max(hi, e, ex, slp) * 1.006
    rng = yhi - ylo
    if lu - yhi < rng:
        yhi = max(yhi, lu) * 1.006
    if ylo - ld < rng:
        ylo = min(ylo, ld) * 0.994
    ax.set_ylim(ylo, yhi); ax.set_xlim(0, 1); ax.set_xticks([])
    ax.grid(axis="y", color="0.9", lw=0.6)
    for y, c, ls, lab, side in [(lu, "r", "-.", "漲停", "R"), (ld, "b", "-.", "跌停", "R"),
                                (pc, "0.55", ":", "前收", "R"), (tpp, "g", "--", "TP", "L"),
                                (slp, "darkorange", "--", "SL", "L")]:
        if ylo <= y <= yhi:
            ax.axhline(y, color=c, ls=ls, lw=1.0, alpha=0.85)
            ax.text(0.995 if side == "R" else 0.005, y, "%s %.2f" % (lab, y), color=c, fontsize=7.5,
                    va="bottom", ha="right" if side == "R" else "left")
    if r["方向"] == "SHORT":
        ax.plot(0.10, e, "v", color="darkorange", ms=12, zorder=5)
        ax.annotate("放空 %.2f" % e, (0.10, e), xytext=(14, 0), textcoords="offset points",
                    color="darkorange", fontsize=9, va="center", fontweight="bold")
    else:
        ax.plot(0.10, e, "^", color="steelblue", ms=12, zorder=5)
        ax.annotate("買進 %.2f" % e, (0.10, e), xytext=(14, 0), textcoords="offset points",
                    color="steelblue", fontsize=9, va="center", fontweight="bold")
    ax.plot(0.90, ex, "X", color="purple", ms=13, zorder=5)
    ax.annotate("出場 %.2f\n%s" % (ex, r["出場原因"]), (0.90, ex), xytext=(-14, 0), textcoords="offset points",
                color="purple", fontsize=9, va="center", ha="right", fontweight="bold")
    ok = r["450萬狀態"].startswith("可下")
    ax.set_title("#%d %s %s  模型分位 %.2f\nGap %.1f%% | TP %.0f%% / SL 4%% | %s\n淨損益 %+.2f%%" %
                 (r["序"], r["股票"], r["方向"], r["模型分位pred_q"], r["調整後gap%"], r["停利TP%"],
                  ("%d 張 / %.1f 萬" % (r["成交張數"], r["成交金額(萬)"])) if ok else "450 萬無法下單",
                  r["淨損益%"]), fontsize=9.5, color=("darkgreen" if ok else "firebrick"))
    ax.text(0.5, -0.17, "當日成交額 %.0f 萬 | 我占 %.2f%% | 設計權重 %.2f%% | 進場距漲停 %.1f%%" %
            (r["當日成交額(萬)"], (r["我占當日額%"] if np.isfinite(r["我占當日額%"]) else 0),
             r["設計權重%"], r["進場距漲停%"]), ha="center", fontsize=7.5, transform=ax.transAxes, color="dimgray")
    msg = []
    if not ok:
        msg.append(r["450萬狀態"])
    if bool(r.get("整天只成交一個價格", False)):
        msg.append("整天只成交一個價格，這個價位在回測裡已被排除")
    if msg:
        ax.text(0.5, 0.04, "\n".join(msg), ha="center", fontsize=8.5, transform=ax.transAxes,
                color="firebrick", bbox=dict(fc="mistyrose", ec="firebrick", alpha=0.92), zorder=6)


def grid(df, path, ttl, ncol=4):
    n = len(df); nrow = max(1, int(np.ceil(n / ncol)))
    fig, axes = plt.subplots(nrow, ncol, figsize=(6.4 * ncol, 4.6 * nrow))
    axes = np.array(axes).reshape(-1)
    for i, (_, r) in enumerate(df.iterrows()):
        panel(axes[i], r)
    for j in range(n, len(axes)):
        axes[j].axis("off")
    fig.suptitle(ttl, fontsize=15)
    fig.tight_layout(rect=[0, 0.012, 1, 0.955])
    fig.savefig(path, dpi=115, facecolor="white")
    plt.close(fig)


def draw(date, T, C, cv, out):
    row = cv.loc[pd.Timestamp(date)]
    tag = date.replace("-", "")
    # The panels are drawn from C, which is the R9 book (participation floor and
    # one-lot-too-big filter included). The engine row["C_*"] is a different book, so
    # the title must not print one count and the other day return (it did: 7 筆 next to
    # +0.723% on 2026-10-30, where 7 筆 is worth -0.026%).
    from v13_engine import CAP0
    own_yuan = float(C["盈虧(元)"].sum())
    own_expo = float(C["成交金額(萬)"].sum()) * 1e4 / CAP0 * 100
    grid(C, os.path.join(out, "audit_grid_%s_450萬實際交易.png" % tag), ncol=2,
         ttl="Gap Fade v13 - %s  450 萬整張實際能下的 %d 筆，合計 %+.0f 元\n"
             "R9 現行下單規則（本圖這 %d 筆）: 曝險 %.1f%% / 當日 %+.3f%%\n"
             "回測引擎 allocate（無參與率上限、無 1 張過大過濾，不是這本書）: %d 筆 / %+.3f%%\n"
             "策略設計面: %d 筆 / 曝險 %.0f%% / 當日 %+.3f%%\n"
             "大盤開盤 Gap %+.2f%%，通過過濾的訊號 %d 個；淨值回撤 %.2f%% -> 倉位倍數 %.1f，30 日邊際倍數 %.1f" %
             (date, len(C), own_yuan, len(C), own_expo, own_yuan / CAP0 * 100,
              row["C_n"], row["C_pnl"] * 100,
              len(T), row["A_expo"] * 100, row["A_pnl"] * 100, row["market_ret"] * 100,
              int(row["n_signals"]), row["cdd"] * 100, row["rs"],
              C["30日倍數"].iloc[0] if len(C) else float("nan")))
    grid(T.sort_values("序").head(12), os.path.join(out, "audit_grid_%s_top12.png" % tag), ncol=4,
         ttl="Gap Fade v13 - %s  模型排名前列 12 筆（標明 450 萬整張能否下單）\n"
             "這 12 筆設計權重合計 %.1f%%；450 萬下只有 %d 筆湊到 1 張" %
             (date, T.sort_values("序").head(12)["設計權重%"].sum(), len(C)))
    for _, r in C.iterrows():
        fig, ax = plt.subplots(figsize=(12, 6.5))
        panel(ax, r)
        ax.set_title("#%d  %s %s | 進場 %.2f -> 出場 %.2f (%s) | 淨損益 %+.2f%% = %+.0f 元 | %d 張 %.1f 萬" %
                     (r["序"], r["股票"], r["方向"], r["進場價"], r["出場價"], r["出場原因"],
                      r["淨損益%"], r["盈虧(元)"], r["成交張數"], r["成交金額(萬)"]), fontsize=13)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "per_stock", "%s_%02d_%s.png" % (tag, r["序"], r["股票"])),
                    dpi=120, facecolor="white")
        plt.close(fig)
    fig, axs = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ea = (1 + cv["A_pnl"]).cumprod(); ec = (1 + cv["C_pnl"]).cumprod()
    axs[0].plot(ea.index, ea.values, color="navy", lw=1.1, label="A 策略設計面（發表版，無整張限制）")
    axs[0].plot(ec.index, ec.values, color="darkorange", lw=1.1, alpha=.85, label="C 450 萬 + 整張（回測引擎 allocate 規則，非 R9）")
    axs[0].axvline(pd.Timestamp(date), color="red", ls="--", lw=1.2)
    axs[0].annotate(date, (pd.Timestamp(date), ea.iloc[-1]), xytext=(-90, -18),
                    textcoords="offset points", color="red", fontsize=10)
    axs[0].set_yscale("log"); axs[0].set_ylabel("成長倍數（log）"); axs[0].legend(); axs[0].grid(alpha=.3)
    axs[0].set_title("Gap Fade v13 淨值曲線（至 %s）：A 設計面 vs C 450 萬整張" % date, fontsize=14)
    axs[1].plot(cv.index, cv["A_n"].values, color="navy", lw=.7, alpha=.8, label="A 每日筆數")
    axs[1].plot(cv.index, cv["C_n"].values, color="darkorange", lw=.7, alpha=.8, label="C 每日筆數(450萬)")
    axs[1].axvline(pd.Timestamp(date), color="red", ls="--", lw=1.2)
    axs[1].set_ylabel("筆數/日"); axs[1].legend(); axs[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "equity_up_to_%s.png" % tag), dpi=115, facecolor="white")
    plt.close(fig)
    print("charts written to", out)
