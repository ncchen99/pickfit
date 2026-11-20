# 舊紀錄的類別矯正（11/20）

`scripts/reclassify_categories.py` 把 11/15 新增五個主題類別之前收錄、留在 `other` 或 `dev_cli` 的紀錄，照 `CATEGORY_GUIDE`（第一個符合的類別）搬到該去的類別。只搬毫無爭議的；播放器、檢視器、螢幕錄影、帶主題的 AI 工具、MCP server 和其他說不準的都留在原處。

每筆只改 `category`、`/category` 那條 evidence 的來源（改成 `method: rule`，不再掛當初抽取的模型）和 `updated_at`。`scores`、`security`、`capabilities`、`verification`、`slug`（所以 `/tool/<slug>`）都不動。不呼叫模型。

## 上架紀錄的筆數

| 類別 | 搬之前 | 搬之後 |
|---|---|---|
| dev_cli | 361 | 331 |
| local_ai | 292 | 292 |
| mcp_server | 228 | 228 |
| other | 245 | 204 |
| security_net | 23 | 40 |
| media_files | 17 | 36 |
| infra_devops | 19 | 30 |
| data_db | 13 | 26 |
| productivity_docs | 13 | 24 |

共搬 71 筆。

## 搬了哪些

**infra_devops（容器、Kubernetes、系統監控）**，11 筆：k9s (dev_cli)、kx (dev_cli)、k8shark (dev_cli)、dive (dev_cli)、bottom (dev_cli)、btop (dev_cli)、hw-smi (dev_cli)、system-monitoring-center (other)、iglance (other)、stats (other)、mac-performance-monitor (other)

**security_net（網路診斷、加密、密碼管理、漏洞掃描）**，17 筆：bandwhich (dev_cli)、dog (dev_cli)、nerva (dev_cli)、subnetlens (dev_cli)、wtfi2 (dev_cli)、nadzoring (dev_cli)、julius (dev_cli)、mcp-audit (dev_cli)、vulners-cli (dev_cli)、nox (dev_cli)、gpgfrontend (other)、keepassxc (other)、revelation (other)、clients (other)、lulu (other)、encrypt-a-lotta (other)、xipher (other)

**data_db（SQL、資料庫用戶端、JSON／CSV／log 工具）**，13 筆：jq (dev_cli)、yq (dev_cli)、miller (dev_cli)、visidata (dev_cli)、harlequin (dev_cli)、lazydb (dev_cli)、masume (dev_cli)、sqlmux (dev_cli)、agent-database-cli (dev_cli)、llmschema (dev_cli)、duckdb-web-shell (other)、tabularis (other)、dlt-viewer (other)

**productivity_docs（筆記、知識庫、白板與圖表、文件轉換）**，11 筆：gote (dev_cli)、excalidraw-cli (dev_cli)、marker (dev_cli)、appflowy (other)、joplin (other)、memos (other)、folio (other)、lemma (other)、collaborative-whiteboard (other)、pardus-pen (other)、pdf-to-epub (other)

**media_files（影音轉檔與剪輯、圖片壓縮、PDF 工具、檔案傳輸）**，19 筆：audacity (other)、yadaw (other)、handbrake (other)、lossless-cut (other)、flacon (other)、gifski (other)、imageflow (other)、converseen (other)、optipress (other)、image-tools (other)、supmover (other)、free-online-tools-for-video-audio-pdfs-images-and-ai (other)、stirling-pdf (other)、pdfkind (other)、djpdf (other)、word-sys-pdf-editor (other)、localsend (other)、transmission (other)、biglybt (other)

## 分數

`other` 和五個主題類別共用合併的熱門度基準，`dev_cli` 有自己的一套。所以搬完要跑 `pickfit score --refresh`：在 repo 外的複本試跑，離開 `dev_cli` 的 24 筆熱門度變動在 ±0.9 分以內，沒有一筆得到或失去寶藏（寶藏維持 202 筆）。

PM 點名的 helmfile、tilt（infra_devops）和 gitleaks、trivy、trufflehog（security_net）本來就在對的類別，沒有搬。
