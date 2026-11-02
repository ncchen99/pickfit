# P6 執行紀錄

只記執行的事實；評分與結果另外寫。時間是台北時間。

## 開跑前的快照（A3，`versions-before.json`）

- 記錄時間：2026-11-02T07:54:30+08:00（協調 session 11/2 送來「snapshot ready」之後）
- pickfit commit：`4e0dd4b382fa0e49794212251f484775a3f56b2e`（main，協調 session 的快照）；本分支 HEAD `864f537549` 只多了 `eval/` 的 commit，eval/ 以外的 tree `1ab18b47a5857082…` 與快照 commit 相同
- 資料：`data/software` 768 筆，`data_sha256` `acb3891c32173105a6521ed0a93b047500363b547c07db8a4e7b3e0d3b6cb3e2`（與協調 session 給的值相同；兩個評測部署的 `/` 也回這個值）
- 實驗組：`pickfit-mcp-eval.ncchen99.workers.dev`（env `eval`），deployment `418c4c68-59c0-4f97-8529-88847f194d3c`、version `bb5215d3-3f7a-4b7d-bf7e-6bfc9efff12c`；`tools=readonly`、`match_mode=model`、768 筆、`index_built_at` 2026-11-01T23:49:26.706159Z
- rules-only：`pickfit-mcp-eval-rules.ncchen99.workers.dev`（env `eval-rules`），deployment `0714f636-d6ea-4b42-92a6-66a87c385bcd`、version `fe7b37fa-416e-43df-9cb1-f4e150e49101`；`tools=readonly`、`match_mode=off`、768 筆、`index_built_at` 2026-11-01T23:49:46.536329Z
- Claude Code：`2.1.304 (Claude Code)`，執行檔 `/Users/ncchen/.pickfit/eval/claude-2.1.304`，sha256 `b9ac5374839f14abf3f1f45610637c332b5daee5ce0d1634726cef87aab78e6a`；模型 `claude-opus-5-5`；每次執行 `DISABLE_AUTOUPDATER=1`
- config.json sha256 `674d0b16aaeff5ef…`、questions.yaml `2e5a2bb0e20f5790…`、questions-b.yaml `493cd75597d05124…`
- 原始沙盒紀錄（D5）：660 筆、缺 0 筆；Windows 的 9 筆來自 `~/.pickfit/eval/windows-raw`（念誠的 Windows 主機，逐位元相同，協調 session 轉交）；manifest sha256 `d0626a8ec7fdab88…`
- 候選庫：20 個 `runs/pipeline.db` 的唯讀副本（2026-11-02T07:52:03+08:00 以 SQLite backup 做成，`~/.pickfit/eval-snapshot-20261102/candidates/`），合併雜湊 `007054d8377ee6c6…`，漏斗雜湊 `55753da73c9bd597…`：

