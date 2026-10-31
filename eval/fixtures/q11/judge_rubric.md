# q11 盲評說明（L2-3 的「answering the prompt」）

這份是 L2-3 語意判斷用的固定評分說明（第 5 節：「需要判斷語意時，用固定版本的 Claude 模型、固定評分說明，看不到組別」）。`score_replies.py --write-judge-requests` 會把下方標記之間的文字當成 system prompt，每個請求只放一題的題目與回覆，不放組別、工具名稱、模型名稱或其他回覆。

- 模型：開跑前固定一個 Claude 模型的完整 ID，記在 `calibration.md`；temperature 0。
- 每個（回覆組、題目）只送一次；回傳不是合法 JSON 時重送一次，仍不合法就由念誠人工判定並記錄。
- 判定結果寫進該回覆組資料夾的 `judge.json`：`{"P1": true, "P2": false, "P3": true, "P5": true}`，原始回應另存 `judge-raw.jsonl`。
- 校準：開跑前用 `samples/` 的合成回覆跑一次（見 `calibration.md`），預期 good 全部 true、`samples/offtopic` 的 P2 是 false。

<!-- RUBRIC START -->
You are grading one reply from a local language model to one Chinese prompt. You see only the prompt and the reply. Decide whether the reply answers the prompt.

Answer "true" only if all of these hold:
1. The reply is about what the prompt asks, not a different topic, a refusal, or a request for clarification.
2. It addresses every part the prompt explicitly asks for, at least briefly:
   - a prompt about steps: gives the steps in a sensible order;
   - a prompt asking for three items: names three distinct items that fit and says something about each;
   - a prompt asking for a definition plus advantages and disadvantages: gives all three;
   - a prompt listing several tasks: covers each listed task.
3. It is coherent: sentences make sense and connect; it is not mostly repeated text, garbled characters, or a list of unrelated words.

Do NOT judge: length or the requested character count, writing style, minor factual slips, formatting, or whether the script is Traditional or Simplified Chinese and which regional vocabulary it uses (those are checked separately).

Reply with JSON only, on one line: {"answers_prompt": true or false, "reason": "<one short sentence in English>"}
<!-- RUBRIC END -->
