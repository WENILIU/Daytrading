import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm, rcParams
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

for f in ("C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msjhl.ttc"):
    try:
        fm.fontManager.addfont(f)
    except Exception:
        pass
rcParams["font.family"] = "Microsoft JhengHei"
rcParams["axes.unicode_minus"] = False

INK="#1f2937"; MUT="#6b7280"
BLUE="#e8f0fb"; BLUE_E="#2f6fb4"
GREEN="#e9f5ec"; GREEN_E="#2f8a4c"
AMBER="#fdf3e0"; AMBER_E="#b7791f"
RED="#fbeaea"; RED_E="#b3352f"
GRAY="#f1f2f4"; GRAY_E="#8a94a6"
LOGC="#f4eefb"; LOG_E="#6b4c9a"

H = 156.0
fig = plt.figure(figsize=(26, H * 0.165), dpi=120)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 100); ax.set_ylim(0, H); ax.axis("off")
ax.add_patch(FancyBboxPatch((0, 0), 100, H, boxstyle="square,pad=0", fc="white", ec="none", zorder=0))

def box(cx, y, w, h, title, body, fc, ec, fs=8.2, tfs=9.6, gap=2.2):
    ax.add_patch(FancyBboxPatch((cx - w/2, y - h), w, h,
                 boxstyle="round,pad=0.25,rounding_size=0.7", fc=fc, ec=ec, lw=1.4, zorder=3))
    ty = y - 2.1
    if title:
        ax.text(cx, ty, title, ha="center", va="top", fontsize=tfs, fontweight="bold",
                color=INK, zorder=4)
        ty -= 2.9
    if body:
        ax.text(cx, ty, body, ha="center", va="top", fontsize=fs, color=INK,
                linespacing=1.6, zorder=4)
    return y - h - gap

def note(cx, y, text, color, fs=7.9, bold=True):
    n = text.count(chr(10)) + 1
    ax.text(cx, y - 0.6, text, ha="center", va="top", fontsize=fs, color=color,
            fontweight="bold" if bold else "normal", linespacing=1.6, zorder=4)
    return y - n * 2.0 - 1.4

def arrow(x, y1, y2, color=MUT, lw=1.8):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>", mutation_scale=15,
                 lw=lw, color=color, zorder=2))

def header(cx, w, y, txt, sub, fc, ec):
    ax.add_patch(FancyBboxPatch((cx - w/2, y - 6.6), w, 6.6,
                 boxstyle="round,pad=0.25,rounding_size=0.7", fc=fc, ec=ec, lw=2.0, zorder=4))
    ax.text(cx, y - 2.0, txt, ha="center", va="top", fontsize=12.6, fontweight="bold", color=INK, zorder=5)
    ax.text(cx, y - 4.9, sub, ha="center", va="top", fontsize=8.8, color=MUT, zorder=5)

ax.text(50, H - 1.6, "Gap Fade v13 開盤跳空反轉 — 一整天在做什麼（每一步對應的 log 都標在同一欄下方）",
        ha="center", va="top", fontsize=18, fontweight="bold", color=INK)
ax.text(50, H - 5.2, "資金 450 萬｜整張(1000股)｜零融資｜成本 0.109%/邊｜群益北高雄 0438724｜回測 CAGR 203% / MDD -4.32%（已含整張限制與真實處置排除）",
        ha="center", va="top", fontsize=9.8, color=MUT)

W = 18.4
C = [8.2, 27.8, 47.4, 67.0, 87.6]
TOP = H - 13.4
for cx, t, s, fc, ec in [
    (C[0], "① 開盤前 08:55", "把模型的「輸入」備齊", BLUE, BLUE_E),
    (C[1], "② 09:00 掃描", "決定：誰有資格被交易", GREEN, GREEN_E),
    (C[2], "③ 評分 + 算部位", "決定：買哪幾檔、各買多少", AMBER, AMBER_E),
    (C[3], "④ 09:00 下單", "一張智慧單搞定進出場", BLUE, BLUE_E),
    (C[4], "⑤ 盤中 → 13:20", "我們只回報，成交在交易所", GREEN, GREEN_E)]:
    header(cx, W, TOP, t, s, fc, ec)
for i in range(4):
    arrow(C[i] + W/2 + 0.5, TOP - 3.3, TOP - 3.3, color=BLUE_E, lw=2.2)
    ax.text(C[i] + W/2 + 0.5, TOP - 1.0, "", ha="center")

# ---------- ① 開盤前 ----------
y = TOP - 8.0
y = box(C[0], y, W, 12.6, "1. 更新因子面板",
 "python v13_factors.py --refresh\n實測 27 秒完成\n面板 = 模型的 21 個特徵\n（大盤狀態、個股歷史、漲停鎖住率…）",
 BLUE, BLUE_E)
