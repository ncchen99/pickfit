# q07 校正紀錄（第一次開跑前填寫）

第一次開跑評測前，在評分用的 image 裡照下面的步驟跑一次，把結果填在表格，與測試資料一起 commit。這些步驟只驗證測試資料與檢查腳本，不涉及任何答案或工具。

## 1. 開跑前要確認的判準

下面兩點是本資料夾對檢查項目的操作定義，開跑前請念誠確認（確認後不再改）：

| 定義 | 內容 | 念誠確認 |
|---|---|---|
| 變動行數 | `git diff --numstat` 的新增與刪除取較大者（改一行 = 1 行），上限 3 | |
| 依答案的格式寫請求檔 | 答案至少要有一個請求檔範例或格式說明；範例沒涵蓋的個別語法可查已安裝版本的官方文件，並記錄 | |

## 2. 在評分 image 裡

前置（本資料夾放在 `/opt/eval-q07/`）：

```sh
mkdir -p /work/cal && cd /work/cal
python3 /opt/eval-q07/server.py --mode ok --log log.jsonl &
E="python3 /opt/eval-q07/egress_run.py --timeout 60"
```

| 步驟 | 指令 | 預期 | 結果 |
|---|---|---|---|
| a | `python3 /opt/eval-q07/egress_run.py --selftest` | `16/16` | |
| b | `python3 /opt/eval-q07/test_q07.py` | 7 個案例都 ok（含 4 個 diff 案例） | |
| c | `$E --report c.json -- python3 -c "import urllib.request as u; print(u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:18081/health').read())"` | 印出 `{"ok": true}`；`egress.verdict` 是 `pass` | |
| d | `$E --report d.json -- python3 -c "import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)"` | `egress.verdict` 是 `fail`，列出 1.1.1.1:80 | |
| e | `$E --report e.json -- python3 -c "import socket; socket.getaddrinfo('example.com', 443)"` | `egress.verdict` 是 `fail`，列出 53 埠的嘗試 | |
| f | `python3 -c "import urllib.request as u; print(u.build_opener(u.ProxyHandler({})).open('http://[::1]:18081/x').status)"` | `200`（伺服器同時聽 ::1；sandbox 沒有 IPv6 時記「無 IPv6」） | |

若 strace 在 sandbox 裡不能用（c–e 的 `egress.checked` 不是 true）：寫下錯誤訊息，在 `eval/README.md` 第 9 節追加一小節說明替代做法，兩組都用同一做法。

| 欄位 | 值 |
|---|---|
| 評分 image digest | |
| `dpkg-query -W python3 strace git` | |
| git 放在哪裡（image 裡，或評分者的機器） | |
| 本資料夾每個檔的 sha256（`shasum -a 256 *`） | |
| 校正者、日期時間（台北） | |
