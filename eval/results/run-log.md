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

## 評分（9.1 C、E，9.2 B）

### 盲測偏好之前念誠已經看到的東西（第 5 節要求在看到任何檢查結果前選；照實揭露）

- 本 session 的報告（念誠在這個 session 直接看得到）：試跑與重跑的 q01、q02 各組首選（q01 對照組 sync-agents-settings、實驗組與 rules-only mcpshare；q02 三組都是 leakguard；作廢的試跑是 q01 對照 cc-switch-cli、實驗與 rules-only sync-agents-settings，q02 對照 ferret-scan、實驗與 rules-only leakguard）；實驗組回 0 個推薦的次數（run1 12/19、各輪合計 51/77）；D5 的違反內容（jevalt、b11、b12）；Meta 404 降級的題號。q01 的盲測偏好因此不是完全盲的；q02 兩組首選相同。
- 協調 session 在 12:3x 轉告念誠「pickfit 的模型組 77 次裡 51 次沒有推薦；rules-only 每次都有」，並說評分會算出其中幾次是正確的「沒有工具符合」。之後所有評分、L1、空答案的細分都先不給念誠，直到他交出偏好表單。
- 沒有任何 L1、L2、L3 的判定在偏好表單之前給念誠。

### 去識別的答案與首選（9.1 C2、C4）

- `blind.py prefer --round run1` → `blind/prefer-run1/`（20 對；form sha256 `eae1ce18…`、key sha256 `dadccead…`）。`blind.py answers --rounds run1 run2 run3 haiku` → `blind/answers-A/`（180 個答案，key `b451a4a8…`）；`--rounds bset` → `blind/answers-B/`（24 個，key `f25faaad…`）。seed 照 9.3 F.2（20261102）。
- 首選的抽取：`extract_picks.py`（新增）——去識別、打亂後的答案逐一送給評分模型（`claude-opus-5-5`，effort low，固定的指示寫在檔頭，回覆存在 `picks-extract.jsonl`），只記錄答案推薦什麼、不判對錯；花費算進評分上限（`grading-spend.json`，A、B 共 $2.70）。抽取的原樣存成 `picks-extracted.csv`。
- 人工修正（`answers-A/picks-corrections.json`，55 筆；B 題組沒有改）：
  - 同一工具的寫法統一（例如 SOPS／SOPS + age、llama-server (llama.cpp)／llama.cpp llama-server、Infinity v2／Infinity、aichat 的各種寫法），讓同一個首選合成一項；安裝方式不合併（例如 brew install sops 與 brew install sops age、Bruno 的 cask 與 formula、Infinity 的兩個 Docker 映像名稱各自一項）。
  - q11、q16 的 [L1] 檢查的是模型（q11：模型可免登入下載、授權；q16：模型授權），所以首選寫成「執行器＋模型」：抽取只寫 Ollama 的 5 筆 q11 依答案原文補上模型；q16 的題目條件寫明「答案原文給的 50 行內的膠水程式算 setup 的一部分」，所以 q16 的 9 筆一律記為 tool（執行器＋模型＋答案的膠水程式），包括抽取記為 custom_script 的 3 筆。
  - q10、q20 的 [L3] 看的是整個答案怎麼說（C4：只能從答案原文判斷的項目逐一評），所以每個答案各自一項（首選後面加 `[answer Axxxx]`，答案編號不透露組別），並把該答案去識別的原文附在那一項的 evidence 裡給評分模型（`l1-A/l1-batch.jsonl` 產生後加上，sha256 `157ef2ba…`）。
  - 「沒有工具符合」：q01 的 A0099、b09 的 A0019、A0023（兩則都先說找不到單一工具全部做到，再給「最接近的」組合）；照 C2 記 no_fit，要做 C6。
