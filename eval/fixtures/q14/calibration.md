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
| dev image digest | `pickfit-eval-l2-dev:4acdd7fff6ab`（`ubuntu:24.04@sha256:78d4744e…2044d`，`eval/results/l2-images.json`） |
| `nproc` | 4（Modal `cpu=4`；CFS quota 4,000,000／1,000,000；2026-10-31 `eval/results/calibration/cgroup-probe-4core/`） |
| 記憶體上限（`/sys/fs/cgroup/memory.max`） | cgroup v1，沒有 `memory.max`；`/sys/fs/cgroup/memory/memory.limit_in_bytes` 是 8589934592（`--memory 8192` 設成 request＝limit），`MemTotal` 8388608 kB |
| `nvidia-smi` | （必須不存在） |
| CPU 型號 | |
| `mem_peak.sh read` 的 method | `sampled memory.current`：沒有峰值計數，評分用 `watch` 每 0.2 秒取樣的 `memory.usage_in_bytes`（不含 page cache；配置 600 MiB 時 634,220,544）。超過 8 GiB 硬上限時整個沙盒以 137 結束（q03 步驟 3b），記為 OOM kill（`_shared/calibration.md` 步驟 4） |

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
