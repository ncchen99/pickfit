# 共用工具的校準（第一次開跑前）

在 L2 的 Linux 沙盒（第 6 項定案的 image）裡做，結果填在下表並在第一次開跑前 commit。各題的 `calibration.md` 不再各自校準 egress 與 OpenCC，改指向這裡。

## 步驟 1：egress 的追蹤在沙盒裡有效

```sh
python3 $SHARED/egress.py selftest --out /tmp/egress-selftest
```

預期 exit 0：`true` 與連 loopback 判 `pass`；連 TEST-NET-1（192.0.2.1）、查 `.invalid` 的名稱、以及背景程序 3 秒後才連 198.51.100.1，三者都判 `fail`（抓得到）。任何一項不如預期，表示 strace 在這個沙盒不能用（例如不允許 ptrace）：egress 項目改記「無法檢查」，請念誠決定替代方式。

| 項目 | 結果 | strace 版本（`strace -V`） | image digest | 日期 |
|---|---|---|---|---|
| selftest | 通過：true、loopback 判 pass；TEST-NET、查 `.invalid`、背景程序 3 秒後的連線都判 fail（抓到）。parser 21／21 | strace 6.8（apt `6.8-0ubuntu2`） | `ubuntu:24.04@sha256:78d4744e…2044d`（linux/amd64）→ `pickfit-eval-l2-dev:4acdd7fff6ab`（im-ROzeGEcvY1kyYQCOgUO4Uf），Modal gVisor | 2026-10-31 |

## 步驟 2：擋外連的方式

用第 6 項定案的方式擋外連後跑：

```sh
python3 $SHARED/egress.py probe --json /tmp/probe.json   # 預期 exit 0（blocked: true）
```

記下 `dns_resolves`（Modal 的 resolver 在擋網路的沙盒裡仍會回答，屬預期，不影響判定）。若用 `egress.py run --block-network`（network namespace），另跑一次 `python3 $SHARED/egress.py run --out /tmp/ns --label ns --block-network -- python3 $SHARED/egress.py probe`，`ns.json` 的 `netns.ok` 要是 `true`。

| 方式 | probe 結果 | dns_resolves | 日期 |
|---|---|---|---|
| 正向對照：網路開著，直接跑 `probe` | 1.1.1.1:443、8.8.8.8:53、9.9.9.9:443 連得到，UDP DNS 有回應（IPv6 沒有路由）；`blocked: false` | true | 2026-10-31 |
| 反向對照：`run --block-network -- probe`（user＋network namespace，uid 全部對應） | 全部 `Network is unreachable`；`blocked: true`；`netns.ok: true`，只有 `lo`，loopback 自我測試成功 | false | 2026-10-31 |
| 擋住時 strace 照樣記錄：`run --block-network` 裡查 example.com | 15 次 port 53 的 connect（172.21.0.1、1.1.1.1、8.8.8.8），都 ENETUNREACH，report 判 fail | — | 2026-10-31 |

單純的 `unshare(CLONE_NEWNET)` 在這個沙盒是 EPERM（root 沒有 CAP_SYS_ADMIN），所以 `egress.py` 自動改用 user＋network namespace；namespace 裡 `su dev` 正常、uid 1001 的檔仍屬 1001。原始輸出在 `eval/results/l2-images.json` 的 `dev.inspected`。

## 步驟 3：OpenCC 字典

照 `needs.json` 取得同一個 tag 的四個檔，放在 `$OPENCC`，記下：

| tag | STCharacters.txt | STPhrases.txt | TSCharacters.txt | TWVariants.txt | 日期 |
|---|---|---|---|---|---|
| | sha256 | sha256 | sha256 | sha256 | |

確認：`python3 $SHARED/zh_script.py --dict-dir $OPENCC probe 台后里着為为們们` 印出 台、后、里、着 是 neutral，為、們 是 traditional，为、们 是 simplified。

## 步驟 4：cgroup 記憶體計數

在 q03、q14 的沙盒設定下各跑一次 `sh $SHARED/mem_peak.sh read /tmp/mem.json`，記下 `cgroup`（v2、v1 或 none）以及 `peak_after`、`max_current` 是不是 null。page cache 算不算由 q03 的 `calibration.md` 步驟 3 決定。

| 題 | cgroup | 有峰值計數 | 有 memory.current | 日期 |
|---|---|---|---|---|
| q03 | | | | |
| q14 | | | | |