- `blind.py l1-batch`：A 批 78 項（1 個答案沒有項目：no_fit）、B 批 18 項（2 個 no_fit）。給念誠的 `l1-form.csv` 在他交出偏好表單之後才給。
- B 題組更正（`answers-B/picks-corrections.json`，2 筆）：b09 的 A0019、A0023 原記 no_fit；但 b09 自己的 [L1] 檢查寫明可以組合多個 server（「each part is named and the combination covers the same steps」），並要求沒有單一 server 全包時寫出缺哪些步驟，所以改記為組合首選（tool），重建 B 批：20 項、0 個沒有項目的答案（key `618d3516…`）。B 批在評分模型讀到之前就換好了。C6 只剩 q01（A0099）。

### 模型評分者（C4 第二評分者、9.2 B 第三評分者）

- `grade.py run`：Claude（`claude-opus-5-5`、effort high）與 Muse Spark Open（Baseten，temperature 0），同一份 `grader_l1.md`、同一批去識別資料；A 批 78 項、B 批 20 項，結果在 `grades/`。花費：評分上限 $20 用了 $4.30（含抽取首選 $2.70）；Baseten $5 用了 $0.90。只描述，以念誠的判定為準；在念誠交出偏好表單前不給他看。

### L2（9.1 C7；Linux 題依題號，兩組第 1 次）

- 執行：`calibrate_box.py --results eval/results/l2`（單一沙盒）與 `l2_boxes.py`（q04、q15、q16 的多沙盒流程），腳本在 `l2/scripts/`，每次的原始輸出在 `l2/<題>-<組>/`，判定與每個判斷在 `l2/l2-results.json`（評分者＝本 session 讀輸出後判；念誠的判定為準）。
- 共同做法：答案的指令在同一個 shell 依序原樣執行、逐行記 exit code；安裝程式要讀 /dev/tty 或問 [Y/n] 時，在 pty 下按 Enter（第 5 節「接受預設值」）；答案只用文字描述的步驟（例如「到 releases 下載 … 解壓」），評分者用映像裡已有的工具照做並記下；`sudo` 在 dev image 沒有，凡答案用到 sudo 的題，評分環境先裝 sudo 套件（9.3 A 的替換，兩組相同）。
- 量測失敗、重做（答案原文不變）：q02 實驗組第 1 次（apt 的 [Y/n] 沒給輸入而中止 → 改成接受預設值）；q04 對照組重做一次只為了留下錯誤訊息（結果相同）；q15 兩組、q16 實驗組第 1 次：評分者的逐行執行器漏掉檔案最後一行（檔尾沒有換行，`read` 讀不到）——q15 漏了模型下載（實驗組是 VAD 模型），q16 漏了 `cmake --build`；修好執行器後重做，第 1 次保留在 `*-attempt1-harness/`。q02–q14 的腳本都用 heredoc（檔尾有換行），不受影響。
- 校準沒做完的題：q13 的凍結 GGUF 與唯讀儲存、q16 的語言辨識器（L2-5）與意義評分者（L2-7）在 calibration.md 都是空白。q13 兩組都在安裝就失敗，所以不影響；q16 的 L2-5、L2-7 記「未實跑（校準沒做）」，q16 因此不算「所有 [L2] 都跑完」的題（D3）。

### C6（「沒有工具符合」的查核）

- 需要做的題：只有 q01（A0099 的主要結論是沒有單一工具全部做到）。b09 的兩則依 b09 自己的檢查項目改記為組合首選，不需要 C6。
- 另開的 agent session：`run.py c6 q01`（新增；`c6_no_fit_search.md` 的固定英文提示原文送出，對照組的隔離，不接 pickfit），valid，$0.241（算進評分上限）。最後一行：`FOUND: cc-switch-cli https://github.com/SaladDay/cc-switch-cli`。結果在 `runs/c6/q01/control/attempt-1/`。
- 念誠的 30 分鐘搜尋（2026-11-02，他自己的帳號，約 30 分鐘；由協調 session 轉述）：
  - Google：貼上 q01 原題。沒有符合的結果；Google 的 AI 回答說沒有這種工具。
  - ChatGPT 網頁版：同樣的提示。建議 mcpfold、sync-agents-settings、agentlink，mcpfold 排第一。
  - 念誠無法確認三個是否符合硬條件，所以三個都和 cc-switch-cli 一樣做 L1 查核（評分模型照 C4 的設定，念誠在他的 L1 時判，附證據）。
  - 順序偏離：這次搜尋是在念誠交出偏好表單之前、讀表單時做的（第 5 節要求的順序是偏好表單在任何檢查結果之前；這次搜尋本身不是檢查結果，但記下來）。
