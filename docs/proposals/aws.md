# AWS 的花費怎麼分

> 提案（2026-11-21）。總覽和共同規則在 [README.md](README.md)。額度的來源、申請狀態和帳號資訊記在本機的額度清單，不進 repo。這裡只寫花費上限和用法。

## 現況

- pickfit 的錢九成花在模型。[tokens.md](tokens.md) 量到一筆 CLI/MCP 紀錄的模型費用約 US$0.40，[machines-cost.md](machines-cost.md) 估箱子一筆約 US$0.02。
- 模型呼叫只走 Anthropic 的 API（[meta.py](../../pickfit/meta.py) 的 `DEFAULT_PROVIDER`）。程式裡沒有 Bedrock 的接法，所以 AWS 這邊的預算現在只付得到 EC2。
- EC2 已經有 Linux 和 Windows 兩種箱子（[ec2_machine.py](../../pickfit/verify/ec2_machine.py)、[ec2_windows.py](../../pickfit/verify/ec2_windows.py)）。Linux 每小時約 US$0.10，Windows 約 US$0.21。一般機型的配額是每區 8 vCPU，同時最多開兩台，11/17 念誠決定不提高。
- Linux 的 gVisor 箱子在 Modal 上跑，242 次驗證估 US$4.43。GPU 箱（T4、L4）也在 Modal，main 上已經接進 watch（[sandbox-env-unlock.md](sandbox-env-unlock.md)）。
- watch 跑在 Scaleway 的 DEV1-S，每月約 €9.5（[deploy/watch/README.md](../../deploy/watch/README.md)）。

## 兩年 US$5,000 的分配

| 用途 | 上限（US$） | 買到什麼 |
|---|---|---|
| Bedrock 上的 Claude：收錄、重驗、線上配對。受測工具用的計費代理如果接 Bedrock，也算這一格 | 3,000 | 照每筆模型費用 US$0.40 算，約 7,500 次 CLI/MCP 驗證。網頁每筆約 US$0.6，Windows GUI 有一次量到 US$1.32 |
| EC2 驗證箱：全權 VM 箱、Windows | 450 | Linux 約 4,000 小時，或 Windows 約 2,000 小時 |
| 映像、快照、流量，和可能搬過來的 watch | 300 | 見 A4 |
| Mac，和 Modal 給不了的 GPU | 300 | Mac 專用主機最少租 24 小時，估夠租十天左右。GPU 平常用 Modal，只有超過 24 GB 顯存的才考慮 EC2 |
| 同帳號 pickfit 以外的用量 | 700 | 帳單是整個帳號一起算的，這部分先扣掉 |
| 預備 | 250 | 配額不夠、重跑、估錯的部分 |

每筆的模型費用是 Anthropic 直連的實測值，假設 Bedrock 同價，還沒查證。失敗和重跑的也要花錢，實際能收錄的筆數會比這個少。

節奏：大量收錄的前三個月花約 US$1,800，之後每月 US$100–130 做重驗和新收錄，可以撐滿兩年。

和其他來源的先後：有效期短的額度先用，AWS 放最後。Linux 的 gVisor 箱子繼續用 Modal 方案每月內含的額度，EC2 只開 Modal 做不到的箱子。

## 提案

### A1 模型呼叫可以走 Bedrock（先做，不然上面的分配用不到）

- 在 `meta.py` 的 `PROVIDERS` 加一個 `bedrock`，請求和回應的轉換放在 [anthropic_messages.py](../../pickfit/anthropic_messages.py) 旁邊。走哪一家由設定決定，預設不變。Bedrock 掛掉或被限流時退回直連。
- 用同一個模型。Bedrock 上沒有現在用的 Opus 型號，或配額不夠跑收錄，就不切過去。不換較弱的模型（11/17 念誠的決定）。
- 帳本的 `provider` 記 `bedrock`，另開一個預算名稱，價格表寫明來源和查的日期。
- 快取的行為要跟直連對過一次，看寫入和讀取有沒有照算。batch 在 Bedrock 上沒有對應的做法（見「11/21 查到的」），那幾個步驟留在直連。
- 憑證：watch 機器上用一把只能呼叫指定模型的 IAM 金鑰，不用 root 的登入 session。IAM 使用者和政策由念誠建，程式只附上政策檔（像 [aws-watch-policy.json](../../deploy/watch/aws-watch-policy.json) 那樣）。

驗收：用假的 client 測請求轉換、退回直連、帳本計價。真的呼叫 Bedrock 的那一次由協調 session 跑，拿同一批請求比對兩邊的回應格式和 token 數。

