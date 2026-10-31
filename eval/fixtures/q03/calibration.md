# q03 凍結前校準（待填）

項目 2、3 的「frozen fixture CSV」「frozen seeded generator」指第一次開跑前 commit 的 `small/` 與 `big/gen_big.sh`（`eval/README.md` 第 3 節）。項目 3 的記憶體量法必須在看到任何答案之前定案。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、base image）做完，結果填進本檔並 commit；之後不改。

**還沒做。**

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
| | | | | |

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
| | | | | | |

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

**定案**（擇一，凍結前 commit）：

| 規則 | 依據（3a／3b 的數字） | Sandbox 參數（cpu、memory） | 日期 |
|---|---|---|---|
| A：memory.peak ≤ 1,000,000,000（3a 顯示 page cache 不計入） | | | |
| B：硬上限 ≤ 1,000,000,000、無 swap，沒有任何一步被 OOM kill | | | |

## 步驟 4：時間的參考

在步驟 3 定案的沙盒設定下，跑一個不判定的參考指令，確認 5 分鐘的限制在這個環境合理：

```sh
sh /opt/eval/fixtures/_shared/mem_peak.sh run /work/cal-ref_wc.json 'wc -l /work/big.csv'
```

| `wc -l` 耗時 | 磁碟類型 | 日期 |
|---|---|---|
| | | |
