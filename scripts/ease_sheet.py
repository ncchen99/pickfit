"""The blind rating page for the usability pilot (docs/usability-pilot.md): 念誠 rates the 12 apps before he sees
pickfit's scores.

For each app in data/calibration/ease-pilot.json the page shows what the model read (pickfit.usability.bundle_for:
the same screenshots, the operation goals, pickfit's checks and the operator's step log) and the same checklist, and
asks for 0/1/2 or "can't tell" per dimension, 1-5 overall and "would you use it". The four apps with a clip also show
it, marked as something the model did not see; web apps link to the site, to try for two minutes. It never reads
~/.pickfit/usability, so no score, finding or verdict can reach the page.

Answers are kept in the browser as he goes; "下載 YAML" saves them in the format of data/calibration/ease-ratings.yaml
(a flat YAML subset with JSON scalars, read by read_ratings), which this script writes as a blank template when it is
missing.

    uv run python scripts/ease_sheet.py        # writes runs/ease-sheet/index.html (one file, screenshots inlined)
"""

from __future__ import annotations

import base64
import html
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from pickfit.usability import FIRST_LOOK_INSTRUCTIONS, IN_USE_INSTRUCTIONS, Bundle, bundle_for

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "data" / "calibration" / "ease-pilot.json"
RATINGS = REPO / "data" / "calibration" / "ease-ratings.yaml"
OUT = REPO / "runs" / "ease-sheet"
VIDEOS = Path.home() / ".pickfit" / "videos"
DIMENSIONS = (
    ("ready", "一打開就能用",
     "2 第一個畫面就是工具本身，可以直接做主要的事；1 中間隔了歡迎頁、設定步驟、行銷頁或對話框，但很快能過；"
     "0 登入牆、很長的設定，或擋住工作的對話框。"),
    ("findable", "功能找得到",
     "每個操作目標需要的控制項：2 看得到、有文字標籤、在會去找的位置；1 少了其中一項（藏在選單、只有圖示沒標籤、"
     "位置出乎意料），但還是做得到；0 app 藏起來或根本沒有。"),
    ("responsive", "操作有回應",
     "2 做完之後，結果出現在正在看的地方，或錯誤訊息說了該怎麼辦；1 結果有出現但容易錯過，或只出現在別處；"
     "0 畫面上看不出有沒有成功，或出錯後沒有路可走。"),
    ("comfortable", "看起來舒服",
     "2 字好讀、主要區域和控制項清楚、沒有重疊、截斷或蓋住工作的東西；1 其中一項有小問題；0 很難讀（字太小或對比太低）、"
     "擠成一團沒有主區、版面破掉，或彈窗蓋住工作。不評配色、風格、品牌。"),
)
STOPS = {"done": "操作員說完成了", "step_cap": "操作員用完步數", "give_up": "操作員放棄", "error": "出錯停下",
         "budget": "預算用完停下", "no_window": "沒有視窗"}


def ratings_template(slugs: list[str]) -> str:
    lines = ["# 念誠的易用性盲評（ease.v1 試點）。由 runs/ease-sheet/index.html 的「下載 YAML」產生，或直接在這裡填。",
             "# ready / findable / responsive / comfortable：0、1、2，或 \"cant_tell\"；沒填是 null。",
             "# overall：1–5。would_use：\"yes\"、\"no\"、\"maybe\"。note：任意文字（JSON 字串）。",
             "# 格式是 YAML 的子集：每個值都是 JSON（數字、null、雙引號字串）。",
             'rater: "念誠"', "rated_at: null", "apps:"]
    for slug in slugs:
        lines += [f"  {slug}:", *(f"    {k}: null" for k, *_ in DIMENSIONS),
                  "    overall: null", "    would_use: null", '    note: ""']
    return "\n".join(lines) + "\n"


