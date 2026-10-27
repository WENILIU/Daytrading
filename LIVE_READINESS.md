# Gap Fade v13 — 上實盤前的待驗證清單

日期：2026-10-26。帳號：群益北高雄 `0438724`（SKCOM 自動偵測 `913R0438724`）。
本檔記錄「回測看不出來、只有接上券商才會發現」的問題，以及已量到的數字。

---

## 0. 本輪修掉的四個真實缺陷

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

### 0.4 回報主機從來沒有連線（影響 live 不只 paper）
`connect()` 註冊了 `ISKReplyLibEvents` 事件，但**從未呼叫 `SKReplyLib_ConnectByID`**——
那是另一條要單獨開啟的連線（官方範例 `PythonExampleV2/Reply/Reply.py:496`）。
後果：所有走回報通道的东西都是盲的——成交回報、智慧單狀態、資產報表。
`GetRealBalanceReport` 會回 `SK_SUCCESS` 然後什麼都不回來，看起來像成功、其實永遠沒資料。

已修：登入後連線回報主機，並補上 `OnNewData` / `OnData` / `OnComplete` 三個通道
（不同報表型別走的通道不一樣，先都收下來）。實測 `Reply host: SK_SUCCESS`。

尚未結：盤後（23:00）實測仍然收不到資產資料，`GetRealBalanceReport` 在裸物件上甚至回
`SK_ERROR_INITIALIZE_FAIL`。這不阻擋三項可行性判定，第一次盤中 `paper` 實跑會把它結算掉。

## 1. 風險一：開盤報價可見延遲 — **策略池已量到（2026-10-27 盤後）**

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

### 2026-10-26 更新：不用等開盤就有一部分答案了

富果的 quote 物件有 **`openTime`**（微秒 epoch），就是**開盤價實際成交的時間**。
以 2026-10-22（最後一個交易日）實測：

| 欄位 | 值 | 換算 |
|---|---|---|
| `openTime` / `highTime`（2330） | `1792630808980736` | **2026-10-22 09:00:08.980736** |
| `lowTime` | `1792645974626148` | 13:12:54.6 |
| `closeTime` / `lastTrade` | `1792647000000000` | 13:30:00.0 |

也就是说：**全市場流動性最好的那檔，開盤價也不是 09:00:00.000 就能成交** —
2330 当天的第一筆落在 09:00:08.98。回測把開盤價當成 09:00:00 可成交，
這 9 秒就是 RISK1 的下限，跟我們的網路速度無關。

⚠️ 誠實標註：`openTime` 是富果給的欄位。**它是交易所官方的開盤成交時間，
還是富果自己收到第一筆的時間，我沒有獨立驗證過。**用它算出的 p50/p90
要當成「上界估計」，不是交易所的正式數字。

### 2026-10-27 盤後：把 RISK1 量在「策略真的會交易的那批股票」上

全市場的分布對決策沒有意義（一半的股票在 09:00:30 還沒有第一筆，但策略根本
只碰 T-1 成交額 ≥ 2,250 萬那幾檔）。`risk1_measure.py` 用今天的真實盤後資料，
把同一個欄位按人群拆開量：

| 人群 | n | p50 | p90 | p99 | max | 09:00:30 前可見 |
|---|---|---|---|---|---|---|
| 全市場（feed 有回的所有碼） | 1,904 | 15.2s | 2,085s | 11,058s | 16,200s | — |
| 上市 TWSE | 1,075 | 13.3s | 1,337s | 4,844s | 15,191s | 74.0% |
| 上櫃 TPEx | 829 | 19.5s | 3,331s | 15,017s | 16,200s | 52.8% |
| **策略合格池（T-1 成交額 ≥ 2,250 萬）** | **186** | **10.1s** | **17.9s** | **19.9s** | **23.5s** | **100%** |
| 今天實際成交的 8 張單 | 8 | 6.3s | 19.3s | 19.3s | 19.3s | 100% |

交叉驗證：同一個欄位今天給 2330 = **8.68s**，跟 2026-10-22 盤中實測的
**8.98s** 一致 → 這個欄位是可重覆的，不是雜訊。

**這條就是 RISK1 的答案，而且比原本擔心的好，也比原本擔心的差：**

- 好的一面：策略交易的股票**全部**在 09:00:24 之前就有開盤價可讀，
  而且掃描只要 0.4 秒。所以「完全看不到價格、錯過整個開盤」不會發生。