| 名稱 | 來源 | 位元組 | sha256 |
|---|---|---|---|
| main | `runs/pipeline.db` | 125,325,312 | `31f5bc7275579d98…` |
| admiring-swartz-eb5316 | `.claude/worktrees/admiring-swartz-eb5316/runs/pipeline.db` | 454,410,240 | `e18066dcafb0bcd2…` |
| adoring-mahavira-fe5ad3 | `.claude/worktrees/adoring-mahavira-fe5ad3/runs/pipeline.db` | 666,558,464 | `2ca2b71e4cd393e8…` |
| agitated-volhard-165dd4 | `.claude/worktrees/agitated-volhard-165dd4/runs/pipeline.db` | 460,517,376 | `072eab826d433241…` |
| angry-wozniak-e9d6ae | `.claude/worktrees/angry-wozniak-e9d6ae/runs/pipeline.db` | 125,325,312 | `bfd0bc1a983e0c66…` |
| busy-gould-52e234 | `.claude/worktrees/busy-gould-52e234/runs/pipeline.db` | 70,836,224 | `0aedf4e19fd12733…` |
| festive-torvalds-46cda9 | `.claude/worktrees/festive-torvalds-46cda9/runs/pipeline.db` | 460,509,184 | `ddce3ee781d573ad…` |
| gpu-mic-7230b0 | `.claude/worktrees/gpu-mic-7230b0/runs/pipeline.db` | 460,517,376 | `072eab826d433241…` |
| happy-hugle-c03caa | `.claude/worktrees/happy-hugle-c03caa/runs/pipeline.db` | 125,325,312 | `bfd0bc1a983e0c66…` |
| mcp-batch2-d1d2501 | `.claude/worktrees/mcp-batch2-d1d2501/runs/pipeline.db` | 300,699,648 | `b715041961aca1d0…` |
| mcp-category-84d365 | `.claude/worktrees/mcp-category-84d365/runs/pipeline.db` | 207,851,520 | `8e0f35bf67b3e752…` |
| mystifying-swanson-ebc2d2 | `.claude/worktrees/mystifying-swanson-ebc2d2/runs/pipeline.db` | 125,325,312 | `02102e1ab6fe7615…` |
| practical-bose-d8c240 | `.claude/worktrees/practical-bose-d8c240/runs/pipeline.db` | 143,360 | `a8c6b099026d6dda…` |
| priceless-edison-336a22 | `.claude/worktrees/priceless-edison-336a22/runs/pipeline.db` | 260,472,832 | `11a927298aeb3b20…` |
| quizzical-curie-d5e85e | `.claude/worktrees/quizzical-curie-d5e85e/runs/pipeline.db` | 70,836,224 | `701123c565557ad9…` |
| reverent-swartz-a2ce44 | `.claude/worktrees/reverent-swartz-a2ce44/runs/pipeline.db` | 460,509,184 | `ddce3ee781d573ad…` |
| sad-hodgkin-782a4d | `.claude/worktrees/sad-hodgkin-782a4d/runs/pipeline.db` | 670,019,584 | `1a6dafde3598c29d…` |
| show-hn-channel-fd0eaa | `.claude/worktrees/show-hn-channel-fd0eaa/runs/pipeline.db` | 633,626,624 | `9145ac0880dd94bc…` |
| web-sources-9da983 | `.claude/worktrees/web-sources-9da983/runs/pipeline.db` | 686,211,072 | `03d5b3095eab3a52…` |
| wonderful-kare-ec8081 | `.claude/worktrees/wonderful-kare-ec8081/runs/pipeline.db` | 241,664 | `ac7d2ee7edf4acfc…` |

快照當時沒有 `runs/pipeline.db` 的 worktree（例如 web-verify、web-product、p6-eval）不在表上。內容相同的副本（例如 agitated-volhard 與 gpu-mic）照樣各列一份。

第一次 before 快照（07:52）因為 Cloudflare 對 urllib 預設 User-Agent 回 1010（403），兩個部署的 `/` 都沒讀到；`864f537` 加上 User-Agent 後重做（07:54），失敗的那份放在 repo 外。這之間對兩個評測部署只有讀 `/`（健康檢查，不呼叫工具、不呼叫模型），還沒跑任何一題。

## 試跑：q01、q02（B1：算正式的第 1 次）

- 指令：`run.py run1 --until q02`，執行器 commit `384a1d2`（含 A3 紀錄）；`TMPDIR` 是系統的 `/var/folders/g7/…/T/`。
- 開跑 2026-11-02 07:56:20，停在 q02 之後 08:03:16（`run1-paused.json`）。順序照 B1：q01 對照 → 實驗 → rules-only；q02 實驗 → 對照 → rules-only。

| 題 | 組 | 開始 | 秒 | 回合 | 花費 | pickfit 呼叫 | 有效 |
|---|---|---|---|---|---|---|---|
| q01 | control | 07:56:20 | 101.3 | 13 | $0.248 | — | True |
| q01 | experimental | 07:58:01 | 51.4 | 6 | $0.134 | find_software | True |
| q01 | rules_only | 07:58:52 | 43.7 | 6 | $0.127 | find_software | True |
| q02 | experimental | 07:59:36 | 80.2 | 7 | $0.136 | find_software | True |
| q02 | control | 08:00:56 | 87.2 | 8 | $0.178 | — | True |
| q02 | rules_only | 08:02:23 | 52.1 | 5 | $0.127 | find_software | True |