y = note(C[0], y, "沒更新 → 同一引擎實測\n2023-25 從 1692% 掉到 260%\n這是整條流程最大的單一風險", RED_E)
y = box(C[0], y, W, 12.0, "2. 載入三個狀態檔",
 "模型 v13_model.pkl（逐年重訓）\n處置股清單 + 借券額度（皆 finlab，取 T-1）\n淨值 equity_state.json（回撤剎車用）",
 BLUE, BLUE_E)
y = box(C[0], y, W, 11.0, "3. 開盤前最後確認",
 "處置股一定要是 finlab 給的\n面板 lag <= 10 天\n淨值不能是模擬留下的舊值",
 GRAY, GRAY_E)
y = box(C[0], y, W, 13.4, "對應的 log 行",
 "Restricted from finlab in 0.77s:\n  14 處置 (both markets), 14 暫停當沖\nv13 model loaded: trained through …\nFactor panel as-of <date> (lag 4d)",
 LOGC, LOG_E, fs=7.6)
y = box(C[0], y, W, 12.6, "看到這些就是壞了",
 "came from the exchange announcement\n  pages → 會漏 5/14 檔處置股\nDISPOSAL PANEL STALE → 三條源全死\nFACTOR PANEL STALE → 改餵 NaN 特徵",
 RED, RED_E, fs=7.6)
print("col1 bottom", round(y, 1))

# ---------- ② 掃描漏斗 ----------
y = TOP - 8.0
y = box(C[1], y, W, 7.0, "全部股票 1,928 檔", "上市 1,077 + 上櫃 851\n（兩市都必須到，上櫃常漏）", GREEN, GREEN_E, fs=8.0)
arrow(C[1], y + 2.0, y + 0.3)
y = box(C[1], y, W, 9.4, "開盤前先砍（省時間）",
 "T-1 成交額 < 1,000 萬 → 掉\n處置股 / 暫停先賣後買 → 掉\n1,928 → 約 905 檔",
 GREEN, GREEN_E, fs=8.0)
y = note(C[1], y, "已驗證不會漏單：被砍掉的檔\n本來就不會成為訊號", GREEN_E, fs=7.6)
y = box(C[1], y, W, 8.0, "09:00 一次抓價",
 "富果批次端點：905 檔 0.3 秒\n（一檔一檔問要 4.86 秒，太慢）",
 GREEN, GREEN_E, fs=8.0)
arrow(C[1], y + 2.0, y + 0.3)
y = box(C[1], y, W, 11.4, "算「相對大盤」的跳空",
 "adj_gap = 個股開盤漲跌 - 0050開盤漲跌\n\n例：大盤開盤漲 2%、個股漲 3%\n→ adj_gap 只有 +1% → 不算訊號",
 AMBER, AMBER_E, fs=8.0)
y = note(C[1], y, "這一步就是策略的 alpha 來源：\n只交易脫離大盤的異常，不交易「跟著大盤漲」", AMBER_E, fs=7.8)
y = box(C[1], y, W, 9.0, "訊號條件",
 "放空 SHORT：adj_gap >= +1.5%\n做多 LONG：adj_gap <= -5.0%\n（1.5~5% 的做多實測是負邊際，已剔除）",
 GREEN, GREEN_E, fs=8.0)
arrow(C[1], y + 2.0, y + 0.3)
y = box(C[1], y, W, 10.0, "最後再排掉不能交易的",
 "開盤鎖死漲/跌停（進場會被鎖住）\n股價 < 30 元（價差太大、流動性差）\n放空：T-1 借券額度 = 0 → 排除\n（做多是現股買，不需要借券）",
 GREEN, GREEN_E, fs=8.0)
y = box(C[1], y, W, 17.2, "對應的 log 行",
 "Pre-open trim: dropped A turnover,\n  B disposal, kept 905\nScan via Fugle (TWSE+TPEx): 905 in 0.3s\nCOVERAGE: full universe answered\n  (TPEx rows in feed: 851)\nMarket gap (0050 open, v13 def): +0.42%\nOpening-locked (excluded): N\nRejected SHORT for no lending quota\n  (T-1): N",
 LOGC, LOG_E, fs=7.4)
y = box(C[1], y, W, 12.2, "看到這些就是壞了",
 "falling back to TWSE MIS → 上櫃看不到\nTPEx rows 掉到 0 → 同上\nFALLBACK (7 large caps, NOT v13 def)\n  → 基準換了，當天訊號不可比",
 RED, RED_E, fs=7.4)
print("col2 bottom", round(y, 1))