- 壞的一面：**中位也有 10 秒**，不是 0 秒。加上下單往返，實際動作時間是
  開盤後 **11–25 秒**。使用者觀察的 4960（09:00:18 開 30.3 → 滑到 28.25）
  正好落在這個區間裡，所以那不是例外，是常態。

### 1.1 延遲 10–25 秒進場到底差多少 —— 用本地 1 分 K 量成實數（2026 全年）

`entry_lag_measure.py`。本地 1 分 K 庫的 `*_2026-01.json` 其實裝的是
**2026-01-02 ~ 2026-10-16、190 個交易日**，979 檔。把策略 2026 年的訊號放上去，
用**同一個出場引擎、同一條 1 分 K 路徑**跑三種進場，差異就純粹是進場時間：

| 進場假設 | 每筆 PnL%（含成本） |
|---|---|
| A 開盤價（回測的假設） | +0.320 |
| B 09:00 那根 K 的收盤（≈ +10–25 秒，就是 RISK1 說我們能做到的） | **+0.281** |
| C 09:01 那根的收盤（≈ +60 秒） | +0.219 |

上表是**策略真的會下注的那批**（每天 pred 排名前 10、190 天、1,879 筆）。
對照組：回測用日內 OHLC 算同一批是 +0.382%。

**三個結論，都是實測：**

1. **延遲吃掉 0.039pp/筆 = 邊際的 10%。** 從 +0.382% → +0.281%（含下面第 2 點的
   修正後是保留 74%）。**策略在延遲下還活著。**
2. **回測用日內 OHLC 判斷停損停利的順序，本身偏樂觀 0.05–0.06pp/筆。**
   同為開盤進場，日 OHLC 版 +0.382%、1 分 K 版 +0.320%。兩者相關 0.981、
   中位差 0.000 —— 模擬器是對的，差的是「一根 K 內先碰到哪邊」這件事日線看不到。
   另外停損若發生在鎖死漲停的那根，成交價是漲停不是停損價（見 §11.1），也計在這裡。
3. **「開盤後一直下滑，所以延遲對放空有利」這個直覺是錯的。** 11,157 筆放空統計：
   延遲後平均**不利 +0.098%**，只有 34.7% 的情況比較便宜。4960 那種案例確實存在，
   但不是平均行為。做多更糟（+0.331%）。

**注意別看錯對象**：如果把「所有通過 `pred_q>=0.20` 的訊號」平均（11,562 筆），
延遲會把邊際從 +0.201% 打到 +0.059%，看起來像要命。**但策略從不交易那批平均，
它只交易每天排最前面那幾筆** —— 在那批上延遲的傷害是 10%，不是 71%。
這個差別就是「能不能上實盤」的分界。

**仍未驗證**：這是 2026 一年、等權重、不含倉位規模的數字；1 分 K 只有這一年有。
`paper` 模式的 `entry slippability` gate 要在盤中實跑，才能把「+10–25 秒之後
市場實際給什麼價」從 1 分 K 近似換成我們自己的成交價。

**還沒有的一半**：「我們自己的程序在幾秒時真的讀到」。那需要 09:00 當下跑
（`scan` 模式會印）。今晚這次跑在盤後，那一行現在會誠實寫
`not measured (this run did not straddle 09:00)`，不會再印 51,356 秒這種無意義的數字。

**對策略設計的含義（這是目前唯一真正未決的執行風險）**：回測以開盤價成交，
實盤要在 +10s（中位）才可能下單。SHORT 在開盤後通常往下走 → 延遲對 SHORT
**有利**；LONG 相反 → **不利**。`paper` 模式的 `entry slippability` 那條 gate
就是為了把這個差距量成實數（門檻：不利滑價 p90 < 0.5%）。

### `scan` 模式已改成直接量 RISK1（不用人工掐時間）

`python gap_fade_auto.py scan` 現在會：

1. 每 2 秒輪詢全市場，**一路到 09:01:00**（非開盤時段自動縮成 6 秒，不會卡住）。
2. 印每次輪詢的 `feed_today` / `has_open` / `has_openTime` / 兩市分佈。
3. 最後用所有 `openTime` 算 **p50 / p90 / p99 / max（距 09:00:00 的秒數）**，
   以及「我們第一次能读到開盤價」是開盤後幾秒。
