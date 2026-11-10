# 02 — 功能規格（Functional Spec）

> 來源：對原版工具（Beezy PF-Pro Advisor）的逆向分析，所有公式與 golden vectors 均經獨立重算驗證、與原版工具介面顯示逐項吻合（2026-11-09）。
> 本檔是**對外行為規格**：實作細節（變數名、檔案切分）由執行者決定，但輸出必須符合本規格與 golden vectors。

## 1. 領域與名詞

| 名詞 | 定義 |
|---|---|
| 總保費 (total premium, A) | 保單整付總保費，USD 計 |
| 保費折扣 (discount %) | 保險公司回贈，以總保費百分比表示 |
| 首日退保價值% (surrender0 %) | 首日退保價值佔總保費比例——**銀行放款的基礎** |
| LTV | 貸款成數，作用在首日退保價值上（不是總保費） |
| 銀行匯率 / FWD 匯率 | 銀行放款以 HKD 計的換匯率 / 保單 USD↔HKD 的換匯率 |
| 利益演示表 | 逐年（保證價值, 歸原紅利, 特別紅利）三元組，來自保單建議書 |
| 實現率 (achievement %) | 非保證紅利的達成比例假設（壓力情境參數） |
| 利率表 (rate brackets) | 最多三段：{endYear, rate}，查表規則 = 第一個 endYear≥V 或 endYear=0（開放段）的 rate |

## 2. 核心公式

```
折扣額     b = A × discount%
首日退保值 d = A × surrender0%
貸款額(USD) p = d × LTV%
首付(USD)  h = −[ (A − b) × fwdFx − p × bankFx ] ÷ fwdFx      # 負值 = 現金流出
槓桿倍數     = A ÷ |h|

對每個保單年度 V（利益表查得 g, c, s）：
  適用利率   k = brackets(V)                                    # 分段查表
  當年利息   z = p × k%                                        # 單利、每年自付、不資本化
  總退保價值 S = g + (c + s) × achievement%
  總回報(扣貸款) F = S − p                                      # 退保可取回現金
  累計利息   J = Σ z(t), t = 1..V−1
  淨利潤       = F + h − J − z  （= S − 貸款本金 − 首付 − 累計利息）
  IRR 現金流  = [h, −z, −z, …, −z, F − z]                        # 第0年首付；第1..V−1年付息；第V年收尾
  IRR        = 使 NPV=0 的年化利率；現金流無正負號變化時為 null（顯示「—」）
```

**IRR 求解器**：原版用 Newton-Raphson（初值依年數：1年−0.8、2年−0.6、其他 0；上限 100 次迭代；容差 1e-7；迭代越界或導數為 0 回傳 null）。重建版可用任何正確求解器（含 scipy.brentq），但**邊界行為必須一致**：無正負號變化 → null；結果收斂到同一數值（golden tests 的容忍度見測試檔）。

## 3. 利率雙軌定價（H/P）

```
H 方案利率 = HIBOR(1M) + h_spread%
P 方案利率 = prime_rate% − p_spread%
採用利率   = min(H, P)                # 銀行只提供 P 方案時，直接取 P
```

原版另接 `/api/hkab-hibor` 即時抓取香港銀行公會港元結算利率並做 localStorage 快取；**重建版 P0 不做**，P3 以「手動輸入 HIBOR」或公開 API 取代（注意 HKAB 數據的授權聲明，重建版不抓取 HKAB 頁面）。

## 4. 壓力測試矩陣

- 欄（貸款利率）：2.00%–5.00%，步進 0.25%；若當前採用利率不在其中，插入後排序（原版行為）。
- 列（實現率）：100%, 95%, …, 60%（共 9 列）。
- 每格：把三段利率表**整體平移**（格利率 − 當前利率，即「利率情境 = 全期同幅度變動」），代入該列實現率，跑同一引擎，取**壓力測試年份**（預設第 20 年）的 IRR。
- 色階（P4 UI 參考）：>10% 深綠、>7% 淺綠、>4% 琥珀、<0% 紅。

## 5. 功能優先級

| 優先級 | 功能 | 說明 |
|---|---|---|
| P0 | 計算引擎 `engine.py` + golden tests | 本封包唯一要求交付物 |
| P1 | FastAPI REST API | `POST /projection`、`POST /stress`；輸入輸出 JSON schema 由 engine 型別推導 |
| P2 | Dockerfile + Terraform → Cloud Run | 見 `01-architecture.md`；需要 Ricky 的 GCP 帳號才能 apply |
| P3 | GitHub Actions CI/CD | PR 上跑 pytest + terraform plan；merge 到 main 部署 |
| P4 | React 前端 | 年度明細表 + 壓力矩陣 + KPI 卡；PDF 匯出**不**納入（避免 jspdf/html2canvas 的 CJK 複雜度，面試可口述取捨） |

## 6. 原版有但重建版刻意不做的（可面試口述）

- Gemini 多模態保單解析（P0 範圍外；P5 選修：upload → Gemini → 利益表）
- 20 頁品牌建議書 PDF（含 FWD 市場數據等版權素材，重建版不得使用）
- 7 家銀行條款資料庫（條款文字屬原版內容資產；重建版改為「自訂銀行參數」欄位）
- 三語 i18n（P4 只做英文 UI 即可）

## 7. 免責與合規文案（P1 API / P4 UI 必附）

每個輸出頁面/API 回應須附：
> "Illustrative figures. Returns exclude bank fees and retained-asset opportunity costs. FX rates are assumptions. Past fulfilment ratios are not indicative of future performance. Final loan terms subject to bank confirmation."

## 8. Golden vectors 摘要（完整見 `tests/vectors.json`）

基準輸入：A=120,000、discount=5%、surrender0=80%、LTV=95%、bankFx=7.75、fwdFx=7.85、利率=4.11% 全期、實現率=100%、利益表 = 第1–10/15/20/25/30 年（數值在 vectors.json 內）。

| 驗證點 | 期望 |
|---|---|
| 貸款額 | 91,200 USD（=706,800 HKD） |
| 首付 | 23,961.78 USD（=188,100 HKD） |
| 槓桿 | 5.01× |
| 當年利息 | 3,748.32 |
| 第4年 淨利潤 / IRR | −43,155 / null |
| 第7年 淨利潤 / IRR | −29,900 / −19.45% |
| 第8年 IRR | −13.33% |
| 第10年 IRR | −6.36% |
| 第20年 淨利潤 / IRR | 69,872 / +4.21% |
| 壓力格 (2.00%, 100%, 20年) | 7.05% |
| 壓力格 (4.11%, 60%, 20年) | 1.35% |
| 採用利率 H/P | min(2.59268+1.5, 5.25−0.65) = 4.09268 |
