# q02 凍結前校準（待填）

項目 2 的「frozen seeded generator」指第一次開跑前 commit 的 `gen_log.py`（`eval/README.md` 第 3 節）。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、dev image）做完，結果填進本檔並 commit；之後不改。

**還沒做。**

## 步驟 1：egress check 的追蹤方式

照 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 1（`egress.py selftest`，各題共用一次）。管線與重導向由 `egress.py run --sh` 原樣交給 `/bin/sh -c`，`_shared/test_shared.py` 有測。

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
