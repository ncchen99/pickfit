# q04 凍結前校準（待填）

q04 的檢查項目沒有寫「at freeze」，但量測方式（追蹤、沙盒之間怎麼傳 repo、dev image 有什麼）會影響判定，必須在看到任何答案之前定案。下面的步驟在第一次開跑前，在 L2 實跑環境（Modal Sandbox、dev image）做完，結果填進本檔並 commit；之後不改。

**還沒做。**

## 步驟 1：egress check 的追蹤方式

與 q01 `calibration.md` 步驟 7 相同（同一份 `egress/` 檔案），另外加一個 q04 會遇到的情況：加解密工具可能啟動留在背景的金鑰 agent，追蹤不能因此卡住，也不能漏記它的連線。

```sh
F=/opt/eval/fixtures/q04/egress
sh $F/run_traced.sh /tmp/c1.log 'true';                       python3 $F/egress_check.py /tmp/c1.log   # 預期 exit 0
sh $F/run_traced.sh /tmp/c2.log 'getent ahosts example.com';  python3 $F/egress_check.py /tmp/c2.log   # 預期 exit 1
time sh $F/run_traced.sh /tmp/c3.log '(sleep 2; getent ahosts example.com) & exit 0'
python3 $F/egress_check.py /tmp/c3.log   # 預期約 2–3 秒回來；背景程序在 1 秒寬限內沒連線時 exit 0，記下實際結果
python3 $F/egress_check.py --self-test   # 預期 PASS
```

c3 說明：`run_traced.sh` 在指令本身結束後等 1 秒，再讓 strace 脫離留在背景的程序。所以寬限之後才發生的背景連線不會被記到。記下這個限制；若要更長的寬限，在凍結前改 `run_traced.sh` 的 `sleep 1` 並在這裡登記。

| 檢查 | 結果 | strace 版本 | 日期 |
|---|---|---|---|
| c1 | | | |
| c2 | | | |
| c3 | | | |
| self-test | | | |

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
