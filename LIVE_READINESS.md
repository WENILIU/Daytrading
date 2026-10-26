# Gap Fade v13 — 上實盤前的待驗證清單

日期：2026-10-26。帳號：群益北高雄 `0438724`（SKCOM 自動偵測 `913R0438724`）。
本檔記錄「回測看不出來、只有接上券商才會發現」的問題，以及已量到的數字。

---

## 0. 本輪修掉的三個真實缺陷

### 0.1 `nQty` 是「張數」不是「股數」（最嚴重）
`6.下單-證券智慧單.docx` 對 `STOCKSTRATEGYORDER` 的定義：

```c
LONG nQty;   //委託張數
```

舊碼寫 `oOrder.nQty = sig.shares`，也就是 1 張傳成 `1000` → **委託量放大 1000 倍**。
這正是之前「委託量變 1000 倍嚇死人」的原因，當時只被當成顯示問題，其實一直在送出
1000 張的單。已改為 `nQty = shares // 1000`。

同一份文件也確認了 `nBuySell` 在當沖物件裡的定義是 `0:現股買 / 1:無券賣出`，
與「無借券費用」的設定一致，這部分原本就是對的。

### 0.2 停損停利改用「絕對觸發價」
v13 的停損是 `min(4%, 漲停價 − 1 tick)`。智慧單的**百分比**停損（`nRDOSLPercent=1`）
無法表達這個上限：股價一旦鎖在漲停，−4% 永遠不會觸發，部位就被鎖死、必須過夜。
改用 `nRDOSLPercent=0` + `bstrSLTrigger=<sl_price>`（停利同理）後，送出去的條件
與回測的動態停損完全一致。

### 0.3 強制平倉上限是 13:20，不是 13:25
文件：`bstrClearCancelTime; //出清時間-時＋分（hhmm）{每日13:20截止}`。
原本送 `1325`。已改送 `1320`，並把出清委託方式從限價改成**市價**——
限價出清在虧損時可能補不回來，變成無意圖的過夜部位。

回測仍以 13:25 平倉結算，兩者差 5 分鐘；先前量過影響 < 0.1%/筆。

---

## 1. 風險一：開盤報價可見延遲 — **尚未量到**

回測假設 09:00:00 的開盤價可直接成交。實際上要等資料源把開盤價吐出來。

- 已把 `_wait_for_quotes()` 改成探測**掃描器同一個資料源**（TWSE MIS）。
  它之前探的是 `SKQuoteLib`，兩者填資料的速度不同，會給出誤導性的答案。
- 現在 `run()` 會把量測基準釘在真正的 09:00:00，並在收盤的
  `EXECUTION RISK REPORT` 輸出：
  - `RISK1 opening price visible: X.XXs after 09:00:00`
  - `RISK1 scan finished: X.XXs after 09:00:00`
- 也可以單獨跑：`python v13_live_risk.py quotes`（建議 08:58 啟動）。
- 已知參考值：掃描 1,928 檔本身只要 **2.9 秒**，瓶頸只在「開盤價何時可見」。
- 使用者先前觀察到的 4960 案例：09:00:18 開 30.3 後一路滑到 28.25。
  若 09:00:20 才看到價格、再花 5 秒下單，SHORT 的進場價會比回測差很多
  （但方向對 SHORT 有利，對 LONG 不利）。

**第一次真的 09:00 跑 `python gap_fade_auto.py live`，這個數字就自動出來。**

## 2. 風險二：1.5–3% 區間的可借券性 — **已量，無差別**

v13 把 SHORT 門檻從 5% 降到 1.5%，新增的這段區間能不能借到券是未驗證的。
近 45 天 SHORT 訊號的可借券覆蓋率（finlab 出借量代理）：

| Gap 區間 | 可借券覆蓋率 |
|---|---|
| 1.5–3% | 94.75% |
| 3–5%   | 94.32% |
| 5%+    | 96.47% |

1.5–3% 與 5%+ 沒有系統性差異，廣度優勢不是紙上的。
要换成券商官方資料需設 `YUANTA_APP_KEY` / `YUANTA_APP_SECRET`，
走 shioaji 1.7.8 的 `credit_enquires`；目前尚未成功驗證。

## 3. 風險三：下單延遲與吞吐 — **已量，不是瓶頸**

用**正式路徑**實測（`SendStockStrategyDayTrade`，1 張買在跌停價所以絕不會成交）：

```
submit->ack  n=6  median=129ms  p95=272ms  max=272ms  -> 7.8 orders/s
22 orders sequentially: 2.8s
cancel via CancelTSStrategyOrderV1: 6/6
```

22 筆/天的量，單執行緒依序送完約 3 秒，不需要非同步。
非同步（`bAsyncOrder=True`）呼叫回得比較快（38–151ms），但 `OnAsyncOrder`
回調沒有進來，會失去拒單碼 —— 所以**正式路徑維持同步送單**。

注意：普通 `SendStockOrder` 在此帳戶一律被拒 `code 999`，只有策略單可用。

---

## 4. 新發現：實盤掃描只看得到一半的訊號（**最大的未解決問題**）

