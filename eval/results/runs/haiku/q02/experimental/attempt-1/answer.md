**Recommendation: Microsoft Presidio (MIT, free, runs offline), wrapped in a short stdin-to-stdout script.** I could not verify this with pickfit. Its catalog search returned no matching tools, so this comes from my own knowledge and I have not tested it. I also ran nothing here.

**Caveat:** no tool I know of removes API keys and tokens with zero regexes. Presidio ships built-in recognizers for email addresses and IP addresses, but not for API keys. For keys you need a pattern list, and the ones below are maintained by someone else. Assumption: you want this on your Linux box, where the logs live.

**Install (Linux, Python 3.9+):**
```bash
python3 -m venv ~/scrub-venv
~/scrub-venv/bin/pip install presidio-analyzer presidio-anonymizer
~/scrub-venv/bin/python -m spacy download en_core_web_lg
```
Presidio uses a spaCy model for its NLP step. The download happens once, so the filter works offline afterwards.

**Script** (save as `~/bin/scrub.py`, then `chmod +x`):
```python
#!/usr/bin/env python3
import sys
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
# Key/token patterns Presidio lacks by default (add more as needed)
keys = PatternRecognizer(supported_entity="API_KEY", patterns=[
    Pattern("aws", r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", 0.9),
    Pattern("bearer", r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{16,}=*", 0.8),
    Pattern("generic", r"\b(sk|pk|ghp|xox[bp])[-_][A-Za-z0-9\-_]{16,}\b", 0.8),
])
analyzer.registry.add_recognizer(keys)
anonymizer = AnonymizerEngine()

for line in sys.stdin:
    results = analyzer.analyze(text=line, language="en",
                               entities=["EMAIL_ADDRESS", "IP_ADDRESS", "API_KEY"])
    print(anonymizer.anonymize(text=line, analyzer_results=results).text, end="")
```

**First run:**
```bash
echo 'user bob@example.com from 203.0.113.7 key AKIAABCDEFGHIJKLMNOP' | ~/scrub-venv/bin/python ~/bin/scrub.py
# expected: user <EMAIL_ADDRESS> from <IP_ADDRESS> key <API_KEY>
tail -n 500 /var/log/app.log | ~/scrub-venv/bin/python ~/bin/scrub.py > /tmp/clean.log
```
Check the output on a sample before pasting anything, since no filter catches everything.

**Trade-offs:**
- Running line by line is slow on very large logs. Batch the input if that matters.
- Presidio's email and IP detection is good, but it can miss unusual formats.
- Key patterns above are illustrative; check them against the key formats you actually use.