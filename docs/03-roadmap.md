# 03 — 路線圖與驗收標準（Roadmap & Acceptance）

> 執行原則：一個里程碑做完、驗收過了，再進下一個。每個 milestone 結束時 `git tag m<N>-complete`。

## M0 — 計算引擎（本封包的核心交付）✅ 優先

**任務**：實作 `src/pfpro/engine.py`，使 `pytest tests/ -v` 全綠。

內容：
- `solve_irr(cashflows) -> float | None`：年化 IRR 求解；無正負號變化回傳 `None`。
- `effective_rate(hibor_1m, h_spread, prime_rate, p_spread) -> float`：`min(H+h_spread, P−p_spread)`。
- `project(params, table) -> list[Row]`：逐年投影（利息、退保價值、總回報、淨利潤、IRR、現金流），公式見 `02-functional-spec.md` §2。
- `stress_matrix(params, table, rates, ratios, stress_year) -> matrix`：規則見 §4。

**驗收標準**：
1. `pytest` 全綠（含 golden vectors 全部驗證點）。
2. 引擎無第三方依賴（`pip install -e .` 後僅標準函式庫）。
3. 每個函數有 docstring 與型別標註。

**建議 commit 順序**：`feat: add solve_irr with sign-change guard` → `feat: add projection engine` → `feat: add stress matrix` → `test: golden vectors from verified reference values`。

## M1 — REST API

**任務**：FastAPI 包裝引擎；`POST /projection`、`POST /stress`、`GET /healthz`；Pydantic 驗證（範圍檢查 + 利益表逐年結構）；回應附免責文案欄位。

**驗收**：
1. `uvicorn` 本地起服，`curl` 三個 endpoint 行為正確（錯誤輸入回 422）。
2. 新增 API 層測試（TestClient），引擎測試不回退。
3. OpenAPI 文件可開（`/docs`）。

## M2 — 容器化 + Terraform（Cloud Run）

**任務**：根目錄 `Dockerfile`（多階段 build、非 root 執行）；`infra/terraform/`：provider、Artifact Registry repo、Cloud Run service、IAM。

**驗收**：
1. `docker build` 成功，本地 `docker run -p 8080:8080` 可訪問 `/healthz`。
2. `terraform fmt && terraform validate` 通過；`terraform plan` 輸出存檔（無法 apply 因缺 GCP 帳號——由 Ricky 執行，見 ADR-3）。
3. 無密鑰進 repo。

## M3 — GitHub Actions

**任務**：`.github/workflows/ci.yml`：PR → pytest + terraform plan（continue-on-error 標註）；push main → build、push Artifact Registry、deploy Cloud Run（需 Ricky 設定 `GCP_SA_KEY` 等 secrets 後才啟用 deploy job，先以 `workflow_dispatch` 手動觸發）。

**驗收**：
1. PR 上 CI 綠燈（pytest + fmt + validate）。
2. terraform plan 結果以 PR comment 呈現。
3. README 補「如何設定 secrets」章節。

## M4 — React 前端

**任務**：`web/`（Vite + React + TS）：參數表單、KPI 卡（首付/槓桿/貸款額）、年度明細表、壓力矩陣色階表。只呼叫 API，不內嵌計算。

**驗收**：
1. 輸入基準參數，畫面數字與 golden vectors 一致（含 IRR 為「—」的情況）。
2. `npm run build` 成功；API base URL 以環境變數注入。

## 交付後 Ricky 要補做的事（非 agent 範圍）

- GCP 專案開通 + billing + service account（M2/M3 需要）。
- GitHub secrets 設定。
- README 加截圖、repo description、topics（`gcp` `cloud-run` `terraform` `fastapi` `premium-financing`）。
- 部署後把 URL 更新到 CV 與求職信。

## 風險與對策

| 風險 | 對策 |
|---|---|
| IRR 求解器在邊界現金流不收斂 | golden tests 已含 null 情況；求解器加迭代上限與越界檢查 |
| Terraform apply 無帳號可驗 | plan 輸出 + 本地 docker run 雙重驗證；文件註明 |
| 前端與引擎邏輯漂移 | 前端禁止內嵌計算（ADR-6），唯一事實來源在後端 |
| 範圍膨脹（想做 PDF/Gemini/i18n） | 本檔 P0–P4 之外一律開 issue 不實作 |
