# q02 凍結前校準（待填）

項目 2 的「frozen seeded generator」指第一次開跑前 commit 的 `gen_log.py`（`eval/README.md` 第 3 節）。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、dev image）做完，結果填進本檔並 commit；之後不改。

**還沒做。**

## 步驟 1：egress check 的追蹤方式

與 q01 `calibration.md` 步驟 7 相同（同一份 `egress/` 檔案）。在 dev image 的沙盒裡：

```sh
F=/opt/eval/fixtures/q02/egress
sh $F/run_traced.sh /tmp/c1.log 'true';                      python3 $F/egress_check.py /tmp/c1.log   # 預期 exit 0
sh $F/run_traced.sh /tmp/c2.log 'getent ahosts example.com'; python3 $F/egress_check.py /tmp/c2.log   # 預期 exit 1
sh $F/run_traced.sh /tmp/c3.log 'echo hi | cat > /tmp/o.txt'; python3 $F/egress_check.py /tmp/c3.log  # 管線、重導向：預期 exit 0，/tmp/o.txt 是 hi
python3 $F/egress_check.py --self-test                       # 預期 PASS
```

q01 已經做過而且是同一個 image 時，可以引用 q01 的紀錄。

| 檢查 | 結果 | strace 版本 | 日期 |
|---|---|---|---|
| c1 | | | |
| c2 | | | |
| c3 | | | |
| self-test | | | |

## 步驟 2：產生器在 dev image 的參考雜湊

```sh
python3 /opt/eval/fixtures/q02/gen_log.py /tmp/q02cal
```

印出的 sha256 必須是 `ac585975926b1d4af3a74b9a75a29e462926053244a182612e151c56b5b655d9`（出題時的參考值）。不同時先找原因，不可以直接改成新值。

| sha256 | 行數 | python3 版本 | 日期 |
|---|---|---|---|
| | | | |

## 步驟 3：檢查腳本的對照組

用不遮任何東西的 `cat` 當過濾器，確認檢查會判不過、一般行會判過：

```sh
cd /tmp/q02cal
cat app.log | cat > clean.log
python3 /opt/eval/fixtures/q02/check_clean.py --manifest manifest.json --input app.log --output clean.log
```

預期：6 個值都 `FAIL`（exact value still present），`ITEM masking FAIL`，`ITEM ordinary PASS`。

| ITEM masking | ITEM ordinary | 日期 |
|---|---|---|
| | | |

做完刪掉 `/tmp/q02cal`（含假值，不保存、不 commit）。
