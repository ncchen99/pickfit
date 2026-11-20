# pickfit watch 的部署

`pickfit watch` 讀 Worker D1 裡的送出（官網的 `/submit` 和 MCP 的 `submit_software`），依平台分流驗證，通過的紀錄 commit 後推到 `origin/main`，由 `.github/workflows/worker.yml` 部署。watch 要在一台一直開著的 Linux 機器上跑，換供應商也一樣：這裡的檔案只假設 Ubuntu 24.04 和 systemd。

- `bootstrap.sh`：在新機器上以 root 執行，裝 git、Node 24、uv、Scaleway CLI、playwright 的 Chromium，建 `pickfit` 使用者、clone repo、裝 systemd 服務。下載的東西都對過官方公布的 SHA-256。重跑沒關係。
- `pickfit-watch.service`：服務本身。啟動前先 `git pull --rebase` 和 `uv sync`，程式有更新時 watch 以 exit 75 結束，服務自動重開。
- `watch.env.example`：服務要的環境變數名稱。值只填在機器上的 `/etc/pickfit/watch.env`，不進 repo。
- `send_secrets.py`：在這台 Mac 上一個指令把金鑰和狀態送過去、啟動服務（見步驟 3）。

## 放在哪裡

2026-11-18 查的價格，未稅。

| 選項 | 規格 | 每月約 | 說明 |
|---|---|---|---|
| Scaleway DEV1-S（nl-ams-1） | 2 vCPU、2 GB、20 GB 本機 SSD | €6.55，加 IPv4 €2.92，共約 €9.5 | 11/18 起用的就是這台。巴黎三個區（fr-par-1/2/3）這個帳號所有一般機型的配額都是 0，阿姆斯特丹、米蘭、華沙、斯德哥爾摩才有 |
| Scaleway PLAY2-PICO | 1 vCPU、2 GB | €10.4，加 IPv4 €2.92，加 20 GB 區塊磁碟，共約 €15 | 比 DEV1-S 貴，CPU 還少一個 |
| Scaleway STARDUST1-S | 1 vCPU、1 GB | 更便宜 | 巴黎沒貨、阿姆斯特丹快沒貨，1 GB 跑 Chromium 不夠 |
| AWS EC2 t4g.small（台北） | 2 vCPU、2 GB | 約 US$35，加 IPv4 US$3.6 | 第三方網站的報價，沒對過 AWS 官方。會占掉 8 vCPU 配額裡的 2 個，驗證箱子能同時開的就少了 |
| GitHub Actions 排程 | 免費（公開 repo） | US$0 | 每次最多 6 小時，Mac 批次可能不夠。job 檔、造訪紀錄要另外存。從美國的 runner 錄 Mac 的畫面一樣慢 |
| Modal 排程 | 用 Modal 的額度 | 視用量 | 狀態要放 Volume，部署方式綁在 Modal 上 |

用 Scaleway 阿姆斯特丹的 DEV1-S，原因有三個：

1. 便宜、規格又夠。watch 本身很輕，驗證都在 Modal、EC2 或 Mac 上跑，2 GB（`bootstrap.sh` 另外開 2 GB swap）留給 wrangler 和偶爾的 Chromium。
2. 離租來的 Mac mini（巴黎 fr-par-1）很近。錄影時 VNC 的畫面從鄰近機房傳，不會像從台北連過去那樣 10 秒以上才一張（loop/issues.md H-012）。
3. 不占 AWS 的 vCPU 配額，`scw` 已經登入同一個專案。缺點是 Windows 的箱子在台北，每個指令多約 0.25 秒。

## 步驟

0. 這個分支的 watch 程式（分流、`--publish push`、這個資料夾）要先併進 main。服務跑的是 main 上的程式，main 沒有時 `send_secrets.py` 會把金鑰和狀態放好，但不啟動服務。