4. 結果寫進 `trading_logs/`（走 logger，不是 `print`），所以
   `RISK1 exchange opening-print time` 這行會變成**永久的完成記號**，
   08:55 的自動提醒就是查這行決定要不要再提醒。

今天（非交易日）實跑：

```
poll#1 22:04:17 via Fugle (TWSE+TPEx): rows=1928 feed_today=0 has_open=1897
       has_openTime=1897 by_exchange={'TWSE': 1077, 'TPEx': 851} 0.49s
FEED IS NOT ON 2026-10-26 - the exchange has no session for today.
RISK1: not measured (no live session today).
```

`has_openTime=1897/1928` → 到真實開盤日，這個分佈會有約 **1,900 個樣本**。
`feed_today=0` 時**拒絕輸出數字**：休市日 feed 回的是上一個交易日，
`openTime` 會變成負幾天，印出來會是瞎猜。

### 順便把「為什麼都沒資料」查清楚了

不是資料源壞掉。finlab 的交易日曆（`data.get_calendar().is_session(d)`）：

| 日期 | 星期 | 是交易日 |
|---|---|---|
| 2026-10-19 ~ 10-22 | Mon–Thu | ✅ |
| 2026-10-23 | Fri | ❌ |
| 2026-10-24 / 10-25 | Sat / Sun | ❌ |
| **2026-10-26** | **Mon** | **❌** |
| **2026-10-27** | **Tue** | **← `next_session()` 給這個** |

所以四家資料源都停在 10/22 是**正確的**，10/23 起交易所連休四天。
下一個可量 RISK1 的日子是 **2026-10-27**，已排 08:55 的自動提醒
（`is_session(today)` 為 False 就保持安靜；日誌裡已有 RISK1 結果也不再提醒）。

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

1. **因子面板時效（每天都要看）**：先跑 `python v13_factors.py --refresh`
   （向 finlab VIP 抓最新日 K）。啟動日誌裡必須看到這一行且 lag 為 0 或 1：
   `Factor panel as-of <日期> (lag 0d), turnover keys <N>`。
   若出現 `FACTOR PANEL STALE by Nd (> 10d). Feeding NaN factors...`，代表模型改餵 NaN
   （與回測對缺日期的處理一致），**當天不要上實盤**：同一引擎實測把面板欄位拿掉，
   2023-25 段從 1692% 掉到 260%。面板價值的量化：停 20 天 ≈ 損失 3% 每筆邊際，
   停 60 天 ≈ 11%。本輪就發生過面板停在 2026-08-19（落後 68 天）≈ 11% 邊際。
   注意 `is_vip()=False` 是 legacy token 登入下的假訊號，不代表沒有權限，不要因此跳過 refresh。
2. **開盤日 08:58 跑 `python gap_fade_auto.py scan`**（09:00 前啟動即可，
   它會自己輪詢到 09:01:00）。要確認兩件事：
   `by_exchange` 裡 TPEx 有 851 檔，以及 `RISK1 exchange opening-print time`
   那組 p50/p90/p99。這是上實盤前**唯一**還沒量到的關鍵數字。
   已排 08:55 自動提醒（見 §1 結尾）。
3. **先跑 `python gap_fade_auto.py paper`（不是 live）**：真實帳戶、真實智慧單，但掛在不可能成交的價格，
   零風險。收盤會印 `LIVE FEASIBILITY REPORT` 與三項 PASS/FAIL（詳見 §11）。
   三項全 PASS 才升級到 `live`；届时再確認收盤報告的 `RISK1 opening price visible`
   與 `MARKET COVERAGE` 兩行。
4. 在群益 App 確認 09:00 那批智慧單是**當日**、且停損停利條件正確。
5. 處置/當沖過濾**不需要手動步驟**：`get_restricted_stocks()` 開盤掃描時直接
   向 finlab 取（§7C）。日誌一定要看到
   `Restricted from finlab ... 14 處置 (both markets)` 這行；若看到
   `came from the exchange announcement pages` 或 `DISPOSAL PANEL STALE`
   代表退化了，當天不要上實盤。