def read_ratings(text: str) -> dict[str, Any]:
    """The ratings file: top-level scalars and apps.<slug>.<field>, every value a JSON scalar."""
    out: dict[str, Any] = {"apps": {}}
    slug = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.strip().partition(":")
        value = value.strip()
        if indent == 0:
            if key != "apps":
                out[key] = json.loads(value) if value else None
        elif indent == 2:
            slug = key
            out["apps"][slug] = {}
        elif indent == 4 and slug is not None:
            out["apps"][slug][key] = json.loads(value) if value else None
    return out


def _e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _copy(src: Path, dest_dir: Path, rel: str) -> str:
    dest = dest_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)
    return rel


def _label(shot: Any) -> str:
    """The model's caption for a first-look image, in Chinese."""
    if shot.operation is not None:
        return f"操作 {shot.operation} 的最後一個畫面"
    return "網頁剛載入時" if "page" in shot.label else "App 剛啟動時的視窗"


def _figure(shot: Any, caption: str) -> str:
    """The screenshot inlined, so the page is one file that opens anywhere."""
    src = "data:image/png;base64," + base64.b64encode(shot.path.read_bytes()).decode("ascii")
    return (f'<figure><img src="{src}" alt="{_e(caption)}" loading="lazy" onclick="zoom(this)">'
            f"<figcaption>{_e(caption)}</figcaption></figure>")


def _video(record: dict[str, Any], slug: str) -> str:
    clip = next((r["video"]["clip"] for r in record["verification"]["runs"] if r.get("video")), None)
    src = VIDEOS / slug / clip if clip else None
    if src is None or not src.is_file():
        return ""
    rel = _copy(src, OUT, f"video/{clip}")
    return (f'<details class="video"><summary>影片（pickfit 錄的操作片段；<b>模型評分時沒看</b>，給你參考）</summary>'
            f'<video controls preload="none" src="{_e(rel)}"></video></details>')


def _form(slug: str) -> str:
    rows = []
    for key, label, _ in DIMENSIONS:
        opts = "".join(f'<label><input type="radio" name="{slug}.{key}" value="{v}"><span>{t}</span></label>'
                       for v, t in (("0", "0"), ("1", "1"), ("2", "2"), ("cant_tell", "看不出來")))
        rows.append(f'<div class="row"><div class="q">{_e(label)}</div><div class="opts">{opts}</div></div>')
    overall = "".join(f'<label><input type="radio" name="{slug}.overall" value="{v}"><span>{v}</span></label>'
                      for v in range(1, 6))
    use = "".join(f'<label><input type="radio" name="{slug}.would_use" value="{v}"><span>{t}</span></label>'
                  for v, t in (("yes", "會"), ("maybe", "看情況"), ("no", "不會")))
    rows.append(f'<div class="row"><div class="q">整體（1 很難用 – 5 很好用）</div><div class="opts">{overall}</div></div>')
    rows.append(f'<div class="row"><div class="q">你自己會用嗎</div><div class="opts">{use}</div></div>')
    rows.append(f'<div class="row note"><div class="q">備註（可空白）</div>'
                f'<textarea name="{slug}.note" rows="2" placeholder="例如：卡在哪、哪裡其實是沙盒的問題"></textarea></div>')
    return f'<form class="rate" data-slug="{_e(slug)}">{"".join(rows)}</form>'


