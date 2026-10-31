# q04 凍結前校準（待填）

q04 的檢查項目沒有寫「at freeze」，但量測方式（追蹤、沙盒之間怎麼傳 repo、dev image 有什麼）會影響判定，必須在看到任何答案之前定案。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、dev image）做完，結果填進本檔並 commit；之後不改。

**還沒做。**

## 步驟 1：egress check 的追蹤方式

照 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 1（`egress.py selftest`，各題共用一次）。原本這裡要記的「背景金鑰 agent 在寬限後的連線記不到」已不存在：`egress.py run` 會繼續記錄留在背景的程序，直到 `egress.py stop`（selftest 的 `leftover` 那一項就是在驗證這件事）。

## 步驟 2：沙盒之間傳 repo

在兩個沙盒之間試一次完整的 bundle 流程（不用任何加密工具）：

```sh
# 沙盒 A
sh /opt/eval/fixtures/q04/setup_repo.sh /work/team-app
git -C /work/team-app bundle create /opt/eval/xfer/team-app.bundle --all
# 把檔案複製到沙盒 B 的 /opt/eval/xfer/
# 沙盒 B
git clone /opt/eval/xfer/team-app.bundle /work/team-app
# 沙盒 A 再 commit 一次、重建 bundle、覆蓋 B 的同一個檔
# 沙盒 B
git -C /work/team-app pull --ff-only && git -C /work/team-app log --oneline
```

| clone | pull 拿到新 commit | 複製方式（例如 Modal 檔案 API） | 日期 |
|---|---|---|---|
| | | | |

## 步驟 3：dev image 內容紀錄

依 `needs.json` 的決定建好 dev image，記下：

```sh
git --version; python3 --version; strace -V | head -1
command -v ssh-keygen gpg || true
dpkg-query -W git python3 strace openssh-client 2>/dev/null
```

| image digest | git | python3 | strace | ssh-keygen | gpg | 其他 | 日期 |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## 步驟 4：檢查腳本的對照組

在沙盒 A，用「不加密、直接 commit 明文」當作錯誤的做法，確認 `check_history.sh` 判不過：

```sh
sh /opt/eval/fixtures/q04/setup_repo.sh /tmp/neg && cd /tmp/neg
python3 /opt/eval/fixtures/q04/make_env.py /tmp/neg/.env /opt/eval/state/q04cal/values.txt
git add .env && git commit -qm plaintext
sh /opt/eval/fixtures/q04/check_history.sh /tmp/neg /opt/eval/state/q04cal/values.txt .env
```

預期：5 個值都 `FAIL history`、`FAIL untracked`、`FAIL ignored`、`RESULT FAIL`。

| 結果 | 日期 |
|---|---|
| | |

做完刪掉 `/tmp/neg` 與 `/opt/eval/state/q04cal`（含假值，不保存、不 commit）。
