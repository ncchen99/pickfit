# q16 開跑前的固定與紀錄

第 3 節：「pinned」「frozen」「choice recorded before freeze」的東西在**第一次開跑評測前 commit**。下面每一步在任何一組開跑前做完，結果填在本檔、commit；之後不改。這裡不跑任何翻譯工具：校準只用 `calibration/` 裡自己寫的對照資料。

## 1. 測試資料是否最新

```bash
python3 eval/fixtures/q16/build_manifest.py --check     # manifest.json 與 docs/ 一致
```

| 項目 | 值 |
|---|---|
| `docs/` 三個檔的 SHA-256（`manifest.json`） | |
| 總字數（`manifest.json` 的 `total_words`，約 1,000） | |
| 意義抽樣的 5 句（`manifest.json` 的 `meaning_sample`，種子 `q16-meaning-v1`） | |

## 2. 固定語言辨識器（`needs.json` 第 1 項）

在評分者自己的 venv 裝固定版本，然後：

```bash
python3 eval/fixtures/q16/lang_check.py --output eval/fixtures/q16/calibration/control-pt-PT \
  --only 02-team-handbook.md --backend <選定的> [--model-path <模型檔>] --out /tmp/q16-lang-ptpt.json
python3 eval/fixtures/q16/lang_check.py --output eval/fixtures/q16/calibration/control-pt-BR \
  --only 02-team-handbook.md --backend <選定的> [--model-path <模型檔>] --out /tmp/q16-lang-ptbr.json
python3 eval/fixtures/q16/lang_check.py --output eval/fixtures/q16/docs --map 02-team-handbook.md=eval/fixtures/q16/docs/02-team-handbook.md \
  --only 02-team-handbook.md --backend <選定的> [--model-path <模型檔>] --out /tmp/q16-lang-en.json
```

| 條件 | 結果 |
|---|---|
| pt-PT 對照：每一段都判為 `pt` 且信心 ≥ 0.9 | |
| pt-BR 對照：每一段都判為 `pt`（這一項只看語言，不看變體） | |
| 英文原文：沒有任何一段通過 | |

第一條不成立，就換一個辨識器（門檻 0.9 是凍結的，不能改）。

| 項目 | 值 |
|---|---|
| 辨識器與版本、模型檔 SHA-256 | |
| 相依套件版本（例如 numpy） | |
| 記錄日期 | |

## 3. 意義評分者（`needs.json` 第 2 項）

1. 念誠決定：看得懂葡萄牙文的盲評者，或固定版本的 LLM。寫在下表。
2. 用 `calibration/judge_cases.json` 的 6 題檢查（格式與正式的 judge input 相同）：
   - 人：`python3 eval/fixtures/q16/meaning/make_judge_input.py sheet --items eval/fixtures/q16/calibration/judge_cases.json --out /tmp/q16-sheet.md`
   - LLM：`python3 eval/fixtures/q16/meaning/make_judge_input.py requests --items eval/fixtures/q16/calibration/judge_cases.json --model <模型 ID> --out /tmp/q16-req.jsonl`，逐行送出 `body`，回答存成 `{"n": .., "run": .., "verdict": ..}` 的 JSON Lines。
3. 6 題都要和 `expected` 相同。不同時修改 `meaning/rubric.md`、重新檢查，修改內容記在這裡；全部對了才凍結。

| 項目 | 值 |
|---|---|
| 選擇（人／LLM） | |
| 人：誰（或角色）、是否知道組別（必須否） | |
| LLM：模型 ID、temperature（0；模型不接受時改 3 次取 2 次） | |
| 6 題結果 | |
| `rubric.md` 修改紀錄 | （預期是「無」） |
| 記錄日期 | |

## 4. 擋外連與外連監測（與 q14 相同）

在擋住的沙盒裡：

```bash
python3 $SHARED/egress.py probe --json /results/probe.json                 # exit 0
python3 $SHARED/egress.py selftest --out /results/selftest                 # _shared/calibration.md 步驟 1，各題共用一次
python3 $SHARED/egress.py run --out /results/quiet --label quiet -- sleep 10
python3 $SHARED/egress.py report --out /results/quiet                      # pass
```

| 項目 | 值 |
|---|---|
| 擋法與指令 | |
| `selftest` 結果 | （記在 `_shared/calibration.md`） |

`selftest` 不通過時，不改用 `/proc` 輪詢判過（它抓不到立刻失敗的連線）；照 `_shared/README.md` 第 1 節，請念誠決定替代做法並寫在這裡。

## 5. dev image 與自我測試

| 項目 | 值 |
|---|---|
| dev image digest | |
| `python3 -m unittest discover -s eval/fixtures/q16/tests -v` | |
| commit | |