def _app(n: int, record: dict[str, Any], bundle: Bundle) -> str:
    slug = bundle.slug
    where = "網頁" if bundle.kind == "web" else f"桌面 App · {'macOS' if bundle.os == 'macos' else 'Linux'}"
    url = (record.get("web") or {}).get("url")
    head = (f'<header><h2><span class="num">{n}</span>{_e(record["name"])} <code>{_e(slug)}</code></h2>'
            f'<p class="meta">{_e(where)} · 沙盒：{_e(bundle.sandbox)}'
            + (f' · <a href="{_e(url)}" target="_blank" rel="noopener">打開網站試兩分鐘</a>' if url else "")
            + f'</p><p class="summary">{_e(record.get("summary") or "")}</p></header>')
    first = "".join(_figure(s, f"圖 {i}：{_label(s)}") for i, s in enumerate(bundle.first_look_shots(), start=1))
    parts = [head, '<h3>第一眼（模型看到的圖）</h3>', f'<div class="shots">{first}</div>']
    if bundle.operated and bundle.operations:
        shots = bundle.in_use_shots()
        index = {id(s): i for i, s in enumerate(shots, start=1)}
        parts.append(f'<h3>使用中（pickfit 的 AI 操作員試了 {bundle.attempted} 個操作，模型看了下面 '
                     f'{len(bundle.operations)} 個）</h3>')
        for op in bundle.operations:
            figs = "".join(_figure(s, f"圖 {index[id(s)]}：操作 {op.number} 的"
                                            f"{'第一個' if s is op.first else '最後一個'}畫面")
                           for s in (op.first, op.last) if s is not None)
            check = "通過" if op.passed else "沒通過"
            stop = STOPS.get(op.stop or "", op.stop or "")
            parts.append(
                f'<div class="op"><p><b>操作 {op.number}</b>　目標（pickfit 寫的）：{_e(op.goal)}</p>'
                f'<p class="meta">pickfit 的檢查（{_e(op.check)}）：<b class="{"ok" if op.passed else "no"}">{check}</b>'
                f" · {_e(stop)} · {op.actions} 步</p>"
                f'<div class="shots">{figs}</div>'
                f'<details><summary>操作員的步驟紀錄（模型也看了）</summary><pre>{_e(chr(10).join(op.steps[:30]))}</pre>'
                f"<p class=\"meta\">pickfit 的檢查紀錄：{_e(op.result)}</p></details></div>")
    else:
        parts.append('<p class="notice">這款在這個 run 沒有通過的操作，模型只看了第一眼。「功能找得到」和「操作有回應」'
                     + ("可以自己打開網站試，或填「看不出來」。" if url else "請填「看不出來」，除非你自己用過。") + "</p>")
    parts.append(_video(record, slug))
    parts.append(_form(slug))
    return f'<section class="app" id="{_e(slug)}">{"".join(parts)}</section>'