# ---------- ③ 評分與部位 ----------
y = TOP - 8.0
y = box(C[2], y, W, 10.0, "1. 模型先淘汰",
 "HistGradientBoosting 預測這筆淨損益\n預測最差的前 20% 直接放棄\n（pred_q < 0.20）",
 AMBER, AMBER_E, fs=8.0)
arrow(C[2], y + 2.0, y + 0.3)
y = box(C[2], y, W, 8.2, "2. 預測分 → 基礎部位",
 "分越高買越多：5% / 7% / 9% / 12%\n（都是占淨值的比例）",
 AMBER, AMBER_E, fs=8.0)
arrow(C[2], y + 2.0, y + 0.3)
y = box(C[2], y, W, 16.6, "3. 三個加減碼開關",
 "zt_mult：離漲停 < 1.5% → x10\n  理由：被漲停封住最多只虧 2%，\n  虧損有上限，所以敢放大\n  離漲停 < 4.5% → x2.5\ndd_scale：淨值已回撤 > 0.6% → x0.30\n  回撤 > 1.2% → x0.12（連賠就縮手）\nk_model / k_trail：最近賺 → 加碼\n  最近賠 → 減碼",
 AMBER, AMBER_E, fs=7.8)
arrow(C[2], y + 2.0, y + 0.3)
y = box(C[2], y, W, 12.4, "4. 三道硬上限",
 "單檔 <= 25% 淨值\n總名義 <= 450 萬（零融資，不用融資券）\n整張湊整：int(金額/價/1000) x 1000\n不足一張 → 跳過（高價股常卡在這裡）",
 RED, RED_E, fs=7.8)
y = box(C[2], y, W, 16.2, "對應的 log 行",
 "Model scored 63 candidates -> kept 22;\n  TP20 share 18%\nMarket regime: DD=-0.4% Vol=1.2%\n  ConsecDown=0 3dRet=+0.8% PrevRet=+0.1%\nENTER 2345 SHORT price=45.5 shares=9000\n  tier=T3 SL=47.4(4.2%) TP=50.9(12%) |\n  limit=50.6/41.2",
 LOGC, LOG_E, fs=7.2)
y = box(C[2], y, W, 12.2, "跳過一定留原因",
 "< 1 zhang, SKIP\nexposure cap reached, SKIP\nSkipped (at price limit): N\nDoes not support day trade, SKIP\n→ 回測會下但實盤沒下的單全部可追",
 GRAY, GRAY_E, fs=7.4)
print("col3 bottom", round(y, 1))

# ---------- ④ 下單 ----------
y = TOP - 8.0
y = box(C[3], y, W, 13.4, "一張智慧單同時掛 4 件事",
 "SendStockStrategyDayTrade\n① 進場限價（開盤價）\n② 停損觸發價 ③ 停利觸發價\n④ 13:20 全部平倉",
 BLUE, BLUE_E, fs=8.0)
y = note(C[3], y, "重點：進出場條件一次交給交易所執行，\n不是我們的程式用網路盯盤。\n網路斷掉、掃描慢一秒，停損照樣生效。", BLUE_E, fs=7.9)
y = box(C[3], y, W, 13.0, "停損 = min(4%, 漲停價 - 1 tick)",
 "用「絕對觸發價」不是百分比\n（百分比在鎖死時永遠不會觸發）\n碰到漲停 → 立刻停損，不會被鎖住\n無法回補 → 不會變成隔日放空",
 BLUE, BLUE_E, fs=8.0)
y = box(C[3], y, W, 10.0, "停利 = 12%",
 "模型很有把握時（q1 >= 0.85）放寬到 20%\n讓大行情跑完，不在 4% 就落袋",
 BLUE, BLUE_E, fs=8.0)
y = box(C[3], y, W, 13.4, "對應的 log 行",
 "SMART ORDER: 2345 SHORT 9 張 @ 45.5\n  [T3] SL=47.4 TP=50.9 clear=13:20\n  key=ST1234567\nTotal exposure: 3,120,000 (69%)\n[OrderResult] …（券商回執原文保留）",
 LOGC, LOG_E, fs=7.4)
y = box(C[3], y, W, 11.6, "! 誠實標註",
 "回測的強制平倉寫 13:25，但系統上限\n只能送 13:20 → 這 5 分鐘的差異\n回測沒有算進去，實盤會早 5 分鐘出場",
 RED, RED_E, fs=7.8)
print("col4 bottom", round(y, 1))

# ---------- ⑤ 盤中 ----------
y = TOP - 8.0
y = box(C[4], y, W, 12.2, "盤中：只做回報",
 "每 60 秒一次批次取價\n22 檔逐檔 4.86 秒 → 批次 0.02~0.16 秒\n（盲區從 5~11 秒壓到 0.2 秒內）",
 GREEN, GREEN_E, fs=8.0)