6. **下單筆數安全網（新增）**：策略本身沒有筆數上限，筆數由零融資的現金額度決定
   （實測 34 個候選/日 → 成交 9.4 筆/日，p99 = 22、max = 26，見 `count_cap.py`）。
   `Config.max_orders_per_day = 30` 只是作業安全網，**不是績效規則**。
   收盤報告看 `Orders placed: N`：正常 N ≈ 9，接近 20 就已经是歷史高位區間。
   若出現 `ORDER CAP HIT: <k> lower-ranked signals not sent (cap 30)`，代表那天超出歷史
   範圍（候選數與可成交數都超過實測上限），先查當天的候選數與曝險，**不要直接調高上限**——
   30 是照 450 萬的資金額度算出來的，調高等於假設資金也變大。
7. 上櫃涵蓋率已解決（§7A），203% 不再是「只能下單一半市場」的數字；
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

> **2026-10-26 更新：這條盤前建表已不需要。** 處置/暫停先賣後買當沖改由
> finlab `disposal_information` + `day_trade_short_suspension` 直接取（兩市、
> 08:10 更新、熱路徑 0.03s），實測還是超集。見 §7C。`limitUpPrice` /
> `boardLot` 那幾個欄位仍然只有這個端點有，但目前回測用的是自有價格庫，
> 不需要它。

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
那才是該修的地方。→ **已修，見 §7C。**

### 試過並否決：只查「最近出現過訊號」的股票
| 回看窗口 | 需查股票數 | 覆蓋的歷史下單 |
|---|---|---|
| 30 天 | 737 | **54.9%** ← 太會漏 |
| 90 天 | 1,110 | 78.1% |
| 365 天 | 1,441 | 89.5% |
| 730 天 | 1,636 | 94.2% |

訊號在 1,636 檔之間非常分散，縮到 30 天會漏掉近一半的單。**不划算，不做。**

### ~~⚠️ 新發現的風險：處置面板可能無聲失效~~ → 已修，見 §7C
`disposal_panel_full.pkl` 最後一筆是 **2026-10-21**。而 `get_restricted_stocks()`
用的是 `dp["date"] == date.today()` **完全比對**：面板一旦沒更新到今天，
`hit` 是空 → 直接掉回 Method 1（finlab `etl:disposal_stock_filter`，**只含上市**）。
也就是**處置過濾會無聲退化成只排上市**，而且不會報錯。

## 7C. 本輪修掉的兩件事：監控批次取價 + 處置過濾改用 finlab（2026-10-26）

### ① 停損停利監控：逐檔取價 → 一次批次（實測 **14–200 倍**）

原本 `monitor_positions()`、`_monitor_now()`、`_force_close_all()`、
`_force_close_all_sim()`、`get_price()` 五處都是**逐檔**呼叫
`fugle_marketdata.RestClient(...).stock.intraday.quote(symbol=...)`，
而且每檔都新建一個 client。22 個部位 = 一輪 22 次 HTTPS 往返。

新增 `GapFadeAutoTrader._fetch_prices(codes)`：用 §7A 那個批次端點
（`intraday/quotes?symbol=a,b,c`）一次取回 `{symbol: lastPrice}`，
並用 `_fugle_session()` 保留同一個 `requests.Session` 重用 TLS 連線。
五處呼叫全部換掉，檔案內已**沒有任何單檔取價**。

實測（2026-10-26，22 檔真實部位簿）：

| 方式 | 22 檔一輪 | 備註 |
|---|---|---|
| 逐檔（改之前） | **4.86s**（同日另一次量到 11.23s） | 網路變因大，兩個數字都是真的 |
| 批次，第一次 | 0.34s | 含建立 TLS |
| 批次，之後每輪 | **0.024–0.16s**（中位 0.119s） | 監控迴圈會重用連線 |
| 批次 100 檔 | 0.051s | 96/100 有價，其餘是停用/無成交 |

重點不是「快幾倍」，而是**監控盲區**：22 檔時原本兩次檢查之間有 5–11 秒
完全不看價格，而跳空股衝過停損只要幾秒。現在盲區 < 0.2 秒。
`_mark_exit()` 的判斷邏輯完全沒動，只換掉取價方式。

### ② 處置/當沖過濾：主線改 finlab，退路一律大聲報警

**為什麼用 finlab**（2026-10-26 實測比較）：

| 來源 | 今日處置數 | 含上櫃 | 對照結果 |
|---|---|---|---|
| `disposal_information`（finlab） | **14** | ✅ 2,255 筆處置記錄中 624 檔是上櫃 | 基準 |
| 交易所公告頁（TWSE punish + TPEx disposal） | 9 | ✅ | **少 5 檔** |
| `disposal_panel_full.pkl` | 0（面板停在 10/21） | ✅ | 當日無資料 |
| `etl:disposal_stock_filter`（舊程式用的） | — | ❌ 只含上市 | — |

