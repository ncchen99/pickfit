# 事後覆蓋率檢查：失分題的正確答案現在收進資料了沒（2026-11-02）

**這是看過評測結果之後的事後檢查**（README 9.1 F 的「看過題目後調整」那一類）。只描述，不改任何事先登記的結果、計數或門檻；不重跑配對，也不判斷會不會被推薦。沒有呼叫任何模型（$0）。產生方式：`python3 eval/runner/coverage.py --out eval/results/final`，逐筆結果在 `post-hoc-coverage.json`。

- **資料版本**：本分支合入 main（到 `b131d6f3`，含 `dd11e240` 與 11/2 晚上用規則 `github-well-known.v1` 加的 102 筆 301–5000 星），`data/software` 共 968 筆。
- **範圍**：有 pickfit 空回應的題（`e-tags/empty-responses.json`，20 題 4 輪與 B 題組），加上第 1 次 E 標記（Claude）含 `tool_error` 或 `not_in_data` 的題。
- **正確答案**：這些題裡任何組、任何一次通過 L1 的首選（`final/answers-l1.json`），加上 q01 的 C6 查核通過的工具。組合型的首選（工具＋模型＋答案自己寫的腳本）拆開，只查軟體那一部分；內建做法（q10）與模型不是軟體紀錄，不查。
- **比對**：先用 repo（答案裡的 GitHub 連結；答案沒附連結的，用評分者指定的官方 repo，見 `coverage.py` 的 `REPO_OVERRIDES`，都用 GitHub API 確認存在）比 `data/software` 的 `repo.full_name`（不分大小寫、去掉結尾的 / 與 .git），找不到再用名稱、別名比。另外用純文字搜尋所有紀錄的 `full_name` 再確認一次。b03 的 Atlas 用名稱會撞到 pickfit 的 `atlas`（Atlas-Inf/atlas，LLM 推論引擎），答案的是 ariga/atlas（資料庫 schema 工具），不算有收。
- **沒收的原因**：照 `pickfit/discover/github.py` 與 `docs/source-terms.md` 的發現規則機械判斷：只搜 **2026 年建立**、**發現前 14 天內有 push**、**5–300 星**（`github-well-known.v1` 是 301–5000 星）的 repo。

## 結果

