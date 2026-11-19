# 安全審查：C/C++ 和沒有原始碼的網頁 App

> 提案（2026-11-20）。接在 [security.md](security.md) 和 [audit-20261120.md](audit-20261120.md) 第 3 節後面。只是設計，還沒有程式。

1,211 筆紀錄裡，SBOM 重播做完後 complete 約 75.5%。剩下兩塊 SBOM 補不了：

- **C/C++，103 筆**，缺口 `advisory_db.no_ecosystem`。OSV.dev 沒有 C/C++ 生態系，多半在 `other` 和 `local_ai` 分類。
- **沒有公開原始碼的網頁 App，50 筆**，缺口 `source.none`（kind `web_app`，驗證是瀏覽器跑一輪，見 `pickfit/verify/web*.py`）。

兩塊都不呼叫模型，只花箱子時間和網路。

## 1. C/C++

### 找什麼、怎麼找

C/C++ 沒有 lockfile，要從三個地方湊出「帶了哪些函式庫、哪個版本」：

1. **replay 箱子裡裝好的東西**（接在 `pickfit/sbom.py` 後面，同一個箱子）。
   - syft 的 binary classifier（openssl、zlib、curl、sqlite 這類靠版本字串認得出的函式庫）。目前 sbom.py 用 `--override-default-catalogers image`，要確認 binary cataloger 有在這組裡，沒有就明確加上。
   - 對安裝資料夾裡的執行檔跑 `ldd`，再用 `dpkg -S` 查出每個共享函式庫屬於哪個 deb 套件。跟箱子映像本來就有的套件清單比對，只留安裝步驟自己 `apt install` 進來的。映像原本的函式庫算作業系統的，不算這套軟體帶來的。
2. **repository 裡 vendored 的程式**（target 維持 `repo_lockfile`）。
   - `third_party/`、`vendor/`、`external/`、`subprojects/` 下面認得出名字的函式庫，版本從標頭檔讀（例如 `zlib.h` 的 `ZLIB_VERSION`、`opensslv.h`）。注意 `PERIPHERAL` 目前會跳過這些資料夾，C/C++ 這條路要另外處理。
   - 建置檔：`vcpkg.json`（加上 builtin-baseline）、`conanfile.txt`／`conanfile.py`、meson 的 `subprojects/*.wrap`、CMake 的 `FetchContent`／`ExternalProject` 裡的 `GIT_TAG`、git submodule 的 commit 對到 tag。
3. **比對漏洞**：用 grype 的漏洞資料庫，離線查。每天抓一次放快取，在 watch 機器上對存下來的 SBOM 跑，不需要每個箱子都下載。NVD API 只當補查，要申請 API key 才有夠用的速率。

### 壓低誤判

CPE 比對很吵，主要來自三件事：從套件名稱猜 CPE、vendor／product 同名撞到別的專案、NVD 的版本範圍寫得不精確。做法：

- **只用一份自己維護的對照表**，函式庫名稱對到確定的 `vendor:product`。syft 的 binary classifier 已經帶固定 CPE，其他的先收 50 個左右常見的（openssl、zlib、curl、sqlite、libpng、libjpeg-turbo、libxml2、expat、freetype、ffmpeg、libwebp、mbedtls、pcre2、protobuf、llama.cpp 等）。grype 從名稱自動產生的 CPE 一律不用。不在表上的函式庫記成缺口，不去猜。
- **版本要確定才比對**。版本從標頭檔、建置檔或 binary 裡的版本字串讀到才算。讀不到就是缺口，不產生 finding。llama.cpp 這類用 build 編號（`b1234`）當版本的，試點時要逐筆核對 NVD 的寫法。
- **deb 套件不走 NVD**。Debian／Ubuntu 會把修補 backport 回舊版號，用上游版本比會誤報。這些查 OSV 的 Debian、Ubuntu 生態系，或 grype DB 裡的發行版資料。
- 排除 NVD 標成 Rejected 或 Disputed 的 CVE。
- data 檔記下每筆比對的依據（CPE、版本從哪裡讀到、檔案路徑），人工抽查時才有東西可以看。

### 放進 sec.v2