那 5 檔（2221/3055/3230/3597/4979）查證都是 **10/19～10/27 的有效處置**，
公告頁因為「公布日期」落在查詢視窗外而漏掉。反方向 **0 檔** 只出現在公告頁。
所以 finlab 是嚴格超集。
另外 `day_trade_short_suspension`（暫停先賣後買當沖）也比 TWSE openapi
`TWTBAU1` 全（14 vs 8 檔四位碼）。

**速度**：冷 1.47s、熱 **0.03s**。finlab 的 `disposal_information` 排程是
`10 8 * * 1-6`（週一～週六 08:10），開盤前一定更新得到。

**新的 `get_restricted_stocks()` 結構**（呼叫端簽名不變，仍回 `set`）：

1. `_from_finlab()` — `disposal_information` + `day_trade_short_suspension`，兩市。
2. `_from_exchanges()` — 交易所公告頁，只在 finlab 完全沒答時用，
   且會**警告「這條路實測會漏 14 檔中的 5 檔」**。
3. `_from_panel()` — 歷史面板，並**明確警告落后幾天**（現在就會印
   `DISPOSAL PANEL STALE: newest row 2026-10-21 is 5 days behind ...`）。
4. 三條都失敗 → `NO RESTRICTION SOURCE ANSWERED`，只剩 hardcoded 兩檔。

另外加了 finlab 資料新穎度檢查：處置都是**前一晚公告、隔天生效**，
所以正常最多落後 1 天；超過 5 天就報 `FINLAB DISPOSAL STALE`。

**端到端驗證**（2026-10-26 21:52 實跑）：

```
Restricted from finlab in 1.47s: 14 處置 (both markets), 14 暫停先賣後買當沖
Restricted (cannot day-trade): 30 codes
Loaded 30 restricted stocks
Pre-open trim: dropped 993 below turnover floor, 30 disposal, kept 905
Scan via Fugle (TWSE+TPEx): 905 quotes in 0.3s
Scan done in 1.2s (898 valid quotes)
```

訊號數 **63 筆，與改之前完全相同** —— 新增排除的 13 檔本來就不是訊號，
所以這是純保險，不犧牲邊際。

### 因子面板：已重跑 `--refresh`（2026-10-26 21:57，27 秒）

先更正我先前寫的「面板停在 2026-08-19、尚未跑」——**那句是錯的**。
日誌顯示 16:22 之後的掃描就已經是 `Factor panel as-of 2026-10-22`，
只有 11:13 與 14:56 那兩次是 08-19。我把舊日誌當成現況了。

本輪重跑的結果：

| 項目 | 內容 |
|---|---|
| 價格庫 5 檔 | 全部 **4,794 × 2,789**，最後一筆 **2026-10-22** |
| `zt_factors.pkl` / `zt_turnover.pkl` | 同樣到 **2026-10-22** |
| 耗時 | **27 秒**（只抓 10 天重疊 tail + 本地重建） |
| 與來源一致性 | 近 13 個交易日 × 2,789 欄，`close` 與 `vol` **0 個不一致**（max rel diff = 0） |

**2026-10-22 就是目前能取到的最後一個交易日**：直接問 finlab
`price:close`，10/15 之後只有 10/15、10/16、10/19、10/20、10/21、10/22
有資料，10/23～10/26 完全沒有 — 與富果/TWSE MIS/Yahoo/群益四家一致。
所以面板的 `lag 4d` 是**日曆天**，交易日是 **0 天落後**，不會觸發
`max_factor_lag_days=10` 的退路。

重跑仍然有意義：`refresh_prices(overlap=10)` 會把最後 10 天**重新下載並覆寫**，
而不是跳過。這是刻意設計 — 本地快照如果在 16:23 前抓，最後一列的成交量會低估
（實測過 2330 差 1.77%、2383 差 5.23%）。這次覆寫後與來源完全一致。

驗證（21:58 實跑）：

```
Factor panel as-of 2026-10-22 00:00:00 (lag 4d), turnover keys 2361
v13 model loaded: trained through 2026-10-22 00:00:00, pool=60000
Scan done in 1.3s (898 valid quotes)
```

