# q12 開跑前固定與確認（待填）

第一次開跑評測前做完、填好並 commit（第 3 節的「at freeze」）。不跑任何答案。

## 1. 固定測試模型（L2-2「repo id and revision pinned at freeze」）

1. 念誠從 `needs.json` 的候選選一個（條件：MLX 格式、4-bit、instruct、≤3B 參數；不需登入、沒有 gated；授權允許評測使用；主流架構；回覆放在一般的 content 裡、不是推理模型）。
2. 在主帳號（連網）：
   ```sh
   sudo mkdir -p /Users/Shared/eval-models && sudo chown "$(id -un)" /Users/Shared/eval-models
   python3 pin_model.py <repo id> --dest /Users/Shared/eval-models/<名稱>
   chmod 700 /Users/Shared/eval-models     # 平常不讓測試帳號讀到（README L2-2）
   ```
   會寫出 `model_pin.json`、`model_pin.env`、`model_files.sha256`，三個檔 commit 進本資料夾。
3. 填表：

| 項目 | 結果 |
|---|---|
| repo id | |
| 固定的 commit（revision） | |
| API 回報的 gated／license | |
| `config.json` 的 quantization（bits 要是 4） | |
| 參數量（依原始模型的說明，≤3B） | |
| 檔案總大小 | |
| 不帶 token 下載成功（`pin_model.py` 本身不送 token） | |

4. 每個 Mac 實跑日開始前，確認 repo 的最新 revision 還是固定的那個（否則照 README L2-2 的規則處理）：
   ```sh
   curl -s https://huggingface.co/api/models/<repo id>/revision/main | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])'
   ```

| 日期 | 最新 revision | 和固定的相同？ |
|---|---|---|
| | | |

## 2. 固定 openai client（L2-3「the pinned official openai Python client」）

```sh
<python> -m venv /Users/Shared/eval-grader/venv
/Users/Shared/eval-grader/venv/bin/pip install "openai==<版本>"
/Users/Shared/eval-grader/venv/bin/pip freeze > grader-requirements.lock    # commit 進本資料夾
chmod -R a+rX /Users/Shared/eval-grader
/Users/Shared/eval-grader/venv/bin/python selftest.py                        # 要 ALL OK（含 SDK 版）
```

| 項目 | 結果 |
|---|---|
| Python（路徑、版本） | |
| openai 版本 | |
| `grader-requirements.lock` 的 SHA-256 | |
| `selftest.py`（評分 venv） | |
| `selftest.py`（本機，2026-10-30） | ALL OK：系統 Python 3.9.6（urllib 版）與 repo 的 `.venv`（Python 3.12、openai 3.40.0，含 SDK 版） |

## 3. Mac 環境

基準環境（Homebrew 的處理、硬體、Xcode 版本）與 q11 相同，記在 `../q11/calibration.md` 第 4 節；`offline.sh` 的確認也記在那裡。
