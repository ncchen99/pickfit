# q05 校正紀錄（第一次開跑前填寫）

第一次開跑評測前，在評分用的 image 裡照下面的步驟跑一次，把結果填在表格。本檔填好後與 `fixture.pdf` 一起 commit（測試資料凍結）。這些步驟只驗證測試資料與檢查腳本，不涉及任何答案或工具。

## 1. 字型與 PDF

1. 依 `needs.json` 選定字型，下載。
2. `python3 make_pdf.py --font <Regular.ttf> [--bold-font <Bold.ttf>]`，把印出的 JSON 貼在下面。
3. `python3 verify_fixtures.py`：兩個檔都要 OK。
4. 用任一 PDF 檢視器打開，確認字形正常、標題較大較粗、表格有框線。

| 欄位 | 值 |
|---|---|
| 字型名稱與字重 | |
| 來源網址、版本或下載日期 | |
| 授權 | |
| Regular 檔 sha256 | |
| Bold 檔 sha256（沒有就寫「無，用描邊粗體」） | |
| `make_pdf.py` 輸出 JSON | |
| `fixture.pdf` sha256、大小 | |
| `fixture.docx` sha256 | `2c6e64426a61dfbb500e672de4f2d62c8d99a9630cfc0d2e1da2b9afc2afef5b`（2026-10-30 產生） |
| `verify_fixtures.py` 結果 | |
| 目視檢查（誰、何時） | |

## 2. 評分 image 與執行包裝

在 Modal Sandbox（4 vCPU、16 GB、沒有 GPU、評分用 image、root）裡，把本資料夾放在 `/opt/eval-q05/`：

| 步驟 | 指令 | 預期 | 結果 |
|---|---|---|---|
| a | `python3 /opt/eval-q05/egress_run.py --selftest` | `16/16` | |
| b | `python3 /opt/eval-q05/test_check_md.py` | `20/20` | |
| c | `python3 /opt/eval-q05/egress_run.py --block-network --report c.json -- python3 -c "import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)"` | 指令失敗；`netns.interfaces` 是 `["lo"]`；`egress.verdict` 是 `fail`，列出 1.1.1.1:80 | |
| d | `python3 /opt/eval-q05/egress_run.py --block-network --report d.json -- python3 -c "import socket; socket.getaddrinfo('example.com', 443)"` | 指令失敗；`egress.verdict` 是 `fail`，列出 53 埠的嘗試 | |
| e | `python3 /opt/eval-q05/egress_run.py --block-network --report e.json -- python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 18999)); s.listen(1); c=socket.create_connection(('127.0.0.1', 18999)); print('ok')"` | 印出 ok、exit 0；`egress.verdict` 是 `pass` | |
| f | `python3 /opt/eval-q05/egress_run.py --report f.json -- python3 -c "import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)"`（不斷網） | `egress.verdict` 是 `fail`（只記錄、不阻擋時也抓得到） | |
| g | `python3 /opt/eval-q05/egress_run.py --block-network --timeout 5 --report g.json -- sleep 30` | exit 124、`timed_out` 為 `true` | |

若 c–e 因為 sandbox 不允許建立網路命名空間或不支援 strace 而無法執行：寫下錯誤訊息，改用替代做法（安裝在可連網的 sandbox 完成後，把檔案系統做成快照，在 `block_network=True` 的新 sandbox 裡轉換），並在 `eval/README.md` 第 9 節追加一小節說明，兩組都用同一做法。

| 欄位 | 值 |
|---|---|
| 評分 image digest | |
| `dpkg-query -W python3 strace` | |
| `python3 --version`、`strace -V` 第一行 | |
| Modal sandbox 設定（cpu、memory、GPU、region） | |
| 本資料夾每個檔的 sha256（`shasum -a 256 *`） | |
| 校正者、日期時間（台北） | |