沒有 `FACTOR PANEL STALE` 警告，且 `_factor_row` 是真實 DataFrame（不是
`None`）— 模型這一次用的是真因子，不是 missing-value 分支。

### 尚未處理

- §1 開盤 09:00 的**實際可見延遲**仍未量到：今天四家資料源都停在 10/22，
  要等開盤日 08:58 跑 `python gap_fade_auto.py scan` 才能量。
  這是上實盤前**唯一**還沒量到的關鍵數字。

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

---

## 10. 一整天跑下來的日誌地圖（2026-10-26 補）

所有東西都寫進 `trading_logs\trading_YYYY-MM-DD.log`，外加
`trading_logs\exec_report_YYYYMMDD.json`（結構化的執行資料，含 `fill_prices`
與 `fill_raw`）。下面每一行都對應一個「實盤可能跟回測不一樣」的地方，
跑完一天照這個順序掃一遍就能定位問題。

### 階段 0：08:55 前置檢查
| 日誌行 | 正常 | 異常代表 |
|---|---|---|
| `Restricted from finlab in X.XXs: N 處置 (both markets), M 暫停先賣後買當沖` | 有，且 N/M 是數字 | 看到 `came from the exchange announcement pages` → 退化成會漏 5/14 的路徑；看到 `DISPOSAL PANEL STALE` → 三條源全死 |
| `FINLAB DISPOSAL STALE: newest 處置 announcement is ...` | 不出現 | finlab 資料落後 >5 天，今天的處置股沒排到 |
| `Factor panel as-of <date> (lag Nd)` | lag ≤ 10 日曆天 | `FACTOR PANEL STALE` → 模型改餵 NaN，邊際大幅縮（實測 2023-25 區段 1692%→260%） |

### 階段 1：09:00 掃描
| 日誌行 | 要看什麼 |
|---|---|
| `Stock universe: N codes` → `Query list after pre-open filters: M codes` | 漏斗是否正常（實測 1,928 → ~905） |
| `Pre-open trim: dropped A below turnover floor, B disposal, kept M (C without panel data...)` | `C without panel data` 不該變大，變大代表面板沒覆蓋到 |
| `Scan via Fugle (TWSE+TPEx): M quotes in X.Xs` | **必須是 Fugle**。出現 `falling back to TWSE MIS` = 上櫃看不到 |
| `COVERAGE: full universe answered (TPEx rows in feed: N)` | N 要 ≈ 850。掉到 0 = 上櫃又漏了 |
| `Market gap (0050 open, v13 def): +X.XX%` | 必须是 `0050 open` 這版定義。出現 `FALLBACK (7 large caps, NOT v13 def)` = 基準換了，訊號不可比 |
| `Opening-locked (excluded by v13): N` | 開盤鎖漲/跌停被排掉的數量 |
| `Rejected for no-borrowable: N` | 若同時出現 `Borrowable list UNAVAILABLE` → SHORT 腿完全沒驗證 |
| `Model scored X candidates -> kept Y; TP20 share Z%` | `TP20 share` 是動態 TP 的占比，跟回測差很多就是模型輸入跑掉了 |

### 階段 2：09:00 下單
| 日誌行 | 要看什麼 |
|---|---|
| `Market regime: DD=.. Vol=.. ConsecDown=.. 3dRet=.. PrevRet=..` | 倉位縮放的全部輸入。要能重現當天為什麼部位大/小 |
| `ENTER <code> SHORT price=.. shares=.. tier=.. SL=..(x%) TP=..(y%) \| limit=up/down` | **這行是重現決策的完整憑證**：進場價、張數、停損停利、漲跌停。逐筆對回測 |
| `<code>: < 1 zhang, SKIP` / `exposure cap reached, SKIP` / `Skipped (at price limit): N` | 回測會下但實盤跳過的單，全部有原因 |
| `Total exposure: N (P%)` | 零融資上限 100%，超過就是 bug |
| `[OrderResult] ...` / `[FILL] ...` / `[CANCEL] ...` | 券商原始回執，保留原文供對帳 |

### 階段 3：盤中監控
`monitor_positions()` 每 60 秒批次取一次價（§7C），觸發時走 `_mark_exit`。
**注意**：實盤的停損停利是群益智慧單在**交易所**執行，我們的監控只做回報。
所以「我們看到觸發」跟「券商實際成交」是兩件事，最終要以 `[FILL]` 為準。

