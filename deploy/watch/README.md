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

   腳本從這台 Mac 已有的地方拿 Anthropic key（環境變數或 repo 的 `.env`）、Modal token（`~/.modal.toml`），問你要 Cloudflare 的 D1 token 和 GitHub 的 fine-grained token（只給 ncchen99/pickfit 的 Contents 讀寫），AWS key 和 Scaleway key 可以跳過。值只經 SSH 的 stdin 送過去，不會印在畫面、不會出現在指令列，也不會寫成本機檔案。腳本也會把 `runs/watch/jobs/`（每個送出做到哪）和 `runs/web/visits.jsonl`（造訪過的網站，同一個網站只造訪一次）搬過去。先跑一次 `--dry-run` 可以看找到哪些名稱、會執行什麼，不顯示任何值。

   main 如果設了分支保護、不讓直接推，push 會失敗，紀錄留在機器上等下次。

4. 看日誌：

   ```bash
   ssh root@機器的IP journalctl -u pickfit-watch -f
   ```

## 平常要知道的事

- macOS 那條預設不租 Mac，只用 `~pickfit/.pickfit/mac-hosts` 裡已經能用的主機。要自動租，在服務的 ExecStart 加 `--mac-rent`。要連 root 步驟也自動做，再加 `--mac-root-from-provider`（向 Scaleway 讀那台的 sudo 密碼，直接餵給主機上的腳本，不記錄、不存檔）。
- watch 自己租的 Mac，付費的第一天過完又沒事做時會自己刪。服務停掉時就不會刪，Scaleway 過了 24 小時按小時計費，要 `pickfit mac-host down 名稱 --yes`。
- `systemctl stop pickfit-watch` 會等跑到一半的工作做完，最多 30 分鐘。
- `pickfit watch --status`（在機器上以 pickfit 使用者執行）列出 D1 的送出、每條分流停著的工作和 Mac 主機。
