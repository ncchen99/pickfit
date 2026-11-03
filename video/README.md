# pickfit demo video

The 3-minute demo for the Meta Global AI Developer Hackathon. Script and decisions: [script.md](script.md). Upload text: [YOUTUBE.md](YOUTUBE.md).

## Rebuild

```bash
cd video && npm install
# animated scenes (three.js + GSAP, rendered frame by frame in Chrome)
node render.mjs night && node render.mjs agents && node render.mjs thread && node render.mjs finale
# real recordings → clips (needs rec/: the screen recordings and the pickfit.app capture)
node capture/web.mjs && node capture/frames2mp4.mjs rec/web
python3 edit/clips.py
node render.mjs screens-main && node render.mjs screens-agents
# narration phrases, mix, final cut
python3 edit/vo_phrases.py
uv run --with numpy python edit/mix.py --music b
python3 edit/assemble.py   # → out/pickfit-demo.mp4
```

`rec/`, `audio/`, `out/` are not in git (recordings of 念誠's screen, ElevenLabs audio, renders).

## Where things come from

| Part | Source |
|---|---|
| 3D scenes | `scenes/*.html` on the kit in `kit/` (clay Fitz, paper cards, stitch) |
| pickfit.app | `capture/web.mjs`: live site, headless Chrome, requests tagged `X-Pickfit-Reporter: demo` |
| Claude Code, MangoDisk | `screencapture` of 念誠's Mac; cut by the sessions' own timestamps (`edit/session_times.py`) into `edit/edl.json` |
| Narration, music, effects | ElevenLabs (念誠's voice, `eleven_v4`; `eleven_music_v2_5`; `eleven_text_to_sound_v2`) |
