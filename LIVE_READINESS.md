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

- 已把 `_wait_for_quotes()` 改成探測**掃描器同一個資料源**（現在是富果批量端點，
  見 §7A）。它之前探的是 `SKQuoteLib`，兩者填資料的速度不同，會給出誤導性的答案。
- 現在 `run()` 會把量測基準釘在真正的 09:00:00，並在收盤的
  `EXECUTION RISK REPORT` 輸出：
  - `RISK1 opening price visible: X.XXs after 09:00:00`
  - `RISK1 scan finished: X.XXs after 09:00:00`
- 也可以單獨跑：`python v13_live_risk.py quotes`（建議 08:58 啟動）。
- 已知參考值：掃描 1,928 檔（含 851 檔上櫃）只要 **0.5 秒**（§7A 實測），
  瓶頸只在「開盤價何時可見」。
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

## 4. 實盤掃描只看得到一半的訊號（**已解決，見 §7A**）

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

### 已解決
掃描來源已從 TWSE MIS 換成**富果批次端點** `intraday/quotes?symbol=...`，
一次請求 1,000 檔、全市場 4 次請求、**兩市 100% 涵蓋**、免費金鑰。
實測 `python gap_fade_auto.py scan`：

```
scan#1 via Fugle (TWSE+TPEx): rows=1928 has_open=1897 has_prevclose=1928
        by_exchange={'TWSE': 1077, 'TPEx': 851}  0.52s
```

TWSE MIS 保留為退路。完整來源比較與 SKCOM 的實測結論見 §7A。
⚠️ 「僅上市 CAGR 70.0%」那一列現在只是**歷史對照**，不再是實盤預期；
203% 的阻礙已排除，但**仍需在開盤日實測 RISK1** 才算真的ready。

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
- 因子面板**已更新到 2026-10-22**（見第 7 節）。每日開盤前需 `--refresh`；
  面板落後超過 10 天時程式自動改餵 NaN，與回測口徑一致。

---

## 6. 上實盤前的檢查清單

1. 每日開盤前 `python v13_factors.py --refresh`（已向 finlab VIP 抓最新日 K，
   面板停在 2026-10-22）。面板過期時程式自動改餵 NaN（與回測一致）並印警告。
2. **開盤日 08:58 先跑 `python gap_fade_auto.py scan`**，確認兩件事：
   `by_exchange` 裡 TPEx 有 851 檔，以及距 09:00:00 的實際延遲（RISK1）。
   這是上實盤前唯一還沒量到的關鍵數字。
3. 再跑一次 `python gap_fade_auto.py live`，確認收盤報告的
   `RISK1 opening price visible` 與 `MARKET COVERAGE` 兩行。
4. 在群益 App 確認 09:00 那批智慧單是**當日**、且停損停利條件正確。
5. 上櫃涵蓋率已解決（§7A），203% 不再是「只能下單一半市場」的數字；
   但 RISK1 未量測前，仍不建議直接全倉。

---

## 7. 因子面板：已修好，現在真的能更新（2026-10-26 更正）

先前寫「不續約就無法更新」是**我的判斷錯誤**：我沒呼叫 `finlab.login()` 就看
`is_vip()`。實際情況：

- 這個帳號**是 VIP**。`finlab.login(token)` 在 2.2.6 是 legacy 路徑，只設
  `FINLAB_API_TOKEN` 環境變數、不會設定 `_default_context._role`，所以
  `is_vip()` / `get_role()` 永遠回 `False`/`None` —— **這兩個指標在 legacy
  登入下不可信**，要用實際下載結果判斷。
- `D.get("price:close", start=..., end=...)` 實測回 **2026-08-10 → 2026-10-22、
  2,789 個代碼**（含上櫃+ETF）。`search()` 表格裡的 `free_until=2023-12-31`
  是免費方案的範圍，不是這個帳號的上限。
