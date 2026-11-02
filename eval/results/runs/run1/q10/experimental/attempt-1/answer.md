# 不用另外裝工具，git 內建的 `--word-diff` 就可以

只是要多加一個設定。git 預設用空白切「詞」，中文字之間沒有空白，所以整段中文會被當成一個詞，結果還是整段紅綠。只要讓 git 把每個中文字當成一個單位，就能看到改了哪幾個字。

我照你說的，沒有在你的電脑上執行任何指令，也沒有改任何檔案。下面的步驟都由你自己決定要不要執行。我也查了 pickfit 的工具庫，裡面沒有比 git 內建功能更適合這件事的工具。

## 第一步：先試一次（不會改任何設定）

在你的 repo 裡執行：

```bash
git diff --word-diff=color --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
```

- `[A-Za-z0-9_]+`：英文單字、變數名稱保持整個詞比對，不會被拆成一個一個字母。
- `[^[:space:]]`：其他非空白字元（中文字、標點）每個字單獨比對。
- `--word-diff=color`：只用顏色標出刪掉和新增的字。如果你的終端機沒有顏色，或是要貼到別的地方，可以改成 `--word-diff=plain`，會顯示成 `[-刪除-]{+新增+}`。

**我的假設：** 你的系統語系是 UTF-8（Ubuntu 預設就是）。如果中文顯示成亂碼，或是比對結果怪怪的，先執行 `locale` 確認 `LC_CTYPE` 是不是類似 `zh_TW.UTF-8` 或 `en_US.UTF-8`。

## 第二步：設定成固定使用（只對 Markdown 生效）

1. 讓 git 用你的切字規則比對 `.md` 檔。這一行會寫進 `~/.gitconfig`：
   ```bash
   git config --global diff.markdown.wordRegex '[A-Za-z0-9_]+|[^[:space:]]'
   ```
2. 在 repo 根目錄的 `.gitattributes` 加上這一行（沒有這個檔就新建一個）：
   ```
   *.md diff=markdown
   ```
3. 設一個簡短的別名：
   ```bash
   git config --global alias.wd 'diff --word-diff=color'
   ```

設定好之後，平常就這樣用：

```bash
git wd                 # 還沒 stage 的改動
git wd --cached        # 已經 stage 的改動
git wd HEAD~1          # 跟上一個 commit 比
git log -p --word-diff=color   # 看歷史紀錄時也能逐字顯示
```

**驗證方法：** 隨便改一個長段落裡的兩三個字，執行 `git wd`。如果只有那幾個字變色，就設定成功了。

## 第三步（可選）：想要更好看的介面

如果你想要左右並排顯示、語法上色，可以考慮 **delta**。Ubuntu 24.04 以後可以用 `sudo apt install git-delta` 安裝。要注意兩件事：
- pickfit 沒有驗證過 delta。
- delta 標示行內差異是靠它自己切詞，中文可能還是會一整串一起標起來。

所以要「準確看出改了哪幾個字」，還是上面的 `--word-diff-regex` 方法最可靠。delta 比較適合當作看程式碼時的外觀升級。

## 補充建議

如果文件是多人協作，可以考慮改用「一句一行」的寫法：每個句號後面換行。Markdown 顯示時會自動合併成同一段，這樣以後連一般的 `git diff`、GitHub 的 PR 頁面都能清楚看出改了哪幾句。