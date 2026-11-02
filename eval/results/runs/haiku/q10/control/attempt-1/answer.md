## 主要建議：不用另外裝工具，用 git 內建的字詞級 diff

**原因**：git 預設以空白切分「字詞」。中文沒有空白，整段就被當成一個字，所以任何一處改動都會整行標紅綠。只要告訴 git 用「字元」或「英數詞」切分，就能看出實際改了哪幾個字。

**Ubuntu 上的步驟**（git 已裝好，不需要安裝任何東西）：

1. 試用一次，確認效果：
   ```bash
   git diff --word-diff=color --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'
   ```
   這個 regex 讓英文和數字以整個單字為單位，每個中文字（和標點）各自獨立，比逐字切分更容易讀。若想逐字切分，把 regex 換成 `.` 即可。

2. 存成別名，之後直接用 `git wdiff`：
   ```bash
   git config --global alias.wdiff "diff --word-diff=color --word-diff-regex='[A-Za-z0-9_]+|[^[:space:]]'"
   ```
   之後執行 `git wdiff` 就會看到類似 `[-舊字-]{+新字+}` 的字級標示。

若想讓 `git diff` 本身就顯示字級差異，可以用 `.gitattributes` 加上自訂 diff driver，但設定較繁瑣，上面的別名通常已足夠。

## 根本的解法：一句一行

這個問題的根源是檔案結構。如果每個句子各佔一行（中文寫作常見的「語意換行」，以句號、分號後換行），改一句話就只會動到那一行，`git diff` 本身就很清楚，連工具都不需要。很多中文技術文件專案都採用這種寫法。可以在寫作規範中加一條「一句一行」，並在編輯器中開啟自動換行顯示，寫作體驗不受影響。

## 可選：用 delta 美化輸出

如果想要更漂亮的並排或語法高亮輸出，可以裝 `delta`：

```bash
sudo apt install git-delta
```

（Ubuntu 23.04 以後才有此套件，可先用 `apt policy git-delta` 確認。）接著在 `~/.gitconfig` 加入：

```ini
[core]
    pager = delta
[interactive]
    diffFilter = delta --color-only
[delta]
    navigate = true
    side-by-side = true
```

`delta` 的字級高亮對中文的效果不一定比上面的 regex 精準，建議先用內建方式，覺得不夠再裝。

**假設說明**：你的系統資訊顯示為 macOS（darwin），但你說是 Ubuntu。以上指令在兩者上都適用，所以我以你說的 Ubuntu 為準。

Sources:
- git 文件 `git-diff` 的 `--word-diff-regex` 與 `diff.<driver>.wordRegex` 說明（https://git-scm.com/docs/git-diff）