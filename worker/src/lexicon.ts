/**
 * Word lists for ranking without a model (rules-only, or when the keyword
 * call fails): generic words that say little about the job, and a small
 * Chinese-to-English dictionary of common software and capability terms so a
 * Chinese request still has English words to match. Written from general
 * knowledge of how people describe software tasks, before any test results;
 * not fitted to the catalog.
 */

/** Words nearly every profile or request uses; they count for little in the rules' relevance. */
export const GENERIC_WORDS = (
  'tool tools terminal console shell command commands line cli code coding app apps application applications ' +
  'program programs software utility utilities util script scripts file files folder folders directory ' +
  'project projects simple easy easily fast quick quickly lightweight light small tiny minimal open source ' +
  'free support supports manage managing manager run running runs runner use uses using help helps helper ' +
  'developer developers dev devs build builds work workflow workflows thing stuff way better new feature ' +
  'features based powered written native modern cross platform plain text output input'
).split(' ');

/**
 * Traditional (and common Simplified) Chinese words -> English words a
 * profile would use. The longest key that matches at each position wins
 * ("記憶體" RAM before "記憶" remember).
 */
export const ZH_EN: Record<string, string> = {
  // files and text
  檔案: 'file', 文件: 'file document', 文檔: 'document docs', 資料夾: 'folder directory', 目錄: 'directory',
  重新命名: 'rename', 改名: 'rename', 更名: 'rename', 批次: 'batch bulk', 批量: 'batch bulk', 大量: 'bulk batch',
  正規表示式: 'regex', 正規表達式: 'regex', 正則表達式: 'regex', 正則: 'regex', 預覽: 'preview',
  搜尋: 'search', 搜索: 'search', 查找: 'find search', 尋找: 'find search', 取代: 'replace', 替換: 'replace',
  比較: 'compare diff', 差異: 'diff', 複製: 'copy', 移動: 'move', 刪除: 'delete', 重複: 'duplicate',
  壓縮: 'compress archive', 解壓縮: 'extract archive', 解壓: 'extract archive', 格式化: 'format', 排版: 'format',
  轉換: 'convert', 转换: 'convert', 轉檔: 'convert', 匯出: 'export', 导出: 'export', 匯入: 'import', 导入: 'import',
  編輯器: 'editor', 編輯: 'edit', 编辑: 'edit', 文字: 'text', 文本: 'text', 編碼: 'encoding', 字型: 'font',
  表格: 'table csv spreadsheet', 試算表: 'spreadsheet', 電子表格: 'spreadsheet',
  // terminal and system
  終端機: 'terminal', 終端: 'terminal', 终端: 'terminal', 命令列: 'command line', 命令行: 'command line',
  指令: 'command', 腳本: 'script', 脚本: 'script', 系統: 'system', 系统: 'system',
  監控: 'monitor', 监控: 'monitor', 監看: 'monitor watch', 監視: 'monitor watch', 盯: 'watch monitor',
  記憶體: 'memory ram', 内存: 'memory ram', 使用率: 'usage', 用量: 'usage', 效能: 'performance', 性能: 'performance',
  處理程序: 'process', 進程: 'process', 进程: 'process', 程序: 'process program', 磁碟: 'disk', 硬碟: 'disk',
  空間: 'space disk', 清理: 'clean cleanup', 排程: 'schedule cron', 定時: 'schedule timer', 自動化: 'automate automation',
  剪貼簿: 'clipboard', 剪贴板: 'clipboard', 視窗: 'window', 快捷鍵: 'shortcut hotkey', 通知: 'notification',
  日誌: 'log logs', 日志: 'log logs', 紀錄: 'log history', 記錄: 'log record', 歷史: 'history',
  設定檔: 'config', 設定: 'config settings', 配置: 'config', 環境變數: 'environment variables env', 密碼: 'password secret',
  金鑰: 'key secret', 密鑰: 'key secret', 機密: 'secret', 加密: 'encrypt encryption', 解密: 'decrypt', 憑證: 'certificate',
  權限: 'permission', 安全: 'security', 漏洞: 'vulnerability', 掃描: 'scan', 備份: 'backup', 同步: 'sync', 還原: 'restore',
  安裝: 'install', 套件: 'package', 依賴: 'dependency dependencies', 相依: 'dependency dependencies', 版本: 'version',
  更新: 'update upgrade', 升級: 'upgrade',
  // network and web
  網路: 'network', 网络: 'network', 伺服器: 'server', 服务器: 'server', 主機: 'host server', 遠端: 'remote', 远程: 'remote',
  連線: 'connection connect', 連接埠: 'port', 端口: 'port', 代理: 'proxy', 流量: 'traffic bandwidth', 頻寬: 'bandwidth',
  請求: 'request http', 網址: 'url', 網頁: 'web page', 网页: 'web page', 網站: 'website web', 瀏覽器: 'browser',
  爬蟲: 'scrape crawler', 爬取: 'scrape crawl', 抓取: 'scrape fetch', 下載: 'download', 上傳: 'upload', 分享: 'share',
  介面: 'interface api', 接口: 'api interface', 郵件: 'email mail', 信件: 'email mail', 訊息: 'message', 聊天室: 'chat',
  行事曆: 'calendar', 日曆: 'calendar', 待辦: 'todo task', 任務: 'task', 筆記: 'notes', 笔记: 'notes', 書籤: 'bookmark',
  // development
  程式碼: 'code source', 代碼: 'code', 代码: 'code', 程式: 'program code', 寫程式: 'coding code', 開發: 'development developer',
  除錯: 'debug debugger', 調試: 'debug', 偵錯: 'debug', 錯誤: 'error bug', 測試: 'test testing', 部署: 'deploy deployment',
  容器: 'container docker', 映像檔: 'image docker', 資料庫: 'database', 数据库: 'database', 查詢: 'query', 數據: 'data',
  資料: 'data', 版本控制: 'version control git', 提交: 'commit', 分支: 'branch', 合併: 'merge', 衝突: 'conflict',
  審查: 'review', 程式碼審查: 'code review', 重構: 'refactor', 文件產生: 'documentation generate', 註解: 'comment',
  自動完成: 'autocomplete completion', 補全: 'completion autocomplete', 語法: 'syntax', 高亮: 'highlight',
  型別: 'type', 編譯: 'compile build', 打包: 'bundle package', 效能分析: 'profile profiling performance',
  // AI and models
  模型: 'model', 大模型: 'llm model', 語言模型: 'language model llm', 本地: 'local', 本機: 'local', 離線: 'offline',
  离线: 'offline', 聊天: 'chat', 對話: 'chat conversation', 助手: 'assistant agent', 助理: 'assistant agent',
  智能體: 'agent', 代理人: 'agent', 提示詞: 'prompt', 提示: 'prompt', 上下文: 'context', 推理: 'inference reasoning',
  推論: 'inference', 微調: 'fine-tune fine-tuning', 訓練: 'train training', 量化: 'quantize quantization',
  顯卡: 'gpu', 显卡: 'gpu', 向量: 'vector embedding', 嵌入: 'embedding', 檢索: 'retrieval rag search',
  知識庫: 'knowledge base rag', 記憶: 'memory remember', 记忆: 'memory remember', 摘要: 'summarize summary', 總結: 'summarize',
  翻譯: 'translate translation', 翻译: 'translate translation', 語音: 'speech voice audio', 语音: 'speech voice audio',
  錄音: 'recording audio', 逐字稿: 'transcript transcribe', 轉錄: 'transcribe transcription', 轉文字: 'transcribe text',
  聽寫: 'dictation speech', 朗讀: 'text to speech tts', 文字轉語音: 'text to speech tts', 語音轉文字: 'speech to text transcribe',
  辨識: 'recognition', 识别: 'recognition', 圖片: 'image', 图片: 'image', 圖像: 'image', 照片: 'photo image',
  影片: 'video', 视频: 'video', 視訊: 'video', 音訊: 'audio', 音频: 'audio', 音樂: 'music audio', 字幕: 'subtitle subtitles',
  截圖: 'screenshot', 生成: 'generate generation', 產生: 'generate', 光學辨識: 'ocr', 文字辨識: 'ocr',
  費用: 'cost', 花費: 'cost spending', 成本: 'cost', 額度: 'quota limit', 工作流: 'workflow',
};