### 階段 4：13:25 收盤回報（`EXECUTION RISK REPORT`）
| 日誌行 | 這是什麼 |
|---|---|
| `RISK1 opening price visible: X.XXs after 09:00:00` | 開盤價幾秒後才看得到。**上實盤前唯一還沒量的數字** |
| `RISK1 scan finished: X.XXs after 09:00:00 (scan itself took Y.Ys)` | 從開盤到全部訊號算完 |
| `MARKET COVERAGE: A/B codes answered, C silent` | 兩市涵蓋率 |
| `submit->ack n=.. median=..ms` | 下單通道速度 |
| `order submission: N orders in X.Xs (R orders/s)` | 22 筆要多久送完 |
| `filled within 5/10/30/60s of 09:00: k/n` | 開盤幾秒內成交幾筆 |
| `ENTRY SLIPPAGE ... SHORT n=.. median_edge=..% \| LONG n=.. median_edge=..%` | **本輪新增**。成交價 vs 回測假設價。`edge>0` 一律代表有利：SHORT 成交較高為正、LONG 較低為正。這是「模型邊際能不能活過現實」的數字 |
| `[FILL] price recovered at numeric field #N` | 第一次實盤用它反推 OnFill 欄位順序，確認後寫死 |
| `[FILL] <code>: cannot isolate the fill price (candidates=..)` | 無法判定成交價 → 用日誌裡的原始 args 修正欄位索引 |
| `rejected orders: N retried: M` + 逐筆 `code=..` | 被券商拒絕的原因 |

### 已知仍未記的事（誠實列）
- **智慧單實際掛出去的條件**：`SendStockStrategyDayTrade` 的回執有條件單號，
  但「券商端實際生效的停損停利條件」沒有回讀驗證。要在群益 App 對。
- **盤中觸發順序**：1 分 K 才有，日誌只有 60 秒一次的取價快照。
- **融資額度**：零融資設定下不會觸發，但額度實際多少沒有查。
---

## 11. 群益能不能下模擬單？——**不能**，所以有 `paper` 模式（2026-10-27）

直接查裝在機器上的型別程式庫（`D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll`）：

| 查證項目 | 結果 |
|---|---|
| `ISKOrderLib` 全部方法 | 155 個，**沒有任何試單／模擬單／paper 單**（只有 `PingandTracertTest`、`TelnetTest` 這種網路測試） |
| `SendStockStrategyDayTrade` 第二個參數 | 是 `bAsyncOrder`（非同步送單），**不是**模擬旗標。官方範例 `PythonExampleV2/Order/TS/TSStrategyOrder/TSStrategyOrder.py:792` 寫得很清楚 |
| 唯一的沙箱 | `SKCenterLib_SetAuthority(2)` = 測試環境。但那是**另一台伺服器＋另一個帳戶**，證明不了「我的帳戶能不能交易」 |

### 所以 `paper` 模式怎麼做

保留所有真實依賴，只把風險拿掉：

1. **全部是真的**：真實登入、真實報價、真實掃描／模型／倉位，與 `live` 完全同一條程式路徑。
2. **用價格把風險歸零**：每個訊號都送一張**真的智慧單**（群益 App 看得到），但只有 `1 張`，
   且掛在不可能成交的價格——**買單掛跌停、賣單掛漲停**。万一真的成交，13:20 的時間平倉會自動收掉，
   最壞情況就是 1 張、幾個小時。
3. **真正的部位在內部位於模擬**：完整張數與真實 SL/TP 用即時報價以 `paper_poll_sec`（預設 10 秒）推演，
   所以還是會產出損益、勝率，以及回測永遠不知道的那個數字——**進場價到底成交不成交得了解**。

### 它會給你什麼

收盤後 `LIVE FEASIBILITY REPORT (paper)` ＋ `trading_logs/paper_report_YYYYMMDD.json`，三項硬標準：

| 檢查 | 標準 | 為什麼要看 |
|---|---|---|
| 送單接受率 | 100%（0 拒單） | 帳戶權限、資券、額度、下單密碼全部會在這裡暴露 |
| `submit→ack` | p90 < 2000 ms | 22 檔一次送完的吞吐夠不夠 |
| 進場可成交性 | 不利滑價 p90 < 0.5% | 這是 RISK1 的實戰版：開盤價看得到、但買不買得到是另一件事 |

