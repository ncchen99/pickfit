# Loop journal

每處理完一個項目就在最後面加一段，只加不改。念誠看這份就知道 loop 做了什麼、哪裡要他決定。格式：

```
## 2026-11-16 01:23 reverify:ferro → verified
- 做了什麼：一兩句
- 結果：level、run 目錄、花費（帳本的數字）
- harness：動了哪個問題（H-00X）、改了哪些檔、加了哪個測試；沒動就寫「無」
- 需要你：沒有就不寫這一行。有的話寫清楚要決定什麼、卡住哪些項目
```

`scripts/loop.sh` 每批結束也會加一段，列出這批改過的既有測試，以及有沒有碰到受保護的檔案。

---

## 2026-11-16 12:25 harness:H-001 → fixed

- 做了什麼：這個 session 第一次真的跑 loop。開工時 43 筆裡只有 4 筆選得到（dog、holdspeak、neoth、semquery），其餘 `verify --batch` 印 `0 to verify`，所以先修 H-001，還沒領任何項目。加了 `pickfit discover --repo owner/name`：不搜尋、不呼叫模型，向 GitHub 拿這個 repo 的資料、README、檔案清單，套規則，存成本機 `runs/pipeline.db` 的候選；之後 `pickfit extract --repo <repo_id> --model prod --limit 1` 抽取，`verify --batch --repo` 就選得到。
- 結果：ferro 的 dry-run 從 `0 to verify` 變成只列 ferro；dog 照樣只列 dog；本機完全沒有候選的 bamboo-agent 也存進來了。花費：ferro 的抽取 US$0.113（帳本），沙盒 US$0。
- harness：H-001。改了 `pickfit/discover/run.py`（`add_repos`）、`pickfit/discover/store.py`（漏斗多一個 `named` 來源）、`pickfit/cli.py`（`discover --repo`）；加了 `tests/test_discover_named.py`（5 個測試，先寫、先失敗）。沒有改既有的測試。沒動箱子和映像，沒跑 `--limits-test`。
- skill 也改了：`.claude/skills/pickfit-loop/SKILL.md`「一圈」第 2 步多兩條，寫 dry-run 印 `0 to verify` 時要先跑上面兩個指令，以及 dry-run 出現 `skip` 行時怎麼看。請看一眼寫法對不對。
- 需要你：
  1. `pickfit discover` 要 `GH_TOKEN`，本機 `.env` 沒有，指令自己的錯誤訊息叫人用 `GH_TOKEN=$(gh auth token)`。這個 session 照做了（token 只當環境變數傳給 pickfit，沒印出來，也沒進沙盒）。這把 token 的權限很大（`repo`、`delete_repo`、`workflow`），pickfit 只用它讀公開 repo。要不要另外發一把只讀公開資料的 token 放進 `.env`，請你決定。在那之前 loop 照現在的做法。
  2. 重新抽取的功能清單，用字可能和紀錄裡 `features` 的不同。寫回之後要不要跑 `pickfit profiles --features-only --slug <slug>` 對齊，loop 沒有做，留給協調的 session。
  3. `verify` 預設的 agent 是 Claude Haiku（dry-run 印的是 `agent claude-haiku-5-5 · judges claude-opus-5-5`）。skill 的指令沒有指定 `--model`，所以 loop 用的就是這個組合。如果重驗要用 Opus 當 agent，要在 skill 裡寫明。

## 2026-11-16 12:40 reverify:agentloom → parked (H-003)

- 做了什麼：dry-run 印 `0 to verify`，用新的 `discover --repo` 存進本機（`refreshed`，規則通過）。看了紀錄裡 10/31 那次的筆記：README 在 Linux 上唯一的路是 `bash linux/scripts/bootstrap_toolchain.sh`，腳本第一步就停在 `required command not found: sudo`，它要用 apt 裝 cmake 和編譯器，再裝 rustup。箱子在這兩點上和 10/31 一樣，重跑只會得到同一個結果，所以沒有花錢重跑，也還沒抽取。
- 結果：park，等 H-003（以 root 代裝具名套件），也用得到 H-002（工具鏈）。花費 US$0。
- harness：無。