- 注意 dataset 名稱：`price:vol` **不存在**，成交量是 `price:成交股數`
  （另有 `price:成交金額` 可直接當成交額用）。

### 7.1 已改成自有價格庫 + 可重覆更新
`v13_factors.py` 現在不再直接讀 finlab 的 pkl，而是：

```
python v13_factors.py --seed      # 一次性把 finlab 1.x pkl 複製到 D:\gapfade_data
python v13_factors.py --refresh   # 向 finlab VIP 抓「最後一天之後」→ append → 重建因子
```

`refresh_prices()` 會把**最後 10 天重新抓並覆寫**，不是只 append。原因：
本地副本是 2026-08-19 **16:23** 快照，盤後量還沒結算，那天 45 檔的量被低估
（2330 少 1.77%、2383 少 5.23%）。重抓一個 window 會自我修正。

實測驗證（新抓的 vs 舊 pkl，2026-08-10..08-19 重疊區間）：

| dataset | 重疊 | 數值不一致 | NaN 不一致 |
|---|---|---|---|
| close / open / high / low | 8 日 × 2,771 檔 | **0** | **0** |
| vol（成交股數） | 8 日 × 2,771 檔 | **45**（全部在 2026-08-19，新值 ≥ 舊值） | **0** |

那 45 筆的比率（2330 1.0177、2383 1.0523）與我獨立用**富果日 K** 比對出來的數字
**完全一致** → 三方（finlab VIP / 富果 / 舊本地副本）交叉驗證，新資料是正確的一方。

### 7.2 結果
```
[refresh] panel ends 2026-10-22 (4794 rows x 2789 cols)
Factor panel as-of 2026-10-22 (lag 4d)   ← 不再觸發 STALE，不再餵 NaN
```
面板現在涵蓋 **2,789 檔**（含上櫃、ETF），`valid_stocks.txt` 1,927/1,928、
回測宇宙 2,242/2,242 全覆蓋。

⚠️ 副作用：我呼叫 `D.get()` 時 finlab 2.2.6 **把使用者自己的
`D:\AI專案\StockAgent\finlab\database\price_*.pkl` 也更新到 2026-10-22 /
2,789 欄**（`save_to_storage=False` 這個參數已被標_deprecated_、實際仍會寫檔）。
對 StockAgent 專案是「資料變新」，但**形狀從 (4751, 2771) 變成 (4794, 2789)**，
若有程式假設舊形狀需要檢查。

### 7.3 面板值多少（保留先前實測，供決策參考）
正式引擎 `v13_dstune.run(dsfac=1.0)`，兩臂只差面板欄位：

| | CAGR | MDD | Sharpe | 2023-25 | 觸板停損 |
|---|---|---|---|---|---|
| 面板可用 | 1265.5% | −3.21% | 9.36 | 1692.1% | 9.4% |
| 面板全 NaN | 446.2% | −4.05% | 7.46 | 259.7% | 12.1% |

⚠️ 兩臂都用 `prod_models` 跑全樣本 → 偏 in-sample，絕對值不能當績效
（walk-forward 的正式數字是 203%）。但**2023-25 從 1692% 掉到 260%** 這個
相對幅度可信：面板不是可有可無的。
機制：面板的工作是**擋壞單**。SHORT 缺面板 → 變保守（少 29% 筆數，擋掉的
都是 +0.037% 邊際單，每筆品質反而升）；LONG 缺面板 → 變寬鬆，放進 2,380 筆
實際 −1.187% 的單，每筆 +1.35%→+0.82%。

---

## 7A. 上櫃涵蓋率：已解決（2026-10-26 找到免費批量來源並整合）

### 問題（保留實測依據）
用富果官方代碼清單分類（TWSE 1,532 / TPEx 1,775，無重疊），模型選出的
124,068 筆訊號：

