# q13 開跑前的固定與紀錄

第 3 節：檢查項目裡的「frozen」「hash recorded」指的是**第一次開跑評測前 commit**。下面每一步在任何一組開跑前做完，結果填在本檔、commit；之後不改。這裡不跑任何推論伺服器：凍結的只有測試資料，不能先拿某個工具試過再挑模型。

## 1. 選定並記錄 GGUF

1. 念誠從 `needs.json` 的候選選一個。
2. 下載一次（只下載這一個檔），在本機算：
   ```bash
   python3 eval/fixtures/q13/gguf_info.py <檔案> > /tmp/q13-gguf.json
   ```
3. 確認：`general.size_label` 在 0.5B–1.5B 之間；是 instruct／chat 版本；`has_chat_template` 是 `true`。任一不符就換候選。
4. 上傳到評測專用的唯讀儲存（`needs.json` 第 2 項），在沙盒裡 `sha256sum /models/<檔名>` 必須等於下表。

| 項目 | 值 |
|---|---|
| 來源 URL | |
| repository commit | |
| 檔名 | |
| bytes | |
| SHA-256 | |
| general.architecture | |
| general.size_label | |
| general.file_type | |
| has_chat_template | |
| 授權（來源頁面） | |
| 唯讀儲存（volume 名稱／路徑） | |
| 記錄日期 | |

## 2. 沙盒與 dev image

開一個 `sandbox.json` 規格的沙盒，記下：

| 項目 | 值 |
|---|---|
| dev image digest | |
| `nproc` | （必須是 8） |
| 記憶體上限 | （必須是 16 GiB） |
| `nvidia-smi` | （必須不存在） |
| CPU 型號（`/proc/cpuinfo` 的 model name） | |
| `/models` 寫入測試（`touch /models/x`） | （必須失敗） |
| 評分用 Python（dev image 內建或 `/eval` 上的獨立版本） | |

再跑一次空的磁碟量測，確認沒有不該算的掛載：

```bash
python3 /eval/q13/disk_usage.py snapshot --exclude /models --exclude /eval --exclude /results --out /results/disk-idle.json
```

| 項目 | 值 |
|---|---|
| 量到的掛載點與檔案系統類型 | |
| 間隔 1 分鐘再量一次的差（閒置雜訊） | |

## 3. 本資料夾的自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q13/tests -v
```

| 項目 | 值 |
|---|---|
| 測試結果 | |
| commit | |
