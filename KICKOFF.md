# KICKOFF — 給 Kimi Code 的啟動指令

把下面這段貼給 Kimi Code 作為第一條訊息（已假設它在本 repo 根目錄工作）：

---

你是這個 repo 的執行工程師。這是一個「保費融資計算器」的 clean-room 重建專案（個人 portfolio 用途）。

**你的第一個任務（M0）**：閱讀 `docs/02-functional-spec.md` 與 `docs/03-roadmap.md`，然後實作 `src/pfpro/engine.py`，直到 `python -m pytest tests/ -v` 全部通過。

規則：
1. `tests/` 裡的 golden vectors 是對外行為合約，**不得修改測試**（若發現合約本身有錯，開 issue 描述，不要直接改）。
2. 引擎只用標準函式庫，保持純函數、無 I/O。
3. 遵循 Conventional Commits，小步提交。
4. 完成 M0 後停下來報告結果，等待下一步指示（M1 FastAPI、M2 Docker+Terraform、M3 GitHub Actions、M4 React 前端）。
5. 規格外的事一律不做的，發現問題先回報。
6. **分支與 PR 工作流**：每個 milestone 用 `feat/m<N>-<名稱>` 分支開發，完成後開 PR，PR 描述寫明驗收標準達成情況；main 只接受 PR 合併，不直接 commit。讓全部進度（branch、PR、後續 CI 狀態）在 GitHub 公開留痕。

**驗收**：`pytest` 全綠 + `python -c "from pfpro.engine import solve_irr, project, stress_matrix, effective_rate; print('ok')"` 成功。

---

## Ricky 自己要先做的事

1. 把 git author 改成你的真實 GitHub email（commit 作者是 portfolio 證據的一部分）：
   ```bash
   git config user.name "Ricky Pang"
   git config user.email "<你的 GitHub email>"
   git commit --amend --reset-author  # 對最後一個 commit；或 rebase 全部
   ```
2. 在 GitHub 開 public repo（建議名：`pf-pro-calculator` 或 `premium-financing-calculator`），push 這個封包作為初始狀態。
3. 之後讓 Kimi Code 在該 repo 上工作，每個 milestone 的進度與 CI 狀態都公開可見——這本身就是給 002 Ambition 職缺的活證據（GCP + Terraform + CI/CD）。
