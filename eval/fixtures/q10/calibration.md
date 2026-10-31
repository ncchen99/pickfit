# q10 開跑前確認（待填）

第一次開跑評測前，在 L2 的實跑環境（Modal Sandbox）做下列各步，結果填在本檔並 commit。只確認環境與測試資料，不跑任何答案。

## 1. base image

```sh
# image：ubuntu:24.04 + git（--no-install-recommends）
cat /etc/os-release | head -3
git --version
command -v script && script --version     # 要是 util-linux 的 script（bsdutils 套件）
LANG=C.UTF-8 locale charmap                # 要印出 UTF-8
ls ~/.gitconfig /etc/gitconfig 2>&1        # 都不存在
```

| 項目 | 結果 |
|---|---|
| image digest | |
| git 版本 | |
| `script` 來源與版本 | |
| `LANG=C.UTF-8 locale charmap` | |
| 沒有全域、系統 git 設定 | |
| 確認日期與確認者 | |

## 2. 測試資料與反例

```sh
sh /fixtures/q10/make_repo.sh /work/repo        # commit 要是 cabbea1e89c5dce8e3bd050f0be2f45e23e438d3
sh /fixtures/q10/capture.sh /work/repo /work/neg1.raw 'git diff'
sh /fixtures/q10/capture.sh /work/repo /work/neg2.raw 'git diff --word-diff'
# 複製出來後
python3 extract_spans.py neg1.raw    # L2-2 要 FAIL（整行標記）
python3 extract_spans.py neg2.raw    # L2-2 要 FAIL（預設 word diff）
python3 selftest.py                  # 在 Linux 跑，會多跑 pty 反例；要印 ALL OK
```

| 項目 | 結果 |
|---|---|
| commit id 相同 | |
| neg1：`mode` 與 L2-2 結果 | |
| neg2：`mode` 與 L2-2 結果 | |
| `selftest.py`（Linux） | |
| `selftest.py`（macOS） | ALL OK（2026-10-30，macOS 27.0.1、git 2.54.0、Python 3.9.6；pty 反例另以 BSD script 轉接測過） |