- 合計 $0.950（Anthropic，結果訊息的 `total_cost_usd`）；B4 預估第 1 次 $9.50（上限 $30）。Meta：`pickfit-eval` 兩次配對 $0.0319（D1 `meta_budget`），`pickfit-eval-rules` $0。
- B2 核對（`check --round run1`）：0 個設定問題；6 次的版本 2.1.304、模型 `claude-opus-5-5`、內建工具只有 WebFetch、WebSearch；實驗組與 rules-only 的 pickfit 都是 connected、工具清單正好 3 個；`permission_denials` 全空；argv 除了 MCP 設定檔與 `mcp__pickfit` 的允許項以外完全相同；同一題三組的 prompt sha256 相同。
- 哪個部署回答：各次資料夾的 `mcp.json` 是設定；D1 事件是伺服器端的證據——實驗組的兩個 rec_id 只在 `pickfit-eval`（`matched_by` muse-spark-1.3、Meta 200），rules-only 的兩個只在 `pickfit-eval-rules`（`matched_by` rules、`degraded_reason` model_off），時間都落在該次執行之內。
- D5（`d5_check.py --rounds run1`）：0 違反、34 筆主張找得到、0 無法檢查（`d5-run1.json`）。
- 對照組的污染掃描：兩題對照組的 WebSearch／WebFetch 都沒有碰到 pickfit 的網址；`pickfit` 字樣只出現在 init 事件的工作目錄與記憶路徑（見下）。
- **發現的問題（暫停，等念誠決定）**：暫存資料夾名稱是 `pickfit-eval-<題號>-<組別>-…`，Claude Code 把工作目錄與記憶路徑（在 HOME 底下）放進受測 agent 的上下文，所以三組的上下文各自含有「pickfit」與自己的組名。`324145f` 改成沒有前綴的 `mkdtemp()`，還沒用它跑任何一次。

## 作廢試跑、重跑 q01、q02（B2）

- 念誠在 09:46 前選擇把資料夾名稱當成設定錯誤（B2）：`run.py void --round run1 --group <組>` 三組各做一次（09:46:43–09:46:45），6 次移到 `runs/voided/run1-<組>-<時間>/`，保留供報告；試跑的 `run1-estimate.json`、`run1-paused.json`、`d5-run1.json` 移到 `runs/voided/run1-markers-20261102-094646/`（commit `a833413`）。
- 重跑：`run.py run1 --until q02`，執行器 `324145f`（暫存資料夾用沒有前綴的 `mkdtemp()`），其餘設定與快照不變（A3 紀錄同一份；eval/ 以外沒動）。開跑 09:46:58，停在 q02 之後 09:52:50。順序同 B1。

| 題 | 組 | 開始 | 秒 | 回合 | 花費 | pickfit 呼叫 | 有效 |
|---|---|---|---|---|---|---|---|
| q01 | control | 09:46:58 | 95.6 | 11 | $0.196 | — | True |
| q01 | experimental | 09:48:33 | 49.3 | 5 | $0.123 | find_software | True |
| q01 | rules_only | 09:49:23 | 45.2 | 7 | $0.139 | find_software | True |
| q02 | experimental | 09:50:08 | 68.3 | 6 | $0.112 | find_software | True |
| q02 | control | 09:51:16 | 46.2 | 4 | $0.097 | — | True |
| q02 | rules_only | 09:52:02 | 48.0 | 5 | $0.125 | find_software | True |

