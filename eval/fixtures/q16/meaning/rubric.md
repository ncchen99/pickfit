You are grading one sentence of a translation from English into Portuguese.

You are given:
- SOURCE SENTENCE: one English sentence from a technical document;
- SOURCE PARAGRAPH: the English paragraph that contains it;
- PORTUGUESE TEXT: the translated paragraph at the same position, with its neighbours, as plain text.

Decide whether the SOURCE SENTENCE is translated correctly somewhere in the PORTUGUESE TEXT.

PASS only when all three hold:
1. Fully translated: every part of the source sentence is rendered in Portuguese. Product names (Quillstack, Tarnwave, Mossgate), commands, code, file names, URLs and numbers may stay as they are. Any other part left in English is a FAIL.
2. Meaning preserved: nothing is left out, nothing is added, and nothing is changed. Numbers, negations, conditions, quantities, time limits and who does what must match the source.
3. Understandable: a Portuguese reader understands the sentence the way the source intends. Grammar slips that do not change the meaning are acceptable.

Do not judge: European versus Brazilian vocabulary (checked separately), style, word order, punctuation, Markdown formatting, or the other sentences of the paragraph.

Answer with one JSON object and nothing else:
{"verdict": "PASS" or "FAIL", "reason": "one short sentence"}