/**
 * For deciding whether a tool fits (rules only; not used for ranking): words in
 * a request that are not part of the job itself. Request filler ("looking",
 * "recommend", "thousands") and the kind of tool, which the category already
 * settles ("MCP", "LLM", "AI assistant", "local").
 */
export const NOT_THE_JOB_WORDS = (
  'want wanted need needs needed looking look find something anything someone way able allow allows let lets ' +
  'recommend recommendation recommended suggest suggestion alternative alternatives similar prefer preferably ideally ' +
  'possible try trying good great nice best better also just only even well really sure kind sort ' +
  'many multiple several lot lots each every all any both other same own whole entire thousand thousands hundred ' +
  'hundreds dozen dozens before after first last next one two three four five few some more most ' +
  'mcp ai llm llms model models local locally offline assistant assistants chatgpt claude cursor copilot'
).split(' ');

/** English phrasings of a job that the profiles say in one word (decision only). */
export const EN_PHRASES: Record<string, string> = {
  'keep an eye on': 'monitor',
  'keep track of': 'track',
  'look up': 'search',
  'clean up': 'cleanup',
  'back up': 'backup',
  'spin up': 'start',
  'set up': 'setup',
  'read aloud': 'text to speech',
  'speak out': 'text to speech',
  'dictate': 'speech to text',
  'take notes': 'notes',
  'jot down': 'notes',
  'turn into': 'convert',
  'figure out': 'analyze',
};
