# twmarket：台灣市場交易規則與選擇權定價參考實作

這是一個獨立的 Python 套件，用來實作台灣市場的交易規則，並提供選擇權定價模型，
之後會合併到量化研究系統使用。設計時以「正確性優先於功能多寡」為原則：

- **Python 3.11 以上，只用標準函式庫**。測試使用 pytest。
- **價格一律以 `Decimal` 計算**。所有公開函式只接受 `Decimal`、`int`、`str`，
  傳入 `float` 會直接拋出 `TypeError`，避免浮點誤差混入計算。
- **每條制度規則都在程式註解中寫明依據**，附官方頁面或法規的 URL 與查閱日期。
  找不到確定依據的規則一律標註 `TODO`，不自行推定。
- 不下載任何市場資料，不需要 API key，也不使用 `.env`。

## 安裝與測試

```bash
cd twmarket
pip install -e ".[test]"
pytest
```

在 repo 根目錄執行 `pytest twmarket` 也可以，`twmarket/conftest.py` 會處理 import 路徑。

## 模組說明

### `tick.py`：升降單位與漲跌停價格

| 函式 | 說明 |
|---|---|
| `tick_size(price, security_type, trade_date)` | 依價格區間回傳升降單位，股票與 ETF 各用不同的表 |
| `round_to_tick(price, direction)` | 將價格對齊到有效檔位，可選向上或向下 |
| `is_valid_price(price, ...)` | 判斷價格是否落在有效檔位 |
| `price_limit_pct(trade_date)` | 回傳漲跌幅：2015-06-01（含）以後為 10%，以前為 7% |
| `price_limits(reference_price, ...)` | 計算漲停價（向下取有效檔位）與跌停價（向上取有效檔位） |

升降單位如下：

- 股票：未滿 10 元為 0.01；10 元～未滿 50 元為 0.05；50 元～未滿 100 元為 0.1；
  100 元～未滿 500 元為 0.5；500 元～未滿 1000 元為 1；1000 元以上為 5。
- ETF：未滿 50 元為 0.01；50 元以上為 0.05。

範例：參考價 95.5 元的股票，跌停價為 86.0、漲停價為 105.0；同樣參考價的 ETF，
跌停價為 85.95、漲停價為 105.05。

### `cost.py`：交易成本

| 函式 | 說明 |
|---|---|
| `commission(amount, discount, min_fee, rounding)` | 手續費，費率 0.1425%，可設定折扣與最低收費（預設 20 元） |
| `securities_tax_rate(category, tax_date)` / `securities_tax(...)` | 證交稅：一般股票 0.3%、現股當沖 0.15%（2017-04-28～2027-12-31）、ETF 0.1% |
| `stock_trade_cost(...)` | 現貨一買一賣的成本，回傳 `.buy`、`.sell`、`.round_trip` |
| `futures_tax(...)` / `futures_round_trip_tax(...)` | 股價類期貨（臺指期、股票期貨）期交稅：契約金額的十萬分之 2 |
| `option_premium_tax(...)` / `option_round_trip_tax(...)` | 選擇權期交稅：權利金的千分之 1 |
| `option_settlement_tax(...)` | 選擇權到期現金結算的期交稅：結算金額的十萬分之 2 |

- 期交稅依期交所課稅實例，**每口先四捨五入到元，再乘以口數**。
- 證券手續費與證交稅計算到「元」時應無條件捨去還是四捨五入，目前查無官方明文，
  所以預設不取整，可以用 `rounding` 參數指定（見 TODO）。

### `contracts.py`：契約規格

常數 `TX`（臺股期貨，每點 200 元）、`TXO`（臺指選擇權，每點 50 元，歐式）、
`STOCK_FUTURES`（股票期貨，每口 2,000 股）、`MINI_STOCK_FUTURES`（小型股票期貨，
每口 100 股）。每項常數都記錄了乘數、交割方式、最後交易日規則、最後結算價規則，
以及官方來源 URL。

`last_trading_day(year, month)` 會回傳該月第三個星期三。**這個函式沒有處理假日**
（見 TODO）。

### `options.py`：選擇權定價

| 函式 | 說明 |
|---|---|
| `black76_price(F, K, T, r, σ, type)` | Black-76 歐式期貨選擇權定價 |
| `black76_greeks(...)` | 計算 delta、gamma、vega、theta、rho |
| `crr_price(S, K, T, r, σ, type, steps, american, carry)` | CRR 二項樹，可算美式或歐式；`carry` 為持有成本：期貨填 0，無股利股票填 r |
| `implied_volatility(price, F, K, T, r, type)` | 用 Brent 法反推隱含波動率；無解時拋出 `NoImpliedVolatilityError` |

Greeks 單位慣例：

- vega：波動率變動 1.00 時的價格變動。
- theta：每年的價格變動。
- rho：利率變動 1.00 時的價格變動（Black-76 下 rho = −T·V）。
- delta 與 gamma 都是對期貨價格 F 微分。

內部計算精度為 50 位有效數字。

**驗證方式**（容許誤差都寫在測試檔中）：

- Hull 教科書數值（書中數值四捨五入到幾位，就容許最後一位的半個單位）：
  - 期貨賣權 1.12
  - Black-Scholes 等價：買權 4.76、賣權 0.81
  - 美式股票賣權：5 步 4.49；30／50／100 步分別為 4.263／4.272／4.278
  - 美式期貨賣權（3 步）2.84
  - Greeks：0.522／0.066／12.1／−4.31／8.91