| 市場 | 筆數 | 佔比 | 勝率 | 每筆淨 PnL |
|---|---|---|---|---|
| 上市 | 68,511 | 55.2% | 53.2% | +0.22% |
| **上櫃** | **52,727** | **42.5%** | **54.4%** | **+0.39%** |
| 其他/ETF | 2,830 | 2.3% | 54.0% | +0.28% |

上櫃占 42.5% 的訊號、每筆 edge 是上市的 1.8 倍，逐年穩定 40–48%。
舊掃描走 TWSE MIS `getStockInfo.jsp` 且**只送 `tse_` 前綴**，所以那行
`COVERAGE: 851/1928 無報價` 的 851 檔正好就是宇宙裡的 851 檔上櫃 ——
這是 train/serve 不一致，203% 在修好前不能當實盤預期。

### 解法：富果批次端點（SDK 沒包，但 HTTP 有）
```
GET https://api.fugle.tw/marketdata/v1.0/stock/intraday/quotes?symbol=A,B,C
```
注意是**複數** `intraday/quotes` + `symbol=` 逗號清單。`fugle_marketdata`
SDK 只包了單檔 `intraday/quote/{symbol}`，所以之前被誤判成「只能逐檔」。

實測（2026-10-26，免費金鑰）：

| 項目 | 實測值 |
|---|---|
| 單次請求上限 | **1,000 檔**（1,000 檔仍 200 OK；空清單才 400） |
| 全市場 3,307 檔 | **4 次請求 / 1.41–1.91 秒** |
| 涵蓋率 | **TPEx 1,775/1,775、TWSE 1,532/1,532（100%）** |
| 重覆三次 | 3,307 / 3,307 / 3,307，1.48–1.91s，**沒有 429** |
| 欄位 | `openPrice` `previousClose` `referencePrice` `high/low/close` `lastPrice` `bids/asks` `total.tradeVolume/tradeValue/tradeVolumeAtAsk/tradeVolumeAtBid` |

`tradeVolumeAtAsk/Bid` 也在裡面 —— 你之前問的「賣量佔比能不能當下知道」，
這個端點就能算，不用等收盤。

### 已整合進 `gap_fade_auto.py`
- `_fugle_batch_scan()`：回傳與 TWSE MIS `msgArray` 同形狀的列（`c/n/o/y/v`），
  所以 `scan_signals` 的過濾/Gap 邏輯完全不用改。
- `_batch_scan()`：優先用富果（兩市），成功率 < 60% 或異常才退回 TWSE MIS。
- 覆蓋率檢查改成會**回報 TPEx 筆數**，缺代號時直接警告。
- `_wait_for_quotes()` 改探同一個來源（之前探 SKQuoteLib，跟實際掃描來源不同）。
- 新增 `python gap_fade_auto.py scan`：只測掃描速度與涵蓋率，**不下單**。

實測（今天 10-26 無行情，資料停在 10-22）：
```
Universe: 1928 codes
scan#1 via Fugle (TWSE+TPEx): rows=1928 has_open=1897 has_prevclose=1928
        by_exchange={'TWSE': 1077, 'TPEx': 851}  0.52s
scan#2 ... 0.46s      scan#3 ... 0.50s
```
**851 檔上櫃全部補齊，策略宇宙 1,928 檔 0.5 秒掃完。**

### 順帶解决的過濾器（同一個金鑰）
`GET .../intraday/ticker/{symbol}` 對**兩市**都回：
`isDisposition`（處置）、`canDayTrade` / `canBuyDayTrade`（當沖可否）、
`canBelowFlatMarginShortSell` / `canBelowFlatSBLShortSell`（空單）、
`limitUpPrice` / `limitDownPrice`、`boardLot`（一張股數）、`securityStatus`。
這是逐檔端點（0.22s/檔），不適合 09:00 掃，但適合**盤前 08:00 一次性**
把 3,300 檔的過濾表建好（5 並發約 2.5 分鐘）。上櫃的處置/當沖過濾因此
也有官方來源可用，不再只能靠 TWSE 公告。

