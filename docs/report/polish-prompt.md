# Prompt for the copy edit

Paste this into ChatGPT, then attach or paste `docs/REPORT.md` below it. Save the answer as `docs/REPORT.md` (or send it back to Claude) and rebuild the HTML with `uvx --with markdown python docs/report/build.py`.

---

You are copy-editing the final report of a hackathon project called pickfit. Improve the tone and flow only. The facts must not change.

Rules:

1. Keep every number, date, model name, file path, command, URL, commit hash and tag exactly as written. Do not add facts, numbers, claims or examples that are not already in the text.
2. Keep the structure: the same headings in the same order, the same tables (you may tighten cell wording), the same Mermaid code blocks unchanged, and the same Markdown syntax.
3. Keep the honesty. Experiments that failed stay failed; limits and "not verified" stay as plain as they are. Do not turn hedged results into confident ones, and do not add hype words (no "revolutionary", "seamless", "cutting-edge", "game-changing") or exclamation marks.
4. Voice: plain, specific, warm; short sentences; active voice; American English. Write for a technical judge who reads quickly: lead each section with the point, then the evidence.
5. Refer to the developer as "the developer" or 念誠, with they/them if a pronoun is needed.
6. Remove repetition between sections, fix grammar, and smooth transitions. You may split long paragraphs.
7. Return the full report as one Markdown document, nothing before or after it.
