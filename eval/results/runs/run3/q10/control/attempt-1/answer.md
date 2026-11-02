# 不用另外裝工具，Git 內建就做得到

Git 本身有字詞級 diff（`--color-words` / `--word-diff`），但預設用空白切詞。中文沒有空白，所以整段被當成一個「詞」，結果還是整段紅綠。只要把切詞規則改成**每個中文字算一個詞、英文單字照舊算一個詞**就行。

以下假設：你用 bash，系統 locale 是 UTF-8，只想改 `.md` 檔的 diff 行為。

## 主要建議：設定一個給 Markdown 用的 diff 規則

### 1. 先直接試（不改任何設定）

在你的 repo 裡執行：

```bash
git diff --color-words=$'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
```

- `[A-Za-z0-9_]+`：英文、數字、變數名稱維持整個詞比對
- `[^\x80-\xbf[:space:]][\x80-\xbf]*`：抓一個完整的 UTF-8 字元。每個中文字、每個全形標點各算一個詞
- `$'...'` 是 bash 的語法，會把 `\x80` 這類寫法轉成真正的位元組。Git 的正規表達式是逐位元組比對的，所以一定要這樣寫，不能直接寫成 `.`

輸出會是同一行裡只有改到的字變色，例如「我們~~使用~~**採用**這個方法」。

### 2. 覺得可以，就設成永久的

**(a) 全域設定 diff 驅動的切詞規則**（只要設一次）：

```bash
git config --global diff.zh.wordRegex $'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
```

**(b) 指定讓 `.md` 套用這個規則**。兩種做法擇一：

- 只套用在單一 repo：在 repo 根目錄的 `.gitattributes` 加上
  ```
  *.md diff=zh
  ```
- 套用在所有 repo：
  ```bash
  git config --global core.attributesFile ~/.gitattributes
  echo '*.md diff=zh' >> ~/.gitattributes
  ```

**(c) 加個簡短的 alias**（可選）：

```bash
git config --global alias.wd 'diff --color-words'
```

### 3. 之後的日常用法

```bash
git wd                       # 工作區的改動，逐字顯示
git diff --color-words       # 跟上一行一樣
git diff --word-diff         # 不靠顏色，用 [-刪-]{+增+} 標記，適合貼給別人看或沒有彩色的終端機
git log -p --color-words     # 看歷史紀錄
git show --color-words HEAD
```

設好 `.gitattributes` 之後，`--color-words` 不用再帶正規表達式，會自動用 `diff.zh.wordRegex`。一般的 `git diff` 輸出不變，`git apply` 和 patch 也照常能用。

## 選用：想要更好看的介面可以裝 delta

如果想要並排顯示、語法上色、行號，可以裝 [delta](https://github.com/dandavison/delta)：

```bash
sudo apt install git-delta      # Ubuntu 22.04 以上的套件庫就有
```

`~/.gitconfig` 加上：

```ini
[core]
    pager = delta
[interactive]
    diffFilter = delta --color-only
[delta]
    side-by-side = true
    line-numbers = true
```

要注意的是，delta 預設的行內差異是用 `\w+` 切詞，一整串連續的中文字可能還是會被當成一個詞，標示效果不一定比上面的 Git 內建做法精確。所以建議以 Git 內建的 `--color-words` 為主，delta 是錦上添花，不是必要的。

## 長遠的小建議

如果文件可以接受，寫 Markdown 時每句話換一行（semantic line breaks），渲染結果不變，但一般的 `git diff`、code review 和 merge 衝突都會清楚很多。