### 免費方案的實際上限（全部實測，避免再走回頭路）
| 來源 | 結果 |
|---|---|
| 富果 WebSocket `stock/streaming` | auth 成功、`channel:"quotes"` 可訂閱上櫃，但**免費方案上限 5 檔**（第 6 檔 `Subscription limit exceeded`）→ 無法全市場 |
| 富果 `snapshot/quotes|movers|actives/{market}` | **403**（方案無權限，含所有 market 變體）→ 這是唯一能一次拿全市場的批量端點，值得打給富果問升級 |
| 富果逐檔 REST | 0.21–0.35s/檔；10 並發只剩 58/120 成功，**20/40 並發全 429** |
| Yahoo `v7/finance/quote` | 部分上櫃被**靜態省略**（1240.TW 不見），且非即時 |
| TPEx 官網 `openapi/v1/...` | 全部路徑都回同一份 SPA HTML，**不是 API**；`emis.tpex.org.tw` DNS 不存在 |
| 群益 SKCOM | 見下 |

### ⚠️ 更正：TWSE MIS 其實**看得到上櫃**（`otc_` 前綴）
`twjackysu/TWSEMCPServer` 的即時工具讓我看見漏掉的一件事：MIS 的 `getStockInfo.jsp`
用 **`otc_<code>.tw`** 就回上櫃報價，`tse_` 只回上市。舊退路只送 `tse_`，
所以上櫃全軍覆沒 —— 那不是 MIS 的限制，是我們前綴用錯。

實測（2026-10-26，免金鑰）：

| 前綴 | 結果 |
|---|---|
| `otc_1240.tw` | **茂生農經 o=54.00 y=54.00 z=53.70 u=59.40 w=48.60**，與富果完全一致 |
| 單次上限 | **100 檔**（200 檔回空） |
| 全部 1,775 檔上櫃 | 只回 **1,403 檔（79%）**，缺 **372 檔** |
| 缺的 372 檔 | 全部 `type=EQUITY` 且富果有真實行情：1260 富味鄉、1269 乾杯、1293 利統、1343、1480、1594、2071… **MIS 真的不載**，不是批次截斷（單檔測也回空） |
| 兩市合計 | 34 次請求 / **7.7 秒**（15 並發） |

已把 `otc_` 重試加進退路 `_twse_batch_scan()`（先 `tse_`，缺的再用 `otc_` 補）。
實測退路現在：**TPEx 850/851、has_open=1896、3.66 秒**（之前是 0 檔上櫃）。

⚠️ 那 372 檔缺的基本都在策略宇宙之外（被 10M 成交額與 30 元價格過濾掉），
所以**退路對我們的 1,928 檔宇宙涵蓋 850/851**，實務可用；
但 MIS 仍不是「完整」來源，富果維持為主線（0.5 秒、100%）。

### 關於 `twjackysu/TWSEMCPServer`（2026-10-26 評估）
MIT、180 星、維護中。它是 **MCP Server**，定位是給 LLM 對話用：
回傳**格式化文字表格**、有 `TWSE_MAX_RESPONSE_BYTES` 上限與 `DISPLAY_LIMIT` 預設 20 筆、
內建 circuit breaker 與 60 秒快取。即時只有 MIS 那一條（見上），
**其餘全部是盤後/日終**（TWSE OpenAPI、TPEx afterTrading、TAIFEX、MOPS）。
→ 不適合 09:00 全市場掃描；但它的**端點清單**很有價值，值得直接抄自己抓。

已實測這些官方端點**免 token、可直連、回 JSON**：