1. 開機器，例如：

   ```bash
   scw instance server create type=DEV1-S zone=nl-ams-1 image=ubuntu_noble name=pickfit-watch ip=new root-volume=l:20GB tags.0=pickfit tags.1=watch
   scw instance server start 機器的ID zone=nl-ams-1 --wait
   ```

   Scaleway 專案裡的 SSH 公鑰會自動放進新機器。哪一區有配額，可以用 IAM API 的 `/iam/v1alpha1/quota` 查，每一項的 `limits` 列出各區的上限。

2. 在機器上跑 `bootstrap.sh`（不需要任何金鑰）：

   ```bash
   scp deploy/watch/bootstrap.sh deploy/watch/pickfit-watch.service root@機器的IP: && ssh root@機器的IP bash bootstrap.sh
   ```

3. 在這台 Mac 的 repo 裡跑一個指令，送金鑰、搬狀態、啟動服務：

   ```bash
   uv run python deploy/watch/send_secrets.py root@機器的IP
   ```

   腳本從這台 Mac 已有的地方拿 Anthropic key（環境變數或 repo 的 `.env`）、Modal token（`~/.modal.toml`），其他的會問你。值只經 SSH 的 stdin 送過去，不會印在畫面、不會出現在指令列，也不會寫成本機檔案。腳本也會把 `runs/watch/jobs/`（每個送出做到哪）和 `runs/web/visits.jsonl`（造訪過的網站，同一個網站只造訪一次）搬過去，你答 y 的話再加上 `~/.pickfit/mac-hosts` 的 Mac 主機、它們的 SSH 金鑰，以及 `~/.pickfit/tart/hosts/` 裡 base VM 的 manifest。少了 manifest，watch 會以為主機上還沒有 base，每 30 分鐘重建一次，每次都因為 VM 已存在而失敗。先跑一次 `--dry-run` 可以看找到哪些名稱、會執行什麼，不顯示任何值。

   watch 用的金鑰都是給它自己的，各自只開必要的權限（11/18 建立）：

   | 金鑰 | 範圍 | 到期 |
   |---|---|---|
   | Cloudflare user token `pickfit watch (D1 edit, from 51.15.56.181)` | pickfit 帳號的 D1 Edit，只接受機器的 IP | 不過期 |
   | GitHub fine-grained token `pickfit watch (51.15.56.181)` | ncchen99/pickfit 的 Contents 讀寫 | 2027-11-18 |
   | AWS IAM 使用者 `pickfit-watch` 的存取金鑰 | 內嵌政策 [aws-watch-policy.json](aws-watch-policy.json)：只在 ap-east-2，只建、只動帶 `pickfit=verify` 標籤的 EC2 資源 | 不過期 |
   | Scaleway IAM 應用程式 `pickfit-watch` 的 API key | Pickfit 專案的 AppleSiliconFullAccess | 2027-11-18 |

   換機器時，Cloudflare token 的 IP 限制要跟著改。

   main 如果設了分支保護、不讓直接推，push 會失敗，紀錄留在機器上等下次。

4. 看日誌：

   ```bash
   ssh root@機器的IP journalctl -u pickfit-watch -f
   ```

## 端到端測試

在機器上跑，一次測完整條路，而且不會新增軟體：

```bash
ssh root@機器的IP systemctl start pickfit-e2e@default   # reject、linux、web；@all 再加 windows、macos
ssh root@機器的IP journalctl -u pickfit-e2e@default -n 60
```

`pickfit e2e`（`pickfit/e2e.py`）照一般人的方式從官網表單和 MCP 的 `submit_software` 送出測試網址，再跟著正在跑的 watch 看它處理。測試網址在送出前先記在 `runs/e2e/canaries.json`，watch 認得它們，每一步照跑，沙盒也照跑。最後在 data/software 的複本上跑 publish 的計畫檢查，紀錄只留在 `runs/e2e/<run>/`，不寫進 data/software、不 commit、不推。D1 那一列最後是 rejected，理由寫真的送出會得到什麼，跑完刪掉，所以下次可以照樣再跑。網站的測試造訪記在那次 run 自己的 visits 檔，不影響真的送出。另外比對 pickfit.app 和 workers.dev 給的資料是不是 origin/main 的資料。