`_twse_batch_scan` 用 `tse_<code>.tw`，而 TWSE MIS **只回答上市公司**。
上櫃與 ETF 會回空陣列，於是無聲地被漏掉。

把回測訊號集照「TWSE 有沒有回答」切開（同一支回測引擎、同一組參數）：

| 市場別 | 訊號佔比 |
|---|---|
| 上市（TWSE 看得到） | 54.0% |
| 上櫃（看不到） | 44.6% |
| ETF（看不到） | 3.3% |

| 可交易範圍 | CAGR | MDD | Sharpe | 筆/日 |
|---|---|---|---|---|
| 全部訊號 | 184.9% | −3.26% | 5.81 | 26.5 |
| 僅上市（實盤目前能做到的） | **70.0%** | −4.31% | 4.21 | 17.4 |

**涵蓋率缺口吃掉約 2.6 倍的 CAGR**，MDD 還略為變差。
（絕對數字與 `STRATEGY_v13.md` 的 203% 不同，因為這裡用的是 `v13_bt.py`
那組含 direction-balance 的設定；重點是**兩列用同一引擎，比值可信**。）

逐年（僅上市 vs 全部）都是同一個形状：2021 180% vs 374%、2024 114% vs 254%、
2026 143% vs 277%。不是某一年特別依賴上櫃，是每一年都少一半。

### 為什麼其他來源不行（本輪已試）
- `SKQuoteLib_GetStockByIndexLONG`（群益自家報價，理應涵蓋兩個市場、而且最快）：
  連三次都回 **0 檔**。需要 `RequestStockList` + message pump 才會有推送，
  先前多次嘗試都卡在這裡。這是**正確解法**，但還要再處理。
- Fugle `stock.snapshot.quotes(market="tpex")`：免費方案 **403 Forbidden**。
- TPEx 官方即時端點：本輪試的 4 個 URL 都是 404，路徑需要再查。
- Yahoo：延遲報價，09:00 不能用。

### 目前的做法
`scan_signals()` 會在 09:00 直接把涵蓋率印出來，不會再無聲漏掉：

```
COVERAGE: 851/1928 codes returned no quote (44%). These are 上櫃/ETF -
the TWSE feed does not carry them. Sample: 1240,1259,1264,...
```

收盤的 `EXECUTION RISK REPORT` 也會固定輸出 `MARKET COVERAGE` 那一行。

---

## 5. 其他已確認的執行面細節

- **智慧單的 ack 寫法會誤導**：`20261026,預約單已送出, 條件單號：27440222, 交易日:20261027`。
  第一個欄位是**當日**日期，取消時回傳也是 `20261026,...刪單已送出`，
  盤中可取消 → 單是當日的，「預約單」只是智慧單主機的標準用語，
  尾端的 `交易日:` 是另一欄訊息。**不是**隔日單。
  （仍需一次 09:00 的實際執行做最終確認。）
- **取消智慧單要用 `CancelTSStrategyOrderV1`**，欄位：
  `nMarket=1`（國內證）、`nTradeKind=11`（當沖）、`nDeleteType=1`（全部）、
  `bstrSmartKey` = ack 裡的條件單號。
  `CancelTSStrategyOrder`（舊版）只支援 6:MIOC / 7:MST / 8:MIT。
  已包成 `gap_fade_auto.cancel_smart_order()`，並在 `monitor_positions()` 結束時
  自動清掉還掛著的條件單，避免隔天出現孤單。
  手動清：`python v13_live_risk.py cancel 27440214 27440215 ...`
- `GetTSSmartStrategyReport` 的正確簽名是
  `(loginID, fullAccount, "TS", 0, "DayTrade", "YYYYMMDD")`，結果由
  `OnTSSmartStrategyReport` 事件回傳。本輪實測：用完整帳號 `913R0438724` 會回
  `SK_SUCCESS` 但**沒有列**回來；用純帳號 `0438724` 會回
  `SK_WARNING_SIGN_TS_SMARTTRADE_RISK_NOITICE_FIRST`（需先簽署證券智慧單風險預告書）。
  送單與刪單都正常，只有查詢回報拿不到 → 盤中自驗證請直接用群益 App。
- `GetBalanceQuery` 在此元件回 `SK_THIS_FUNCTION_NOT_SUPPORTED`。
- **因子面板已過期 68 天**（停在 2026-08-19）。量過的成本：落後 20 天約損失
  3% 邊際、60 天約 11%。上實盤前要先更新 `D:\AI專案\StockAgent\finlab\database`。

---

## 6. 上實盤前的檢查清單

1. 更新因子面板（`python v13_factors.py --refresh`），否則模型邊際會掉。
2. 先跑一次 `python gap_fade_auto.py live`，確認
   `RISK1 opening price visible` 與 `MARKET COVERAGE` 兩行。
3. 在群益 App 確認 09:00 那批智慧單是**當日**、且停損停利條件正確。
4. 決定上櫃涵蓋率怎麼補（SKQuoteLib / Fugle 升級 / TPEx 端點）。
   在此之前，實盤表現應以「僅上市」那一列（CAGR ~70%）預估，不是 203%。
