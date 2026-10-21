# Gap Fade v3 - 台股當沖自動交易系統

## 策略概述

基於開盤跳空反轉（Gap Fade）的當沖策略，利用散戶造成的超漲超跌回歸均值獲取 alpha。

### 核心邏輯
- **SHORT**: 個股開高超過大盤 5%+ → 放空等待反轉
- **LONG**: 個股開低超過大盤 5%+ → 做多等待反彈
- **出場**: TP 4% / SL 6% / 13:25 強制平倉

### 績效 (2010-2026, 17年)
| 指標 | 值 |
|------|-----|
| CAGR | 83.3% |
| MDD | -4.8% |
| Sharpe | ~9 |
| 勝率 | 55.2% |
| 交易成本 | 0.198%/筆 (1.7折+當沖稅減半) |
| 資金 | 450萬, 整張交易 |

### 倉位管理 (Model C)
動態倉位 2-12%，基於：
- 大盤因子：回撤、波動率、連跌天數、訊號密度、星期效應
- 個股因子：趨勢方向、回撤、新高懲罰、出現頻率

## 檔案結構

### 主要策略
- \gap_fade_auto.py\ - 實盤自動交易（群益 SKCOM + TWSE 掃描）
- \gap_fade_module.py\ - 策略模組（回測用）
- \gap_fade_scanner.py\ - 即時掃描器

### 回測
- \_modelc_realistic.py\ - Model C 現實版回測（450萬+整張）
- \_modelc_report.py\ - Model C 完整報告
- \_wf_modelc.py\ - Walk-Forward 驗證
- \acktest_kelly_lot.py\ - Kelly 倉位 + 整張回測

### 測試/除錯
- \	est_*.py\ - 各種 API 連接測試
- \_test_*.py\ - 功能測試腳本

## 使用方式

### 實盤交易
\\\ash
python gap_fade_auto.py live
\\\

### 回測
\\\ash
python _modelc_realistic.py
\\\

## 依賴
- Python 3.10+
- pandas, numpy
- shioaji (群益證券 API)
- requests (TWSE 即時報價)
- finlab (歷史數據)

## 券商
- 群益證券 (Capital Securities)
- SKCOM 即時報價 + 下單
- SendStockStrategyDayTrade 策略單（自動掛 TP/SL）