- 合計 $0.792；B4 預估第 1 次 $7.92（上限 $30）。執行器的 B4 花費只算 `runs/run1/`，作廢的 $0.950 不算進第 1 次的上限；到這裡 Anthropic 實際花在第 1 次的是 $1.742。Meta：`pickfit-eval` 重跑兩次配對 $0.0331（`meta_budget` 2026-11-02 UTC），試跑另有 $0.0319；`pickfit-eval-rules` $0。
- B2 核對：0 個設定問題；6 次都是 2.1.304、`claude-opus-5-5`、`permission_denials` 空；argv 只差 MCP 設定檔路徑與 `mcp__pickfit` 允許項；同一題三組的 prompt sha256 相同；`mcp.json`：對照 `{}`、實驗 `pickfit-mcp-eval`、rules-only `pickfit-mcp-eval-rules`；兩個 MCP 組的 pickfit 都 connected。
- init 事件掃描（不含 mcp_servers、tools；兩個 MCP 組的伺服器都叫 pickfit）：6 次的工作目錄都是 `/private/var/folders/g7/…/T/tmpXXXXXXXX/work`，找不到 pickfit、組名、題號、eval、Software-Advisor、ncchen、worktree 字樣。
- 哪個部署回答（D1）：實驗組 `rec_db6b3272…`（09:48:38）、`rec_f962b07a…`（09:50:13）只在 `pickfit-eval`，`matched_by` muse-spark-1.3、Meta 200；rules-only `rec_5d2f1b08…`（09:49:28）、`rec_79305247…`（09:52:07）只在 `pickfit-eval-rules`，`matched_by` rules、`model_off`；時間都落在該次執行之內。兩個資料庫裡另外只有試跑的 4 筆。
- 對照組污染：兩題對照組的串流裡沒有 pickfit 或 ncchen99；搜尋與讀取的網址都不是 pickfit 的。
- D5：0 違反、34 筆主張找得到、0 無法檢查（`d5-run1.json`）。結果裡沒有金鑰。
- 觀察（不是流程問題）：實驗組兩題的 pickfit 仍回 0 個推薦（沒降級），agent 改用網路搜尋；rules-only 各回 3 個。
- B3 的 24 小時：執行器從重跑的 q01（09:46:58）起算；第一次試跑的 q01 是 07:56:20。兩種算法都會在報告寫出。

## 第 1 次：q03–q20（接在重跑之後）

- 指令：`run.py run1`（從 q03 接續；q01、q02 已完成的格子跳過），執行器 `324145f`。開跑 09:54:06，`run1-complete.json` 10:35:18。
- 60 格全部有效、每格 1 次（0 次無效、0 次重試）；第 1 次合計 $6.403（上限 $30；另有作廢的試跑 $0.950）。`within_24_hours` true（09:46:58–10:35:18）。

| 組 | 次數 | 花費合計 | 平均花費 | 平均秒 | 平均回合 |
|---|---|---|---|---|---|
| control | 20 | $1.899 | $0.095 | 41.4 | 2.9 |
| experimental | 20 | $2.060 | $0.103 | 52.3 | 3.5 |
| rules_only | 20 | $2.444 | $0.122 | 47.5 | 3.9 |

- B2 核對（`check --round run1`）：0 個設定問題。init 掃描：60 次的工作目錄都是中性的 `tmpXXXXXXXX/work`，沒有 pickfit、組名、題號等字樣；對照組都沒有 MCP 伺服器，兩個 MCP 組都是 pickfit connected。對照組的工具輸入都沒有 pickfit 或 ncchen99，也沒有拿到任何 rec_id。
- pickfit 呼叫：實驗組 find_software 15、find_alternatives 5；rules-only 13、6。其中各有 1 次是 Claude Code 在送出前就擋下的 `InputValidationError`（agent 寫出無法解析的 JSON；q13 實驗組、q07 rules-only 的 find_alternatives），沒有到伺服器，agent 之後重送；B2 不算無效（不是 API 錯誤、也不是執行器當掉）。
- 伺服器端（D1）：實驗組 19 個 rec_id 都只在 `pickfit-eval`（`matched_by` muse-spark-1.3、沒有降級、`model_statuses` 都是 [200]）；rules-only 18 個都只在 `pickfit-eval-rules`（rules、`model_off`）；每筆的時間都在該次執行之內；09:46:58 之後兩個資料庫沒有任何串流裡找不到的事件。
- Meta：`meta_budget` 2026-11-02（UTC）23 次呼叫、$0.4185＝19 次配對的 `meta_cost_usd` 合計；多出的 4 次是 `expand.ts` 的關鍵字擴充（同一筆事件的費用已含在內）。加上試跑的 $0.0319，評測部署的 Meta 合計 $0.450（上限每天 $10）。
- 實驗組 19 次 pickfit 回應裡 12 次回 0 個推薦（q01–q07、q08 的 alternatives、q09、q10、q12、q14）；rules-only 18 次都有推薦。只記事實，評分另做。
- D5（`d5_check.py --rounds run1`）：**1 次違反**、376 筆主張找得到、2 筆無法檢查（`d5-run1.json`）。
  - 違反：q14 rules-only 的 find_software，`jevalt`、linux x86_64，features.checked 三項（`python3 /tmp/check_f1.py`、`check_f2.py`、`check_f3.py`）。開跑前 commit 的比對規則（a1a8ab4）要求 replay 裡有「完全相同指令」的通過檢查；原始紀錄 `verify-jevalt-20261101-163415-6a0e`（festive-torvalds worktree）的 replay 檢查指令是把 heredoc 寫檔與 `python3 /tmp/check_fN.py` 合成一行（`cat > /tmp/check_f1.py << 'PY' … PY\npython3 /tmp/check_f1.py`），三項都通過、印出預期訊號，feature_judge 三項都是 shows_it_working；資料檔把 heredoc 拆成 setup、指令只留最後一行。照開跑前的規則仍算 1 次違反（D5 的寫法：寫明次數與內容）；比對規則沒有改。
  - 無法檢查：q07 rules-only、q13 實驗組各 1 則 find_alternatives 回應，就是上面被 Claude Code 擋下的那 2 次（沒有到伺服器，沒有 rec_id、沒有回應內容）。
