# q01 凍結前校準（待填）

`eval/README.md` 第 3 節：檢查項目裡的「pinned … at freeze」「pre-freeze calibration」指**第一次開跑評測前 commit**。下面每一步都在第一次開跑前，在 L2 實跑環境（Modal Sandbox、dev image）做完，把結果填進本檔並 commit。commit 之後不改；之後的修正只能在 `eval/README.md` 勘誤區照第 3 節處理。

**2026-10-31 做了步驟 1、3、4、5、6、8**（`calibrate.sh`，經 `eval/runner/calibrate_box.py` 在 dev image 沙盒跑；原始輸出在 `eval/results/calibration/q01/`（sandbox `sb-01M68A1C6XX3Q8T1T42TEG4SQM`））。步驟 2 只做了實測對照（各 agent 自己的 add 指令寫到哪個檔），還沒逐一讀固定版本的文件。做校準時不讀任何答案（還沒有答案），也不讀 pickfit 的資料。

## 步驟 1：固定版本

在 `needs.json` 的候選中選定版本，裝進 dev image。

| 項目 | 版本 | 完整性（integrity／sha256） | 安裝指令 | 日期 |
|---|---|---|---|---|
| dev image（base digest、最終 digest） | `pickfit-eval-l2-dev:4acdd7fff6ab`（im-ROzeGEcvY1kyYQCOgUO4Uf） | base `ubuntu:24.04@sha256:78d4744e…2044d` | `eval/runner/l2_image.py build --variant dev` | 2026-10-31 |
| Node.js | v26.13.0（官方 linux-x64 build；需要 apt `libatomic1` 14.2.0-4ubuntu2~24.04.1，映像沒有，算預先裝好的環境） | sha256 `d28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997` | 解壓到 `/usr/local/node`，PATH 加 `/usr/local/node/bin` | 2026-10-31 |
| Claude Code CLI | 2.1.316（linux-x64 二進位 2.1.316） | sha256 `0b23c8ff73a58c263e88aa740bd8647723141f70dad089df63061858e019c4c3`；二進位 `745e1b196eb475161a185a00f5e1144d7324ec6094e21149eae719fa42481000` | `npm install -g @anthropic-ai/claude-code@2.1.316` | 2026-10-31 |
| Codex CLI | 0.166.0（linux-x64 0.166.0） | sha256 `67ee6f4069d9328956401f54ac202c20369233159058af9f4ec1af731b87f5b7`；二進位 `cbc00a26d3d0e2ceefc4be8891f8a81ef1e349b3b175bc0ae308762bc001fd93` | `npm install -g @openai/codex@0.166.0` | 2026-10-31 |
| Gemini CLI | 0.66.0 | sha256 `269734d35287fbd8ed2982534258ecf4a95f184b6e06e6732e0d6850c28701d9` | `npm install -g @google/gemini-cli@0.66.0` | 2026-10-31 |
| strace | 6.8（apt `6.8-0ubuntu2`，在 dev image 裡） | — | 映像內建 | 2026-10-31 |
| python3 | 3.12.3（apt `3.12.3-0ubuntu2.1`，在 dev image 裡） | — | 映像內建 | 2026-10-31 |

三個 list 指令就是 `claude mcp list`、`codex mcp list`、`gemini mcp list`（`help-*-mcp.txt`）。

也記下三個 agent 的 list 指令實際名稱（預設 `claude mcp list`、`codex mcp list`、`gemini mcp list`）。

## 步驟 2：對照固定版本的文件，確認設定位置與格式

對每個固定版本，讀它的官方文件（或該版本 repo 裡的文件），確認：

1. `seed/locations.json` 列的每個 user／project scope MCP 設定位置都存在於文件中；文件有、這裡沒有的位置要補上。
2. 每個位置寫入的無關設定是該版本接受的 key（不會讓 agent 報錯）。
3. `seed/validate_shape.py` 的 `SHAPES`（stdio 項目的欄位）與文件一致。

需要修改時，直接改 `locations.json`／`validate_shape.py`，在下表寫明改了什麼、依據哪份文件，和本檔一起在凍結前 commit。

| agent | 文件網址與讀取日期 | 位置（scope → 路徑） | 改了什麼（沒有就寫「無」） |
|---|---|---|---|
| Claude Code | （文件未逐一讀，待補） | user：`~/.claude.json`（`claude mcp add --scope user` 實際寫這個檔） | 無 |
| Codex CLI | （文件未逐一讀，待補） | user：`~/.codex/config.toml`（`codex mcp add` 實際寫這個檔） | 無 |
| Gemini CLI | （文件未逐一讀，待補） | user：`~/.gemini/settings.json`（`gemini mcp add -s user` 實際寫這個檔） | 無 |

project scope 的位置（`.mcp.json`、`.codex/config.toml`、`.gemini/settings.json`）還沒用固定版本的文件或 add 指令對照。

## 步驟 3：基準（負對照）