- 用中央差分逐一核對每個 Greek。
- 驗證 Put-call parity：Black-76 誤差小於 1e-40；美式期貨選擇權符合 Hull 的不等式上下界。
- CRR 收斂性：步數 N 增加時會收斂到 Black-76／Black-Scholes，誤差小於 3/N。

## 規則依據清單（查閱日期：2026-10-14）

> **查證限制**：開發環境的網路政策擋住了證交所、期交所與全國法規資料庫，
> 無法直接開啟這些網站。以下內容是透過搜尋引擎取得官方頁面的摘要後確認的。
> 合併進研究系統前，**請人工逐條對照原文**。

| 代號 | 規則 | 來源 |
|---|---|---|
| R1 | 證交所營業細則第 62 條（升降單位）、第 63 條（漲跌幅度） | https://twse-regulation.twse.com.tw/m/LawContent.aspx?FID=FL007304 |
| R2 | 股票升降單位表（自 2005-03-01 實施） | https://www.twse.com.tw/downloads/zh/trading/introduce/introduce004.pdf |
| R3 | 受益憑證買賣辦法：ETF 升降單位 | https://twse-regulation.twse.com.tw/m/LawContent.aspx?FID=FL007114 、 https://www.twse.com.tw/zh/products/securities/etf/overview/rules.html |
| R4 | 漲跌停價計算範例（40.60 → 44.65） | https://www.twse.com.tw/zh/products/system/trading.html |
| R5 | 2015-06-01 漲跌幅由 7% 放寬為 10% | https://www.tpex.org.tw/web/stock/trading/information/range.php?l=zh-tw |
| C1 | 手續費 0.1425%、未滿 20 元以 20 元計（1990 年函釋） | https://twse-regulation.twse.com.tw/TW/int/DAT01_print.aspx?FLCODE=FE064320 |
| C2 | 證券交易稅條例第 2 條（股票 0.3%、其他有價證券 0.1%） | https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=G0340078&flno=2 |
| C3 | 受益憑證（ETF）證交稅 0.1% | https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/securities-transaction-tax/filing/KJZD0QV |
| C4 | 證券交易稅條例第 2 條之 2：現股當沖 0.15%，期限至 2027-12-31 | https://www.dot.gov.tw/singlehtml/ch26?cntId=fde9d7d1546d4df8a4db96bf23e2f57c |
| C5 | 期貨交易稅條例第 2 條 | https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=G0340079&flno=2 |
| C6 | 期交稅現行徵收率：股價類期貨十萬分之 2、選擇權千分之 1 | https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-saving-manual/national/future-transaction-tax/12B2ODn 、 https://www.taifex.com.tw/cht/4/feeSchedules |
| C7 | 選擇權類課稅實例（每口四捨五入後再乘口數） | https://www.taifex.com.tw/chinese/4/%E9%81%B8%E6%93%87%E6%AC%8A%E9%A1%9E%E8%AA%B2%E7%A8%85%E5%AF%A6%E4%BE%8B.doc |
| K1 | 臺股期貨契約規格 | https://www.taifex.com.tw/cht/2/tX |
| K2 | 臺指選擇權契約規格 | https://www.taifex.com.tw/cht/2/tXO |
| K3 | 股票期貨契約規格（2,000 股／100 股） | https://www.taifex.com.tw/cht/2/sTF 、 https://www.taifex.com.tw/chinese/event/HSTF/event.asp |

## TODO 清單

1. **全部規則**：以官方原文逐字核對（理由見上方「查證限制」）。
2. **千元以上股票檔位改為 1 元**：證交所董事會已在 2026-08-25 通過修正營業細則第 62 條，
   目前尚待主管機關核定。依媒體報導，最快 2027 年 7 月實施。正式生效日公告後，
   需要在程式中加入依日期切換的檔位表。
3. **ETF 升降單位沿革**：查不到 ETF 檔位表的起始生效日和歷史版本，
   目前所有日期一律套用現行表。
4. **2005-03-01 以前的股票升降單位**：尚未查證，傳入更早的日期會拋出錯誤。
5. **ETF 漲跌幅特例**：槓桿／反向 ETF 的漲跌幅倍數、國外成分證券 ETF，
   以及新上市股票前 5 日不設漲跌幅等情況，程式都不會自動判斷，
   需要由呼叫端用 `limit_pct` 參數自行處理。
6. **漲跌幅未滿一檔的處理**：目前只依搜尋摘要實作，尚待用條文原文核對。
7. **證券手續費與證交稅計算到「元」的取整方式**：查無官方明文，目前預設不取整。
8. **債券 ETF 證交稅**：暫停徵收的法源、期限與適用範圍都未查證，
   目前 ETF 一律以 0.1% 計算。
9. **當沖減稅期間的判斷日**：條文期間是以成交日還是交割日判斷，尚待核對；
   目前由呼叫端傳入 `tax_date`，建議傳交割日。
10. **選擇權到期結算課稅對象**：是否只對履約（價內）部位課徵，尚待核對。
11. **期貨與選擇權手續費**：由期貨商與交易人議定，程式未計算。
12. **TXO 權利金升降單位、股票期貨升降單位**：尚未查證，所以目前不提供。
13. **最後交易日遇假日**：遇休市時的順延規則未確認，程式也沒有接交易日曆。
14. **TXO 週選擇權**：最後交易日規則尚未實作。
