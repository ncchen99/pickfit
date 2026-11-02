# 不用另外裝工具，git 內建的 word diff 就能做到

先講結論：git 本身就能標出一行裡改了哪幾個字，只是預設用空白分隔「詞」。中文段落沒有空白，所以整段會被當成一個詞，看起來就是整行紅綠。只要告訴 git 把每個中文字當成一個單位就行了。

我的假設：你用 bash（Ubuntu 預設），檔案是 UTF-8 編碼。

## 第一步：先試一次（不會改任何設定）

在你的 repo 裡執行：

```bash
git diff --color-words=$'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
```

這個正規表示式的意思：
- `[A-Za-z0-9_]+`：英文單字、數字、變數名照常整個算一個詞，不會被拆成單一字母。
- `[^\x80-\xbf[:space:]][\x80-\xbf]*`：一個 UTF-8 字元（開頭位元組加上後面的延續位元組）算一個單位。所以每個中文字、全形標點都會分開比對。
- `$'...'` 是 bash 的寫法，讓 `\x80` 這類寫法變成真正的位元組。這段一定要照抄，不能換成一般的單引號或雙引號。

結果應該只有改過的字會標紅或標綠，其他部分照原樣顯示。

如果你要的是沒有顏色的輸出（例如要貼到別處），改用 `--word-diff=plain`，會顯示成 `[-刪除-]{+新增+}` 這種格式：

```bash
git diff --word-diff=plain --word-diff-regex=$'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
```

## 第二步：試過覺得好用，就設成永久

**做法 A：全域設定（最簡單）**

```bash
git config --global diff.wordRegex $'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
git config --global alias.wd 'diff --color-words'
```

之後打 `git wd` 就是逐字比對。`git log -p --color-words`、`git show --color-words` 也都會套用這個規則。一般的 `git diff` 不受影響，還是整行顯示。

**做法 B：只對 Markdown 生效**

在 repo 根目錄的 `.gitattributes` 加一行：

```
*.md diff=cjk
```

然後設定：

```bash
git config --global diff.cjk.wordRegex $'[A-Za-z0-9_]+|[^\x80-\xbf[:space:]][\x80-\xbf]*'
```

之後對 `.md` 檔用 `git diff --color-words` 時會逐字比對，其他程式碼檔案還是用一般規則。

## 備註

- **想要更好看的介面，可以考慮 delta**（`sudo apt install git-delta`，Ubuntu 22.10 以後的版本才有這個套件）。它會並排顯示，也有行內標示。不過它預設也是以「詞」為單位，一整串中文可能還是被當成一個詞。我沒有實際測過它處理中文的效果，所以建議先用上面內建的方法。
- **長期的做法**：很多人寫技術文件會採用「一句一行」（semantic line breaks），也就是在句號後換行。Markdown 渲染時同一段落裡的換行不會顯示出來，但 diff、code review 和解衝突都會清楚很多。這個做法可以和上面的設定一起用。