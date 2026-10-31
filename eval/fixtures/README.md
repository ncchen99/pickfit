# L2 測試資料

[eval/README.md](../README.md) 第 8 節的測試資料：每題一個資料夾（`q01`–`q20`），各自的 `README.md` 寫 [L2] 項目怎麼做、`calibration.md` 寫第一次開跑前要固定與記錄的事、`needs.json` 列要從外部取得、等念誠決定的東西（**這裡都沒有下載**）。

各題共用的四件事（沒有對外連線、繁體比例、記憶體量測、git diff 改了幾行）只有一份，在 [`_shared/`](_shared/README.md)。

草稿在 2026-10-30 寫成，2026-10-31 commit 並把共用的判定統一到 `_shared/`。

## 自我測試

全部只用本機，不連網、不呼叫模型：

```sh
python3 _shared/test_shared.py
python3 _shared/test_ollama_scope.py
(cd q01 && python3 server/selftest.py)
(cd q05 && python3 test_check_md.py && python3 verify_fixtures.py)
(cd q06 && python3 test_q06.py)
(cd q07 && python3 test_q07.py)
for q in q09 q10 q11 q12; do (cd $q && python3 selftest.py); done
for q in q13 q14 q15 q16; do (cd $q && python3 -m unittest discover -s tests); done
for q in q17 q18 q19 q20; do (cd $q && sh selftest.sh); done
```

2026-10-31 在 macOS（Python 3.9）全部通過。strace 與擋外連的實測在 L2 沙盒做過（2026-10-31，`_shared/calibration.md` 步驟 1、2）。

各題要在 L2 沙盒做的校準（2026-10-31）：q01、q03、q14、q18、q19、q20 照各自的 `calibrate.sh` 經 `eval/runner/calibrate_box.py` 在新的 Modal 沙盒跑，結果填在各題 `calibration.md`，原始紀錄在 `eval/results/calibration/`；cgroup 計數在 `_shared/calibration.md` 步驟 4。

## 產生器重跑（2026-10-31）

每個產生器重跑，與 commit 的檔案或記下的雜湊比對，結果都相同：

| 題 | 產生器 | 比對 | 結果 |
|---|---|---|---|
| q02 | `gen_log.py`（預設 seed，跑兩次） | `app.log` SHA-256 等於 README 第 2 節的 `ac585975…b655d9`；兩次的 `app.log`、`manifest.json` 逐位元相同 | 相同 |
| q03 | `small/make_small.py --check` | `sample.csv`、`tasks.json`、`expected/*.csv` | 相同 |
| q03 | `big/gen_big.sh`（seed 20261028，macOS BSD awk，94 秒） | `big.csv` `0b0fa6e9…5f2ce`、`big.csv.expected_counts.csv` `b5cd81a0…7b206`（`calibration.md` 的參考值） | 相同 |
| q04 | `make_env.py`（v1、v2 各跑兩次） | 兩次逐位元相同 | 相同 |
| q05 | `make_docx.py` | 與 commit 的 `fixture.docx` 逐位元相同 | 相同 |
| q09 | `make_repo.sh` | commit id `56cc386237ac98db667679cfb869d19e4359950a` | 相同 |
| q10 | `make_repo.sh`（三種模式各跑兩次） | 兩次的 HEAD commit id 相同 | 相同 |
| q16 | `build_manifest.py --check` | `manifest.json` | 相同 |
| q17 | `verify_corpus.py --regenerate` | 55 個檔與 `SHA256SUMS` | 相同 |
| q05 | `build_pdf.sh`（固定版本的 Noto Sans TC 與 fontTools，在 dev image 沙盒跑兩次） | 兩次的 `fixture.pdf` 逐位元相同，`verify_fixtures.py` OK | 相同 |

沒有重跑的：q15 `build_clip.py`（錄音等念誠確認後才下載）。

固定版本的工具、模型、字典檔、字型：[PINS.md](PINS.md)。Mac 題的步驟：[_mac/CHECKLIST.md](_mac/CHECKLIST.md)。