新沙盒、dev image＋三個 agent，照 README 第 5 節步驟 1–3 寫入設定，**不裝任何其他工具**，封鎖對外連線（步驟 6 的方式），不登入，在 `/work/proj` 跑三個 list 指令（`env -i HOME="$HOME" PATH="$PATH" timeout 120 …`）。

預期：每個指令在 120 秒內結束、不要求登入、不列出 `fixture-echo`；Claude Code 列出 `keep-existing`。跑完再執行一次 `seed_configs.py check`，記下 agent 自己有沒有改寫設定檔（只記錄；這是項目 2 要在 agent 指令之前檢查的原因）。

| agent | exit code | 耗時 | 要求登入？ | 輸出摘要 | 跑完後 check 結果 |
|---|---|---|---|---|---|
| Claude Code | 0 | 0.6 秒 | 否 | 健康檢查後列出 `keep-existing`（project 的 `.mcp.json`），沒有 `fixture-echo` | PASS（三個 agent 跑完後 `seed_configs.py check` 一次：每個檔都在、能解析、無關設定沒變） |
| Codex CLI | 0 | 0.4 秒 | 否 | 沒有 server，沒有 `fixture-echo` | （同上） |
| Gemini CLI | 0 | 2.1 秒 | 否 | 沒有 server，沒有 `fixture-echo` | （同上） |

封鎖方式：`egress.py run --block-network`（步驟 6）。Claude Code 的 list 在封鎖下仍嘗試查名稱 30 次（172.21.0.1、1.1.1.1、8.8.8.8 的 port 53，都失敗），Codex、Gemini 0 次；這是 agent 自己的行為，不在項目 4 的範圍（項目 4 只看答案的加入與同步步驟），只記錄。

## 步驟 4：正對照

同樣的環境，用每個 agent **自己的**加入指令（或照文件手動編輯）把 `fixture-echo` 加到 user scope，例如：

```sh
claude mcp add --scope user fixture-echo -- python3 /opt/eval/fixtures/q01/server/fixture_mcp_server.py
codex mcp add fixture-echo -- python3 /opt/eval/fixtures/q01/server/fixture_mcp_server.py
gemini mcp add -s user fixture-echo python3 /opt/eval/fixtures/q01/server/fixture_mcp_server.py
```

（實際語法以步驟 1 的固定版本為準。）然後封鎖對外連線、不登入，跑三個 list 指令，確認都列出 `fixture-echo`（`grep -F -w`）。再對每個 agent 跑 `validate_shape.py`，確認替代檢查在正確設定上也會過。

| agent | 加入方式 | list 列出 fixture-echo？ | validate_shape.py |
|---|---|---|---|
| Claude Code | `claude mcp add --scope user fixture-echo -- python3 …/fixture_mcp_server.py` | 是（`✔ Connected`） | PASS |
| Codex CLI | `codex mcp add fixture-echo -- python3 …/fixture_mcp_server.py` | 是 | PASS |
| Gemini CLI | `gemini mcp add -s user fixture-echo python3 …/fixture_mcp_server.py` | 是 | PASS |

## 步驟 5：替代登記

某個 agent 在步驟 3 不能離線、免登入執行，或步驟 4 列不出已加入的 server，該 agent 在項目 3 改用 `validate_shape.py`。在下表登記，並在凍結前 commit（項目 3 的規定）。

| agent | 用 list 指令或替代 | 原因（引用步驟 3／4 的紀錄） |
|---|---|---|
| Claude Code | list 指令 | 步驟 3、4：封鎖網路、不登入可以跑，列得出加入的 server |
| Codex CLI | list 指令 | 同上 |
| Gemini CLI | list 指令 | 同上 |

沒有 agent 需要替代。

## 步驟 6：封鎖對外連線的方式

決定項目 3 怎麼「egress blocked」，例如：項目 2 做完後對沙盒做檔案系統快照，從快照另開 `block_network=True` 的沙盒；或在同一沙盒用 network namespace（`unshare -rn`，只有 loopback）。驗證：在封鎖的環境裡 `getent hosts example.com` 失敗、`python3 -c "import socket; socket.create_connection(('1.1.1.1', 443), 5)"` 失敗，而 fixture server 的 selftest 仍然 PASS。

| 方式 | 驗證結果 | 日期 |
|---|---|---|
| `egress.py run --block-network`（Modal gVisor 裡是 user＋network namespace，9.3 B.3） | 公開位址與 DNS 都連不到、loopback 可用（`_shared/calibration.md` 步驟 2）；fixture server 在 namespace 裡由 list 指令啟動並連上 | 2026-10-31 |

## 步驟 7：egress check 的追蹤方式

照 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 1（`egress.py selftest`，各題共用一次）。在 q01 的 dev image 沙盒裡做過即可，結果記在那裡。

## 步驟 8：fixture server

`python3 /opt/eval/fixtures/q01/server/selftest.py` 在 dev image 印出 `RESULT PASS`。

| 結果 | python3 版本 | 日期 |
|---|---|---|
| `RESULT PASS` | 3.12.3 | 2026-10-31 |
