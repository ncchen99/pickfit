# q08 校正紀錄（第一次開跑前填寫）

第一次開跑評測前由念誠照下面做一次，填好後與測試資料一起 commit。這些步驟不裝任何候選工具、不涉及任何答案。

## 1. 固定映像檔（在主帳號，只查 registry，不拉映像）

用 Docker Hub 的公開 API 查多架構索引的 digest。匿名 token 在執行時取得，用完即丟，不寫進任何檔案：

```sh
for repo_tag in nginx:1.27-alpine redis:7.2-alpine hello-world:latest; do
  repo=${repo_tag%%:*}; tag=${repo_tag#*:}
  tok=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/$repo:pull" \
        | sed -E 's/.*"token":"([^"]+)".*/\1/')
  curl -s -H "Authorization: Bearer $tok" \
       -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
       "https://registry-1.docker.io/v2/library/$repo/manifests/$tag" -o "/tmp/q08-$repo.json" -D - \
       | grep -i '^docker-content-digest'
  grep -o '"architecture": *"arm64"' "/tmp/q08-$repo.json" | head -1
done
```

| 映像檔 | 索引 digest | 有 linux/arm64？ | 決定（加進 compose.yaml／只記錄） |
|---|---|---|---|
| nginx:1.27-alpine | | | |
| redis:7.2-alpine | | | |
| hello-world:latest | | | 只記錄（指令已凍結） |

決定釘 digest 時，把 `compose.yaml` 的映像改成 `nginx:1.27-alpine@sha256:<digest>`、`redis:7.2-alpine@sha256:<digest>`，與本檔一起 commit。

## 2. 環境決定（`needs.json`）

| 事項 | 念誠的決定 |
|---|---|
| Homebrew 做法（A／B／C） | |
| docker CLI 基準（基準 1／基準 2） | |
| Rosetta（維持未安裝／事先安裝） | |
| 開跑時段（沒有其他工作需要主帳號的 Homebrew、容器 app、8080 埠） | |

## 3. 演練帳號流程（不裝任何工具）

1. 主帳號：照 README 第 3 節準備（Touch ID、8080、另一套 app 的連結、Homebrew）。
2. `sh snapshot.sh /Users/Shared/q08-runs/cal/before.txt`。
3. 建 `q08evalcal` 帳號，登入，跑 `sh /Users/Shared/q08-fixture/preflight.sh`：要沒有 FAIL。
4. 在該帳號開新的終端機，確認 `zsh -il -c 'echo $PATH; command -v docker'` 沒有找到 docker。
5. 登出，`sudo sysadminctl -deleteUser q08evalcal`，`sh snapshot.sh /Users/Shared/q08-runs/cal/after.txt`，`diff` 只剩時間不同。
6. 復原 README 第 6 節第 5 步的暫時改動，再比一次基準。

| 欄位 | 值 |
|---|---|
| macOS 版本（`sw_vers`）、機型 | |
| `preflight.txt`（貼上或附檔路徑） | |
| 第 4 步輸出 | |
| 第 5、6 步的 diff 結果 | |
| 本資料夾每個檔的 sha256（`shasum -a 256 *`） | |
| 校正者、日期時間（台北） | |
