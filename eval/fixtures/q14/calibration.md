# q14 開跑前的固定與紀錄

第 3 節：「pinned」「frozen」的東西在**第一次開跑評測前 commit**。下面每一步在任何一組開跑前做完，結果填在本檔、commit；之後不改。這裡不啟動任何 embedding／rerank 伺服器，也不拿任何模型試 `data.json`：凍結的是輸入，不是預期答案。

## 1. 固定 openai client 與評分用 Python

| 項目 | 值 |
|---|---|
| 評分用 Python（來源、版本、SHA-256） | |
| openai 版本 | |
| `pip install --require-hashes` 用的 requirements（含相依套件與雜湊）存放位置 | |
| 記錄日期 | |

確認：`/eval` 上的 Python 能 `import openai`，印出的 `openai.__version__` 等於上表。

## 2. dev image 與沙盒

| 項目 | 值 |
|---|---|
| dev image digest | |
| `nproc` | （必須是 4） |
| 記憶體上限（`/sys/fs/cgroup/memory.max`） | （必須是 8589934592） |
| `nvidia-smi` | （必須不存在） |
| CPU 型號 | |
| `mem_peak.py read` 的 method | （有 `memory.peak` 最好；沒有時記下，評分改用 `watch`） |

## 3. 擋外連與外連監測

1. 決定擋法（`needs.json` 第 3 項），寫下實際用的指令或旗標。
2. 在擋住的沙盒裡（先 `apt-get install -y strace`，再擋）：
   ```bash
   python3 /eval/q14/egress_check.py probe --log /results/probe.json        # exit 0 = 擋住
   python3 /eval/q14/egress_check.py selftest --log /results/selftest.json  # ok 必須是 true
   python3 /eval/q14/egress_check.py run --log /results/quiet.json -- sleep 10
   ```
   `selftest` 故意連 RFC 5737 的測試位址（192.0.2.1、198.51.100.1），監測必須兩個都記到；`quiet.json` 必須是 0 次外連嘗試（沒有背景雜訊）。

| 項目 | 值 |
|---|---|
| 擋法與指令 | |
| strace 版本 | |
| `selftest` 的 monitor 與結果 | |
| `quiet.json` 的 attempt_count | （必須是 0） |
| `probe` 的 blocked | （必須是 true） |

`selftest` 在 `strace+seccomp` 與 `strace` 都失敗時（例如沙盒不允許 ptrace），不要改用 `/proc` 輪詢判過：2026-10-30 在離線容器實測，`/proc` 輪詢抓不到立刻失敗的連線（`detected: []`）。請念誠在開跑前決定替代做法（例如允許 ptrace 的沙盒設定），寫在這裡。

## 4. 本資料夾的自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q14/tests -v
```

| 項目 | 值 |
|---|---|
| 測試結果 | |
| commit | |
