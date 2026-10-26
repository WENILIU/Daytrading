# Daytrading — 台股開盤跳空反轉（Gap Fade v13）

當沖策略：交易**相對大盤**異常跳空的個股，賭散戶造成的超漲超跌在盤中回歸均值。
全部部位當沖平倉，零融資，整張交易，資金 450 萬。

## 現況

| 版本 | 狀態 | 說明 |
|---|---|---|
| **v13** | **目前版本** | CAGR 203%／MDD −4.32%／Sharpe 5.61（2010-2026，整張、零融資、成本已扣） |
| v8 | 已淘汰 | CAGR 140% 但含大盤前視；每筆邊際 −79.9%（p=0.0001）的結構性衰退 |
| v5 | 保留為 `gap_fade_v5_legacy.py` | 舊的手寫 score 制倉位 |

v13 的兩個關鍵修正：
1. **大盤基準改用 0050 開盤跳空**（9:00 可觀察）。v3~v12 用的是「當日大盤報酬」，那是前視，數字全部偏高。
2. **訊號下限 5% → 1.5%**。1.5-3% 區間觸及漲停率只有 5-12%（5%+ 區間 31-43%），把近年衰退的主因
   （觸板停損）從風險結構移除，同時取得 5-10 倍的交易廣度。

## 檔案

| 檔案 | 用途 |
|---|---|
| `STRATEGY.md` | 完整策略說明、參數、績效、衰退審計、實盤要求 |
| `gap_fade_auto.py` | 實盤／模擬下單（群益 SKCOM 智慧單）。`python gap_fade_auto.py [live\|sim\|now\|scan]`，`scan` 只測全市場掃描速度與涵蓋率 |
| `v13_live_risk.py` | 上實盤前三項風險量測（報價延遲／可借券／下單延遲） |
| `LIVE_READINESS.md` | **上實盤前必讀**：已修掉的下單缺陷、三項風險實測數字、上櫃涵蓋率的解法與各資料源實測 |
| `v13_factors.py` | 因子面板與 T-1 成交額產生器。每日開盤前 `--refresh`（向 finlab VIP 抓最新日 K → append → 重建因子）。<br>首次先 `--seed` 一次。見 `LIVE_READINESS.md` 第 7 節 |
| `v13_build.py` `v13_train.py` `v13_bt.py` | 回測宇宙、walk-forward 訓練、回測引擎 |
| `v13_export_model.py` | 輸出可上線模型 `v13_model.pkl`（模型與分位池，未入 repo，需自行產生） |
| `v13_decay.py` `v13_dstune.py` `v13_frontier.py` `v13_rawedge.py` `v13_ic.py` `v13_stale2.py` | 衰退歸因、槓桿前沿、模型健全度、因子延遲 |
| `RESEARCH_v11_expansion.md` | 研究記錄：所有試過並被否決的方向與原因 |
| `v13_final_report.txt` `v8_final_report.txt` | 逐年／逐月完整績效 |

## ✅ 上櫃涵蓋率已補齊（2026-10-26）

掃描原本走 TWSE 公開 API，**它只回答上市公司**，上櫃回空陣列被無聲漏掉 ——
那佔掉 45.9% 的訊號，用同一支回測引擎實測差 2.6 倍 CAGR（僅上市 70.0% vs 全部 184.9%）。

已改成富果批次端點 `GET /marketdata/v1.0/stock/intraday/quotes?symbol=A,B,C`
（複數路徑，SDK 沒包但 HTTP 有），**免費金鑰**即可：

| 項目 | 實測 |
|---|---|
| 單次請求 | 1,000 檔 |
| 全市場 3,307 檔 | 4 次請求 / 1.5 秒 |
| 涵蓋率 | TPEx 1,775/1,775、TWSE 1,532/1,532（**100%**） |
| 策略宇宙 1,928 檔 | **0.5 秒**（含 851 檔上櫃） |

TWSE MIS 保留為退路。驗證指令：`python gap_fade_auto.py scan`（只測速度與涵蓋率，
不下單）。來源比較與群益 SKCOM 的實測結論見 `LIVE_READINESS.md` §7A。
⚠️ 仍需在**開盤日**量一次 09:00 的實際報價可見延遲（RISK1），那是最後一個未知。

## 快速開始

```bash
# 1. 產生因子面板與 T-1 成交額（向 finlab VIP 抓最新日 K，append 後重建）
#    注意：is_vip() 在 legacy token 登入下永遠回 False，不可拿來判斷權限
python v13_factors.py --seed      # 只需一次
python v13_factors.py --refresh

# 2. 產生可上線模型
python v13_export_model.py

# 3. 今天模擬跑一遍（不下真單，now = 立即執行）
python gap_fade_auto.py now

# 4. 上實盤前
python v13_live_risk.py borrow     # 可借券覆蓋（已初步通過：各 gap 區間皆約 95%）
python v13_live_risk.py quotes     # 08:58 執行，量測開盤報價可見延遲
python v13_live_risk.py orders     # 盤中執行，量測 submit->ack 延遲與送單吞吐
```

## 必要外部資料

| 路徑 | 內容 |
|---|---|
| `D:\AI專案\StockAgent\finlab\database\price_*.pkl` | 每日 OHLCV（因子面板來源，需維持更新） |
| `D:\gapfade_data\zt_factors.pkl` `zt_turnover.pkl` `zt_latest.pkl` | 因子面板／成交額／最新列快取 |
| `D:\gapfade_data\disposal_panel_full.pkl` | 處置股逐日面板（TWSE + TPEx 官方公告，47,714 筆） |

## 已知限制

- 22.8 筆/日 → 必須自動下單。
- 高價股（300 元以上）常因「不足一張」被跳過，實際曝險低於模型設計值；回測已含此損耗。
- 每單位曝險的每筆邊際仍在衰退（約 −9%），v13 是用廣度與槓桿吸收，不是治好。
- 開盤 5 秒內的**成交率**尚未量測（滑價已量化：可承受額外 +0.27%/邊）。