y = note(C[4], y, "最終成交以券商 [FILL] 為準，\n不是以「我們看到觸發」為準。\n兩者可能不同 → 這正是要回查的東西", RED_E, fs=7.9)
y = box(C[4], y, W, 14.4, "一筆交易只有 4 種結局",
 "① 觸停利 → 賺 12% / 20%\n② 觸停損 → 賠 4%（或漲停前 1 tick）\n③ 13:20 強制平倉 → 這才是主要獲利來源\n   實測 79.9% 的筆數靠這步，平均 +0.44%\n④ 開盤就被跳過 → 根本沒進場",
 GREEN, GREEN_E, fs=7.8)
y = box(C[4], y, W, 10.2, "收盤：更新三個狀態檔",
 "trail30（近 30 筆損益）\nsignal_history（個股訊號歷史）\nequity_state（淨值 / peak）→ 明天要用",
 GREEN, GREEN_E, fs=8.0)
y = box(C[4], y, W, 13.0, "對應的 log 行",
 "EXITED: 2345 SHORT @ 44.1 [force_close]\n  PnL=+12,340\n[FILL] …（原始 args 全部留底）\n[CANCEL] …\ntrail30 updated: SHORT=+0.42% …",
 LOGC, LOG_E, fs=7.4)
y = box(C[4], y, W, 12.0, "第一次實盤要做的事",
 "[FILL] price recovered at numeric\n  field #N → 確認成交價在第幾個欄位，\n  確認後把索引寫死，不要再猜",
 AMBER, AMBER_E, fs=7.6)
print("col5 bottom", round(y, 1))

# ---------- 底部：收盤後回查 ----------
BAND_TOP = 20.0
ax.add_patch(FancyBboxPatch((2.0, 1.2), 96.0, BAND_TOP - 1.2,
             boxstyle="round,pad=0.3,rounding_size=0.8", fc="#fbfbfc", ec=INK, lw=1.8, zorder=3))
ax.text(50, BAND_TOP - 1.6, "⑥ 收盤後：EXECUTION RISK REPORT —— 要回查「實盤 vs 回測」就看這 5 行",
        ha="center", va="top", fontsize=13, fontweight="bold", color=INK, zorder=4)
items = [
 ("RISK1 opening price visible: X.XXs",
  "開盤價幾秒後才看得到。這是上實盤前\n唯一還沒量到的關鍵數字。\n（下界已定 ~9 秒：2330 的 openTime\n 是 09:00:08.98，與我們的網路無關）"),
 ("ENTRY SLIPPAGE … edge>0 = favourable",
  "成交價 vs 回測假設價，逐向中位/p90。\n這是「模型的邊際能不能活過現實」\n的數字。SHORT 成交較高=有利，\nLONG 成交較低=有利"),
 ("filled within 5/10/30/60s of 09:00: k/n",
  "開盤幾秒內成交幾筆。\nk/n 很低 → 代表回測的價格\n假設根本不成立"),
 ("submit->ack median / order submission",
  "22 筆要多久送完、每秒能送幾張。\n已實測：不是瓶頸"),
 ("rejected orders: N retried: M",
  "被券商退單的原因逐筆列 code=\n（不支持當沖、資券不足…）"),
]
xw = 96.0 / 5
for i, (t, b) in enumerate(items):
    cx = 2.0 + xw * (i + 0.5)
    ax.text(cx, BAND_TOP - 5.4, t, ha="center", va="top", fontsize=8.8, fontweight="bold", color=BLUE_E, zorder=5)
    ax.text(cx, BAND_TOP - 8.2, b, ha="center", va="top", fontsize=7.6, color=INK, linespacing=1.6, zorder=5)
ax.text(50, 6.0, "回查標準動作：拿 ENTER 那行的 price / 張數 / SL / TP → 去對 [FILL] 的實際成交價 → 差額就是 edge。三個數對不起來，問題一定在「掃描延遲 / 成交率 / 智慧單條件」三者之一。",
        ha="center", va="top", fontsize=9.2, fontweight="bold", color=INK, zorder=5)
ax.text(50, 3.7, "檔案都在 trading_logs\\ ：trading_YYYY-MM-DD.log（全流程）｜exec_report_YYYYMMDD.json（含 fill_raw，可離線重解析成交價）｜trades_YYYY-MM-DD.csv（逐筆損益）",
        ha="center", va="top", fontsize=8.2, color=MUT, zorder=5)
ax.text(50, 1.9, "signal_history.json、trail30_state.json、equity_state.json 是模型的輸入狀態，隔天要用，不要刪",
        ha="center", va="top", fontsize=8.2, color=MUT, zorder=5)

fig.savefig("strategy_flow.png", dpi=120, facecolor="white")
print("SAVED strategy_flow.png")