### A2 花費上限和對帳（先做）

- `loop/budget.json` 給 Bedrock 一組每日和總額上限。這是 loop guard 保護的檔案，數字由念誠定。
- [machines-cost.md](machines-cost.md) 的 M1、M2 已經規劃 `boxes` 表和對帳指令。這裡多兩件帳號設定，由念誠決定要不要開：`pickfit:purpose` 設成 cost allocation tag、AWS Budgets 每 US$1,000 通知一次。
- 對帳時把 pickfit 以外的用量分開列，才看得出 pickfit 自己花了多少。

### A3 全權 VM 箱的 lane（可以並行做）

箱子怎麼做寫在 [privileges.md](privileges.md) 的 P6。這裡只管預算和並行：

- 這條 lane 同時最多兩台，agent 和重播各一台，同一時間只有一筆。
- 每筆的機器費用上限先訂 US$0.50（約 Linux 5 小時），超過就停，記 `budget_exceeded`。
- 映像只留最新的一份，舊的 AMI 和快照由清理程式刪掉。

### A4 watch 要不要搬到 EC2（先查價，不急）

搬過來每月省約 €9.5 的現金。但有三件事要先確認：

- 價格。11/21 查到台北的 t4g.small 每月約 US$14.2，加上 IPv4 和磁碟比 Scaleway 貴。只有在額度付得到的時候才省現金。
- 配額。watch 開在台北會占掉 2 個 vCPU，驗證箱就少一台。要搬就開在別的區。
- 當初選 Scaleway 有一個原因是離租來的 Mac mini 近。現在沒有 Mac 主機，之後如果又租在巴黎，這個原因還在。

部署檔只假設 Ubuntu 和 systemd，搬不搬都不用改程式。

### A5 Mac 和大顯存的 GPU（等配額決定）

GPU 機型和 Mac 專用主機各有自己的配額，新帳號常常是 0，跟一般機型那 8 vCPU 分開算。要不要申請由念誠決定。申請之前這一格的預算不動。

- GPU：24 GB 以下的繼續用 Modal。超過 24 GB 的紀錄現在不驗，筆數夠多再考慮在 EC2 開，一筆一台，用完就關。
- Mac：照 machines-cost 的 M7，攢到 150–300 筆 macOS 項目再租一次。在 EC2 租還是在別家租，到時候比價。

## 不做的事

- 把網站、D1、R2 搬到 AWS。沙盒層和部署都不綁平台（11/16 的設計準則），預算有效期到了還要能搬走。
- 為了把預算花完而開著機器。機器只在測試時開。
- 提高一般機型的 vCPU 配額。
- 用預付的方案（Reserved Instances、Savings Plans）或 Marketplace 的東西，這些多半不在額度涵蓋範圍內。

## 11/21 查到的

實作 A1 的 subagent 讀了 AWS 和 Anthropic 的官方頁面（2026-11-21 讀的，網址在它的回報裡）。協調 session 沒有逐項再查。跟上面寫的不一樣的地方，以這一節為準。

- **型號有。** Opus 5.5 和 Haiku 5.5 都在 Bedrock 上。台北只能用 global 的 inference profile，請求可能在任何商用區域執行。
- **價格跟直連一樣。** global profile 是 Anthropic 的牌價，區域型的 profile 貴 10%。
- **沒有 batch。** Bedrock 上這兩個型號沒有批次折扣，也沒有 Message Batches。[tokens.md](tokens.md) T3 的批次步驟留在直連。
- **不用填用途表。** 那張表只有 Opus 4.7 以前的型號要填。但帳號第一次呼叫會經 AWS Marketplace 訂閱，呼叫的身分要有 Marketplace 的訂閱權限，最多等 15 分鐘。
- **額度付不付要看種類。** Bedrock 上的 Claude 經 Marketplace 計費。Activate 的條款寫明可以抵 Bedrock 上第三方模型的費用，一般促銷額度預設不行。到 Billing 的 Credits 頁看「Applicable Products」才算數。
- **t4g.small 在台北每月約 US$14.2**（每小時 US$0.0194），美東約 US$12.3。部署文件原本記的 US$35 是錯的，那個分支已經改掉。加上 IPv4 和磁碟，比 Scaleway 的 €9.5 貴。
- **台北沒有 GPU 機型，也沒有 Mac 專用主機。** Mac 最近的在新加坡，mac2（M1）每小時 US$0.779。美東的 mac2 是 US$0.65，租滿最少的 24 小時是 US$15.60。美東的 g4dn.xlarge（T4 16 GB）每小時 US$0.526。A5 如果要做，機器不會開在台北。
- **巢狀虛擬化**（實作全權 VM 箱的 subagent 查的）：c7i-flex、m7i-flex 都在支援清單上，不用換機型。台北能不能用還沒透過 API 確認。