報告在 `runs/e2e/<run>/report.json`。11/18 第一次跑的模型費：reject 幾乎是 0，linux 約 US$0.27，web 約 US$0.39，windows 約 US$0.31，macos 約 US$0.18。default 三條約 US$0.7，第二次起會重用初篩和抽取。

發布那一段比對 pickfit.app 和 workers.dev 的資料是不是 origin/main 的。pickfit.app 由 Cloud Run 提供，CI 只部署 workers.dev，所以 Cloud Run 沒跟著部署時，這一段會失敗，整份報告也是 FAILED。

## 收集來源（harvest）

`pickfit harvest`（`pickfit/harvest/`，說明在 [docs/research/harvest-sources.md](../../docs/research/harvest-sources.md)）在這台機器上有三個 timer：

| timer | 時間（UTC） | 做什麼 | 費用 |
|---|---|---|---|
| `pickfit-harvest-probe.timer` | 每天 02:50 | 每個來源各讀一小批，接著 check、一筆初篩、對 D1 的 dry-run feed，全在丟棄式資料庫裡。報告在 `runs/harvest/probe.json`，有來源壞掉時 unit 會失敗 | 約 US$0.05 |
| `pickfit-harvest.timer` | 每天 03:30 | 讀所有來源，結果在 `runs/harvest/last-run.json` | X 約 US$0.5，其他免費 |
| `pickfit-harvest-feed.timer` | 每小時 | 初篩 `HARVEST_SCREEN_PER_HOUR` 筆（預設 20），再把收下的 `HARVEST_FEED_PER_HOUR` 筆（預設 5）送進 D1 | 初篩約 US$0.04，送出的每筆進 watch 約 US$0.36 |

Bluesky、X 的 key 和這些設定只改 watch.env 裡那幾行，在這台 Mac 跑：

```bash
uv run python deploy/watch/send_secrets.py root@機器的IP --key ~/.pickfit/ssh/scaleway-mac --add BSKY_HANDLE --add BSKY_APP_PASSWORD --add X_BEARER_TOKEN --add HARVEST_FEED_PER_HOUR=5 --harvest-db
```

`--harvest-db` 把這台的 `runs/harvest.db` 一起帶過去，timer 就從已經收集、初篩過的 lead 接著做。看狀況：

```bash
ssh root@機器的IP systemctl list-timers 'pickfit-harvest*'
```

```bash
ssh root@機器的IP systemctl --failed
```

## 維護用的 timer（11/20）

`pickfit maintenance`（`pickfit/maintenance.py`）有三件定期的維護工作。每件都在 watch 旁邊另一個 git worktree（`/var/lib/pickfit/maint`）裡做，不碰 watch commit 和 push 用的那個 checkout，所以兩邊不會搶同一個 index。跑的程式是 watch checkout 的版本，只有紀錄來自 worktree。每次都從 `origin/main` 重新開始，上一次中斷留下的東西會清掉。

| timer | 時間（UTC） | 做什麼 | 費用 | 結果去哪 |
|---|---|---|---|---|
| `pickfit-security-weekly.timer` | 每週日 04:30 | `pickfit security --stale-days 7 --write`，接著 `pickfit score --refresh` | 不呼叫模型 | commit 後推到 main，CI 部署 |
| `pickfit-outcomes.timer` | 每天 05:10 | `pickfit outcomes sync`，把 D1 裡外部的使用回報算進分數 | 不呼叫模型 | commit 後推到 main，CI 部署 |
| `pickfit-reverify.timer` | 每天 06:00 | `pickfit reverify --limit 3`，在新箱子重驗使用者回報裝不起來的紀錄 | **要錢**：每筆約一次驗證的費用，受 watch 同一個每日金額上限管 | commit 在 `maint/reverify-日期` 分支並推上去，**不進 main** |

