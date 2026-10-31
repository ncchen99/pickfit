# 共用工具的校準（第一次開跑前）

在 L2 的 Linux 沙盒（第 6 項定案的 image）裡做，結果填在下表並在第一次開跑前 commit。各題的 `calibration.md` 不再各自校準 egress 與 OpenCC，改指向這裡。

## 步驟 1：egress 的追蹤在沙盒裡有效

```sh
python3 $SHARED/egress.py selftest --out /tmp/egress-selftest
```

預期 exit 0：`true` 與連 loopback 判 `pass`；連 TEST-NET-1（192.0.2.1）、查 `.invalid` 的名稱、以及背景程序 3 秒後才連 198.51.100.1，三者都判 `fail`（抓得到）。任何一項不如預期，表示 strace 在這個沙盒不能用（例如不允許 ptrace）：egress 項目改記「無法檢查」，請念誠決定替代方式。

| 項目 | 結果 | strace 版本（`strace -V`） | image digest | 日期 |
|---|---|---|---|---|
| selftest | | | | |

## 步驟 2：擋外連的方式

用第 6 項定案的方式擋外連後跑：

```sh
python3 $SHARED/egress.py probe --json /tmp/probe.json   # 預期 exit 0（blocked: true）
```

記下 `dns_resolves`（Modal 的 resolver 在擋網路的沙盒裡仍會回答，屬預期，不影響判定）。若用 `egress.py run --block-network`（network namespace），另跑一次 `python3 $SHARED/egress.py run --out /tmp/ns --label ns --block-network -- python3 $SHARED/egress.py probe`，`ns.json` 的 `netns.ok` 要是 `true`。

| 方式 | probe 結果 | dns_resolves | 日期 |
|---|---|---|---|
| | | | |

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
