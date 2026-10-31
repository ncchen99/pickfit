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
| `mem_peak.sh read` 的 method | （有 `memory.peak` 最好；沒有時記下，評分用 `watch` 的取樣；`_shared/calibration.md` 步驟 4） |

## 3. 擋外連與外連監測

1. 決定擋法（`needs.json` 第 3 項），寫下實際用的指令或旗標。
2. 在擋住的沙盒裡：
   ```bash
   python3 $SHARED/egress.py probe --json /results/probe.json                   # exit 0 = 擋住
   python3 $SHARED/egress.py selftest --out /results/selftest                   # _shared/calibration.md 步驟 1，各題共用一次
   python3 $SHARED/egress.py run --out /results/quiet --label quiet -- sleep 10
   python3 $SHARED/egress.py report --out /results/quiet                        # 必須是 pass（沒有背景雜訊）
   ```

| 項目 | 值 |
|---|---|
| 擋法與指令 | |
| `selftest` 結果 | （記在 `_shared/calibration.md`） |
| `quiet` 的 report | （必須是 pass） |
| `probe` 的 blocked | （必須是 true） |

strace 不能用時（`selftest` 沒過），不要改用 `/proc` 輪詢判過：2026-10-30 在離線容器實測，`/proc` 輪詢抓不到立刻失敗的連線（`detected: []`）。照 `_shared/README.md` 第 1 節，請念誠在開跑前決定替代做法（例如允許 ptrace 的沙盒設定），寫在這裡。

## 4. 本資料夾的自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q14/tests -v
```

| 項目 | 值 |
|---|---|
| 測試結果 | |
| commit | |
