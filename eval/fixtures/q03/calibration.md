# q03 凍結前校準

項目 2、3 的「frozen fixture CSV」「frozen seeded generator」指第一次開跑前 commit 的 `small/` 與 `big/gen_big.sh`（`eval/README.md` 第 3 節）。項目 3 的記憶體量法必須在看到任何答案之前定案。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、base image）做完，結果填進本檔並 commit；之後不改。

2026-10-31 在 Modal Sandbox（gVisor、base image）做完，紀錄在 `eval/results/calibration/q03-3a/`（不設上限）與 `q03-3b/`（硬上限），腳本 `calibrate.sh`（經 `eval/runner/calibrate_box.py` 執行）。

## 出題時的參考值（不是校準結果）

出題時在本機產生過完整檔案，校準時用來核對：

| 項目 | 值 |
|---|---|
| `big.csv` SHA-256（預設 seed 20261028、目標 2,000,000,000 位元組） | `0b0fa6e979cdc58b3e5a01f951700d69f33bd6be3e7024f45a99f5695ee5f2ce` |
| `big.csv.expected_counts.csv` SHA-256 | `b5cd81a0d5dd11a47a551591ef3f0e3360a0db2efb8daedb11b82a08d7e0b206` |
| 列數、位元組數（`big.csv.meta`） | 12,732,399 列、2,000,000,065 位元組 |
| 產生時間 | mawk 1.3.4（Debian x86_64 容器，在 Apple silicon 上模擬執行）148 秒；macOS BSD awk 118 秒。兩者產生的檔案 SHA-256 相同 |

出題時也在本機 Linux 容器（cgroup v2）觀察到：沒有記憶體上限時，產生 200 MB 檔案後、還沒跑任何工具，memory.peak 已是 208 MB（page cache 被算進去）；設 256 MB 硬上限時，400 MB 檔案仍能寫出、`cat` 讀完（page cache 被回收，memory.peak 停在上限），而一個配置 400 MB 字串的 awk 被 OOM kill（exit 137、memory.events 的 oom_kill 增加）。這是步驟 3 要在 L2 沙盒上確認的現象。

## 步驟 1：base image 基準

```sh
cat /etc/os-release | head -2
awk -W version | head -1
sh /opt/eval/fixtures/q03/check_runtime.sh    # 預期 stdout 空白、exit 0
nproc                                          # 預期 4
```

| image digest | `check_runtime.sh` | awk 版本 | nproc | 日期 |
|---|---|---|---|---|
| `pickfit-eval-l2-base:b39ae9123e77`（`ubuntu:24.04@sha256:78d4744e…2044d`，`eval/results/l2-images.json`）；Ubuntu 24.04.5 LTS | stdout 空白、exit 0 | mawk 1.3.4 20240123 | 4（Modal `cpu=4`，CFS quota 4） | 2026-10-31 |

基準不是空的（例如平台自動放了 python3）時，項目 1 無法照題目判定：先換成不注入 runtime 的執行方式，再填本表。

## 步驟 2：產生器在 base image 的參考值

```sh
time sh /opt/eval/fixtures/q03/big/gen_big.sh /work/big.csv
cat /work/big.csv.meta
sha256sum /work/big.csv /work/big.csv.expected_counts.csv
```

兩個雜湊必須等於上面的參考值；不同時先找原因，不可以直接改成新值。

| big.csv SHA-256 | expected_counts SHA-256 | 列數 | 位元組數 | 產生時間 | 日期 |
|---|---|---|---|---|---|
| `0b0fa6e9…5f2ce`（等於參考值） | `b5cd81a0…7b206`（等於參考值） | 12,732,399 | 2,000,000,065 | 45 秒（3a）、44 秒（3b，953 MiB 硬上限內寫完） | 2026-10-31 |

小檔案的 `make_small.py --check` 在評分者電腦上 6 行 `OK`（2026-10-31，`eval/fixtures/README.md` 產生器重跑表）。

也確認小檔案沒被改過（在評分者電腦上）：`python3 small/make_small.py --check`，預期 6 行都是 `OK`。

## 步驟 3：記憶體量法定案

**3a. 不設上限**（題目原文的量法）。新沙盒，cpu=4、不設記憶體上限，產生檔案後：

```sh
cd /work
sh /opt/eval/fixtures/_shared/mem_peak.sh run /work/cal-baseline_cat.json 'cat /work/big.csv > /dev/null'
cat /work/cal-baseline_cat.json
```

記下 `peak_before`、`peak_after`、`max_anon`（共用的 `mem_peak.sh`，`_shared/README.md` 第 3 節）。若 `peak_after` 比只算工具本身的記憶體大很多（`cat` 幾乎不用記憶體，`peak_after` 卻接近或超過 1,000,000,000），表示 memory.peak 含 page cache，題目原文的量法對任何工具都會不過 → 用 3b。