- **target**：箱子裡找到的維持 `installed_artifact`，repository 裡找到的維持 `repo_lockfile`，不新增。ecosystem 用已經在用的 `c/c++` 和 `deb`。
- **新的缺口代碼**，沿用 GAP_CODES 的命名，放在既有分類裡：
  - `advisory_db.no_cpe`（advisory_db，capability `cpe_map:{detail}`）：認出函式庫和版本，但對照表沒有它。
  - `binary.version_unknown`（binary_no_metadata，capability `binary_analysis`）：認出函式庫，讀不到版本。
  `advisory_db.no_ecosystem` 留給完全沒處理到的情況。`pickfit/schema.py` 的 `GapCode` Literal 和 `GAP_CATEGORY` 要一起加。
- **coverage**：complete 要同時滿足：每個 vendored 函式庫、建置檔列出的依賴、安裝步驟帶進來的共享函式庫，都有對照表上的 CPE 和確定的版本，而且 binary 掃描沒有剩下認不出的部分。有任何一項沒做到就是 partial，並列出上面的缺口。
- **等級**：只靠 CPE 和版本對上的 finding，最高 conditional。往下或往上要有證據：
  - present_unreachable：動態連結時，執行檔匯入的符號是可以完整列出的（`nm -D`）。advisory 點名的函式（S6 的 triage 抽出來的）不在匯入清單裡，就算沒用到。靜態連結又 strip 過的判不出來，維持 conditional。reach 方法用既有的 `symbol_grep`。
  - exposed：有匯入那個函式的證據，而且軟體預設會處理網路或不受信任的輸入（例如有 HTTP transport 的 MCP server、會開 port 的服務）。
  - blocked：上面的 exposed 條件成立，而且 CVE 在 CISA KEV 上。
- **細節放哪**：record 只放現有欄位的摘要和 finding。CPE、版本來源、路徑、`ldd` 結果放 `data/security/<slug>.json`。

## 2. 沒有原始碼的網頁 App

### 找什麼、怎麼找

使用者拿到的是瀏覽器載入的那些程式，這部分 pickfit 看得到。伺服器端看不到。

- **收集**：`web_guard.py` 已經記下每個 flow 的 URL 和類型，但沒有存回應內容。在 mitmproxy 的 response hook 裡，對 script 類型的回應存 SHA-256、檔頭檔尾各幾 KB、`sourceMappingURL`，不存整份程式。
- **認出函式庫**，由可靠到不可靠：
  1. 檔案 hash 和 URL 樣式（`jquery-3.5.1.min.js`、cdnjs／jsdelivr／unpkg 路徑裡的版本）。
  2. 檔頭版權註解（`/*! lodash v4.17.21 */`，打包工具常會保留）。
  3. 頁面裡的執行期變數（`jQuery.fn.jquery`、`React.version`），在既有的瀏覽器裡跑 retire.js 的 extractor。
  4. source map 列出的 `node_modules/<pkg>/` 路徑。這只給名稱，通常沒有版本，只能拿來列出「有用到但版本不明」。
  偵測規則用 retire.js 的 `jsrepository.json`。
- **比對漏洞**：函式庫能對到 npm 套件時（jquery、lodash、react-dom、moment），查 OSV 的 npm 生態系，跟現有流程同一條路。retire.js DB 的漏洞資料當補充，兩邊用 CVE／GHSA alias 去重。
- **另外一次造訪**：之前 50 筆的 web run 沒存回應內容，要再開一次箱子。照紀錄裡已經走過的 URL 用 GET 載入頁面，不用 agent，也不呼叫模型。guard 原本就允許 GET。

### 放進 sec.v2

- **target**：新增一個值 `served_page`，schema 的 target Literal 要一起加。這是唯一新增的 target，因為現有三個都在講「裝了什麼」，頁面不是安裝出來的。
- **ecosystem**：對到 npm 的用 `npm`，scope 是 runtime，component 寫 `page:<url>`。對不到的用 `js`，只觀察，沒有 advisory 來源。
- **新的缺口代碼**：`binary.bundle_unidentified`（binary_no_metadata，capability `source_map`）：一支 script 認不出裡面有哪些函式庫或版本，`found` 是 script 數。
- **coverage**：每支 script 都認出函式庫和版本，或確定是沒有夾帶第三方程式的自家程式碼，才算 complete。打包過的大 bundle 大多會落在 partial。
- **伺服器端算不算缺口**，要念誠決定。建議不算：伺服器是營運者的，使用者沒有拿到，target 已經寫明是 `served_page`，頁面上寫「檢查範圍：瀏覽器載入的程式」。如果決定算，這 50 筆最多到 partial，complete 的提升就是 0。
- **等級**：預設 conditional。
  - present_unreachable：advisory 點名的函式在這輪造訪中沒被呼叫，只能當弱證據，所以不用來降級。
  - exposed：在頁面腳本執行前，用 init script 包住 advisory 點名的函式（例如 jQuery 的 `htmlPrefilter`），造訪時確實被呼叫，而且頁面會顯示使用者或遠端來的內容。
  - blocked：script 來自已知被劫持的網域（例如 2024 年的 polyfill.io），或 OSV 把那個 npm 版本標成 MAL-。KEV 上的前端函式庫很少。