| 端點 | 內容 | 對策略的用途 |
|---|---|---|
| `openapi.twse.com.tw/v1/exchangeReport/TWTBAU1` | **暫停先賣後買當日沖銷預告**（Code/Name/StartDate/EndDate/Reason） | 當沖過濾，比現在只排 2330/2317 精準 |
| `openapi.twse.com.tw/v1/exchangeReport/MI_INDEX` | 盤後每日行情 | 面板備源 |
| `www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O` | **上櫃公司全清單**（938KB，Date=1151026） | 上櫃宇宙/公司資料 |

### 群益 SKCOM 報價：本輪實測結論（記錄下來免得重試）
- `SKDLLPython`：`ManageServerConnection(id, 0, 1)`（target **1 = 國內行情**）
  **2.2 秒**就把報價伺服器連起來，`GetStockByStockNo(0,"2330")` 回真實資料
  （前收 2420、漲停 2660、跌停 2180、`nYQty`、`nDayTrade`、`nTradingDay=20261022`）。
- 但**上櫃訂閱不起來**：`SKQuoteLib_RequestStocks("1240")` →
  `SK_SUBJECT_COMMODITY_IS_NOT_EXIST`；`LoadCommodity(1)` 回 SK_SUCCESS 也沒用。
  這個 wrapper **沒有帶市場碼的訂閱**（DLL 只匯出 `RequestStocks`/
  `GetStockByStockNo`/`RequestStockList`，沒有 `RequestStocksWithMarketNo`、
  也沒有 `GetStockByIndexLONG`）。
- COM（comtypes）那條路：`SKQuoteLib_EnterMonitorLONG()` 回 SK_SUCCESS，
  但 `OnConnection` 在 40 秒內從未派發（comtypes 事件需要訊息泵），
  之後 `RequestStockList` 仍 `SK_ERROR_QUOTE_CONNECT_FIRST`。
- 訂閱另有**單頁上限**：200 檔一批 → `SK_SUBJECT_QUOTE_LIMIT_EXCEED_IN_ONE_PAGE`。

→ **上櫃掃描不走 SKCOM**，改走富果批量。SKCOM 仍只負責下單（本來就用得好好的）。
⚠️ 今天休市，以上都是「涵蓋率與速度」的實測；**09:00:00 實際延遲（RISK1）
仍需在開盤日用 `gap_fade_auto.py scan` 實測一次**。

## 7B. 開盤前先把不用查的股票排掉（2026-10-26）

### 能砍多少（以 2026-10-22 的真實資料算漏斗）
```
3,307  全市場
2,358  有 T-1 收盤資料
1,410  前收 >= 30 元
  873  T-1 成交額 >= 1000 萬
  866  非處置股            <- 開盤只需要查這些，減 73.8%
```
只用成交額這一條（開盤前一定拿得到）：3,307 → **1,134**；從 `valid_stocks.txt`
的 1,928 → **904**。

### 不會漏單（已驗證）
拿 124,596 筆模型實際下單的歷史訊號比對：**98.6% 本來就通過價格+成交額過濾**。
被誤排的 1,725 筆（1.4%）**全部是 `prev_close < 30`**，而實盤 `min_price=30`
本來就把它們排掉 → 前置過濾等於零行為改變。
端到端實測：開/關前置過濾，`scan_signals()` 產出的訊號集合**逐筆完全相同**（63 筆）。

### 順帶修掉一個既有的 train/serve bug（重要）
`_load_reference_panels()` 原本**只在 `_score_signals()` 裡被呼叫**，也就是
**掃描之後**。但 `scan_signals()` 的成交額過濾要用 `self._t1_turnover`，而
`_t1_turnover` 的類別預設值是空 dict → 實盤 09:00 永遠拿到空字典，
成交額過濾**全部走 `volume x open` 的代理值**，從沒用過回測那套真實 T-1 成交額。
已把載入移到 `scan_signals()` 開頭，並讓它冪等（`_score_signals` 再呼叫會直接回）。

### 速度（實測）
| | 查詢數 | 請求數 | 掃描時間 |
|---|---|---|---|
| 改之前 | 1,928 | 2 | 0.50s |
| 改之後 | **912** | **1** | **0.30s** |