CSS = """
:root{--paper:#F4F5EC;--tag:#FFFEF7;--sunk:#E9ECDD;--ink:#17231A;--ink-2:#4B584E;--rule:#D5DAC6;--tape:#F5C243;
--tape-ink:#3A2905;--mat:#1D3D2A;--on-mat:#F4F1DE;--pass:#2E7A35;--fail:#B23A26;--stitch:#C4552D}
@media (prefers-color-scheme: dark){:root{--paper:#101A13;--tag:#18241B;--sunk:#0B140E;--ink:#ECEFE3;--ink-2:#B4BEB0;
--rule:#2A382D;--mat:#16301F;--pass:#7CCB7A;--fail:#F08A73;--stitch:#E07A4F}}
*{box-sizing:border-box}html{font-size:17px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,-apple-system,"PingFang TC","Noto Sans TC",
sans-serif;line-height:1.6}
.top{background:var(--mat);color:var(--on-mat);padding:28px 16px 20px}.top>div,main{max-width:1100px;margin:0 auto}
.top h1{margin:0 0 6px;font-size:1.7rem;line-height:1.2}.top p{margin:4px 0;max-width:75ch}
main{padding:12px 16px 120px}
.rubric,.app{background:var(--tag);border:1px solid var(--rule);border-radius:10px;padding:16px 18px;margin:18px 0}
.rubric dt{font-weight:700;margin-top:8px}.rubric dd{margin:0 0 4px 0;color:var(--ink-2)}
h2{margin:0;font-size:1.3rem;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
h2 code{font-size:.8rem;color:var(--ink-2)}.num{background:var(--tape);color:var(--tape-ink);border-radius:6px;
padding:0 8px;font-size:1rem}
h3{font-size:1rem;margin:18px 0 8px;border-top:1px dashed var(--rule);padding-top:12px}
.meta{color:var(--ink-2);font-size:.9rem;margin:2px 0}.summary{margin:6px 0 0}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
figure{margin:0}figure img{width:100%;height:auto;border:1px solid var(--rule);border-radius:6px;background:var(--sunk);
cursor:zoom-in}#zoom{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;
justify-content:center;z-index:9;cursor:zoom-out}#zoom img{max-width:98vw;max-height:96vh}
figcaption{font-size:.85rem;color:var(--ink-2)}
.op{margin:10px 0 16px}.ok{color:var(--pass)}.no{color:var(--fail)}
pre{white-space:pre-wrap;font-size:.8rem;background:var(--sunk);padding:8px;border-radius:6px;max-height:320px;overflow:auto}
.notice{background:var(--sunk);padding:8px 12px;border-radius:6px}
video{width:100%;max-height:480px;margin-top:6px}details.video{margin:12px 0}
form.rate{margin-top:16px;border-top:2px solid var(--stitch);padding-top:12px}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 0}.q{min-width:12em;font-weight:600}
.opts{display:flex;gap:6px;flex-wrap:wrap}.opts label{cursor:pointer}.opts input{position:absolute;opacity:0}
.opts span{display:inline-block;min-width:2.4em;text-align:center;padding:4px 10px;border:1px solid var(--rule);
border-radius:999px;background:var(--paper)}
.opts input:checked+span{background:var(--tape);color:var(--tape-ink);border-color:var(--tape);font-weight:700}
.opts input:focus-visible+span{outline:2px solid var(--stitch)}
.note{align-items:flex-start}textarea{flex:1;min-width:240px;font:inherit;padding:6px;border:1px solid var(--rule);
border-radius:6px;background:var(--paper);color:var(--ink)}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--mat);color:var(--on-mat);padding:10px 16px;display:flex;
gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;z-index:5}
.bar button{font:inherit;font-weight:700;border:0;border-radius:8px;padding:8px 14px;background:var(--tape);
color:var(--tape-ink);cursor:pointer}.bar button.alt{background:transparent;color:var(--on-mat);border:1px solid var(--on-mat)}
.bar nav a{color:var(--on-mat);margin:0 3px;font-size:.85rem}.bar nav a.done{opacity:.55}
"""

JS = r"""
const KEY='pickfit-ease-sheet-v1', DIMS=%DIMS%, SLUGS=%SLUGS%;
const load=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}};
const save=s=>{try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}};
let state=load();
function apply(){for(const el of document.querySelectorAll('form.rate input,form.rate textarea')){const v=state[el.name];
 if(el.type==='radio')el.checked=(v===el.value);else if(v!==undefined)el.value=v;}progress();}
function progress(){let done=0;for(const s of SLUGS){const ok=[...DIMS,'overall','would_use'].every(k=>state[s+'.'+k]);
 if(ok)done++;const a=document.querySelector('.bar nav a[href="#'+s+'"]');if(a)a.classList.toggle('done',ok);}
 document.getElementById('count').textContent=done+' / '+SLUGS.length+' 款填完';}
document.addEventListener('input',e=>{const el=e.target;if(!el.name||!el.closest('form.rate'))return;
 state[el.name]=el.value;save(state);progress();});
function yaml(){const L=['# 念誠的易用性盲評（ease.v1 試點），由 runs/ease-sheet/index.html 產生。',
 '# ready / findable / responsive / comfortable：0、1、2 或 "cant_tell"；overall 1–5；would_use "yes"/"no"/"maybe"。',
 'rater: "念誠"','rated_at: '+JSON.stringify(new Date().toISOString()),'apps:'];
 for(const s of SLUGS){L.push('  '+s+':');for(const k of DIMS){const v=state[s+'.'+k];
  L.push('    '+k+': '+(v===undefined?'null':(v==='cant_tell'?'"cant_tell"':Number(v))));}
  const o=state[s+'.overall'];L.push('    overall: '+(o===undefined?'null':Number(o)));
  const u=state[s+'.would_use'];L.push('    would_use: '+(u===undefined?'null':JSON.stringify(u)));
  L.push('    note: '+JSON.stringify(state[s+'.note']||''));}
 return L.join('\n')+'\n';}
document.getElementById('dl').onclick=()=>{const b=new Blob([yaml()],{type:'text/yaml'});const a=document.createElement('a');
 a.href=URL.createObjectURL(b);a.download='ease-ratings.yaml';a.click();};
document.getElementById('cp').onclick=async()=>{try{await navigator.clipboard.writeText(yaml());
 document.getElementById('cp').textContent='已複製';}catch(e){prompt('複製這段：',yaml());}};
function zoom(img){const z=document.getElementById('zoom');z.firstChild.src=img.src;z.style.display='flex';}
document.getElementById('zoom').onclick=e=>{e.currentTarget.style.display='none';};
apply();
"""