**3b. 硬上限**（登記的替代規則）。新沙盒，cpu=4、記憶體硬上限 ≤ 1,000,000,000 位元組（Modal 以 MiB 設定時用 953 MiB）、不用 swap：

```sh
sh /opt/eval/fixtures/q03/big/gen_big.sh /work/big.csv                      # 必須能在上限內寫完
sh /opt/eval/fixtures/_shared/mem_peak.sh run /work/cal-limit_cat.json 'cat /work/big.csv > /dev/null'   # 預期 exit 0、oom_kills 0
sh /opt/eval/fixtures/_shared/mem_peak.sh run /work/cal-limit_hog.json "awk 'BEGIN{s=\"x\"; while (length(s) < 1500000000) s = s s; print length(s)}'"   # 預期被 OOM kill：exit 137、oom_kills ≥ 1
cat /work/cal-limit_*.json /sys/fs/cgroup/memory.max
```

兩個對照都如預期，才能用 3b。

**實測（2026-10-31）**：

- L2 沙盒的記憶體 cgroup 是 **v1**，只有 `memory.limit_in_bytes` 與 `memory.usage_in_bytes`；沒有峰值計數（v2 `memory.peak`、v1 `memory.max_usage_in_bytes` 都不存在）、沒有 `memory.stat`、沒有 OOM 計數。所以 `mem_peak.sh` 的值一律是每 0.2 秒取樣的 `usage_in_bytes`（`method` 記為 `sampled memory.current`），`peak_before`、`peak_after`、`oom_kills` 是 null。
- **3a**（cpu=4、記憶體只設 request 4096 MiB、不設上限；`limit` 顯示 353,066,205,184）：`cat` 2 GB 的檔 exit 0、0.12 秒，取樣最大值 2,215,936 位元組，所有程序 RSS 加總最大 40,546,304。→ **讀檔的 page cache 不計入**這個計數。同一個計數會跟著程序自己配置的記憶體走：q14 的探測（`eval/results/calibration/cgroup-probe-4core/`）配置 600 MiB 時是 634,220,544，結束後回到 1,843,200。
- **3b**（cpu=4、硬上限 953 MiB，`limit_in_bytes` 999,292,928，`SwapTotal` 0）：`gen_big.sh` 在上限內寫完、雜湊相同；`cat` exit 0、取樣最大值 2,461,696。1.5 GB 的 awk 字串**讓整個沙盒結束**（Modal 回報沙盒的 returncode 137），不是只有那個程序被 kill、留下 exit 137 與 OOM 計數；跑了兩次都一樣。沙盒裡的 `/out` 因此拿不回來，紀錄是沙盒外收到的 `console.log`。

**定案**（擇一，凍結前 commit）：

| 規則 | 依據（3a／3b 的數字） | Sandbox 參數（cpu、memory） | 日期 |
|---|---|---|---|
| **A（採用）**：memory.peak ≤ 1,000,000,000（3a 顯示 page cache 不計入） | 3a：`cat` 2 GB 時取樣最大值 2,215,936（只有工具本身），不是 page cache 的 2 GB；沒有峰值計數，所以照 `_shared/README.md` 第 3 節用取樣的 `usage_in_bytes`（`MAX_BYTES=1000000000`，每一步的 `result`） | cpu=4；memory request 4096 MiB、不設硬上限（`calibrate_box.py --cpu 4 --memory 4096 --no-memory-limit`） | 2026-10-31 |
| B：硬上限 ≤ 1,000,000,000、無 swap，沒有任何一步被 OOM kill | 不採用：3a 已顯示 page cache 不計入，照上面 3a 的說明用 A；而且 3b 的超量讓整個沙盒結束，看不到那一步的 exit code 與 OOM 計數 | — | 2026-10-31 |

取樣的限制（照實寫進報告）：每 0.2 秒取一次，比 0.2 秒還短的尖峰可能漏掉；配置 1 GB 以上的記憶體通常要更久，所以影響小。

## 步驟 4：時間的參考

在步驟 3 定案的沙盒設定下，跑一個不判定的參考指令，確認 5 分鐘的限制在這個環境合理：

```sh
sh /opt/eval/fixtures/_shared/mem_peak.sh run /work/cal-ref_wc.json 'wc -l /work/big.csv'
```

| `wc -l` 耗時 | 磁碟類型 | 日期 |
|---|---|---|
| 0.307 秒（3a 的設定；3b 的硬上限下 2.07 秒） | gVisor 的根目錄 overlay（`df` 顯示 `none 8.0E`，檔案內容在記憶體裡，讀檔接近記憶體速度）；`/work` 在其中 | 2026-10-31 |

5 分鐘的限制在這個環境綽綽有餘；讀檔比一般本機 SSD 快，報告照實寫明。
