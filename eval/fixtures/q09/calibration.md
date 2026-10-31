# q09 開跑前確認（待填）

第一次開跑評測前，在 L2 的實跑環境（Modal Sandbox）做下列各步，結果填在本檔並 commit。只確認環境與檢查腳本，不跑任何答案。

## 1. dev image

```sh
cat /etc/os-release | head -3
git --version; jq --version; python3 --version
id dev; sudo -n -u dev true && echo sudo-ok     # 依 needs.json 的決定
```

| 項目 | 結果 |
|---|---|
| image digest | |
| 套件清單（`dpkg-query -W` 存檔的 SHA-256） | |
| `dev` 的 uid、是否有 sudo | |
| 確認日期與確認者 | |

## 2. egress 檢查

```sh
# strace 已在 dev image 裡（9.3 B.2），不另外安裝；任何檢查都不把它算進答案
python3 /fixtures/_shared/egress.py selftest --out /tmp/es
```

即 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 1（各題共用一次，結果記在那裡）。另外確認經 `su` 也記得到：`EGRESS_LOG=/tmp/es/su.log sh /fixtures/q09/dev_shell.sh 'getent hosts egress-selftest.invalid; true'` 之後 `python3 /fixtures/_shared/egress.py report --out /tmp/es --labels su` 要是 `fail`（抓到查名稱）。沒過就照 `_shared/README.md` 第 1 節，egress 記「無法檢查」並請念誠決定。

| 項目 | 結果 |
|---|---|
| strace 版本 | |
| 自我測試結果 | |
| 經 `su` 的確認 | |

## 3. 檢查腳本

```sh
python3 /fixtures/q09/selftest.py      # 要印 ALL OK
sh /fixtures/q09/make_repo.sh /tmp/r   # base 要是 56cc386237ac98db667679cfb869d19e4359950a
```

| 項目 | 結果 |
|---|---|
| `selftest.py`（Linux dev image） | |
| `selftest.py`（macOS） | ALL OK（2026-10-30，macOS 27.0.1、git 2.54.0、Python 3.9.6） |
| base commit id | |