- 推到 main 時如果 watch 先推了，會 fetch、rebase 再推，最多試三次。還是失敗的話，commit 留在 worktree，報告寫在 `runs/maintenance/<task>.json`。
- reverify 會照使用者的回報改紀錄的安裝步驟，所以要有人看過 diff 才上線，和 watch 不准 `--reverify` 搭 `--publish` 是同一個理由。看過沒問題就把分支合進 main。
- `SECURITY_STALE_DAYS`、`REVERIFY_LIMIT` 寫在 watch.env，留空就是預設值。

`bootstrap.sh` 只安裝這些 unit，不啟用。要開的時候在這台 Mac 跑（reverify 要錢，要不要開另外決定）：

```bash
ssh root@機器的IP systemctl enable --now pickfit-security-weekly.timer pickfit-outcomes.timer
```

```bash
ssh root@機器的IP systemctl enable --now pickfit-reverify.timer
```

先手動跑一次、不推送，看看會改哪些紀錄：

```bash
ssh root@機器的IP sudo -u pickfit sh -c 'cd /var/lib/pickfit/pickfit && uv run pickfit maintenance security --no-push'
```

## 平常要知道的事

- macOS 那條沒有能用的 Mac 時，批次到了會自己租一台（`--mac-rent`，一週最多一台），root 步驟也自動做（`--mac-root-from-provider`，向 Scaleway 讀那台的 sudo 密碼，直接餵給主機上的腳本，不記錄、不存檔）。拿掉這兩個參數就只用 `~pickfit/.pickfit/mac-hosts` 裡已經能用的主機。
- watch 自己租的 Mac，付費的第一天過完又沒事做時會自己刪。服務停掉時就不會刪，Scaleway 過了 24 小時按小時計費，要 `pickfit mac-host down 名稱 --yes`。
- `systemctl stop pickfit-watch` 會等跑到一半的工作做完，最多 30 分鐘。
- `pickfit watch --status`（在機器上以 pickfit 使用者執行）列出 D1 的送出、每條分流停著的工作和 Mac 主機。

## 吞吐量的設定（11/19）

watch 原本最多同時跑 2 筆，每筆先保留 US$6，花到約 US$24 就不再開新工作，要等重啟才會動。11/19 起改成這樣（[docs/proposals/throughput.md](../../docs/proposals/throughput.md)）：

- 錢看帳本最近 24 小時花了多少，上限是 `loop/budget.json` 的 `model_usd.daily`（現在 US$80），不再從程式啟動起累計。每個在跑的工作保留所在分流最近 50 筆的 p95 花費，一條分流還不到 5 筆紀錄時才用 US$6。
- 每條分流自己算同時幾筆：linux 6、web 2、windows 最多 2（EC2 的 8 vCPU 配額）、macos 看主機開得了幾台 VM。不再限制每小時開始幾筆。
- id 以 `sub_harvest` 開頭的送出（`pickfit harvest feed` 要用 `pickfit.watch.harvest_submission_id()` 產生）排在一般人的送出後面，所有分流加起來最多占 4 格，每條分流留 1 格給人，而且要留 US$10 的當日額度給人。
- 工作做完就馬上拿下一筆，新送出還是每 60 秒查一次。

數字都能在 `/etc/pickfit/watch.env` 用 `PICKFIT_WATCH_*` 改，名稱和預設值寫在 `watch.env.example` 的最後一段。`send_secrets.py` 不會送這些變數，要改就在機器上直接加那幾行，再 `systemctl restart pickfit-watch`。之後重跑 `send_secrets.py` 會整份覆寫 `watch.env`，手加的行要再加一次。

watch 每一輪把狀態寫到 `runs/watch/status.json`：每條分流在跑幾筆、上限幾筆、排隊或停著幾筆，以及沒開新工作的原因（錢、格子滿了、harvest 的額度、分流在休息、等 Mac 的那一批）。卡在錢的時候，原因會寫出是哪幾個數字加起來超過上限。`pickfit watch --status` 會一起印出來，journal 裡也看得到同樣的摘要。
