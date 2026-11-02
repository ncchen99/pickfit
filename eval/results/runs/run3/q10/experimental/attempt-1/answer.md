# 不用另外裝工具，git 內建的 word diff 就能做到

git 本身就能顯示一行裡改了哪些字，問題在於「字」怎麼切。`git diff --word-diff` 預設用空白切詞，中文段落裡沒有空白，所以整段被當成一個「詞」，結果還是整段紅綠。解法是自己給 git 一條切詞規則（`wordRegex`）：**英文和數字照整個單字切，中文一個字切一段**。

## 主要建議：用 `.gitattributes` 為 Markdown 設定切詞規則

### 1. 先試一次，不改任何設定

在你的 repo 裡執行：

```bash
git diff --word-diff=color --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
```

這樣只會把改過的字標出來，刪掉的是紅色，新增的是綠色，不會再整行紅綠。效果如果滿意，再做下面的永久設定。

### 2. 永久設定（全域，所有 repo 都適用）

```bash
# 定義一個名叫 markdown 的 diff 規則：英文單字整個算，其他非空白字元一個字算一段
git config --global diff.markdown.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'

# 建立全域的 attributes 檔，讓 *.md 套用這個規則
mkdir -p ~/.config/git
echo '*.md diff=markdown' >> ~/.config/git/attributes
```

（如果只想套用在某個 repo，就把 `*.md diff=markdown` 寫進該 repo 的 `.gitattributes`。）

### 3. 平常使用

```bash
git diff --word-diff=color      # 或 --color-words，效果一樣
git show --word-diff=color HEAD
git log -p --word-diff=color
```

想少打幾個字可以設 alias：

```bash
git config --global alias.wd 'diff --word-diff=color'
# 之後執行：git wd
```

要讓 git 在每次 diff 時自動用 word diff，沒有單一設定可以開；用 alias 是最常見的做法。

## 如果中文出現亂碼

這個規則要靠 UTF-8 locale 才能正確辨認一個中文字。你可以執行 `locale` 檢查，應該要看到 `LANG=...UTF-8`，Ubuntu 預設就是這樣。我的假設是你的 locale 是 UTF-8。如果輸出還是出現 `�` 這種被切壞的字，就改用照 UTF-8 位元組切字的寫法（要在 bash 裡執行）：

```bash
git diff --word-diff=color --word-diff-regex=$'[A-Za-z0-9_]+|[^\x80-\xbf][\x80-\xbf]*'
```

## 可選：想要更好看的介面

如果你還想要並排顯示、語法高亮，可以裝 **delta**。在 Ubuntu 22.10 以後的版本可以用 `sudo apt install git-delta` 安裝，指令名稱是 `delta`。不過它判斷行內差異也是靠斷詞，對沒有空白的中文長段落，效果不一定比上面的內建做法好。我建議先用內建的方式，覺得不夠再試 delta。

## 長期做法

很多人寫技術文件會「一句一行」（semantic line breaks），diff 就自然只顯示改到的那一句。但要注意，中文句子中間換行時，部分 Markdown 渲染器會在兩行之間多插一個空白。發布前先確認你的渲染器怎麼處理，再決定要不要改寫法。

---

依你的要求，以上指令我都沒有在你的機器上執行，也沒有實際在你的 Ubuntu 上驗證過。上面這條切詞規則是我根據 git 的運作方式推斷的，請先跑第 1 步確認效果，再做永久設定。