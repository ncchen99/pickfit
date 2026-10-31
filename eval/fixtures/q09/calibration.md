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
apt-get install -y strace        # L2-1 之後才裝，不影響安裝步驟的檢查
sh /fixtures/q09/egress_selftest.sh /tmp/es
```

要印出 `egress self-test: OK`：`true` 與連 loopback 沒有 egress；連 TEST-NET-1（192.0.2.1）與查 `.invalid` 名稱都抓得到。沒過就改用 README 的斷網備案，並記在這裡。

| 項目 | 結果 |
|---|---|
| strace 版本 | |
| 自我測試結果 | |
| 採用的方式（strace／斷網備案） | |

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