- 結果裡沒有金鑰（`sk-ant-` 掃描）。

## 補充重跑（第 2、3 次）、Haiku 對照（9.2 C）、B 題組（9.2 E）

- 指令：一個背景工作依序跑 `run.py reruns`、`haiku`、`bset`（前一段結束碼不是 0 就停）；執行器 `324145f`，設定與快照不變。念誠選了繼續之後，照預先登記的順序接著跑。
- reruns：10:38:42–11:43:36；`plan_reruns` 照 B4 估算排第 2、3 次（上限 $100）；24 小時期限 2026-11-03T09:46:58+08:00（從重跑的 q01 起算）。haiku：11:43:36–12:00:43（`claude-haiku-5-5`，其餘同第 1 次）。bset：12:00:43–12:26:31（12 題）。
- 144 次全部有效、每格 1 次（0 次無效、0 次重試）。花費：第 2、3 次 $7.902（上限 $100）、Haiku $0.480（上限 $15）、B 題組 $3.377（上限 $40）。

| 回合 | 組 | 次數 | 花費 | 平均花費 | 平均秒 | 平均回合 | 模型 |
|---|---|---|---|---|---|---|---|
| run2 | control | 20 | $2.062 | $0.103 | 44 | 3.0 | claude-opus-5-5 |
| run2 | experimental | 20 | $2.111 | $0.106 | 55 | 3.5 | claude-opus-5-5 |
| run3 | control | 20 | $1.866 | $0.093 | 45 | 2.7 | claude-opus-5-5 |
| run3 | experimental | 20 | $1.864 | $0.093 | 51 | 3.5 | claude-opus-5-5 |
| haiku | control | 20 | $0.267 | $0.013 | 22 | 2.1 | claude-haiku-5-5 |
| haiku | experimental | 20 | $0.213 | $0.011 | 30 | 2.5 | claude-haiku-5-5 |
| bset | control | 12 | $1.610 | $0.134 | 59 | 4.7 | claude-opus-5-5 |
| bset | experimental | 12 | $1.767 | $0.147 | 70 | 5.8 | claude-opus-5-5 |