⚠️ 誠實說：**速度不是這裡的重點**（0.5s 本來就夠快）。真正的價值是
(1) 請求數減半、降低觸限風險，(2) 查詢清單與模型實際可交易集合一致，
(3) 處置股過濾真的被套用（這次排掉 16 檔）。
**瓶頸在停損停利監控**：22 檔逐檔取價一輪 **11.2 秒**，改批次 **0.47 秒（24 倍）**，
那才是該修的地方，尚未修。

### 試過並否決：只查「最近出現過訊號」的股票
| 回看窗口 | 需查股票數 | 覆蓋的歷史下單 |
|---|---|---|
| 30 天 | 737 | **54.9%** ← 太會漏 |
| 90 天 | 1,110 | 78.1% |
| 365 天 | 1,441 | 89.5% |
| 730 天 | 1,636 | 94.2% |

訊號在 1,636 檔之間非常分散，縮到 30 天會漏掉近一半的單。**不划算，不做。**

### ⚠️ 新發現的風險：處置面板可能無聲失效
`disposal_panel_full.pkl` 最後一筆是 **2026-10-21**。而 `get_restricted_stocks()`
用的是 `dp["date"] == date.today()` **完全比對**：面板一旦沒更新到今天，
`hit` 是空 → 直接掉回 Method 1（finlab，**只含上市**）。
也就是**處置過濾會無聲退化成只排上市**，而且不會報錯。
上實盤前要嘛把面板接進每日 `--refresh`，要嘛改用官方
`openapi.twse.com.tw/v1/exchangeReport/TWTBAU1`（免 token、即時可直連，已驗證）。

## 8. 本輪另外修掉的兩個執行面問題

### 8.1 `__init__` 在建立 logger 之前就讀淨值狀態
`_load_equity_state()` 在 `self.log` 建立**之前**被呼叫，只有在
`equity_state.json` **已存在**時才會走到那行 log → `AttributeError: ... no attribute 'log'`。
之前能跑是因為檔案不存在；是某次成功執行由 `_save_equity_state()` 產生了它，
下一次就必崩。已把 logger 設定移到 `_load_equity_state()` 之前。

### 8.2 `equity_state.json` 的模擬殘留會立刻觸發回撤剎車
實測檔內 `peak_equity = 4,660,089`（450 萬 + 3.57%），是**模擬**跑出來的。
實盤從 450 萬開始會被當成已回撤 **−3.4%**，直接掉進 `>2.5% → 縮至 15%` 那一檔，
等於第一天就只敢下 15% 部位。已刪除該檔，讓實盤從 450 萬乾淨起步。
**上實盤前請確認這個檔不存在**（或內容就是 4,500,000）。

---

## 9. 今天的市場其實沒有資料（2026-10-26 15:00 實測）
三個獨立來源一致回報**最後一個交易日是 2026-10-22**，10-23 與 10-26 皆無資料：

| 來源 | 最後一筆 | 2330 當日 OHLC |
|---|---|---|
| TWSE MIS | `d=20261022` | 2435 / 2435 / 2385 / 2385 |
| Yahoo `2330.TW` | 10-22（10-23 是 volume=0 的佔位列） | 2435 / 2435 / 2385 / 2385 |
| 富果 `intraday.quote` | `"date": "2026-10-22"` | 2435 / 2435 / 2385 / 2385 |

所以 `python gap_fade_auto.py now` 今天掃到的是 **2026-10-22 的 K 線**，
不是今天的。程式行為沒有錯（喂什麼算什麼），但**別把它當成今天的訊號**；
`now` 印的 `Market gap` 與訊號日期要一起看。
`scan` 模式只測速度與涵蓋率、不產訊號，因此不受這個影響（它印的 `has_open`
是 10-22 的開盤價，正好用來驗證「兩個市場都抓得到」）。