| 題 | 在範圍的原因 | 正確答案（軟體） | 現在收了 | listed | 驗證到 install 以上 | 沒收的原因 |
|---|---|---|---|---|---|---|
| q01 | E: tool_error；empty response | 3：cc-switch-cli（SaladDay/cc-switch-cli，5423 星，2025 年建立）；mcpfold（dj-pearson/MCPFold，0 星，2026 年建立）；sync-agents-settings（Leoyang183/sync-agents-settings，7 星，2026 年建立） | 0 | 0 | 0 | cc-switch-cli：超過 5000 星、2026 年以前建立；mcpfold：不到 5 星；sync-agents-settings：發現前 14 天內沒有 push |
| q02 | E: tool_error；empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| q03 | E: tool_error；empty response | 2：DuckDB CLI（duckdb/duckdb，42743 星，2018 年建立）；qsv（dathere/qsv，3817 星，2020 年建立） | 0 | 0 | 0 | DuckDB CLI：超過 5000 星、2026 年以前建立；qsv：2026 年以前建立 |
| q04 | empty response | 1：SOPS（getsops/sops，23585 星，2015 年建立） | 0 | 0 | 0 | SOPS：超過 5000 星、2026 年以前建立 |
| q05 | E: tool_error；empty response | 1：Docling（docling-project/docling，70011 星，2024 年建立） | 0 | 0 | 0 | Docling：超過 5000 星、2026 年以前建立 |
| q06 | E: tool_error；empty response | 3：@ivotoby/openapi-mcp-server（ivo-toby/mcp-openapi-server，301 星，2024 年建立）；AWS Labs openapi-mcp-server（awslabs/mcp，9863 星，2025 年建立）；openapi-mcp-generator（harsha-iiiv/openapi-mcp-generator，643 星，2025 年建立） | 0 | 0 | 0 | @ivotoby/openapi-mcp-server：2026 年以前建立、發現前 14 天內沒有 push；AWS Labs openapi-mcp-server：超過 5000 星、2026 年以前建立；openapi-mcp-generator：2026 年以前建立 |
| q07 | E: tool_error；empty response | 2：Bruno（usebruno/bruno，47986 星，2022 年建立）；Hurl（Orange-OpenSource/hurl，19295 星，2020 年建立） | 0 | 0 | 0 | Bruno：超過 5000 星、2026 年以前建立；Hurl：超過 5000 星、2026 年以前建立 |
| q08 | empty response | 1：Colima（abiosoft/colima，31492 星，2021 年建立） | 0 | 0 | 0 | Colima：超過 5000 星、2026 年以前建立、發現前 14 天內沒有 push |
| q09 | E: tool_error；empty response | 1：Beads（gastownhall/beads，28417 星，2025 年建立） | 0 | 0 | 0 | Beads：超過 5000 星、2026 年以前建立 |
| q10 | E: tool_error；empty response | 只有內建做法（不是軟體紀錄） | — | — | — | — |
| q12 | E: tool_error；empty response | 1：mlx-lm（ml-explore/mlx-lm，7533 星，2025 年建立） | 0 | 0 | 0 | mlx-lm：超過 5000 星、2026 年以前建立 |
| q14 | E: tool_error；empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| q15 | E: not_in_data；empty response | 3：faster-whisper（SYSTRAN/faster-whisper，26405 星，2023 年建立）；OpenCC（BYVoid/OpenCC，10089 星，2010 年建立）；whisper.cpp（ggml-org/whisper.cpp，54867 星，2022 年建立） | 0 | 0 | 0 | faster-whisper：超過 5000 星、2026 年以前建立；OpenCC：超過 5000 星、2026 年以前建立；whisper.cpp：超過 5000 星、2026 年以前建立 |
| q16 | E: not_in_data；empty response | 3：Ollama（ollama/ollama，185674 星，2023 年建立）；llama.cpp llama-server（ggml-org/llama.cpp，133152 星，2023 年建立）；mdpo（mondeja/mdpo，34 星，2020 年建立） | 0 | 0 | 0 | Ollama：超過 5000 星、2026 年以前建立；llama.cpp llama-server：超過 5000 星、2026 年以前建立；mdpo：2026 年以前建立、發現前 14 天內沒有 push |
| q18 | empty response | 1：ollmcp（jonigl/mcp-client-for-ollama，833 星，2025 年建立） | 0 | 0 | 0 | ollmcp：2026 年以前建立、發現前 14 天內沒有 push |
| b01 | empty response | 1：nsjail（google/nsjail，4181 星，2015 年建立） | 0 | 0 | 0 | nsjail：2026 年以前建立 |
| b02 | empty response | 1：git-spice（abhinav/git-spice，778 星，2023 年建立） | 0 | 0 | 0 | git-spice：2026 年以前建立 |
| b03 | empty response | 2：Atlas（ariga/atlas，8806 星，2021 年建立）；sqldef's sqlite3def（sqldef/sqldef，3187 星，2018 年建立） | 0 | 0 | 0 | Atlas：超過 5000 星、2026 年以前建立；sqldef's sqlite3def：2026 年以前建立 |
| b04 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| b05 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| b07 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| b09 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| b10 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |
| b11 | empty response | 沒有（任何組、任何一次都沒有首選通過 L1） | — | — | — | — |

**合計**：範圍內 24 題，正確答案（不同的軟體 repo）26 個，現在收進資料 0 個（listed 0、驗證到 install 以上 0）。

## 讀法

- 沒收的原因全部是發現規則本身的範圍，沒有一個是被規則、初篩或驗證擋掉：大多是**超過 5000 星**而且 **2026 年以前建立**的知名工具（Bruno、Docling、SOPS、DuckDB、Colima、Ollama、llama.cpp、whisper.cpp 等）；其餘是 5000 星以下、但 **2026 年以前建立**的工具（qsv、nsjail、git-spice、sqldef、mcp-client-for-ollama、openapi-mcp-generator 等）；q01 的兩個 2026 年新工具，mcpfold **不到 5 星**、sync-agents-settings **發現前 14 天內沒有 push**。
- 11/2 晚上加的 `github-well-known.v1`（301–5000 星）沿用「2026 年建立」與「最近 14 天有 push」的條件，所以這些題的正確答案一個也沒有被它收進來。要收這類工具，得改的是建立年份與星數上限的條件，不是配對。
- 沒有正確答案可查的題：q02、q14（L1 都沒過或判不出來），以及 B 題組的 b04、b05、b07、b09、b10、b11。q10 的正確答案是 git 內建做法，不需要資料。