- 還要做：cc-switch-cli、mcpfold、sync-agents-settings、agentlink 與其他答案的 q01 首選由念誠判 L1——任何一個通過 L1，q01 的「沒有工具符合」就被推翻（C6）。

#### L2 結果（Linux 17 題，第 1 次；Mac 題 q08、q11、q12 改由 agent 在 tart 虛擬機做，見下方「Mac 題 L2 的方法變更」）

| 題 | 對照組 | 實驗組 | 對照組沒過的第一個原因 | 實驗組沒過的第一個原因 |
|---|---|---|---|---|
| q01 | fail | fail | L2-3: claude lists fixture-echo | L2-1: `brew install uv` exit 127 |
| q02 | fail | fail | L2-1: rustup under a pty with the default accepted | L2-2: the pipeline `cat app.log | leakguard > clean.log` exit 127 |
| q03 | fail | fail | L2-1: base image | L2-1: base image |
| q04 | fail | pass | L2-1: `sops encrypt .env > secrets.enc.env` exit 1 | — |
| q05 | fail | fail | L2-1: `python3 -m venv ~/docling-env` exit 1 | L2-1: `python3 -m venv ~/.venvs/docling` exit 1 |
| q06 | fail | fail | L2-2: the stdio server `npx -y @ivotoby/openapi-mcp-server ...` cannot start | L2-1: `node --version` exit 127, then the answer's `brew install node` exit 127) |
| q07 | fail | fail | L2-1: `brew install bruno` exit 127, `npm install -g @usebruno/cli` exit 127 | L2-1: `brew install --cask bruno` exit 127, `npm install -g @usebruno/cli` exit 127) |
| q09 | fail | fail | L2-1: `brew install backlog-md` exit 127 | L2-1: method A `go install github.com/steveyegge/beads/cmd/bd@latest` exit 127 |
| q10 | pass | fail | — | L2-4: after `git config --global diff.markdown.wordRegex ...`, `*.md diff=markdown` and `alias.w |
| q13 | fail | fail | L2-1: the answer names `llama-<build>-bin-ubuntu-x64.zip` and says to unzip it | L2-1: downloaded and extracted llama-b12032-bin-ubuntu-x64.tar.gz as the prose says |
| q14 | fail | fail | L2-1: `docker run ...` exit 127 | L2-1: `docker run ...` exit 127 |
| q15 | fail | fail | L2-2: Run A, B and C each stopped at the 600 s limit, exit 124 | L2-2: Run A, B and C each stopped at the 600 s limit, exit 124 |
| q16 | fail | fail | L2-1: `curl -fsSL https | L2-2: the server cannot load the model |
| q17 | fail | fail | L2-1: `curl -fsSL https | L2-1: `less ollama-install.sh && sh ollama-install.sh` exit 127 |
| q18 | fail | fail | L2-1: `pipx install ollmcp` exit 127 | L2-1: `uv tool install --upgrade ollmcp` exit 127 |
| q19 | fail | fail | L2-1: `brew install uv` exit 127, `uv tool install --python 3.12 aider-chat` exit 127) | L2-1: `brew install aider` exit 127 |
| q20 | pass | pass | — | — |
| q08 | not run | not run | macOS 客體沒有巢狀虛擬化（另有對照官方文件的盲評筆記，不是 L2） | 同左 |
| q11 | fail | fail | L2-1：要下載 app、拖進「應用程式」、打開，第一次開啟跳出授權對話框（GUI） | L2-1：安裝第 4 行  exit 1（伺服器晚 1 秒起來的 race；照 C7；不算 race 時是 L2-3 不過，解盲後問念誠） |
| q12 | fail | fail | L2-2：（uv 裝到 ~/.local/bin，不在 PATH） | L2-2：同左（ 也是 exit 127） |

- 通過：對照組 q10、q20（2 題）；實驗組 q04、q20（2 題）。安裝失敗的題照 C7 算實跑過、其餘 [L2] 都不過。
- q15：兩組（同一個工具與做法）的轉錄每次都超過 600 秒。這個沙盒裡編出來的 whisper.cpp `system_info` 沒有列出任何 SIMD 功能，編碼器每 30 秒視窗約 232 秒，但沙盒 CPU 有 avx2／avx512（`l2/q15-cpu-flags/`），基準 openai-whisper small 同樣的沙盒 33–40 秒。可能是在 gVisor 裡編譯的問題、不是答案的錯；照第 2 節記不過，**請念誠決定**。
- 截止（2026-11-03 12:00）前 Linux 17 題兩組都做完，沒有「未實跑」。

### Mac 題 L2 的方法變更（q08、q11、q12；2026-11-02）

- 念誠 11/2 決定：Mac 題的 L2 改由 agent（本 session）執行，不再親手做（`method: human` → `method: agent`）。決定時他還沒交偏好表單，也還沒看到任何檢查結果（由協調 session 轉述）。
- 環境（取代 9.3 E 的「另開乾淨 macOS 使用者帳號」）：這台 Mac（Apple M5、24 GB、macOS 27.2）上的 tart 虛擬機，每一題的每一組從固定 digest 的基底映像 clone 一台全新的，跑完就刪，兩組起點相同。細節（映像 digest、vCPU、記憶體、斷網方式、哪些步驟因為在虛擬機裡而不同）在實跑時記在 `l2/<題>-<組>/run.json` 與本節。
- q11 的虛擬機給 16 GB（題目寫的記憶體），先停掉其他虛擬機。q11、q12 需要 GPU：先在客體裡確認 Metal 可用，不可用就停下回報。斷網的檢查在客體裡關掉網路服務。
- q08（Colima）要在 macOS 客體裡再開虛擬機：只有 `tart run --nested` 對 macOS 客體真的可用時才跑；不行就兩組都記「L2 未實跑」並寫原因。念誠不要在他自己的 Mac 上裝再移除 Docker。
- 不在念誠自己的 macOS 帳號上跑任何答案的步驟。
- 協調 session 11/2 轉述的決定：可以在客體磁碟下載（全在丟棄式 clone 裡）；OrbStack 裡沒有東西在跑時可以結束它，Mac L2 做完再打開（11/2 16:24 結束，當時 orb list 與 docker ps 都是空的）；補做的校準照提案（下面）；q08 的 L2 跑不了時，加一份「每個答案和官方文件的差異」盲評筆記（不是 L2）。

#### 閘門（一台丟棄式 clone，跑任何答案之前；`l2/mac-gate/gate.json`）

- 基底映像：`ghcr.io/cirruslabs/macos-tahoe-base@sha256:4aaa751f…`（本機已有；客體 macOS 26.6.2）。沒用 `pickfit-macos-26`：那是 pickfit 自己驗證用的強化映像（非管理者 sbx 帳號、調高 ulimit），不中立，也不像一般 Mac。
- 巢狀虛擬化：`tart run --nested` 被 tart 拒絕（「macOS virtual machines do not support nested virtualization」），客體 `kern.hv_support` 是 0。所以 **q08 兩組都記「L2 未實跑」**：Colima 要用 Apple 的虛擬化框架開 Linux VM，在 macOS 客體裡做不到；念誠不要在自己的 Mac 上裝再移除 Docker。
- Metal：客體裡 MLX 看得到「Apple Paravirtual device」，GPU 上的矩陣乘法跑得出來。

#### 補做的校準（在任何 q11、q12 實跑之前，兩組相同；協調 session 同意）

- q11 L2-3 盲評：`claude-opus-5-5`，effort high（C4 評分者的設定；Opus 5.5 不接受 temperature）。用 `samples/` 校準：good 四題全 true、offtopic 的 P2 false，和預期相同（`l2/q11-calibration/`）。
- q12 測試模型：`needs.json` 第一個候選 `mlx-community/Qwen2.5-1.5B-Instruct-4bit`，revision `8b403126…`（在閘門 clone 裡跑 `pin_model.py`，模型檔留在 VM 裡；`model_pin.*` commit 進 `fixtures/q12/`）。openai client 固定 3.42.1（PyPI 當時最新，11/1 上架）。
- q16 的 L2-5、L2-7 仍記「未實跑」：發現沒校準時它的輸出已經存在。

#### 做法（`eval/runner/mac_vm.py`、`l2/scripts/mac_baseline.sh`、`_mac_common.py`、`q11.py`、`q12.py`）

- 每題每組：從上述 digest clone 一台新的（16 GB、8 vCPU、無畫面），跑完停機並刪除。指令經 Tart Guest Agent（vsock）送進客體，所以客體斷網時仍控制得到。
- 起始環境（照 CHECKLIST 在 VM 裡做）：映像自己的 `/opt/homebrew`（有很多預裝套件）與 `/etc/paths.d/homebrew` 移到旁邊；新開一個管理者帳號 `evaluser`，自動登入（密碼在客體裡隨機產生、不印出）；用 Homebrew 官方安裝程式裝一份空的 Homebrew（`NONINTERACTIVE=1`，沒有「按 Enter 繼續」），照安裝程式最後的提示把 `brew shellenv` 那行加進 `~/.zprofile`；preflight 要 PASS；拍 before 快照。之後所有步驟都以 `evaluser` 在它自己的圖形登入工作階段裡、用 `zsh -il`（終端機視窗的 shell）執行。
- 和親手做的差異（兩組相同）：`evaluser` 的 sudo 不用密碼（人會在終端機的 sudo 提示輸入）；新帳號第一次登入的設定助理用映像管理者的設定略過（屬於開帳號）；沒有人看螢幕，所以每個關鍵步驟後記下工作階段裡的 app 清單（`lsappinfo`），有對話框就記下並寫明評分者做了什麼。
- zsh 的 `interactivecomments` 在評分者的 shell 打開，讓行尾的 `# ...` 是註解（和 Linux 上的 bash 一樣）；zsh 互動模式的預設會把它當成指令的參數。
- 答案給多個安裝選項時，照抽取首選時記下的安裝方式（9.1 C2「含指定的安裝方式」）；沒有就用第一個（和 Linux 題相同）。標成「選用」的步驟不跑。
- q11 問題的方式：答案的第一種用法 `ollama run tw`，每題一次新的執行、把凍結的題目貼進去（stdin）。答案的 Modelfile 設 temperature 0.6、Ollama 文件沒有可以固定 seed 的環境變數或設定檔，所以 P1–P5 跑 3 次、2 次過算過。記憶體量測（footprint_watch）從第一行安裝前到最後一個回覆後；重算時排除 Tart Guest Agent（以測試帳號身分、從非系統路徑執行）。
- 主機記憶體（2026-11-02 約 17:50）：q11 對照組問第 1 題時主機嚴重換頁（swap 24.7/25.6 GB、可用記憶體約 130 MB、CPU 幾乎全滿；16 GB 的 VM 只有 4.5 GB 留在實體記憶體），第 1 題花了 8 分 50 秒（README 的上限是 10 分鐘）。照協調 session 的規則停下回報（`l2/q11-control/host-memory-stop.json`）；那兩則回覆移到 `replies-attempt1-hostswap`，之後從 P1 重做。協調 session 決定先做 q12、q11 等念誠釋出記憶體或晚上主機空閒時再做；q11 對照組的 clone 用 `tart suspend` 暫停（安裝、模型、記憶體狀態都保留）。
- q12 改用 8 GB 的 clone（1.5B 測試模型用不到 16 GB；協調 session 同意）；之後新開的 clone 都加 `--suspendable`（停用音訊與熵裝置，兩組相同）。
- q12 的評分 venv：映像的 Homebrew Python 移開後跑不起來，macOS 內建的 3.9 又低於 openai 3.42.1 要求的 3.10，改用固定版本的獨立 CPython 3.12.16（python-build-standalone 20261026，SHA-256 驗過），放在 `/var/eval-grader`，不在測試帳號的家目錄與 PATH 裡。對照組因此在 setup 之後先停下，答案的安裝行已在客體裡開始，就讓它自己跑完（每行的 exit code 在 steps.txt），再建 venv、跑檢查（`l2/q12-control/run-phase-stopped.log`）。
- q11 對照組第 3 次（定案，2026-11-02 18:20 起，新 clone 從頭做；第 2 次的暫停狀態還原失敗：tart「failed to restore … invalid argument」，那台 clone 開機時沒加 `--suspendable`）。每組題目前的主機記憶體與每題花的時間（秒）：
  - 第 1 組前：memory_pressure 可用 33%，swap 11.8／13.3 GB，壓力等級 2；P1–P5：97、97、121、16、72。
  - 第 2 組前：可用 37%，swap 11.7／12.3 GB，等級 2；101、90、33、7、105。
  - 第 3 組前：可用 36%，swap 11.6／12.3 GB，等級 2；126、97、42、8、110。
  - 評分者失誤：記憶體量測的停止檔由測試帳號建立，但量測程式以 root 建的資料夾不讓它寫，量測一直到 VM 刪除都沒輸出結果，所以對照組的 footprint 沒量到。對照組的 L2-1 本來就因為要用 GUI 而不過，不影響判定；實驗組改用 sudo 建停止檔。`offline.sh` 的位址檢查因為 PATH 沒有 /sbin 而沒跑（`ifconfig: command not found`），其他斷網檢查都過；實驗組已修。
