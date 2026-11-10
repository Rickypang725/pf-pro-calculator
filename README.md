# PF-Pro Rebuild — Kimi Code 任務封包

## 這個 repo 是什麼

這是**交給 Kimi Code（或其他 AI coding agent）自主執行的任務封包**，目標是從零重建一個「保費融資計算器」（Premium Financing Calculator）：

- 行為規格來源：對一個實際運作中的同類工具（Beezy PF-Pro Advisor）的逆向分析，其計算結果已逐項驗證（見 `docs/02-functional-spec.md` 與 `tests/vectors.json`）。
- `tests/test_engine.py` 是**完成與否的客觀合約**：agent 的任務是實作 `src/pfpro/engine.py`，直到 `pytest` 全綠。
- 重建版必須是**原創程式碼**，做為個人 cloud portfolio 專案，最終部署上 GCP Cloud Run（Terraform 管理）。

## 給執行者的第一條指令

```bash
pip install pytest
pytest tests/ -v          # 現在應該全部失敗（engine 尚未實作）——這是起點
```

然後依序閱讀：

1. `docs/02-functional-spec.md` — 功能規格與數學公式（含已驗證的 golden vectors）
2. `docs/01-architecture.md` — 技術棧決策與理由、目標架構
3. `docs/03-roadmap.md` — 里程碑與驗收標準（M0→M4）
4. `tests/vectors.json` + `tests/test_engine.py` — 驗收合約

## 硬約束（不可違反）

1. **原創性**：不得複製任何第三方工具的程式碼、品牌素材（FWD 標誌/文案）、或銀行條款原文。公式與數值是行業常識事實，可以使用；demo 資料必須自製。
2. **Golden tests 是唯一驗收標準**：不得以「修改測試」方式讓測試通過；測試數值與原版工具實測結果一致，是對外行為的合約。
3. **Git 紀律**：小步提交、Conventional Commits（`feat:` / `fix:` / `test:` / `docs:` / `chore:` / `refactor:`），每個 commit 只做一件事。
4. **無密鑰進 repo**：所有金鑰（Gemini API key、GCP service account）走環境變數或 secret manager；`.env` 已列入 `.gitignore`。
5. **不做未要求的範圍擴張**：依 Roadmap 的 P0→P4 順序，每完成一個里程碑停下來驗收。

## 專案結構

```
pf-pro-rebuild/
├── README.md               ← 本檔（任務簡介）
├── docs/
│   ├── 01-architecture.md  ← 架構決策（為什麼選這些技術）
│   ├── 02-functional-spec.md ← 功能規格：公式、golden vectors、UI 範圍
│   └── 03-roadmap.md       ← 里程碑 M0–M4 與驗收標準
├── src/pfpro/
│   ├── __init__.py
│   └── engine.py           ← 【待實作】核心計算引擎（P0 唯一交付物）
├── tests/
│   ├── vectors.json        ← 已驗證的輸入/輸出對（來自原版工具實測）
│   └── test_engine.py      ← pytest 驗收合約
├── infra/terraform/        ← 【M2 待實作】GCP Cloud Run + Terraform
└── web/                    ← 【M4 待實作】React 前端
```

## 背景一句話

香港保險顧問銷售整付分紅保單的保費融資方案時，需要計算客戶首付、槓桿、逐年 IRR，以及利率/紅利實現率的壓力測試。本專案重建一個乾淨、可部署、可測試的開源版本。
