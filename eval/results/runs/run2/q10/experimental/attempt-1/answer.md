**不用另外裝工具。** Git 內建的 word diff 就能做到，只是要告訴它「中文一個字算一個詞」。

Git 預設用空白切詞，中文段落沒有空白，整段會被當成一個詞，所以還是整行紅綠。改用正規表示式切詞就好：

```bash
git diff --word-diff=color --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
```

這樣切：
- 英文單字和數字（像 `config`、`v2`）整個算一個詞，不會被拆成字母
- 中文、標點等其他非空白字元，每個字各算一個詞

結果是同一行裡只有改到的那幾個字會變色。

---

## 設定成預設（建議）

**1. 定義一個 diff 驅動，寫入全域設定：**

```bash
git config --global diff.cjk.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'
```

**2. 讓 `.md` 檔套用這個驅動。** 在專案根目錄的 `.gitattributes` 加一行：

```
*.md diff=cjk
```

如果想讓所有專案都套用，可以改寫在 `~/.config/git/attributes`。

**3. 加一個簡短的 alias：**

```bash
git config --global alias.wd 'diff --word-diff=color'
```

**第一次使用：**

```bash
git wd                 # 看工作區的改動
git wd --cached        # 看已 staged 的改動
git log -p --word-diff=color -- docs/xxx.md   # 看歷史
```

驗證方法：改一段文字裡的兩三個字，再執行 `git wd`。如果只有那幾個字標成紅色或綠色，就是成功了。

**我的假設和注意事項：**
- 假設你的終端機 locale 是 UTF-8。Ubuntu 預設就是，可以用 `locale` 確認。如果不是，中文可能會被拆成位元組而出現亂碼。
- 只想偶爾用一下的話，最短的寫法是 `git diff --color-words=.`，每個字元都算一個詞。缺點是英文也會被逐字母比對，看起來比較雜。
- 不建議把 word diff 設成 `git diff` 的全域預設，因為會影響 `git add -p` 和產生 patch 的工具。用 alias 比較安全。

---

## 選用：想要更好看的介面

如果想要並排顯示、語法上色和行內高亮，可以裝 **delta**。這是很多人在用的工具，但這次我沒有實際驗證過：

```bash
sudo apt install git-delta      # Ubuntu 24.04 以後；舊版請從 GitHub releases 下載 .deb
git config --global core.pager delta
git config --global interactive.diffFilter 'delta --color-only'
git config --global delta.side-by-side true
```

delta 的行內高亮適合改動不多的情況。如果一個很長的段落改了很多地方，上面的 word diff 通常比較清楚，兩種可以一起用。

---

## 長期建議

如果可以改寫作習慣，**一句一行**（semantic line breaks）會更好：在 Markdown 裡，單一換行在渲染後不會斷行，不影響輸出結果。這樣不管用哪種 diff，改動都能精確到句子，code review 和解決合併衝突也會容易很多。