- q11 實驗組（2026-11-02 19:2x–22:30；一台 clone，`--suspendable`）：
  - 安裝第 4 行 `ollama pull` 失敗：和 `brew services start ollama` 同一秒執行，伺服器晚 1 秒才起來（race；整段貼上也會這樣）。照 C7 是安裝失敗；這個 race 算不算，協調 session 決定解盲後再問念誠，所以其餘項目照跑並記下觀察值。答案的下一步 `ollama create` 會自己下載模型，第一次碰到評分者自訂的 20 分鐘步驟上限而中斷，之後不設上限重跑。
  - 主機記憶體：第一組題目時主機又嚴重換頁（VM 常駐只剩 1.5 GB），停下、乾淨重開客體、從頭問；之後等記憶體（`l2/q11-experimental/host-wait-2026-11-02.log`），swap 15.4 GB、可用 54%、等級 1 時就繼續（協調 session 訂的是約 14 GB；可用記憶體比對照組第 3 次順利跑完時還多，已告知）。
  - 每題前的主機狀態（`steps.json` 的 `host before run R Pn`）：VM 常駐 3.8–5.1 GiB、swap-in 16–889 頁／秒、swap 13.3–14.7 GB、壓力等級 1–2。run 1 P2–P4 的讀數只存在記憶體裡，評分者在題與題之間停掉迴圈時遺失；那三題 ollama 伺服器記的時間是 2 分 20 秒、2 分 10 秒、44 秒。
  - 評分者失誤：10 分鐘上限原本用 perl 的 alarm，停不了 ollama，run 1 P1（模型重複迴圈）跑了 24 分鐘才由評分者停掉，P2 排在它後面（P2 移到 `harness-discarded/`）；改成真的 watchdog。watchdog 的 `sleep` 留著輸出管道，讓每題的步驟都等滿 10 分鐘（題目本身的時間不受影響），之後修正。記憶體分三段量（安裝、create 與第一次題目、重開後），重算時取各段最大值。