- **細節放哪**：script 的 URL、hash、認出的函式庫和方法放 `data/security/<slug>.json`。不存網站的原始碼。

## 3. 授權，加之前要確認的事

| 東西 | 授權 | 要先確認 |
|---|---|---|
| grype | Apache-2.0 | 程式本身沒問題 |
| grype DB | Anchore 建的，彙整 NVD、GHSA、各發行版的資料 | Anchore 對下載 DB 的使用條款；各上游來源（GHSA 是 CC-BY-4.0，發行版各自不同）在公開頁面顯示 finding 時要怎麼標出處 |
| NVD 資料／API | 美國政府資料，NVD 的使用條款要求標「This product uses data from the NVD API but is not endorsed or certified by the NVD」 | 這句話放在哪；API key 由念誠申請 |
| CVE 內容 | CVE Program 的使用條款 | 只引用 CVE 編號和摘要，確認不需要額外標示 |
| retire.js | Apache-2.0 | `jsrepository.json` 是否也適用 repository 的 LICENSE，或另有條款 |
| syft | Apache-2.0 | 已在映像裡 |

## 4. 成本

不呼叫模型。

- **C/C++**：在 SBOM 重播的箱子裡多跑 `ldd`、`dpkg -S` 和 binary 掃描，每筆多約 1 分鐘。不在那 155 筆重播名單裡的，要單獨重播一次，每筆幾分錢。grype DB 每天下載一次，約數百 MB。合計估 US$3–8。工作量約 4–6 天，其中對照表和 vendored 偵測佔一半。
- **網頁**：每筆一次無 agent 的造訪，約 2–3 分鐘箱子時間，50 筆估 US$1–3。retire DB 和 OSV 查詢只是網路。工作量約 3–4 天。

## 5. 預期提升（都是估計）

- **C/C++**：103 筆約佔 1,211 的 8.5%。假設九成以上能到 complete，complete 從 75.5% 到約 84%。
- **網頁**：50 筆約 4.1%，假設伺服器端不算缺口、而且大多能到 complete，提升約 4%。

會變小的原因：

- 紀錄還有其他缺口（同一筆也缺 lockfile 或 adapter），補了這塊仍是 partial。
- 靜態連結又 strip 過的執行檔讀不到版本，落在 `binary.version_unknown`。
- `local_ai` 的工具要 GPU 或 CUDA，Linux 箱子裝不起來，沒有 replay 就沒有箱子這半邊。
- 對照表沒收的函式庫，落在 `advisory_db.no_cpe`。
- 網頁的 bundle 沒有檔頭也沒有 source map，落在 partial。
- 念誠決定伺服器端算缺口，網頁這 4% 歸零。

## 6. 風險和試點

風險：

- **誤報把一批紀錄推成 conditional**，影響分數和 MCP 的提醒。對策是先上線成「只觀察、不計入」（counted 為 false），試點的準確率過了門檻才計入。
- 網站每天在換，結果有時效，要接上 S8 的定期重掃。CDN 的 A/B 測試或地區差異也會讓兩次造訪看到不同的 script。
- 加了 response hook 後，guard 的記錄檔會變大，要限制只存 script 類型、只存檔頭檔尾。

試點各挑約 10 筆（C/C++ 的 `other` 和 `local_ai` 各半，網頁挑有 CDN 函式庫的和全打包的各半），量這些：

- 比對的準確率：每個 CVE 人工對照上游的 release notes，目標 90% 以上才計入。
- 認出版本的函式庫占所有找到的函式庫的比例。
- 到 complete 的筆數，用來修正第 5 節的估計。
- 每筆多花的箱子分鐘數。
- 漏報：各挑 2 筆已知帶舊版函式庫的，看有沒有抓到。
- 網頁：認出的 script 比例，retire.js 和 OSV npm 的結果一致多少，guard 有沒有擋掉這次造訪的請求。