## 11/22 第一次真的呼叫

念誠建了只能呼叫這兩個型號的 IAM 金鑰，協調 session 跑了 `pickfit ping` 和 `scripts/bedrock_compare.py`（Opus 5.5，兩邊合計約 US$0.51）。跟「11/21 查到的」不一樣的地方，以這一節為準。

- **新帳號的配額是 0。** 每次呼叫都回 `Operation not allowed`。在 Service Quotas 送申請之後，AWS 在案件裡要求做一次身分驗證，驗證完才開通。Service Quotas 只收大於預設值的數字。
- **台北不能用，改從 us-east-1 送。** 開通後 us-east-1 和 us-west-2 的配額是預設值，台北還是 0，連舊型號也被拒絕。預設區域和金鑰的政策檔都改成 us-east-1。global profile 的價格和從哪裡送無關。
- **token 數和快取跟直連對得上。** 帶圖片和 JSON schema 的單次判定，兩邊的輸入都是 7,971 個 token。工具迴圈第一輪寫入 8,089，第二輪讀到 8,089、再寫 240，直連是 233。一小時的快取 Bedrock 有回報寫入多少（7,693），第二次也讀到了。
- **換邊接續可以。** 在直連開始、帶著 thinking block 的對話，第二輪送到 Bedrock 有成功。
- **提到跑 shell 指令的請求常被拒答。** 訊息是「查這是哪個 shell，呼叫一次 run_command」。送到 Bedrock 8 次，7 次回 `refusal`，類別 `cyber`，說明文字要人去申請 Cyber Verification Program。拿掉工具定義也一樣被拒，所以被擋的是訊息內容。同樣的請求直連 Opus 5.5 都有回答，沒有換成備援模型。訊息改成「印出受測工具的版本，用 `tinyq --version` 呼叫一次 run_command」再跑一次，送到 Bedrock 的 4 次裡還是有 1 次被拒。
- **拒答要付兩次錢。** 被拒的那次 Bedrock 照收輸入 token 的錢（寫快取的那次照寫入價），退回直連再算一次。抽取、判定這類不提指令的請求沒有被拒。
- **比對腳本改過了。** 第一次跑的時候它說「明確的 breakpoint 沒有做到自動快取做的事」，那是因為 Bedrock 那一邊的回應其實是退回直連後拿到的。看 trace 裡 Bedrock 自己的用量，快取有寫也有讀。現在退回直連的那一輪只列出來，不拿去比。模型這次有沒有先思考、第二輪多寫十幾個 token，這兩種每次跑都會變的差別也不再算成不一致。改完之後兩次的結果裡，剩下的差別只有拒答。
- **用途表可能還是要填。** Bedrock 主控台有提示說 Anthropic 要求第一次使用的客戶提交使用情境。還沒填，呼叫照樣成功。

- **真的驗證沒有被拒。** 同一天拿一筆紀錄（agent-database-cli，Modal 的服務箱，不寫回）把模型呼叫全部走 Bedrock：agent 11 次、兩個判定各 1 次，13 次都有回答，沒有一次退回直連。驗到 `function`，重播通過，模型花費 US$0.29，同一筆走直連是 US$0.25。agent 的 233,678 個輸入 token 裡有 207,084 個是從快取讀的。真的 agent 的提示這次沒有碰到拒答。只跑了一筆，資安類的軟體還沒試。

接下來要決定的：哪些步驟走 Bedrock。照這次的結果，抽取、評分、判定、翻譯和驗證 agent 都能走。開了之後要看 trace 裡 `fallback` 的 `declined (cyber)` 有多少，尤其是資安類的軟體，拒答多的話那一類留在直連。

## 還沒確認的

- 台北什麼時候能用。11/22 us-east-1 的配額是預設值（Opus 5.5 每分鐘 3,000 萬 token），台北是 0。
- 這筆額度到底抵不抵 Bedrock 上的 Claude。等第一筆小額帳單出來看。
- 驗證 agent 在 Bedrock 上被拒答的比例。11/22 跑的一筆是 13 次裡 0 次，樣本只有這一筆。
- GPU 機型和 Mac 專用主機的配額。
- pickfit 以外的用量每月實際多少。US$700 是照機型牌價估的。