- 評分者自己的操作失誤（答案不變，第一次保留）：q11 對照組第 1 次（`q11-control-attempt1-setupassistant/`）：關掉新帳號的設定助理會讓那個帳號登出，記憶體量測因此中斷，整台重來；同一次裡評分者用 `open -a Ollama` 代替「打開」，LaunchServices 還沒登記剛複製的 app 而失敗，重做時改成 `open /Applications/Ollama.app`（等於在 Finder 雙擊）。

### 凍結快照裡的產品錯誤：`gui.tier` 的輸出 schema（2026-11-02 協調 session 通報）

- 錯誤：快照 `4e0dd4b` 的 `worker/src/server.ts:66`，zod 輸出 schema 的 `gui.tier` 只列 `['window', 'ui_rendered']`；驗到功能層級的 GUI 紀錄是 `action_checked`。回應裡只要有這種首選，`find_software`、`find_alternatives`、`get_install_guide` 都會輸出驗證失敗（`isError: true`，「Output validation error: … picks.N.verification.gui.tier: Invalid option」）。修正 5eb1f2c 在 `claude/hotfix-gui-tier`（未合併）；評測部署維持凍結。
- 快照資料裡會觸發的紀錄（`gui.tier` = `action_checked`，10 筆）：breaktimer-app、concessio、itsypad-macos、neon-vision-editor、nip4、portfolio、qelectrotech-source-mirror、quran-companion、sigil、waywallen。
- 有沒有影響評測：沒有。
  - 所有 stream-json（run1–run3、haiku、bset、c6；作廢的不算）裡 pickfit 工具結果共 101 個：`find_software` 76 個、`find_alternatives` 25 個；沒有一個是「Output validation error」，也沒有一個提到上面 10 筆紀錄；`get_install_guide` 沒有被呼叫過。
  - 兩個評測部署的 Worker 事件（D1 匯出，80＋20 筆）沒有任何 `error_excerpt`，`results` 也沒有那 10 筆的 slug。
  - pickfit 工具結果裡的 5 個錯誤（run1 q13 實驗組、run1 q07 rules_only、run2 q13 實驗組、haiku q08、haiku q15 實驗組，都是 `find_alternatives`）是 Claude Code 端的 `InputValidationError`：agent 送出的參數不是合法 JSON，請求沒有到 pickfit。不是這個錯誤，也不算 E 的 `tool_error`（「pickfit 回傳錯誤」）；第 1 次的兩則在 E 標記時另行判斷。

