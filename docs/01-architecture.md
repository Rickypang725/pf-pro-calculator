# 01 — 架構決策（Architecture Decisions）

> 每個決策都給出**理由**與**替代方案**，供面試時解釋取捨。決策標記：[採用] / [考慮後否決]。

## ADR-1 計算引擎：獨立 Python 套件，零框架依賴

**[採用]** `src/pfpro/engine.py`：純 Python（僅標準函式庫，不強制 numpy/scipy），不 import FastAPI、不讀環境變數、不做 I/O。

- **理由**：引擎是純函數（輸入參數 + 利益表 → 輸出投影），隔離框架後 golden tests 秒開、無需起伺服器；未來換 API 框架或前端不影響引擎。
- **替代方案**：(a) 直接用 Node/TypeScript 實作——與前端同語言，但數值求解與測試生態不如 Python 直接；(b) 引擎放進 FastAPI route 裡——測試必須起 HTTP，違反「引擎是純函數」的邊界。

## ADR-2 API 框架：FastAPI

**[採用]** P1 階段以 FastAPI 包裝引擎，Pydantic v2 做輸入驗證。

- **理由**：型別即文件（OpenAPI 自動生成，面試 demo 可直接展示 Swagger UI）；Pydantic 驗證擋掉非法輸入（LTV>100、負利率等）；與未來 P5 Gemini 解析（google-genai Python SDK）同生態。
- **替代方案**：(a) Flask——更輕但無內建驗證/文件；(b) Node Express/NestJS——與前端同語言但與 AI SDK 生態割裂；(c) tRPC——型別安全最佳，但要求前後端皆 TS，違反 ADR-1。

## ADR-3 部署目標：GCP Cloud Run（region: asia-east2 香港）

**[採用]** 容器化（Docker）後由 Terraform 部署到 Cloud Run；region 選 asia-east2（延遲 + 資料落地考量）。

- **理由**：Cloud Run = 請求導向、scale-to-zero，無閒置成本，正對目標職缺（Junior Cloud Engineer, GCP-first）的技術面；Terraform 管理全部資源，符合 IaC 紀律，可寫進 CV：`Terraform-managed Cloud Run service`。
- **替代方案（考慮後否決）**：(a) GKE——對單一 stateless 服務過度工程，但面試可說「GKE 是下一步當需要 sidecar/service mesh 時」；(b) App Engine——部署簡單但底層控制力弱、不利展示 Terraform 能力；(c) AWS——目標職缺 GCP 為主，否決。
- **注意**：`terraform apply` 需要 Ricky 的 GCP 帳號與 billing——M2 驗收以 `terraform plan` + `gcloud run deploy --no-traffic` 文件為準，實際 apply 由 Ricky 執行。

## ADR-4 CI/CD：GitHub Actions

**[採用]** PR 觸發：pytest + `terraform plan`（plan-on-PR，對應 006 職缺評估的建議）；merge 到 main：build → push Artifact Registry → deploy Cloud Run。

- **理由**：plan-on-PR 讓基礎設施變更有可審查的預覽，是團隊協作的基本紀律；GitHub Actions 與 repo 原生整合，免額外系統。
- **替代方案**：Cloud Build——與 GCP 整合更深但綁定單一雲，GitHub Actions 可攜（multi-cloud 敘事）。
- **Artifact Registry vs Docker Hub**：選 Artifact Registry——部署在同一專案內，權限由 IAM 單一管理，無外部依賴。

## ADR-5 無資料庫（P0–P4）

**[採用]** 不引入資料庫；利益演示表由請求 JSON 帶入（或前端內建 demo 資料）。

- **理由**：計算無狀態，資料庫只會增加部署面與成本；原版工具亦無 DB，行為對齊。
- **何時翻案**：當需要「儲存客戶方案歷史」時再引（Cloud SQL 或 Firestore），屆時是獨立 ADR。

## ADR-6 前端：React + TypeScript + Vite（P4）

**[採用]** 與引擎解耦：前端只呼叫 REST API，不內嵌計算邏輯（避免雙邊邏輯漂移——原版正是全在前端計算，重建版把邏輯收斂到後端是架構改進點，面試可講）。

- **替代方案**：(a) Next.js SSR——對純內部計算工具無 SEO/SSR 需求，否決；(b) 純 HTML+JS 單檔——維護性差，否決。

## 目標架構圖（P2 完成後）

```
┌────────┐   HTTPS   ┌──────────────────────────────┐
│  React │ ────────► │  Cloud Run (FastAPI + engine)│
│  (CDN) │ ◄──────── │  · POST /projection          │
└────────┘   JSON    │  · POST /stress              │
                     │  · GET  /healthz             │
                     └──────┬───────────────────────┘
                            │（唯讀，P3+）
                     ┌──────┴────────┐
                     │  Artifact Reg │◄── GH Actions (build & push)
                     └───────────────┘
   Terraform 管理：Cloud Run service + IAM + Artifact Registry repo
```

## 安全與合規基線

- 輸入驗證全部在 Pydantic 層（範圍檢查：0<LTV≤100、rate≥0、fx>0、年份為正整數）。
- 容器以非 root 使用者執行；只暴露 8080。
- `.env`、service account key 一律不進 repo（`.gitignore` 已備）。
- CORS：P4 前端同源部署時可鎖定 origin。
