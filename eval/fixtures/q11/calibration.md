# q11 開跑前校準（待填）

第一次開跑評測前做完、填好並 commit。這些是第 3 節所說「at freeze」的固定版本與測試資料；不跑任何答案。

## 1. OpenCC 字元表（L2-4；q15 共用）

1. 從 `needs.json` 選定的 OpenCC 版本取得 `data/dictionary/STCharacters.txt` 與 `data/dictionary/TSCharacters.txt`，放在評分機器的固定位置（不 commit 進 repo）。
2. 記下版本與 SHA-256：

| 項目 | 結果 |
|---|---|
| OpenCC 版本（tag） | |
| 取得來源 URL | |
| `STCharacters.txt` SHA-256 | |
| `TSCharacters.txt` SHA-256 | |

3. 逐字分類的抽查（`python3 opencc_scorer.py --dict-dir DIR --probe <字>`），把結果填進表格：

| 字組 | 預期 | 結果 |
|---|---|---|
| 台 后 里 干 只 才 面 系 | neutral（兩種字體都用） | |
| 為 軟 視 頻 網 絡 認 這 說 們 個 會 裡 臺 | traditional | |
| 为 软 视 频 网 络 认 这 说 们 个 会 | simplified | |

   有和預期不同的字（例如台灣常用、但被判成只屬簡體的字），在這裡列出，並在開跑前決定：照凍結的規則照算，或在 9.x 勘誤登記改法（兩組一起套用）。
4. 用正式字元表跑合成回覆：

```sh
python3 opencc_scorer.py --dict-dir DIR samples/good/P*.txt        # 預期 PASS
python3 opencc_scorer.py --dict-dir DIR samples/simplified/P*.txt  # 預期 FAIL
```

| 項目 | 結果（比例、不同字數、只屬簡體的字） |
|---|---|
| samples/good | |
| samples/simplified | |

## 2. 盲評模型（L2-3）

| 項目 | 結果 |
|---|---|
| Claude 模型完整 ID | |
| temperature | 0 |
| samples/good 四題的判定（預期全部 true） | |
| samples/offtopic P2 的判定（預期 false） | |

```sh
python3 score_replies.py --write-judge-requests /tmp/cal.jsonl samples/good samples/offtopic
```

## 3. 取樣規則（L2-2～L2-5）

README「取樣設定」的順序（seed `0` → temperature `0` → 跑 3 次取 2 次），念誠確認：＿＿（日期、確認）

## 4. Mac 環境（L2-1、L2-2）

| 項目 | 結果 |
|---|---|
| 機器、晶片、記憶體、macOS 版本 | Apple M5、24 GiB、macOS 27.0.1（2026-10-30 記錄，開跑前再確認） |
| Xcode／Command Line Tools 版本 | |
| 基準環境選項（needs.json 的 Mac baseline） | |
| 基準 Homebrew 版本（選項 A） | |
| `python3 selftest.py --mac`（在這台 Mac） | ALL OK（2026-10-30，主帳號；開跑前在測試帳號再跑一次） |
| 在一個測試帳號跑 `offline.sh off` → `check` → `on` | |
| `footprint_watch.py` 與 `/usr/bin/time -l` 對照（同一個程式，差距應 < 1%） | |

對照方法：`footprint_watch.py` 開著時，在被量的 shell 裡跑 `/usr/bin/time -l /usr/bin/python3 -c "b=bytearray(500*1024*1024); b[::4096]=b'x'*len(b[::4096])"`，比較 `time` 的「peak memory footprint」和 `footprint.json` 裡同一個 pid 的 `peak_footprint`。