### 偏好表單交回（第 1 次，2026-11-02 約 16:30）

- `blind/prefer-run1/choices.json`：念誠的匯出檔原樣複製（sha256 `84586da7…`；檔內 `form_sha256` = `eae1ce18…`，和表單相同；20 題）。還沒解盲；L1 表單交回前，結果不給念誠。
- 理由欄：大多是空的，只有 6 題平手寫「差不多」。他口述的兩段是整體理由，原文照錄在 `blind/prefer-run1/prefer-notes.md`（語音轉文字，含語助詞）；不要求補填。
- 可能部分解盲（偏好結果的限制）：口述 2 說，他從「查了工具、沒有找到合適的，所以推薦…」這類寫法認得出接了 pickfit 的答案。去識別沒有拿掉這類寫法，表單的「可能透露來源的字」清單也沒涵蓋：清單（`blind.py` 的 TELLS）只列 sandbox、verified、replayed、沙盒、驗證過、實測等字。依 `blind/prefer-run1/blinding-tells.json`（表單 40 個答案逐一比對，組別取自 key）：
  - 去識別本身留下的 `[source]`（原文的 pickfit 或其工具名被換掉的地方）：實驗組 20 個答案裡 19 個有，對照組 1 個。
  - 「查了工具／目錄、沒有找到合適的或沒有測試過的」：實驗組 10 個，對照組 0 個。
  - 「只給建議、沒有在你的電腦上執行指令」：兩組都有（10 與 9），不分得出組別。
  - 20 題裡有 18 題，只有實驗組那邊有前兩種寫法之一。這 18 題的偏好可能不是盲的；報告寫偏好結果時要附上這個限制。
- 順序：口述 1 是讀表單時、交出之前說的；q01 的 30 分鐘搜尋也在交出之前（見 C6）。

### 盲測偏好前的揭露（補充）

- 本 session 在跑 L2 與評分時，過程中的訊息寫出了部分檢查結果（例如 L2 各題哪一組過、模型評分者的通過數）。念誠可以直接看到這個 session；如果他在交出偏好表單前讀了這些訊息，該題的偏好就不是盲的。之後本 session 的訊息不再寫任何結果，結果只寫進 repo 與給協調 session 的筆記。
