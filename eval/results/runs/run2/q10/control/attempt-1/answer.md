# 中文 Markdown 的 git diff：不用另外裝工具，git 內建的 word diff 就夠用

**建議：直接用 git 內建的 word diff，再把「詞」的切法改成以單一中文字為單位。**

git 預設用空白分隔「詞」。中文句子中間沒有空白，所以整段會被當成一個詞，看起來還是整行紅綠。只要換一個切詞規則，就能看出改了哪幾個字。

## 1. 先試一下（不改任何設定）

```bash
git diff --color-words='[A-Za-z0-9_]+|[^[:space:]]'
```

- `[A-Za-z0-9_]+`：英文單字和變數名稱維持整個詞。
- `[^[:space:]]`：其他字元一個一個比，所以中文會以「字」為單位。

結果會標在同一行裡，刪掉的字是紅色，新增的字是綠色。

如果要貼到沒有顏色的地方（例如 code review 留言），改用：

```bash
git diff --word-diff=plain --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
```

輸出會長這樣：`[-舊字-]{+新字+}`。

## 2. 設成永久設定（只對 Markdown 生效）

**第一步：全域設定一個 diff driver**

```bash
git config --global diff.cjk.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'
git config --global alias.wdiff 'diff --color-words'
```

**第二步：在 repo 根目錄的 `.gitattributes` 加一行**

```
*.md diff=cjk
```

如果想讓所有 repo 都套用，可以寫在 `~/.config/git/attributes`。

**之後的用法**

```bash
git wdiff            # 工作區的變更
git wdiff --staged   # 已 add 的變更
git log -p --color-words   # 歷史紀錄也能逐字看
```

一般的 `git diff` 不受影響，還是逐行顯示。`git apply` 和 patch 也照常運作。

## 前提與假設

- **我假設你的 locale 是 UTF-8。** 這是 Ubuntu 的預設。可以用 `locale` 確認 `LANG` 是否像 `zh_TW.UTF-8` 或 `C.UTF-8`。如果是 `C` 或 `POSIX`，一個中文字可能會被拆成好幾個 byte，結果出現亂碼。這時先執行 `export LANG=C.UTF-8` 再試。
- 我沒有在你的機器上實際跑過這些指令，請以你第一次執行的結果為準。

## 選用：想要更好看的介面就裝 delta

delta 是 side-by-side、帶行號的 diff 顯示工具，會在逐行 diff 裡另外標出行內改動的部分。不過它的行內比對對中文的效果不一定比上面的 `--color-words` 好，所以當作輔助就好。

```bash
sudo apt install git-delta     # 較新的 Ubuntu 版本有收錄；沒有的話到 GitHub dandavison/delta 的 Releases 下載 .deb
git config --global core.pager delta
git config --global interactive.diffFilter 'delta --color-only'
git config --global delta.side-by-side true
```

## 寫作習慣上的根本解法

可以改成一句一行（semantic line breaks），也就是在「。」「；」後面換行。Markdown 渲染時，段落內的單一換行不影響結果（GitHub 等環境中，中文之間頂多多出一個空格）。這樣連一般的 `git diff` 都能看清楚改了哪一句，衝突也比較容易解決。