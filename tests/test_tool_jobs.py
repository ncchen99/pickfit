from scripts.tool_jobs import Job, clean_readme, grounded, profile_text

README = """# Vox

![badge](https://img.shields.io/x.svg) <img src="logo.png">

Vox runs **Whisper** models to transcribe audio files offline. See [the docs](https://example.invalid).

```bash
vox transcribe meeting.wav
line 2
line 3
line 4
line 5
line 6
line 7
line 8
line 9 is cut
```
"""


def test_clean_readme_drops_images_html_and_long_code_but_keeps_link_text() -> None:
    text = clean_readme(README)
    assert "img.shields" not in text and "logo.png" not in text
    assert "See the docs." in text
    assert "line 8" in text and "line 9 is cut" not in text


def test_a_job_is_kept_only_with_a_quote_from_the_readme_or_profile() -> None:
    sources = profile_text({"name": "Vox", "summary": "Offline speech to text.", "use_cases": ["transcribe meetings"],
                            "tags": ["asr"]}) + "\n" + clean_readme(README)
    assert grounded(Job(job="transcribe audio", evidence="runs Whisper models to transcribe audio files"), sources)
    assert grounded(Job(job="speech to text", evidence="Offline speech to text."), sources)  # from the profile
    assert not grounded(Job(job="clone a voice", evidence="clones any voice from samples"), sources)  # not in the docs
    assert not grounded(Job(job="transcribe", evidence="audio"), sources)  # one word is not a quote
    assert not grounded(Job(job="a very long job that says far too much", evidence="transcribe audio files offline"), sources)