def build() -> Path:
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))["apps"]
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sections, slugs = [], []
    for n, app in enumerate(pilot, start=1):
        record = json.loads((REPO / "data" / "software" / f"{app['slug']}.json").read_text(encoding="utf-8"))
        bundle = bundle_for(record)
        if bundle is None:
            raise SystemExit(f"{app['slug']}: no run with copied evidence")
        sections.append(_app(n, record, bundle))
        slugs.append(app["slug"])
    rubric = "".join(f"<dt>{_e(label)}（{key}）</dt><dd>{_e(text)}</dd>" for key, label, text in DIMENSIONS)
    page = f"""<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>易用性盲評</title><style>{CSS}</style></head><body>
<div class="top"><div><h1>易用性盲評：12 款（ease.v1 試點）</h1>
<p>每款看 pickfit 自己在沙盒拍的畫面、操作目標和 pickfit 的檢查結果，和模型評分時看到的是同一批。網頁可以自己打開網站試兩分鐘。</p>
<p>只評 app 本身：沙盒造成的（Linux 沒有視窗管理器所以沒有標題列、缺字型、macOS 權限框、無頭瀏覽器、固定解析度）不扣分；
AI 操作員點偏、繞路、步數用完，也不算 app 的錯。看不出來就選「看不出來」。這頁沒有 pickfit 的分數。</p>
<p>答案會自動存在這個瀏覽器。做完按下方「下載 YAML」，存成 <code>data/calibration/ease-ratings.yaml</code>
（或按「複製」貼給 session）。大約 40 分鐘。</p></div></div>
<main><section class="rubric"><h2>評分標準（和給模型的是同一份）</h2><dl>{rubric}</dl>
<p class="meta">整體 1–5 是你自己的整體感受；「會不會用」是假設你需要這類工具。</p>
<details><summary>給模型的原文（英文）</summary><pre>{_e(FIRST_LOOK_INSTRUCTIONS)}</pre><pre>{_e(IN_USE_INSTRUCTIONS)}</pre>
</details></section>
{"".join(sections)}</main>
<div class="bar"><span id="count"></span><nav>{"".join(f'<a href="#{_e(s)}">{i}</a>' for i, s in enumerate(slugs, 1))}</nav>
<button id="dl">下載 YAML</button><button id="cp" class="alt">複製</button></div>
<div id="zoom"><img alt=""></div>
<script>{JS.replace("%DIMS%", json.dumps([k for k, *_ in DIMENSIONS])).replace("%SLUGS%", json.dumps(slugs))}</script>
</body></html>
"""
    (OUT / "index.html").write_text(page, encoding="utf-8")
    if not RATINGS.exists():
        RATINGS.write_text(ratings_template(slugs), encoding="utf-8")
    return OUT / "index.html"


def main() -> int:
    path = build()
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