- B2 核對（`check --round` run2、run3、haiku、bset）：都是 0 個設定問題；版本都是 2.1.304。
- init 掃描（全部 264 次，排除 mcp_servers、tools、session_id、uuid、model）：工作目錄都是中性的 `tmpXXXXXXXX/work`；以字詞邊界找 pickfit、組名、題號、eval、bset、Software-Advisor、ncchen、worktree 都沒有。對照組都沒有 MCP 伺服器；MCP 組都是 pickfit connected。對照組沒有碰到 pickfit、也沒有拿到 rec_id。
- 伺服器端（D1）：每個 rec_id 都只在該組的部署、時間都在該次執行之內（實驗組：run1 19、run2 18、run3 18、haiku 12、bset 11；rules-only run1 18）；09:46:58 之後兩個資料庫沒有串流裡找不到的事件。
- **Meta 404 降級 5 次**：`pickfit-eval` 有 5 筆 `matched_by` rules、`degraded_reason` model_http、`model_statuses` [404,404]、Meta 費用 $0——11:02:56、11:03:45（run2 q09、q16）、11:27:04（run3 q09）、11:47:04、11:47:28（haiku q05、q06）。前後的呼叫都是 [200]，看起來是間歇的。照 eval/README.md 第 4 節，pickfit 回錯誤或降級都不算無效、照常評分（E 的 `tool_error`）。
- 被 Claude Code 擋下的 pickfit 呼叫（agent 寫出無法解析的 JSON，沒有到伺服器）共 5 次：run1 q07 rules-only、run1 q13、run2 q13、haiku q08、haiku q15（後四次是實驗組），都是 find_alternatives。
- 0 個推薦的實驗組回應：run1 12/19、run2 11/18、run3 13/18、haiku 6/12、bset 9/11；rules-only run1 0/18。只記事實。
- Meta 合計（`pickfit-eval` 的 `meta_budget`）：2026-11-01 UTC 2 次 $0.0319（作廢的試跑），2026-11-02 UTC 91 次 $1.5647（78 次配對＋13 次 `expand.ts` 關鍵字擴充；78 筆事件的 `meta_cost_usd` 合計相同）；共 $1.597。`pickfit-eval-rules` $0。
- D5：
  - 9.1（`d5_check.py --rounds run1 run2 run3`，`d5-run1-run2-run3.json`）：**1 次違反**（就是上面 run1 q14 rules-only 的 jevalt，linux）、518 筆找得到、3 筆無法檢查（run1 q07 rules-only、run1 q13、run2 q13 被擋下的 find_alternatives）。
  - Haiku（`d5-haiku.json`）：0 違反、61 筆找得到、2 筆無法檢查（haiku q08、q15 被擋下的呼叫）。
  - B 題組（`d5-bset.json`，照 9.2 分開列）：**3 次違反**，都是規則 (e)（模型寫的句子裡驗證類字詞與作業系統同句）：
    - b11 實驗組、find_software 的 well_known_option「PostgreSQL MCP Server」、linux：句子是 "…SQL query tools that run on Linux for remote clients…"；比對腳本把 `run on` 列為驗證類字詞。這個選項本身是 `verified: false`，how_we_know 寫明 pickfit 沒裝過、沒確認在 linux 能跑。
    - b12 實驗組、find_software 的 indexio 與 agent-lsp、macos：句子是 "Verified only on linux x86_64, not on macOS, though platforms lists macOS."；第一個 macOS 前面有 not，第二個（platforms lists macOS）離 not 超過腳本的 30 字元窗，所以算成 macOS 的驗證主張，兩個工具各 1 次。
    - 比對腳本沒有改，次數照腳本算；上面是逐筆讀過原文的內容（D5 的寫法：寫明次數與內容）。
- 結果裡沒有金鑰（`sk-ant-` 掃描）。
- Anthropic 合計（評測執行器）：第 1 次 $6.403＋第 2、3 次 $7.902＋Haiku $0.480＋B 題組 $3.377＝$18.163；另有作廢的試跑 $0.950、準備時的管線測試 $0.094，共 $19.207。評分還沒做（上限 $20）。

## 跑完後的快照（A3，`versions-after.json`、`versions-compare.json`）

- 第一次 after 快照（12:29:33）把本 session 還沒 commit 的 `eval/results/` 結果檔記成問題（`uncommitted changes`；比對本身 0 差異）；那份放在 repo 外。結果 commit（`7db57b1`）之後重做：記錄時間 2026-11-02T12:31:05+08:00，problems []。
- `compare`：**0 差異**。pickfit commit `4e0dd4b`、eval/ 以外的 tree `1ab18b47…` 與 commit 相同；served data `acb3891c…`（768 筆）；實驗組 deployment `418c4c68…`／version `bb5215d3…`（model、readonly）、rules-only `0714f636…`／`fe7b37fa…`（off、readonly），兩邊的 `/` 都回同一個 `data_sha256` 與 `index_built_at`；候選庫合併雜湊 `007054d8…`、漏斗 `55753da7…`；evidence manifest `d0626a8e…`；Claude Code 2.1.304、執行檔 sha256 `b9ac5374…`；config、questions、questions-b 的雜湊都沒變。
- 評測執行到這裡結束：2026-11-02 09:46:58（重跑的 q01）到 12:26:31（B 題組最後一格）；作廢的試跑另在 07:56:20–08:03:16。評分（C4、9.2 B 的第三評分者）、E 的輸因標記、L2 還沒做。
