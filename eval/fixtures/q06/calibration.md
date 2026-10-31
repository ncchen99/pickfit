# q06 校正紀錄（第一次開跑前填寫）

第一次開跑評測前，在評分用的 image 裡照下面的步驟跑一次，把結果填在表格，與測試資料一起 commit。這些步驟只用本資料夾的校正 server（`calib_mcp_server.py`），不涉及任何答案或工具。

## 1. 固定參考 client

| 欄位 | 值 |
|---|---|
| 參考 client 的選擇（本資料夾的 `mcp_ref_client.py`，或 `needs.json` 的其他候選） | |
| `mcp_ref_client.py` sha256（`shasum -a 256 mcp_ref_client.py`） | |
| 其他檔案 sha256（`shasum -a 256 *`） | |

## 2. 在評分 image 裡

前置（root，本資料夾放在 `/opt/eval-q06/`）：

```sh
mkdir -p /work/cal && cd /work/cal
python3 /opt/eval-q06/mock_api.py --port 18080 --log mock_log.jsonl --state mock_state.json &
C="python3 /opt/eval-q06/calib_mcp_server.py --spec /opt/eval-q06/openapi.json --base-url http://127.0.0.1:18080"
E="python3 /opt/eval-q06/egress_run.py --timeout 600"
R="python3 /opt/eval-q06/mcp_ref_client.py"
K="python3 /opt/eval-q06/check_q06.py --mock-log mock_log.jsonl --mock-state mock_state.json"
```

每一步之前清空紀錄：`: > mock_log.jsonl`。

| 步驟 | 指令 | 預期 | 結果 |
|---|---|---|---|
| a | `python3 /opt/eval-q06/egress_run.py --selftest` | `16/16` | |
| b | `python3 /opt/eval-q06/test_q06.py` | 7 個案例都 ok | |
| c | `$E --report s1.json -- $R --report c1.json --stdio -- $C --stdio` 然後 `$K --client-report c1.json --egress s1.json` | 三項都 PASS | |
| d | `$E --report s2.json -- $R --report c2.json --http http://127.0.0.1:18090/mcp --spawn "$C --http-port 18090"` 然後 `$K --client-report c2.json --egress s2.json` | 三項都 PASS | |
| e | `$E --report s3.json -- $R --report c3.json --stdio -- $C --stdio --fault spec-servers` 然後 `$K --client-report c3.json --egress s3.json` | `tool_calls` 與 `egress` FAIL（egress 列出查詢 `items-api.example.internal` 的 DNS 嘗試） | |
| f | `$E --report s4.json -- $R --report c4.json --stdio -- $C --stdio --fault extra-tool` 然後 `$K --client-report c4.json --egress s4.json` | `tools_list` FAIL | |
| g | `$E --report s5.json -- $R --report c5.json --stdio -- $C --stdio --fault startup-egress` 然後 `$K --client-report c5.json --egress s5.json` | `tools_list`、`tool_calls` PASS，`egress` FAIL（server 啟動時連 1.1.1.1:80 被抓到） | |

若 strace 在 sandbox 裡不能用（c、e、g 的 `egress.checked` 不是 true）：寫下錯誤訊息，在 `eval/README.md` 第 9 節追加一小節說明替代做法，兩組都用同一做法。

| 欄位 | 值 |
|---|---|
| 評分 image digest | |
| `dpkg-query -W python3 strace` | |
| `python3 --version`、`strace -V` 第一行 | |
| 校正者、日期時間（台北） | |
