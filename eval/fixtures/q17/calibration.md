# q17 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：測試資料、固定的版本與量測方式，在**第一次開跑前** commit（測試資料凍結）。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、commit。**不要在看到任何一組答案後才填或改。**

q17 的檢查項目沒有要固定的模型（模型由答案自己帶），所以這裡只校準兩件事：沙盒與 egress 量測方式（E 段，q17–q20 共用，做一次即可，四題的本檔都寫同一份結果），以及語料在 dev image 裡讀得到（C 段）。

## E. 沙盒與 egress 量測（q17–q20 共用）

在 needs.json 決定好的 dev image 上做。`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q17`），`SHARED` 是 `eval/fixtures/_shared` 在沙盒裡的位置。

| 步驟 | 做法 | 要看到 |
|---|---|---|
| E1 規格 | 用 dev image 開 Modal Sandbox：4 vCPU、16 GiB、無 GPU。跑 `nproc; free -m; uname -a; python3 --version; id` | 4 核、約 16 GiB、python3 ≥ 3.9 |
| E2 封鎖網路 | 沙盒 A（網路開）寫一個檔，`snapshot_filesystem()`；用快照開沙盒 B，`block_network=True`。B 裡跑 `python3 -c "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)"`；再起 `python3 -m http.server 18080 --bind 127.0.0.1 &` 並用 `python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:18080').status)"` 連 | 外連失敗；loopback 回 200；A 寫的檔在 B 裡 |
| E3 egress | 照 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 1、2（各題共用一次）：`python3 $SHARED/egress.py selftest`；B 裡 `python3 $SHARED/egress.py probe` | selftest exit 0；B 的 probe exit 0（`dns_resolves` 只記錄） |
| E4 對照 | B 裡：`python3 $SHARED/egress.py run --out /tmp/eg4 --label lo --sh '<E2 的 http.server 與 client>'`、`stop --out /tmp/eg4 --kill`、`report --out /tmp/eg4` | `result` 是 `pass` |

結果（第一次開跑前填）：

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | |
| E1 輸出 | |
| E2 外連失敗／loopback 成功／快照帶過去 | |
| E3 selftest、probe 結果 | （selftest 記在 `_shared/calibration.md`） |
| E4 result | |
| 記錄人、時間、commit | |

## C. q17 語料

| 步驟 | 做法 | 要看到 |
|---|---|---|
| C1 | 在 dev image 裡 `python3 $F/verify_corpus.py --regenerate` | `ok: 55 files, 5 questions, hashes match` |
| C2（選做） | 在另一個裝了 poppler-utils 的檢查用 image 裡：`for f in $F/corpus/*.pdf; do pdftotext "$f" -; done \| grep -c -E 'HOLDRAVEL-1701\|OLUNOSTOLUN-1589'` | `2` |
| C3 | `sh $F/selftest.sh` | 兩個測試都 `0 failure(s)` |

結果：

| 項目 | 結果 |
|---|---|
| C1 | |
| C2（選做） | |
| C3 | |
| 記錄人、時間、commit | |

寫 fixture 時已在本機（macOS）做過：語料重產生逐位元組相同（Python 3.9、3.12、3.13）；兩個有 token 的 PDF 以 stdlib 解碼、poppler `pdftotext`、Apple PDFKit、pypdf 6.16.2 都讀得到完整 token。這些只是作者的檢查，不代替 C1。
