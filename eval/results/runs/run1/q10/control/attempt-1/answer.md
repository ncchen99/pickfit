# 不用另外裝工具，git 內建的 word diff 就能做到

要加的只有一個設定。git 有 `--word-diff` 和 `--color-words`，只顯示行內改動的部分。

但直接用在中文上沒有效果。git 預設用空白切詞，一整段中文中間沒有空白，會被當成一個「詞」，結果還是整段紅綠。所以要給它一個正則，**把每個中文字當成一個單位，英文單字保持完整**。

## 主要推薦：用 `--color-words` 加上自訂切詞規則

### 1. 先試一次（不用改任何設定）

在你的 repo 裡執行：

```bash
git diff --color-words='[A-Za-z0-9_]+|[^[:space:]]'
```

- `[A-Za-z0-9_]+`：英文、數字、變數名稱整個當成一個詞，例如 `config_file`
- `[^[:space:]]`：其他非空白字元各自算一個單位，所以每個中文字和標點都分開比對

輸出會是同一行裡只有改到的字變紅或變綠。如果終端機沒有顏色，或你想複製貼上，可以改用文字標記：

```bash
git diff --word-diff=plain --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
```

刪掉的字顯示成 `[-舊字-]`，新增的字顯示成 `{+新字+}`。

### 2. 只對 Markdown 套用，設定一次就好

在 repo 根目錄的 `.gitattributes` 加一行（沒有這個檔就新建）：

```
*.md diff=cjk
```

然後設定這個 `cjk` diff driver 的切詞規則：

```bash
git config --global diff.cjk.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'
```

之後只要打 `git diff --color-words` 或 `git diff --word-diff`，`.md` 檔就會自動用這個規則，其他程式碼檔案不受影響。

### 3. 設一個短指令（可選）

git 沒有「預設開啟 word diff」的設定，所以通常用 alias：

```bash
git config --global alias.wdiff 'diff --color-words'
```

以後打 `git wdiff` 就可以了。`git wdiff --cached` 和 `git wdiff HEAD~1` 這類寫法照常能用。`git log -p --color-words` 和 `git show --color-words` 也一樣有效。

### 我假設的前提

- **系統 locale 是 UTF-8**。Ubuntu 預設是 `en_US.UTF-8` 或 `C.UTF-8`，通常沒問題。如果中文字被切成亂碼（例如出現 `<E4>` 這種位元組），用 `locale` 檢查一下，確認 `LANG` 結尾是 `.UTF-8`。
- 我沒有在你的機器上實際跑過這些指令，請以你那邊的輸出為準。

## 補充：另一個習慣上的做法

很多人寫中文 Markdown 會改成**一句一行**，也就是在 `。`、`？` 後面換行。Markdown 渲染時同一段落裡的單一換行不會變成斷行，結果看起來一樣，但 diff 天然就是逐句的，`git blame` 和 merge 衝突也會清楚很多。這可以和上面的 word diff 一起用。

## 如果之後想要更好看的介面

- **delta**（`sudo apt install git-delta`）：有並排顯示、語法高亮。不過它預設的行內比對對中文是以整段連續中文為單位，效果不如上面的 `--color-words`，所以只是錦上添花，不能取代上面的設定。
- **diff-highlight**：Ubuntu 的 git 套件附帶，在 `/usr/share/doc/git/contrib/diff-highlight`，需要先 `make` 才能用。它只標出前後相同部分中間的差異區段，適合一段只改一處的情況。

結論：先跑第 1 步那行指令看效果，滿意的話再做第 2、3 步，什麼都不用裝。