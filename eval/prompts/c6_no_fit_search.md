# C6：「沒有工具符合」的另開搜尋（固定提示）

依 eval/README.md 第 9.1 節 C6：只在所有執行結束後、某題有答案說「沒有任何工具符合全部條件」時使用；每題只做一次。用 eval/runner/config.json 的同一個 Claude Code 版本與模型、同一套隔離方式（空 HOME、空工作目錄），只給 WebSearch、WebFetch，**不接 pickfit**（`--strict-mcp-config`，MCP 設定是空的）。送出的內容是下面這段英文，`{...}` 換成該題 questions.yaml 的欄位原文；不附任何組別的答案，也不說是哪一組說了「沒有工具符合」。

---

You are checking whether any existing software meets every hard requirement below. Do not run commands or change files on this machine; search and read only.

Need, in the user's words:
{prompt}

Hard requirements:
- OS: {constraints.os}; CPU: {constraints.arch}; budget: {constraints.budget}; must run locally: {constraints.must_run_locally}
{constraints.other, one per line}

The answer passes only if the tool meets each of these, checked against its official repository, documentation or license:
{each [L1] item from success_checklist, one per line}

Search broadly: package registries, GitHub, project sites, and recent releases. For each candidate you check, give its name, official URL, and for every requirement above either the source that shows it is met or the reason it is not. Then answer with one line: either "FOUND: <name> <official URL>" for the best candidate that meets every requirement, or "NONE FOUND" if no candidate you checked meets all of them.