外加模擬帳（筆數、勝率、含成本總損益、出場原因分布）。

### 執行方式

```bash
python gap_fade_auto.py paper     # 只在交易日 08:55-13:40 之間有效，其他時間直接拒絕執行
```

時段保護是刻意加的：夜間跑會掃到今天收盤的舊開盤價、所有單都被拒，verdict 會誤判。

### 尚未做

`paper` 模式已通過離線煙霧測試（探測價＝跌停/漲停、滑價符號、報告與 PASS/FAIL 皆正確），
但**還沒有在真實開盤跑過一次**。第一次實跑要在下一個交易日 08:55 後執行。

### 11.1 用今天的真實資料把整條鏈路預演過一次（2026-10-27 盤後）

`paper_rehearsal.py`：除了「送給交易所」這一步換成 stub，其他全部是真的 ——
真實報價、真實掃描、真實過濾器、v13 模型、真實倉位計算、真實 `STOCKSTRATEGYORDER`
結構組裝。目的就是把「除了交易所收不收之外，還有沒有別的東西會壞」這件事先排除掉。

```bash
python paper_rehearsal.py        # 任何時間都能跑，不會送單到交易所
```

**已驗證（2026-10-27 實測）**

| 項目 | 實測 |
|---|---|
| 掃描 | 721 檔 / **0.4 秒**（富果批量，含上櫃 236 檔，覆盖率 100%） |
| 處置/當沖限制 | finlab 1.01 秒拿到 14 處置 + 16 暫停先賣後買，排除 32 檔 |
| 可借券 | T-1 出借限額 as-of 2026-10-27，2095 檔；2 檔因無額度被拒 |
| 開盤鎖死 | 排除 1 檔（v13 規則） |
| 訊號 → 單 | 186 個訊號 → **8 張單**，總名額 4,483,800 = **100% 淨值**（零融資到頂） |
| 智慧單欄位 | **8/8** 都是 SL 絕對價 + TP 絕對價 + 13:20 市價時間平倉 + `nQty`=1 張 |
| 全部停損的最大損失 | 139,400 = **3.1% 淨值** |

8 筆的部位分别是 18.3/18.5/13.3/20.6/17.3/6.1/3.6/1.9%（合計 100%），
其中 6933 距漲停只有 0.97% → 停損被壓到漲停 −1 tick，最大損失只剩 7,000（0.16% 淨值），
倉位因此放大到 18.3%。這是 ZT-aware 倉位的設計行為，不是 bug。

**預演量化出來的兩個「實盤 ≠ 回測」差距**

1. **鎖死時的 1 個 tick**：停損掛在漲停 −1 tick，若個股鎖死在漲停，市價回補會成交在
   漲停本身，比回測假設差一格。今天 2 筆停損（6933、6213）**都是**這種情況，
   各多付 1,000 元 ≈ 名額的 0.12%。報告會自己標出來（`limit_pinned_tick_cost`）。
2. **今天的 1 分 K 不在本地**：`股票價格Ｋ線` 的 1 分 K 只到 2025-10，2026-10 沒有。
   8 筆裡 3 筆連当日 high/low 都拿不到（Yahoo 沒回傳、富果即時端點這個金鑰回 401），
   只能用收盤價，無法判斷盤中有沒有先觸停損。所以報告把 PnL 拆成
   「可解析 5 筆 +82,388（+1.83%）」與「只有收盤價 3 筆 +112,062」兩塊，
   並明確寫 **不要把總數當成實測**。

**探測單的風險邊界（今天剛好踩到）**

6933 與 6213 的探測價就是漲停價，而這兩檔當日確實摸到漲停 → 探測單有可能真的成交
1 張。這是設計上接受的邊界：最多 1 張、13:20 交易所自動平倉。

**盤後跑的非確定性（別把這個數字當天花板）**

同一晚跑兩次，第一次 7 張單、第二次 8 張單。盤後富果即時端點回的是當日完成價，
批次之間不完全一致；開盤時不該拿這個數字當基準。真正的基準要等 §1 的 RISK1 量到之後
由 `paper` 模式在盤中產生。

**仍未驗證（只有真實盤中能答）**

送單接受率、submit→ack 延遲、開盤 5 秒內的實際成交價（進場滑價）。
这三項在預演報告裡一律標 `[NOT TESTED]`，不會假裝通過。


---

