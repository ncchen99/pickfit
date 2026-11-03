/**
 * The stylesheet, in the order DESIGN.md lays the system out: tokens, base,
 * components, then page layouts. One string, sent inline under the CSP nonce.
 */

const TOKENS = `
@font-face{font-family:"Bricolage Grotesque";src:url(/assets/fonts/bricolage-grotesque.woff2) format("woff2");font-weight:400 800;font-display:swap}
/* One ground per page; colour lives only in the conversation (DESIGN.md §2). Every pair below is checked
   for contrast in both schemes (redesign tokens.py). Grounds: paper < tag (cards) < raised (your request, popovers);
   voice is Fitz's olive, only for Fitz's answer and his waiting words. */
:root{
--paper:#F7F7F4;--tag:#FFFFFF;--raised:#FFFFFF;--voice:#F1F6E2;--voice-line:#CDD7AB;
--sunk:#F0F1EC;--code-bg:#FFFFFF;--rule:#DEDFD9;--line-ctl:#80817A;
--ink:#1A1D17;--ink-2:#4F5149;--ink-3:#65655E;
--tape:#F5C243;--tape-edge:#A57710;--tape-deep:#D9A21B;--tape-ink:#3A2905;--tape-tab:#C3CAD2;
--stitch:#C4552D;--fitz-line:#4A2E22;--fitz-ink:#4A2E22;
--pass:#2E7A35;--caution:#8A5300;--fail:#B23A26;--info:#28698A;
--pass-soft:color-mix(in srgb,var(--pass) 14%,var(--tag));--caution-soft:color-mix(in srgb,#E09A1E 18%,var(--tag));
--fail-soft:color-mix(in srgb,var(--fail) 12%,var(--tag));--info-soft:color-mix(in srgb,var(--info) 12%,var(--tag));
/* Retired with the cutting mat: kept as aliases of the new values until the templates drop them. */
--mat:var(--paper);--mat-deep:var(--raised);--mat-line:var(--rule);--mat-line-2:var(--rule);--on-mat:var(--ink);--on-mat-2:var(--ink-2);
--code:var(--code-bg);--code-ink:var(--ink);
--lift-1:0 1px 2px rgb(26 29 23/.05),0 6px 18px -10px rgb(26 29 23/.24);
--lift-2:0 2px 4px rgb(26 29 23/.07),0 16px 32px -16px rgb(26 29 23/.32);
--lift-3:0 4px 10px rgb(26 29 23/.10),0 28px 56px -20px rgb(26 29 23/.42);
--scrim:color-mix(in srgb,var(--ink) 42%,transparent);
--r-card:14px;--r-ctl:10px;
--display:"Bricolage Grotesque",ui-sans-serif,system-ui,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
--t-display:clamp(2.3rem,4.1vw,3.5rem);--t-title:clamp(1.6rem,2.6vw,2.2rem);--t-head:1.25rem;--t-lead:1.15rem;--t-small:.875rem;
--ease-out:cubic-bezier(.16,1,.3,1);--ease-io:cubic-bezier(.65,0,.35,1);
--gap:clamp(64px,9vw,128px)}
/* Dark: the more it matters, the lighter it is. Shadows don't show on a dark page, so lifts are hairlines. */
@media (prefers-color-scheme:dark){:root{
--paper:#161613;--tag:#242521;--raised:#2E2E29;--voice:#1E2413;--voice-line:#394129;
--sunk:#0E0F0C;--code-bg:#0E0F0C;--rule:#393A34;--line-ctl:#7A7B74;
--ink:#EBEAE2;--ink-2:#BFBEB6;--ink-3:#A5A59D;
--tape-edge:#F5C243;--stitch:#E07A4F;--fitz-line:#93938A;--fitz-ink:#93938A;
--pass:#7CCB7A;--caution:#F0B45A;--fail:#F08A73;--info:#86C4E6;
--pass-soft:color-mix(in srgb,var(--pass) 16%,var(--tag));--caution-soft:color-mix(in srgb,var(--caution) 16%,var(--tag));
--fail-soft:color-mix(in srgb,var(--fail) 16%,var(--tag));--info-soft:color-mix(in srgb,var(--info) 14%,var(--tag));
--lift-1:0 0 0 1px var(--rule);
--lift-2:0 0 0 1px color-mix(in srgb,var(--line-ctl) 55%,var(--rule));
--lift-3:0 0 0 1px var(--rule),0 18px 40px -16px rgb(0 0 0/.7);
--scrim:color-mix(in srgb,var(--sunk) 78%,transparent)}}
`;

const BASE = `
*,*::before,*::after{box-sizing:border-box}
[hidden]{display:none!important}
html{-webkit-text-size-adjust:100%;scroll-padding-top:16px}
@media (min-width:1024px){html{font-size:17px}}
body{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.55 var(--sans);overflow-wrap:break-word;-webkit-font-smoothing:antialiased;accent-color:var(--pass)}
::selection{background:var(--tape);color:var(--tape-ink)}
textarea,input{caret-color:var(--stitch)}
html{scrollbar-color:color-mix(in srgb,var(--ink) 30%,transparent) transparent}
:focus-visible{outline:3px solid var(--stitch);outline-offset:2px;border-radius:4px}
.wrap{max-width:1240px;margin-left:auto;margin-right:auto;padding-left:24px;padding-right:24px}
h1,h2,h3,h4{font-family:var(--display);font-weight:700;letter-spacing:-.02em;text-wrap:balance;margin:0;line-height:1.2}
h1{font-size:var(--t-display);font-weight:700;letter-spacing:-.03em;line-height:1.04;font-variation-settings:"opsz" 96}
h2{font-size:var(--t-title);line-height:1.1}
h3{font-size:var(--t-head)}
h4{font-size:1rem;margin:20px 0 8px}
p{margin:0 0 12px;max-width:68ch}
ul,ol{margin:0 0 12px;padding-left:22px}
a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{text-decoration-color:var(--stitch);text-decoration-thickness:2px}
code,pre,kbd{font-family:var(--mono);font-size:.875em}
.quiet{color:var(--ink-2)}
.small{font-size:var(--t-small)}
.num{font-variant-numeric:tabular-nums}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
button{font:inherit;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
img{max-width:100%;height:auto}
figure{margin:0}
.skip{position:absolute;left:-9999px;top:12px;z-index:30;background:var(--tape);color:var(--tape-ink);padding:10px 14px;border-radius:var(--r-ctl);font-weight:600}
.skip:focus{left:12px}
.i{width:1.15em;height:1.15em;flex:none;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round;vertical-align:-.2em}
html:not(.js) .js-only{display:none!important}
.js .no-js-only{display:none!important}
section[id]{scroll-margin-top:24px}
`;

const COMPONENTS = `
/* mat: retired. The cutting mat, its grid and the rulers under each band are gone: one ground per page.
   The class stays on some templates until they drop it, so it only sets the page's own ground and ink. */
.mat{background-color:var(--paper);color:var(--ink)}
.mat .quiet,.mat .on-mat-2{color:var(--ink-2)}
.ruler{display:none}

/* header */
.top{position:relative;z-index:5}
.top-row{display:flex;align-items:center;justify-content:space-between;gap:24px;height:72px}
.brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font:800 1.45rem/1 var(--display);letter-spacing:-.03em}
.brand picture{display:flex}
.brand img{width:32px;height:32px}
.i-dot{position:relative}
.i-dot::after{content:"";position:absolute;left:50%;top:.02em;width:.26em;height:.26em;border-radius:50%;background:var(--stitch);transform:translateX(-50%);box-shadow:0 0 0 .07em var(--paper)}
/* The nav: plain words on the page ground. The current page is underlined, not a pill (pills are switches). */
.nav{display:flex;gap:28px;margin-left:auto}
.nav a,.menu-nav a{display:inline-flex;align-items:center;gap:6px;text-decoration:none;padding:8px 0;font:500 .95rem/1.2 var(--sans);color:var(--ink-2);transition:color .2s,border-color .2s}
.nav a{border-bottom:2px solid transparent}
.nav a:hover,.menu-nav a:hover{color:var(--ink)}
.nav a[aria-current=page]{color:var(--ink);border-bottom-color:var(--ink)}
.nav a:focus-visible,.lang-switch:focus-visible{outline-offset:4px}
.menu-nav a[aria-current=page]{color:var(--ink);text-decoration-line:underline;text-decoration-thickness:2px;text-underline-offset:6px}
.count{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--ink);color:var(--paper);font:700 .75rem/20px var(--sans);text-align:center}
.lang-switch{display:inline-flex;align-items:center;padding:3px 0 3px 20px;border-left:1px solid var(--rule);text-decoration:none;font:500 .95rem/1.2 var(--sans);color:var(--ink-2);white-space:nowrap}
.lang-switch:hover{color:var(--ink);text-decoration:underline}
.top-end{display:flex;align-items:center;gap:12px}
.menu{display:none;position:relative}
.menu summary{list-style:none;cursor:pointer;padding:10px;border-radius:var(--r-ctl);color:var(--ink)}
.menu summary::-webkit-details-marker{display:none}
.menu-nav{position:absolute;right:0;top:calc(100% + 6px);display:flex;flex-direction:column;min-width:220px;padding:8px;background:var(--raised);color:var(--ink);border-radius:var(--r-card);box-shadow:var(--lift-3)}
.menu-nav a{padding:12px 14px;border-radius:var(--r-ctl)}

/* buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 20px;border:0;border-radius:var(--r-ctl);
font:700 1rem/1 var(--display);letter-spacing:-.01em;text-decoration:none;cursor:pointer;white-space:nowrap;
transition:transform .12s var(--ease-out),box-shadow .2s var(--ease-out),background-color .2s}
.btn:hover{text-decoration:none}
.btn:active{transform:translateY(1px)}
.btn[disabled],.btn[aria-disabled=true]{opacity:.55;cursor:not-allowed;transform:none}
/* The one action on a screen is solid tape; its 1px edge carries it on the light page, where tape on white is only 1.66:1. */
.btn-primary{background:var(--tape);color:var(--tape-ink);box-shadow:0 1px 0 var(--tape-deep),inset 0 0 0 1px var(--tape-edge)}
.btn-primary:hover{background:color-mix(in srgb,var(--tape) 88%,#fff);box-shadow:0 1px 0 var(--tape-deep),inset 0 0 0 1px var(--tape-edge)}
/* Everything else is quiet: no fill, a 1px control line (3:1 on every ground). .btn-on-mat is the retired band's button, now the same. */
.btn-quiet,.btn-on-mat{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1px var(--line-ctl)}
.btn-quiet:hover,.btn-on-mat:hover{background:color-mix(in srgb,var(--ink) 6%,transparent);box-shadow:inset 0 0 0 1px var(--ink-2)}
.btn-ghost{background:transparent;color:inherit}
.btn-ghost:hover{background:color-mix(in srgb,currentColor 8%,transparent)}
/* The results' "How to read a tool card" and "Compare these" are ways to go, so they read as links. */
.res-tools .btn{min-height:32px;padding:0;background:none;box-shadow:none;font:500 .95rem/1.3 var(--sans);color:var(--ink-2);text-decoration:underline;text-decoration-color:var(--line-ctl);text-decoration-thickness:1px;text-underline-offset:4px}
.res-tools .btn+.btn{margin-left:16px}
.res-tools .btn:hover{background:none;box-shadow:none;color:var(--ink);text-decoration:underline;text-decoration-color:var(--stitch)}
.res-tools .btn .i{display:none}
.btn-sm{min-height:36px;padding:0 14px;font-size:.9rem}
.btn-icon{padding:0;width:44px}
.btn[aria-busy=true]{cursor:progress}
.btn[aria-busy=true] .btn-label::after{content:"";display:inline-block;width:1.2em;text-align:left;animation:dots 1.2s steps(4) infinite}

/* chips, segmented control, selects: the switches, and the only pills on the page.
   A transparent ground and a 1px control line (3:1 on every ground). On is the same for a chip and a segment: a faint ink
   tint and an ink ring, 2px of ink where off is 1px of --line-ctl (3.5:1 apart or more), and a chip adds a check and bolder
   words, so the state is never colour alone and never outweighs the screen's one solid yellow. */
.chip{position:relative;display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 14px;border:1px solid var(--line-ctl);border-radius:999px;cursor:pointer;
font:500 .9rem/1 var(--sans);background:transparent;color:var(--ink);transition:background .2s,color .2s,border-color .2s;user-select:none}
.chip input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.chip:hover{background:color-mix(in srgb,var(--ink) 8%,transparent)}
.chip:has(input:checked),.chip.on{background:color-mix(in srgb,var(--ink) 11%,transparent);color:var(--ink);border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink);font-weight:600}
.chip:has(input:checked)::before,.chip.on::before{content:"";flex:none;width:.9em;height:.9em;margin-left:-2px;background:currentColor;
-webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E") center/contain no-repeat;
mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E") center/contain no-repeat}
.chip:has(input:focus-visible){outline:3px solid var(--stitch);outline-offset:2px}
.chip .i,.chip .os{width:1em;height:1em}
/* A chip's word says it; its icon would say it twice. Compare keeps its mark: on narrow Browse cards it is the whole button. */
.chip:not(.chip-compare) .i{display:none}
a.chip{text-decoration:none}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.seg{display:inline-flex;padding:3px;gap:2px;border:1px solid var(--line-ctl);border-radius:999px;background:transparent}
.seg label{position:relative;display:inline-flex;align-items:center;min-height:32px;padding:0 14px;border-radius:999px;cursor:pointer;font:500 .9rem/1 var(--sans);color:var(--ink-2);transition:background .2s,color .2s}
.seg input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.seg label:hover{color:var(--ink)}
.seg label:has(input:checked){background:color-mix(in srgb,var(--ink) 11%,transparent);color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.seg label:has(input:focus-visible){outline:3px solid var(--stitch);outline-offset:1px}
.select{appearance:none;font:500 .9rem/1 var(--sans);color:var(--ink);background:transparent no-repeat right 12px center/14px;min-height:40px;padding:0 34px 0 14px;border:1px solid var(--line-ctl);border-radius:999px;cursor:pointer;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234F5149' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")}
@media (prefers-color-scheme:dark){.select{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23BFBEB6' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")}}
.select:hover{background-color:color-mix(in srgb,var(--ink) 8%,transparent)}
.seg label.seg-icon{padding:0 13px}
.seg-icon .os{width:1.15em;height:1.15em}
/* the page script's own dropdown: a select's button and list, and the compare page's name picker */
.dd{position:relative;display:inline-block}
.dd-btn{display:inline-flex;align-items:center;text-align:left}
.dd-btn[aria-expanded=true]{background-color:color-mix(in srgb,var(--ink) 8%,transparent)}
.dd-list{position:absolute;left:0;top:calc(100% + 6px);z-index:30;min-width:100%;width:max-content;max-width:min(360px,calc(100vw - 32px));max-height:300px;overflow-y:auto;margin:0;padding:6px;list-style:none;
background:var(--raised);color:var(--ink);border-radius:14px;box-shadow:var(--lift-3);outline:0}
.dd-list.up{top:auto;bottom:calc(100% + 6px)}
.dd-list[hidden]{display:none}
.dd-list li{display:flex;align-items:center;gap:8px;padding:9px 12px 9px 10px;border-radius:9px;font:500 .95rem/1.25 var(--sans);cursor:pointer}
.dd-list li .i{width:15px;height:15px;flex:none;visibility:hidden;color:var(--pass)}
.dd-list li[aria-selected=true]{font-weight:600}
.dd-list li[aria-selected=true] .i{visibility:visible}
.dd-list li.active{background:color-mix(in srgb,var(--ink) 9%,transparent)}
.dd-list li.dd-empty{cursor:default;color:var(--ink-2)}
.dd-list mark{background:none;color:inherit;font-weight:700}
.combo{position:relative;flex:0 1 auto;min-width:min(320px,100%)}
.combo input{width:100%}
.combo .dd-list{width:100%;max-width:none}
.combo .dd-list li{display:block}
/* install steps per system, as tabs */
.os-tabs{display:flex;flex-wrap:wrap;gap:2px;padding:3px;margin:0 0 14px;border:1px solid var(--line-ctl);border-radius:999px;background:transparent;width:max-content;max-width:100%}
.os-tabs[hidden]{display:none}
.os-tabs button{display:inline-flex;align-items:center;gap:7px;min-height:34px;padding:0 16px;border:0;border-radius:999px;background:none;color:var(--ink-2);font:500 .92rem/1 var(--sans);cursor:pointer}
.os-tabs button:hover{color:var(--ink)}
.os-tabs button[aria-selected=true]{background:color-mix(in srgb,var(--ink) 11%,transparent);color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.os-tabs button:focus-visible{outline:3px solid var(--stitch);outline-offset:1px}
.os-tabs .os{width:1.05em;height:1.05em}
.os-tabs .arch{font-weight:500;font-size:.8rem;color:var(--ink-3)}
.os-mine{font:600 .78rem/1 var(--sans);color:var(--pass)}
.js .run-panel[role=tabpanel] .run-head{display:none}
.run-panel[hidden]{display:none}
.run-panel+.run-panel{margin-top:24px;padding-top:20px;border-top:1px solid var(--rule)}
.install-card .run-head{margin-bottom:12px}
.install-card .install-body{padding:0}
.install-card .stage-tabs button[aria-current=step]{background:var(--sunk);box-shadow:none}
@media (max-width:520px){.run-card.install-card{padding:18px 16px}.os-tabs .arch{display:none}.os-tabs button{padding:0 12px;gap:6px}}

/* badges: facts, so plain text in their tone (pills are only for switches). The icon goes when the words say
   the same; a short badge (its text is a tooltip) keeps its marks, since they are all it shows. */
.badge{display:inline-flex;align-items:center;gap:6px;padding:0;border:0;border-radius:0;background:none;font:600 .9rem/1.3 var(--sans);letter-spacing:0;white-space:nowrap}
button.badge{cursor:help;min-height:24px;text-decoration:underline dotted;text-decoration-thickness:1px;text-underline-offset:4px}
.badge .i{width:1em;height:1em;stroke-width:2}
/* A short badge keeps its icon unless visible marks follow it (a span hidden from readers, e.g. "Tested" and the OS marks):
   an icon-only badge (the gem) shows its icon, since the icon is all it shows. Every icon carries aria-hidden itself, so the
   test is for a span, not any [aria-hidden] child. */
.badge:not(.badge-short)>.i,.badge-short:has(>span[aria-hidden])>.i{display:none}
.badge-pass{color:var(--pass)}
.badge-gem{background:transparent;color:var(--ink-3)}
.badge-free{color:var(--ink-2)}
.badge-caution{color:var(--caution)}
.badge-fail{color:var(--fail)}
.badge-info{color:var(--info)}
.badge-quiet{color:var(--ink-2)}
.badges{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin:0}
.badge-short{gap:6px;padding:0}
.os{width:1.05em;height:1.05em;flex:none;fill:currentColor}
/* marks for facts every card repeats: kind, OSes, a system, a run */
.kind,.sys,.oses{display:inline-flex;align-items:center;gap:5px;vertical-align:-.15em}
.kind .i{width:1.05em;height:1.05em}
.oses{gap:6px}.oses .os{width:1.1em;height:1.1em}
.oses-pass{color:var(--pass)}.oses-caution{color:var(--caution)}.oses-quiet{color:var(--ink-2)}
.run-facts{list-style:none;display:flex;flex-wrap:wrap;gap:6px 18px;padding:0;margin:2px 0 10px;font-size:.9rem;color:var(--ink-2);max-width:none}
.rf{display:inline-flex;align-items:center;gap:6px}
.rf .i,.rf .os{width:15px;height:15px}
/* Words that say it (Replayed from scratch, Works offline, Open source…) lose their icon; a bare date or version keeps its mark, its only label. */
.run-facts .i:not(.i-calendar):not(.i-package){display:none}
.rf-yes{color:var(--pass);font-weight:600}.rf-no{color:var(--caution);font-weight:600}
.sprite{position:absolute;overflow:hidden}
@media (hover:hover){
[data-tip]{position:relative}
[data-tip]:hover::after{content:attr(data-tip)}
[data-tip]:hover::after,.cat-card .chip-compare:hover::after{position:absolute;left:0;bottom:calc(100% + 6px);z-index:3;padding:6px 9px;border-radius:6px;background:var(--ink);color:var(--paper);font:600 .78rem/1.3 var(--sans);width:max-content;max-width:220px;white-space:normal;pointer-events:none}
}

/* tape meters */
.meter{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:6px 12px}
.meter-label{display:inline-flex;align-items:center;gap:4px;font:600 .85rem/1.2 var(--display);color:var(--ink-2)}
.meter .tape{grid-column:1/2;width:100%;height:14px;overflow:visible;display:block}
.meter-read{grid-row:1/3;grid-column:2;font:700 1.35rem/1 var(--display);font-variant-numeric:tabular-nums;min-width:2.2ch;text-align:right}
.meter-wide{grid-row:auto;grid-column:1/-1;font:500 var(--t-small)/1.3 var(--sans);text-align:left;color:var(--ink-2)}
.meter-note{grid-column:1/-1;font-size:var(--t-small);color:var(--ink-2)}
.meter-none .meter-read{font:500 var(--t-small)/1 var(--sans);color:var(--ink-2)}
.tape-track{fill:var(--sunk)}
.meter-none .tape-track{fill:none;stroke:var(--rule);stroke-width:1.5;stroke-dasharray:4 4;vector-effect:non-scaling-stroke}
/* A reading, not an action: the tape's ticks in ink, never yellow (the screen's one solid yellow is its action).
   The fill is 3:1 or more on the track in both schemes. */
.tape-fill{fill:color-mix(in srgb,var(--ink) 48%,var(--sunk))}
.meter-quiet .tape-fill{fill:color-mix(in srgb,var(--ink) 26%,var(--sunk))}
.tape-ticks{stroke:color-mix(in srgb,var(--sunk) 70%,transparent);stroke-width:1.2;vector-effect:non-scaling-stroke}
.tape-mark{stroke:var(--ink);stroke-width:2.5;vector-effect:non-scaling-stroke}
.cov-ok{fill:var(--pass)}.cov-fail{fill:var(--fail)}.cov-open{fill:color-mix(in srgb,var(--ink) 18%,var(--sunk))}

/* at-a-glance cells */
.glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:2px;border-radius:var(--r-ctl);overflow:hidden;background:var(--rule);margin:0}
.gl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:0 8px;align-content:start;align-items:start;padding:12px;background:var(--tag)}
.gl .i,.gl .os{width:17px;height:17px;margin-top:1px;color:var(--ink-2)}
.gl-value{grid-column:2;font:600 .92rem/1.3 var(--sans);color:var(--ink)}
.gl-pass .i,.gl-pass .os,.gl-pass .gl-value{color:var(--pass)}
.gl-pass .gl-value small{color:var(--ink-2)}
.gl-caution .i,.gl-caution .os,.gl-caution .gl-value{color:var(--caution)}
.gl-fail .i,.gl-fail .gl-value{color:var(--fail)}
.gl-quiet .gl-value{color:var(--ink-2);font-weight:500}

/* Fitz says */
.says{display:flex;align-items:flex-end;gap:12px}
.says .fitz{flex:none}
/* Fitz's words are in Fitz's own olive (--voice); the 2px outline belongs to your request only. */
.bubble{position:relative;background:var(--voice);color:var(--ink);border:1px solid var(--voice-line);border-radius:16px 16px 16px 6px;padding:16px 20px;margin-bottom:18px;max-width:62ch}
/* The tail: an outline triangle, and a fill triangle inset 1px from its outer edges that also covers the bubble's border where they meet */
.bubble::before,.bubble::after{content:"";position:absolute;left:-18px;bottom:4px;width:20px;height:20px}
.bubble::before{background:var(--voice-line);clip-path:polygon(18px 2.2px,18px 15.6px,0 20px)}
.bubble::after{background:var(--voice);clip-path:polygon(20px 1.6px,20px 14.1px,3.3px 18.2px)}
.bubble p:last-child{margin-bottom:0}
.bubble h2,.bubble h3{margin-bottom:4px}

/* seam: stitching on verified evidence */
.seam{height:2px;margin:20px 0;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.seam-sample{display:inline-block;width:34px;height:2px;vertical-align:middle;margin-right:8px;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.tape-sample,.cov-sample{display:inline-block;width:34px;height:10px;border-radius:2px;vertical-align:middle;margin-right:8px;background:linear-gradient(90deg,color-mix(in srgb,var(--ink) 48%,var(--sunk)) 0 70%,var(--sunk) 70%)}
.cov-sample{background:linear-gradient(90deg,var(--pass) 0 50%,var(--fail) 50% 62%,color-mix(in srgb,var(--ink) 18%,var(--sunk)) 62%)}

/* commands */
/* A command wraps instead of scrolling, so all of it shows; Copy still copies the text exactly as printed.
   It wraps as a terminal does (to the edge, not at a hyphen), and a wrapped part hangs 2ch in, so it never reads as
   the next command; each line of several is its own block (.ln) and starts flush. */
.cmd{display:flex;align-items:center;background:var(--code-bg);color:var(--ink);border:1px solid var(--rule);border-radius:var(--r-ctl);margin:6px 0 10px;min-width:0}
.cmd pre{flex:1;min-width:0;margin:0;padding:12px 14px 12px calc(14px + 2ch);text-indent:-2ch;overflow-x:auto;line-height:1.6;white-space:pre-wrap;word-break:break-all;scrollbar-color:color-mix(in srgb,var(--ink) 30%,transparent) transparent}
.cmd .ln{display:block}
.copy{display:none;align-items:center;gap:6px;flex:none;min-height:32px;font:600 .85rem/1 var(--sans);color:var(--ink);background:transparent;border:1px solid var(--line-ctl);border-radius:8px;padding:0 12px;margin:0 8px 0 0;cursor:pointer;transition:background .2s,color .2s,border-color .2s}
.copy .i{display:none}
.js .copy{display:inline-flex}
.cmd-multi{align-items:flex-start}
.cmd-multi .copy{margin-top:8px}
.copy:hover{background:color-mix(in srgb,var(--ink) 8%,transparent)}
.copy.done{color:var(--pass);border-color:var(--pass)}

/* notices */
.notice{display:flex;align-items:center;gap:18px;border-radius:var(--r-card);padding:18px 22px;margin:28px 0;background:var(--tag);box-shadow:var(--lift-1)}
.notice h2{font-size:var(--t-head);margin-bottom:4px}
.notice p{margin:0}
.notice.busy{background:var(--caution-soft)}
.notice.busy h2{color:var(--caution)}
.notice.error{background:var(--fail-soft)}
.notice.error h2{color:var(--fail)}
.notice .fitz{flex:none}

/* popovers and the legend dialog: on --raised, the surface that comes up to meet you */
.pop{margin:0;inset:auto;position:fixed;width:min(340px,calc(100vw - 32px));padding:16px 40px 14px 16px;border:0;border-radius:var(--r-card);background:var(--raised);color:var(--ink);box-shadow:var(--lift-3);font-size:var(--t-small)}
.pop:popover-open{animation:pop-in .2s var(--ease-out)}
.pop p{margin:0 0 8px}.pop p:last-child{margin:0}
.pop-title{font:700 1rem/1.2 var(--display)}
.pop-close{position:absolute;top:8px;right:8px;display:grid;place-items:center;width:30px;height:30px;border:0;border-radius:8px;background:transparent;color:var(--ink-2);cursor:pointer}
.pop-close:hover{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink)}
.help{display:inline-grid;place-items:center;width:24px;height:24px;margin:-4px 0;padding:0;border:0;border-radius:50%;background:transparent;color:var(--ink-2);cursor:help}
.help:hover{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink)}
.help .i{width:16px;height:16px}
.sheet{width:min(640px,calc(100vw - 32px));max-height:calc(100dvh - 48px);padding:28px;border:0;border-radius:20px;background:var(--raised);color:var(--ink);box-shadow:var(--lift-3)}
/* A neutral scrim from the page's own tokens (an older browser, where ::backdrop inherits nothing, gets the near-black one). */
.sheet::backdrop{background:var(--scrim,rgb(14 15 12/.55));backdrop-filter:blur(2px)}.sheet[open]{animation:pop-in .25s var(--ease-out)}
.sheet-close{position:absolute;top:12px;right:12px;margin:0}
.sheet-head{display:flex;align-items:center;gap:14px;margin-bottom:18px}
.legend{margin:0;display:grid;gap:14px}
.legend div{display:grid;grid-template-columns:200px minmax(0,1fr);gap:16px;align-items:start}
.legend dt{font:600 .95rem/1.3 var(--display)}
.legend dd{margin:0;color:var(--ink-2);font-size:.95rem}
.legend dt:has(.mark-sample){display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.mark-sample{display:inline-flex;align-items:center;gap:6px;color:var(--ink-2)}
/* Browse cards show the gem as its outline only, so the legend shows that outline beside its name. */
.legend .badge-gem>.i{display:inline-block}
.mark-sample.rf .i{width:18px;height:18px}
.mark-sample .oses .os{width:18px;height:18px}

/* compare tray and toasts */
.tray{position:fixed;left:0;right:0;bottom:0;z-index:20;padding:10px 0;background:var(--raised);color:var(--ink);border-top:1px solid var(--rule);box-shadow:0 -12px 30px -18px rgb(0 0 0/.35);animation:tray-in .35s var(--ease-out)}
.tray[hidden]{display:none}
.tray-row{display:flex;align-items:center;gap:12px}
/* The tools in the tray are names with a remove button, not pills: pills are switches. */
.tray-list{display:flex;flex-wrap:wrap;gap:4px 18px;list-style:none;padding:0;margin:0;flex:1;min-width:0}
.tray-list li{display:inline-flex;align-items:center;gap:2px;font:600 .92rem/1.2 var(--sans)}
.tray-list button{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:50%;background:transparent;color:var(--ink-2);cursor:pointer}
.tray-list button:hover{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink)}
.tray-list .i{width:16px;height:16px}
.tray-note{font-size:var(--t-small);color:var(--ink-2)}
.tray .btn-ghost{color:var(--ink-2)}
.toasts{position:fixed;left:50%;bottom:84px;z-index:40;display:flex;flex-direction:column;align-items:center;gap:8px;transform:translateX(-50%);pointer-events:none}
.toast{padding:10px 16px;border-radius:var(--r-ctl);background:var(--raised);color:var(--ink);font:500 .92rem/1.3 var(--sans);box-shadow:var(--lift-2);animation:toast 2.4s var(--ease-out) both}

/* skeleton */
/* skeleton: one dashed outline in the answer's shape (a name, the fit, a line, the command). It doesn't pulse:
   the tape unrolling above it is the only motion while Fitz looks. */
.skel{border-radius:var(--r-card);border:1px dashed var(--line-ctl);padding:22px 24px;display:grid;gap:12px}
.skel+.skel{display:none}
.skel i{display:block;height:12px;border-radius:6px;background:color-mix(in srgb,var(--ink) 9%,transparent)}
.skel i:nth-child(1){width:34%;height:20px}.skel i:nth-child(2){width:78%}.skel i:nth-child(3){width:58%}.skel i:nth-child(4){width:100%;height:44px;border-radius:var(--r-ctl);margin-top:6px}

/* fact sheets */
.facts-dl{margin:0;display:grid;gap:0}
.facts-dl div{display:grid;grid-template-columns:minmax(110px,40%) minmax(0,1fr);gap:12px;padding:9px 0;border-bottom:1px solid var(--rule)}
.facts-dl div:last-child{border-bottom:0}
.facts-dl dt{color:var(--ink-3);font-size:var(--t-small)}
.facts-dl .kind .i{display:none}
.facts-dl dd{margin:0;font-size:.95rem}
.unknown{color:var(--ink-2);font-style:normal}

/* data tables */
.table-wrap{overflow-x:auto;border-radius:var(--r-card);background:var(--tag);box-shadow:var(--lift-1)}
.dt{width:100%;border-collapse:collapse;font-size:.95rem}
.dt th,.dt td{text-align:left;vertical-align:top;padding:12px 16px;border-bottom:1px solid var(--rule)}
.dt thead th{font:700 .85rem/1.2 var(--display);color:var(--ink-2);background:var(--sunk);position:sticky;top:0}
.dt tbody tr:last-child td,.dt tbody tr:last-child th{border-bottom:0}
.dt tbody th{font:600 .85rem/1.3 var(--display);color:var(--ink-2);white-space:nowrap}
.dt .grp th{background:color-mix(in srgb,var(--sunk) 60%,var(--tag));font:700 .8rem/1 var(--display);color:var(--ink);padding:10px 16px;letter-spacing:.02em}
.best{display:inline-flex;align-items:center;gap:4px;margin-left:6px;font:700 .72rem/1 var(--display);color:var(--pass)}
.best .i{width:.9em;height:.9em;stroke-width:2.4}

/* section heads */
.sec{padding-top:var(--gap)}
.sec-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:32px;flex-wrap:wrap}
.sec-head h2{max-width:22ch}
.sec-head>div{flex:1 1 0;min-width:min(100%,20rem)}
.sec-head p{margin:10px 0 0;color:var(--ink-2);font-size:var(--t-lead);max-width:68ch}
/* "See the full method": a link is underlined words; the arrow beside them said the same thing. */
.more{display:inline-flex;align-items:center;gap:6px;font:600 1rem/1.3 var(--sans);text-decoration:underline;text-decoration-color:var(--line-ctl);text-underline-offset:4px;white-space:nowrap}
.more:hover{text-decoration-color:var(--stitch)}
.more .i{display:none}

/* page head (every page but home): on the page's own ground, a hairline under it; Fitz stands on the line */
.head{padding:28px 0 0;position:relative;z-index:4;overflow:clip visible;background:var(--paper);border-bottom:1px solid var(--rule)}
.head-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:24px;padding-bottom:28px}
.head h1{font-size:clamp(2rem,3.2vw,2.75rem)}
.head .lede{font-size:var(--t-lead);color:var(--ink-2);margin:12px 0 0;max-width:68ch;text-wrap:balance}
.head .fitz{margin-bottom:-6px}
.head .badges{margin-top:14px}
.crumbs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 14px;font:600 .9rem/1 var(--display);color:var(--ink-2)}
.crumbs a{color:var(--ink-2);text-decoration:none}.crumbs a:hover{color:var(--ink);text-decoration:underline}

/* footer: one quiet row on the page ground, under a hairline. The links, then the two trust sentences. */
.foot{margin-top:var(--gap);background:var(--paper);color:var(--ink-2);border-top:1px solid var(--rule);padding:28px 0 40px}
.foot-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 48px}
.foot-links{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 24px}
.foot-links a{display:inline-block;padding:4px 0;color:var(--ink-2);font:500 .95rem/1.3 var(--sans);text-decoration-color:var(--line-ctl);text-underline-offset:4px}
.foot-links a:hover{color:var(--ink);text-decoration-color:var(--stitch)}
.foot-row p{margin:0;max-width:62ch;font-size:var(--t-small);color:var(--ink-3)}
`;

const RESULTS = `
/* the request: where you talk to Fitz. The one raised surface, outlined in Fitz's own line colour. */
.ask-card{position:relative;background:var(--raised);color:var(--ink);border:2px solid var(--fitz-line);border-radius:16px;padding:16px 22px;box-shadow:var(--lift-1);transition:box-shadow .2s var(--ease-out)}
/* Typing: the outline thickens (2px to 3px, drawn as a ring so nothing shifts), so focus never rests on the yellow alone. */
.ask-card:focus-within{box-shadow:0 0 0 1px var(--fitz-line),var(--lift-1)}
@media (prefers-color-scheme:dark){.ask-card{box-shadow:none}.ask-card:focus-within{box-shadow:0 0 0 1px var(--fitz-line)}}
.ask{position:relative;display:flex;align-items:baseline;gap:12px;padding:2px 0 22px}
/* The signature: Fitz's measuring tape is the request's baseline. At rest, fine ticks on a 2px line (no numbers:
   decoration must not look like data); while you type, the whole tape unrolls under your words, its metal tab at the end. */
.ask::before,.ask::after{content:"";position:absolute;left:0;right:0;bottom:0;height:12px;pointer-events:none}
.ask::after{background:
linear-gradient(var(--tape-edge),var(--tape-edge)) left bottom/100% 2px no-repeat,
repeating-linear-gradient(90deg,var(--tape-edge) 0 2px,transparent 2px 48px) left bottom/100% 12px no-repeat,
repeating-linear-gradient(90deg,var(--tape-edge) 0 1.5px,transparent 1.5px 8px) left bottom/100% 6px no-repeat}
.ask::before{z-index:1;border-radius:2px;box-shadow:inset 0 -1px 0 var(--tape-deep);background:
repeating-linear-gradient(90deg,var(--tape-ink) 0 1.5px,transparent 1.5px 48px) 12px 0/calc(100% - 12px) 7px no-repeat,
repeating-linear-gradient(90deg,color-mix(in srgb,var(--tape-ink) 65%,transparent) 0 1px,transparent 1px 8px) 12px 0/calc(100% - 12px) 4px no-repeat,
linear-gradient(var(--tape-tab),var(--tape-tab)) left/12px 100% no-repeat,
var(--tape);
clip-path:inset(0 100% 0 0);transition:clip-path .45s var(--ease-out)}
.ask:focus-within::before{clip-path:inset(0 0 0 0)}
.ask label{font:700 1.4rem/1.3 var(--display);letter-spacing:-.02em;color:var(--ink-2);white-space:nowrap}
/* field-sizing lets the field fit the whole sentence before (or without) the page script. */
.ask textarea{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font:500 1.4rem/1.3 var(--display);letter-spacing:-.015em;resize:none;padding:0;overflow:hidden;field-sizing:content}
.ask textarea::placeholder{color:var(--ink-3);opacity:1}
.ask textarea:focus-visible{outline:none}
.ask-meta{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px 16px;margin-top:14px}
.ask-opts{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.ask-go{display:flex;align-items:center;justify-content:flex-end;gap:12px;margin-left:auto}
.ask-meta .label{font:500 .85rem/1 var(--sans);color:var(--ink-3);margin-right:2px}
.ask-meta .grow{flex:1}
.ask-meta .btn-primary{min-height:48px;padding:0 24px;font-size:1.05rem}
/* the words already say Free, Offline, Data stays local and Find tools: their icons go */
.ask-opts .chip>.i,.ask-go .btn>.i{display:none}
.counter{font:500 .8rem/1 var(--sans);color:var(--ink-3);font-variant-numeric:tabular-nums}
.counter:empty{display:none}
.counter.over{color:var(--fail);font-weight:700}
/* examples: underlined words that fill the request (only switches are pills) */
.tries{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 20px;margin-top:16px}
.tries .label{font:500 .9rem/1 var(--sans);color:var(--ink-3)}
.try{display:inline-flex;align-items:center;min-height:32px;padding:0;border:0;background:none;color:var(--ink-2);font:500 .95rem/1.3 var(--sans);text-align:left;text-decoration:underline;text-decoration-color:var(--line-ctl);text-decoration-thickness:1px;text-underline-offset:4px;cursor:pointer;transition:color .2s,text-decoration-color .2s}
.try:hover{color:var(--ink);text-decoration-color:var(--stitch)}

/* results area */
.results{padding-top:8px}
.results:focus{outline:none}
.results:empty{display:none}
.res-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px 32px;align-items:end;margin:40px 0 24px}
/* One Fitz on the results: he stands over the answer without a bubble of his own, so only the first pick is in his olive. */
.res-head .says{align-items:center;gap:20px}
.res-head .fitz{width:88px;height:auto}
.res-head .bubble{background:none;border:0;border-radius:0;padding:0;margin:0;box-shadow:none;max-width:72ch}
.res-head .bubble::before,.res-head .bubble::after{content:none}
.results-title{font-size:var(--t-title)}
.match-line{color:var(--ink-3);margin:6px 0 0;font-size:var(--t-small)}
.res-tools{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}
.ask-note,.aside{background:var(--tag);border-radius:var(--r-card);padding:18px 22px;margin:20px 0;box-shadow:var(--lift-1);max-width:none}
.ask-note{display:flex;gap:14px;align-items:center;background:var(--info-soft)}
.ask-note .fitz{flex:none}
.ask-note p{margin:0}
.aside h3{margin-bottom:8px}
.lead-in{font-weight:700;font-family:var(--display)}
.picks{display:grid;grid-template-columns:minmax(0,1fr);gap:28px}

/* a pick: the fitting ticket. The answer comes first: the first pick sits in Fitz's olive (--voice) with every step
   and the one solid yellow (Copy); the others follow on the page under "Also fits", each a few lines of text with
   a three-stitch seam (pickfit ran it). A row of wrapping flex items, so "Why it fits" and the foot share a line
   until the fold opens. */
.pick{position:relative;display:flex;flex-wrap:wrap;align-items:center;background:var(--tag);border-radius:var(--r-card);box-shadow:var(--lift-1);padding:26px 28px 22px;animation:rise .6s var(--ease-out) both}
.pick>*{flex:0 0 100%;min-width:0}
.pick>.t-more:not([open]){flex:0 0 auto;margin-right:18px}
.pick>.t-foot{flex:1 1 auto}
.picks>:nth-child(n+2){animation-delay:.1s}
.pick:target{box-shadow:0 0 0 3px var(--stitch)}
.picks .pick:first-child{background:var(--voice);border:1px solid var(--voice-line);box-shadow:none;padding:28px 32px 22px}
.picks .pick:first-child:target{box-shadow:0 0 0 3px var(--stitch)}
.also{font:600 1rem/1.3 var(--sans);letter-spacing:0;color:var(--ink-2);margin:16px 0 -16px;animation:rise .6s .1s var(--ease-out) both}
.picks .pick:not(:first-child){background:none;box-shadow:none;border-radius:0;border-top:1px solid var(--rule);padding:20px 0 0}
.picks .pick:not(:first-child):target{box-shadow:none;outline:3px solid var(--stitch);outline-offset:6px}
.t-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;align-items:start}
.t-name{font-size:1.6rem;letter-spacing:-.025em}
.t-name a{text-decoration:none}.t-name a:hover{text-decoration:underline;text-decoration-color:var(--stitch)}
.t-kind{font:500 .88rem/1.3 var(--sans);color:var(--ink-3);margin:2px 0 0}
.t-kind .i,.pick .badges .i{display:none}
.t-top .badges{justify-content:flex-end;max-width:320px}
.summary{color:var(--ink-2);margin:14px 0 0}
.fit{font:600 1.3rem/1.4 var(--display);letter-spacing:-.015em;margin:12px 0 20px;max-width:56ch;text-wrap:balance}
/* Fitz's answer in the system face: it is often Chinese, and the tool's name above already carries the display face. */
.pick .fit{font:500 1.2rem/1.45 var(--sans);letter-spacing:0;max-width:60ch}
.t-glance{grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:0}
.gl-value small{display:block;font:500 .8rem/1.3 var(--sans);color:var(--ink-2)}
/* The verdict strip as plain facts between two hairlines: only the OS keeps its mark, the words say the rest. */
.picks .t-glance{gap:0 24px;background:none;border-radius:0;overflow:visible;border-block:1px solid var(--voice-line)}
.picks .gl{display:block;padding:12px 0;background:none;line-height:1.3}
.picks .gl .i{display:none}
.picks .gl .os{display:inline-block;width:16px;height:16px;margin:0 6px 0 0;vertical-align:-2px}
.picks .gl-value small{margin-top:2px}
.instead{margin:16px 0 0;color:var(--ink-2);max-width:68ch}
.instead a{color:var(--ink);font-weight:600}
.pick .seam{margin:18px 0 16px}
.t-install-label{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;font:400 .95rem/1.4 var(--sans);margin:0 0 8px}
.t-install-label b{font-weight:700;color:var(--ink)}
.t-install-label .i{display:none}
.t-install .cmd{margin:0}
.t-install .caution{margin:8px 0 0}
.t-fix{display:flex;gap:8px;align-items:flex-start;margin:10px 0 0;font-size:var(--t-small);color:var(--ink-2);max-width:68ch}
.t-fix .i{display:none}
.t-fix b{color:var(--ink)}
.t-install .cmd pre{font-size:.95rem;padding:14px 16px 14px calc(16px + 2ch)}
/* The one solid yellow on the results: the first pick's (first) Copy. Not for steps that ran on another OS than
   the one chosen (t-elsewhere): those are said with a caution and stay quiet. Every Copy in the fold is quiet. */
.picks .pick:first-child .t-install:not(.t-elsewhere) .cmd:first-of-type .copy{background:var(--tape);color:var(--tape-ink);border-color:var(--tape-edge);min-height:36px;padding:0 16px}
.picks .pick:first-child .t-install:not(.t-elsewhere) .cmd:first-of-type .copy:hover{background:color-mix(in srgb,var(--tape) 88%,#fff)}
.picks .pick:first-child .t-install:not(.t-elsewhere) .cmd:first-of-type .copy.done{background:transparent;color:var(--pass);border-color:var(--pass)}
.t-install-label+.caution{margin:0 0 8px}
.t-install .cmd+.cmd{margin-top:8px}
/* Inside the fold, boxes are a tint of the ground they sit on, so they read on the olive and on the page alike. */
.pick .t-measure,.pick .install,.pick .issues li{background:color-mix(in srgb,var(--ink) 4%,transparent)}
.t-open{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0;max-width:none}
.t-open .quiet{overflow-wrap:anywhere}
/* Also fits: name, kind and fit sentence, the three stitches, then one line of facts; the steps and the README fix
   are in the fold and on the tool page, so a Linux command never shows unexplained to a Mac user. */
.picks .pick:not(:first-child)>.t-top,.picks .pick:not(:first-child)>.fit{order:-2}
.picks .pick:not(:first-child)>.seam{order:-1;clip-path:inset(0 calc(100% - 31px) 0 0);margin:0 0 10px}
.picks .pick:not(:first-child) .t-name{font-size:1.25rem}
.picks .pick:not(:first-child) .fit{font-size:1rem;font-weight:400;margin:6px 0 12px}
.picks .pick:not(:first-child) .t-glance{display:flex;flex-wrap:wrap;gap:4px 18px;border:0}
.picks .pick:not(:first-child) .gl{padding:0}
.picks .pick:not(:first-child) .gl:has(>.i-terminal){display:none}
.picks .pick:not(:first-child) .gl-value{font-weight:500;font-size:.92rem}
.picks .pick:not(:first-child) .gl-plain .gl-value{color:var(--ink-2)}
.picks .pick:not(:first-child) .gl-value small{display:inline;margin:0 0 0 18px;font:inherit;color:var(--ink-2)}
.picks .pick:not(:first-child) .t-install{display:none}
.picks .pick:not(:first-child) .t-more{margin-top:8px}
.picks .pick:not(:first-child) .t-foot{margin-top:8px}
.web-facts{list-style:none;padding:0;margin:4px 0 8px;display:grid;gap:4px}
.web-facts li{display:flex;gap:8px;align-items:flex-start;font-size:var(--t-small)}
.web-facts .i{flex:none;width:16px;height:16px;margin-top:2px}
.web-facts li:not(.yes):not(.no){color:var(--ink-2)}
/* a web app's "open it" card: an address bar ending in the button, then the facts two to a row */
.web-bar{display:flex;align-items:center;gap:12px;margin:16px 0 20px;padding:6px 6px 6px 16px;border-radius:999px;background:var(--sunk)}
.web-addr{flex:1;min-width:0;display:flex;align-items:center;gap:10px;color:var(--ink-2);font:500 .92rem/1.3 var(--mono)}
.web-addr .i{flex:none;width:18px;height:18px}
.web-addr span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.web-bar .btn{flex:none;border-radius:999px}
.web-facts-grid{grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:12px 24px;margin:0}
.web-facts-grid li,.web-facts-grid li:not(.yes):not(.no){align-items:center;gap:10px;font:500 .95rem/1.35 var(--sans);color:var(--ink)}
.web-facts-grid .i,.web-facts-grid .yes .i,.web-facts-grid .no .i{box-sizing:content-box;width:16px;height:16px;margin:0;padding:6px;border-radius:50%;background:var(--sunk);color:var(--ink-2)}
.web-facts-grid .yes .i{background:var(--pass-soft);color:var(--pass)}
.web-facts-grid .no .i{background:var(--caution-soft);color:var(--caution)}
@media (max-width:520px){.web-bar{flex-direction:column;align-items:stretch;gap:8px;padding:12px;border-radius:var(--r-ctl)}.web-bar .btn{justify-content:center}}
.t-more{margin-top:16px;border-radius:var(--r-ctl)}
.t-more>summary{display:inline-flex;align-items:center;gap:8px;list-style:none;padding:8px 0;font:600 .95rem/1.3 var(--sans);color:var(--ink-2)}
.t-more>summary::-webkit-details-marker{display:none}
.t-more>summary:hover{color:var(--ink)}
.t-more>summary .i{transition:transform .25s var(--ease-out)}
.t-more[open]>summary .i{transform:rotate(180deg)}
.t-more-body{padding-top:12px;display:grid;grid-template-columns:minmax(0,1fr);gap:20px}
.t-more-body .record{padding-top:20px;border-top:1px solid var(--rule)}
.t-links{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0}
.t-links a{display:inline-flex;align-items:center;gap:6px;font:600 .9rem/1 var(--display)}
.t-links a .i{display:none}
.t-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:28px 40px}
.t-body h4:first-child{margin-top:0}
.t-measure{display:grid;gap:18px;align-content:start;align-self:start;padding:18px;border-radius:var(--r-ctl);background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.coverage{color:var(--ink-2);font-size:var(--t-small)}
.why{list-style:none;padding:0;margin:0 0 8px}
.why li{position:relative;padding-left:30px;margin-bottom:12px}
.why li::before{content:"";position:absolute;left:2px;top:2px;width:18px;height:18px;border-radius:50%;background:var(--pass-soft) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232E7A35' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E") center/12px no-repeat}
.cite{display:block;font-size:var(--t-small);color:var(--ink-2);margin-top:2px}
.why-marks li{display:block;padding-left:0;margin-bottom:10px}
.why-marks li::before{content:none}
/* The reason's words say what its mark said; the file mark after them stays: it says the citation opens. */
.why-marks .why-i{display:none}
.why-i{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--pass-soft);color:var(--pass)}
.why-i .i,.why-i .os{width:13px;height:13px}
.why-src summary{list-style:none;cursor:pointer}
.why-src summary::-webkit-details-marker{display:none}
.why-src summary .i{width:.85em;height:.85em;margin-left:6px;vertical-align:-.1em;color:var(--ink-2);opacity:.75}
.why-src[open] summary .i{color:var(--stitch);opacity:1}
.why-src .cite{margin:4px 0 0}
.cite code{font-size:.85em}
.tradeoffs{list-style:none;padding:0;margin:0}
.tradeoffs li{position:relative;padding-left:30px;margin-bottom:10px}
.tradeoffs li::before{content:"";position:absolute;left:6px;top:.62em;width:10px;height:2px;border-radius:1px;background:var(--caution)}
.vs{margin-top:14px}
.level{display:flex;align-items:center;gap:8px;font:700 1.05rem/1.3 var(--display);margin:0 0 6px}
.level-caution{color:var(--caution)}
.check{width:22px;height:22px;flex:none;border-radius:50%;background:var(--pass);padding:4px}
.level-i{display:grid;place-items:center;width:22px;height:22px;flex:none;border-radius:50%;background:var(--pass);color:var(--tag)}
.level-i .i{width:13px;height:13px;stroke-width:2.4}
.check path{fill:none;stroke:var(--tag);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.record{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:8px 40px}
.record>*{grid-column:1}
.record .mine{grid-column:2;grid-row:1/span 3;align-self:start}
.record:not(:has(.mine)){grid-template-columns:minmax(0,1fr)}
.record p{margin:0 0 6px}
/* A label in text ink: --stitch is for stitches and focus, and is under 4.5:1 as text on the light grounds. */
.record-title{display:flex;align-items:center;gap:8px;font:700 .8rem/1 var(--display);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);margin:0 0 10px}
.record-title .i{display:none}
.mine{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:var(--r-ctl);font-weight:600;max-width:none}
.mine .i{margin-top:2px}
.mine-yes{background:var(--pass-soft);color:var(--pass)}
.mine-no{background:var(--caution-soft);color:var(--caution)}
.mine-unknown{background:var(--sunk);color:var(--ink)}
details>summary{cursor:pointer}
/* One disclosure mark on every page: a chevron before the words, pointing down, up once open (as "Why it fits").
   A summary without its own icon draws it here; the ones with a chevron icon put it first (order:-1). */
details:not(.menu)>summary:not(:has(>.i)){list-style:none}
details:not(.menu)>summary:not(:has(>.i))::-webkit-details-marker{display:none}
details:not(.menu)>summary:not(:has(>.i))::before{content:"";display:inline-block;width:1.1em;height:1.1em;margin-right:6px;vertical-align:-.2em;background:currentColor;transition:transform .25s var(--ease-out);
-webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") center/contain no-repeat;
mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") center/contain no-repeat}
details[open]:not(.menu)>summary:not(:has(>.i))::before{transform:rotate(180deg)}
.how summary{font:600 var(--t-small)/1.4 var(--display);color:var(--ink-2);margin-top:4px}
.how p{font-size:var(--t-small);color:var(--ink-2);margin-top:6px}
.install{margin:16px 0 0;border-radius:var(--r-ctl);background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.install>summary{display:flex;align-items:center;gap:10px;list-style:none;padding:14px 16px;font:700 1rem/1.3 var(--display)}
.install>summary::-webkit-details-marker{display:none}
.install>summary .i:last-child{order:-1;transition:transform .25s var(--ease-out)}
.install[open]>summary .i:last-child{transform:rotate(180deg)}
.install-body{padding:0 16px 14px}
.install-body h4{font:700 .95rem/1.3 var(--display);margin:18px 0 6px}
[data-stepper]{scroll-margin-top:16px}
.stage-tabs{display:flex;flex-wrap:wrap;align-items:center;gap:4px;list-style:none;padding:0;margin:0 0 6px}
.stage-tabs li{display:flex;align-items:center;gap:4px}
.stage-tabs li+li::before{content:"";width:16px;height:2px;border-radius:1px;background:color-mix(in srgb,var(--ink-2) 35%,transparent)}
.stage-tabs button{display:inline-flex;align-items:center;gap:8px;min-height:34px;padding:0 12px 0 5px;border:0;border-radius:999px;background:none;color:var(--ink-2);font:600 .9rem/1 var(--display);cursor:pointer}
.stage-tabs button:hover{color:var(--ink)}
.stage-tabs .n{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--sunk);font-size:.78rem}
.stage-tabs button[aria-current=step]{background:var(--tag);color:var(--ink);box-shadow:var(--lift-1)}
.stage-tabs button[aria-current=step] .n{background:var(--ink);color:var(--paper)}
.stage-tabs button.done .n{background:var(--pass-soft);color:var(--pass)}
.stage-tabs button:focus-visible{outline:3px solid var(--stitch);outline-offset:1px}
.inst-stage[hidden]{display:none}
.inst-stage+.inst-stage{margin-top:6px}
.js .inst-check>h4:first-child{display:none}
.js .inst-stage .open-hint:first-child{margin-top:10px}
.stage-nav{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:20px;padding-top:14px;border-top:1px solid color-mix(in srgb,var(--ink-2) 18%,transparent)}
.stage-nav .stage-next{margin-left:auto}
@media (max-width:520px){.stage-tabs{flex-wrap:nowrap}.stage-tabs button:not([aria-current]) .lbl{display:none}.stage-tabs button:not([aria-current]){padding-right:5px}}
.steps{padding-left:24px;margin:0}.steps li{margin-bottom:12px}.steps li::marker{font:700 .9rem var(--display);color:var(--ink-2)}.steps li p{margin-bottom:4px}
.caution{color:var(--caution)}
.issues{list-style:none;padding:0}.issues li{padding:10px 12px;margin-bottom:8px;border-radius:var(--r-ctl);background:var(--tag)}
.t-foot{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;margin-top:16px}
.t-foot a{display:inline-flex;align-items:center;gap:6px;font:500 .95rem/1.3 var(--sans);text-underline-offset:4px}
.t-foot .grow{flex:1}
.t-foot .more .i,.pick .chip-compare .i{display:none}
.chip-compare{min-height:36px}
.outside{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 18px;margin:36px 0 0;padding:22px;border-radius:var(--r-card);border:2px dashed var(--rule);color:var(--ink-2);max-width:none}
.outside>.i{grid-row:1/5;width:28px;height:28px;color:var(--ink-2)}
.outside h3{font:600 1.1rem/1.35 var(--sans);letter-spacing:0;color:var(--ink);margin-bottom:6px}
.unchecked{display:inline-block;background:var(--caution-soft);color:var(--caution);border-radius:var(--r-ctl);padding:8px 12px;font-weight:600;max-width:none}
.nofit{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:40px;align-items:start}
.nofit .outside{margin:0}
.best-free{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px 40px;align-items:start}
.best-free>p:first-child{grid-row:span 2}
.sbs{margin-top:24px}
/* A fold, not a button: the same disclosure line as "Why it fits". */
.sbs>summary{display:inline-flex;align-items:center;gap:8px;list-style:none;font:600 .95rem/1.3 var(--sans);color:var(--ink-2);padding:8px 0}
.sbs>summary:hover{color:var(--ink)}
.sbs>summary .i{transition:transform .25s var(--ease-out)}
.sbs[open]>summary .i{transform:rotate(180deg)}
.picks+p{margin-top:28px}
.sbs>summary::-webkit-details-marker{display:none}
.sbs[open]>summary{margin-bottom:16px}
/* waiting: Fitz talks (his --voice bubble) while his tape unrolls; one dashed outline shows where the answer will land */
.loading{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;margin-top:32px;max-width:1040px}
.loading .bubble{max-width:760px;padding:20px 24px}
.loading .bubble h2{font-size:1.35rem}
.loading ol{color:var(--ink-2);padding-left:20px;margin:10px 0 8px;font-size:.95rem}
.loading .quiet{color:var(--ink-3)}
/* the outline lines up under the bubble: Fitz (104px) and the 12px gap */
.loading .skel{max-width:760px;margin-left:116px}
@media (max-width:640px){.loading .skel{margin-left:0}}
.unroll{position:relative;height:12px;max-width:420px;margin-top:14px;background:
linear-gradient(var(--tape-edge),var(--tape-edge)) left bottom/100% 2px no-repeat,
repeating-linear-gradient(90deg,var(--tape-edge) 0 1.5px,transparent 1.5px 8px) left bottom/100% 5px no-repeat}
.unroll::after{content:"";position:absolute;inset:0;border-radius:2px;box-shadow:inset 0 -1px 0 var(--tape-deep);background:
repeating-linear-gradient(90deg,var(--tape-ink) 0 1.5px,transparent 1.5px 48px) 12px 0/calc(100% - 12px) 7px no-repeat,
repeating-linear-gradient(90deg,color-mix(in srgb,var(--tape-ink) 65%,transparent) 0 1px,transparent 1px 8px) 12px 0/calc(100% - 12px) 4px no-repeat,
linear-gradient(var(--tape-tab),var(--tape-tab)) left/12px 100% no-repeat,
var(--tape);
clip-path:inset(0 40% 0 0);animation:unroll 2.4s var(--ease-io) infinite alternate}
`;

const PAGES = `
/* home: the hero is on the page's own ground. One focus: the request card, Fitz standing beside it. */
.hero{padding:clamp(40px,8vh,96px) 0 clamp(16px,3vh,32px);position:relative;z-index:4;overflow:clip visible}
.hero-grid{display:grid;grid-template-columns:minmax(0,820px) auto;justify-content:start;gap:24px clamp(40px,6vw,88px);align-items:center}
.hero h1{max-width:none}
/* no yellow word: the screen's one solid yellow is Find tools */
.hero h1 em{font-style:normal;color:inherit}
.hero .lede{font-size:var(--t-lead);color:var(--ink-2);margin:16px 0 32px;max-width:56ch;text-wrap:pretty}
.hero-fitz{position:relative;align-self:center;justify-self:start}
.hero-fitz .fitz{width:clamp(150px,16vw,220px);height:auto;display:block;animation:hop-in .9s .1s var(--ease-out) both}
.hero-form{max-width:none}
/* the numbers, in ink on a hairline: no icons (the words say it), no yellow */
.proof{display:flex;flex-wrap:wrap;gap:8px 28px;margin:32px 0 0;padding:20px 0 0;border-top:1px solid var(--rule);list-style:none;color:var(--ink-3);font-size:.95rem}
.proof li{display:inline-flex;align-items:baseline;gap:6px}
.proof strong{font:700 1.05rem/1 var(--display);color:var(--ink);font-variant-numeric:tabular-nums}
.proof .i{display:none}
body.is-results .hero{padding:12px 0 0}
body.is-results .hero-grid{grid-template-columns:minmax(0,1fr)}
body.is-results .hero h1,body.is-results .hero .lede,body.is-results .proof,body.is-results .tries{display:none}
.res-status{list-style:none;padding:0;margin:-8px 0 28px;display:grid;gap:8px;max-width:86ch}
.st{display:flex;gap:10px;align-items:flex-start;font-size:var(--t-small);color:var(--ink-2)}
.st .i{margin-top:2px;flex:none}
.st strong{font-family:var(--display);color:var(--ink)}
.st-busy .i{color:var(--caution)}.st-caution .i,.st-caution summary{color:var(--caution)}.st-info .i{color:var(--info)}
.st details summary{cursor:pointer;font-weight:600}
.st details[open] summary{margin-bottom:4px}
/* One Fitz per screen: on the results he stands over the answer, so the hero's Fitz goes; Find tools steps back so the first pick's Copy is the one solid yellow. */
body.is-results .hero-fitz{display:none}
body.is-results .ask-card .btn-primary{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1px var(--line-ctl)}
body.is-results .ask-card .btn-primary:hover{background:color-mix(in srgb,var(--ink) 6%,transparent);box-shadow:inset 0 0 0 1px var(--ink-2)}
body.is-results .home-only{display:none}

/* stages: one real tool through the four steps */
.stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:auto auto auto;column-gap:24px;list-style:none;padding:0;margin:0;position:relative}
.stages::before{content:"";position:absolute;left:4%;right:4%;top:84px;height:2px;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.stage{display:grid;grid-template-rows:subgrid;grid-row:span 3;row-gap:8px;position:relative;text-align:center;justify-items:center}
.stage-fitz{height:150px;display:flex;align-items:flex-end;justify-content:center;position:relative;z-index:1}
.stage-fitz .fitz{height:130px;width:auto;background:var(--paper);border-radius:50%;padding:0 6px}
.stage h3{font-size:1.3rem}
.stage>p{color:var(--ink-2);margin:0;max-width:16em}
/* On the home page the four steps are words only, numbered on a hairline: one Fitz per screen (/how keeps the four). */
.home-only .stages{counter-reset:stage}
.home-only .stages::before,.home-only .stage-fitz{display:none}
.home-only .stage{text-align:left;justify-items:start;align-items:start;padding-top:16px;border-top:1px solid var(--rule)}
.home-only .stage h3::before{content:counter(stage);counter-increment:stage;display:block;margin-bottom:10px;font:600 .9rem/1 var(--sans);letter-spacing:0;color:var(--ink-3)}
.stage-ui{background:var(--tag);border-radius:var(--r-card);padding:14px 16px;box-shadow:var(--lift-1);font-size:var(--t-small);min-height:180px}
.stage-ui .ui-title{font:700 .85rem/1.3 var(--display);color:var(--ink-2);margin-bottom:10px}
.stage-ui dl{margin:0}.stage-ui dl div{display:grid;grid-template-columns:84px minmax(0,1fr);gap:8px;padding:3px 0}
.stage-ui dt{color:var(--ink-2)}.stage-ui dd{margin:0}
.stage-ui pre{background:var(--code-bg);color:var(--ink);border:1px solid var(--rule);border-radius:8px;padding:8px 10px 8px calc(10px + 2ch);text-indent:-2ch;margin:0 0 8px;white-space:pre-wrap;word-break:break-all;font-size:.8rem}
.stage-ui .why li{margin-bottom:8px}
.stage-ui .level{font-size:.9rem}
.diff{display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;margin:8px 0 0}

/* fresh runs */
.fresh{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:40px;align-items:start}
.fix-card{background:var(--tag);border-radius:var(--r-card);padding:20px 22px;box-shadow:var(--lift-1)}
.fix-card h3{margin-bottom:10px}
.fix-kicker{display:flex;align-items:center;gap:8px;font:600 .85rem/1.2 var(--sans);color:var(--ink-2);margin:0 0 6px}
.fix-kicker .i,.run-row .kind .i{display:none}
.fix-card pre{background:var(--code-bg);color:var(--ink);border:1px solid var(--rule);border-radius:8px;padding:9px 12px 9px calc(12px + 2ch);text-indent:-2ch;margin:10px 0 0;white-space:pre-wrap;word-break:break-all;font-size:.85rem}
.fix-card figcaption{font-size:var(--t-small);color:var(--ink-2);margin-top:10px}
.readme-vs{display:grid;gap:6px;margin:10px 0 0;padding:0;list-style:none}
.readme-vs li{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;font-size:.92rem}
.readme-vs b{font:700 .8rem/1.6 var(--display)}
.readme-vs .was b{color:var(--fail)}.readme-vs .now b{color:var(--pass)}
.runs-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.run-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 16px;align-items:center;padding:14px 18px;background:var(--tag);border-radius:var(--r-card);box-shadow:var(--lift-1);transition:box-shadow .2s,transform .2s var(--ease-out)}
.run-row:hover{box-shadow:var(--lift-2);transform:translateY(-1px)}
.run-row a.name{font:700 1.1rem/1.2 var(--display);text-decoration:none}
.run-row a.name::after{content:"";position:absolute;inset:0}
.run-row{position:relative}
.run-row .meta{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px 14px;font-size:var(--t-small);color:var(--ink-2)}
.run-row .meta span{display:inline-flex;align-items:center;gap:5px}
.run-row .meta{position:relative;z-index:1}
.run-row .sum{grid-column:1/-1;margin:0;color:var(--ink-2);font-size:.95rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* care label: Fitz's rules */
.care{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:48px;align-items:center}
.care h2{margin-bottom:14px}
.agents-band h2{margin-bottom:10px}
/* Fitz's rules: a plain card, the rules one per line on hairlines (no tilt, no punched hole, no capitals) */
.label-tag{position:relative;background:var(--tag);border-radius:var(--r-card);padding:24px 28px;box-shadow:var(--lift-1)}
.rules{list-style:none;margin:0;padding:0;display:grid;gap:0}
.rules li{display:block;padding:12px 0;border-top:1px solid var(--rule)}
.rules li:first-child{border-top:0;padding-top:0}
.rules li:last-child{padding-bottom:0}
.rules .i{display:none}
.rules b{display:block;font:600 1.05rem/1.35 var(--display)}
.rules span{color:var(--ink-2);font-size:.95rem}

/* agents: an ordinary card on the page (no mat) */
.agents-band{background:var(--tag);color:var(--ink);box-shadow:var(--lift-1);border-radius:var(--r-card);padding:clamp(24px,3.5vw,40px);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px 40px;align-items:center}
.agents-band h2{color:var(--ink)}
.agents-band p{color:var(--ink-2);font-size:var(--t-lead)}
.agents-band .cmd{max-width:780px;margin-top:18px}
.agents-band .btn>.i{display:none}

/* detail and compare */
.layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:40px;align-items:start;margin-top:40px}
.side{position:sticky;top:20px;display:grid;gap:20px}
.panel{background:var(--tag);border-radius:var(--r-card);padding:20px 22px;box-shadow:var(--lift-1)}
.panel h2,.panel h3{font-size:1.1rem;margin-bottom:12px}
/* The scores sit in At a glance as quiet readings: the tape's ticks and the number stay, the yellow is kept for the screen's one action. */
.panel-measure{margin-top:16px;padding:16px 0 0;background:none;border-radius:0;border-top:1px solid var(--rule);gap:14px}
.panel-measure .meter-label{font:500 .85rem/1.2 var(--sans);color:var(--ink-3)}
.panel-measure .meter .tape{height:8px}
.panel-measure .meter-read{font:600 1.05rem/1 var(--sans)}
.panel-measure .meter .meter-wide,.panel-measure .meter-none .meter-read{font:500 var(--t-small)/1.3 var(--sans);color:var(--ink-2)}
.panel-measure .tape-mark,.cmp-table .tape-mark{stroke-width:2}
.panel .visual-check{margin:12px 0 8px}
.sources{padding:4px 2px;background:none;box-shadow:none}
.sources>summary{font:600 .95rem/1.4 var(--sans);color:var(--ink-2);cursor:pointer}
.sources>summary:hover{color:var(--ink)}
.sources[open]>summary{margin-bottom:10px}
.block{margin-bottom:48px}
.block>h2{font-size:1.5rem;margin-bottom:14px}
.block h3{margin:24px 0 8px}
.block .run-card h3,.block .run-head h3{margin:0}
/* tool page: a quiet head on the page ground (name, one sentence, the facts and links in a line), then the clip */
.tool-head{padding-top:16px}
.tool-head .head-row{align-items:end;padding-bottom:24px}
.tool-head .crumbs{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px;font:500 .9rem/1.3 var(--sans);color:var(--ink-3)}
.tool-head .crumbs a{color:var(--ink-2);text-decoration:none}
.tool-head .crumbs a:hover{color:var(--ink);text-decoration:underline}
.crumb-sep{color:var(--ink-3)}
.tool-head h1{font-size:clamp(2.1rem,3.4vw,2.9rem)}
.tool-head .lede{font-size:1.1rem;color:var(--ink-2);margin:8px 0 0;max-width:none;text-wrap:pretty}
.tool-facts{display:flex;flex-wrap:wrap;align-items:center;gap:10px 20px;margin-top:14px}
.tool-facts .badges{gap:6px 16px;margin:0}
.tool-head .badge{gap:6px;padding:0;min-height:0;background:none;border-radius:0;font:600 .92rem/1.4 var(--sans)}
.tool-head .badge .i{display:none}
.tool-head .badge .os{width:1.05em;height:1.05em}
.tool-head .badge-pass{color:var(--pass)}
.tool-head .badge-gem,.tool-head .badge-info,.tool-head .badge-quiet{color:var(--ink-2)}
.tool-head button.badge{cursor:pointer;text-decoration:underline dotted;text-decoration-color:var(--line-ctl);text-underline-offset:4px}
.tool-links{display:flex;flex-wrap:wrap;align-items:center;gap:6px 18px;margin:0;padding-left:20px;border-left:1px solid var(--rule)}
.tool-link{font:500 .92rem/1.4 var(--sans);color:var(--ink);text-decoration:underline;text-decoration-color:var(--line-ctl);text-underline-offset:4px}
.tool-link:hover{text-decoration-color:var(--stitch)}
.tool-head .chip-compare{min-height:32px;padding:0 12px;font-size:.85rem}
.tool-head .chip-compare .i{display:none}
.tool-head .fitz{flex:none;margin:0}
@media (max-width:640px){.tool-links{padding-left:0;border-left:0}.tool-head .lede{font-size:1.02rem}}
/* The clip with chapters gets its own row: the player as wide as the clip can be in the first view; right beside it,
   its chapters and then where the clip came from (the column takes what is left, from 280px). */
.tool-clip{padding-top:28px}
.tool-clip .showcase{display:grid;grid-template-columns:auto minmax(280px,1fr);grid-template-rows:auto 1fr;gap:16px 40px;align-items:start;margin:0}
.tool-clip .chap-list,.tool-clip .showcase>figcaption{max-width:440px}
.tool-clip .player{grid-column:1;grid-row:1/span 2}
.tool-clip .chap-list{grid-column:2;grid-row:1}
.tool-clip .showcase>figcaption{grid-column:2;grid-row:2;margin:0}
.tool-clip+.layout{margin-top:48px}
.showcase{margin:0 0 48px}
/* The clip gives up width, never its bar: at any window height the head, the clip and its bar (play, chapters) fit
   in the first view, down to a 280px-tall clip. The player shrinks to the clip, so there are no black bars beside it. */
.showcase video{display:block;width:auto;max-width:100%;height:auto;max-height:max(280px,calc(100svh - 356px));object-fit:contain;background:#000}
.showcase figcaption{margin-top:8px;font-size:var(--t-small);color:var(--ink-3)}
.player{width:fit-content;max-width:100%;border-radius:12px;overflow:hidden;background:#000}
.player:fullscreen{display:flex;flex-direction:column;justify-content:center;width:100%;max-width:none;border-radius:0}
.player:fullscreen video{flex:1;width:100%;min-height:0;max-height:none}
/* The player's own bar is dark in both schemes, as a player is; its fill is Fitz's tape running along the chapters. */
.player-bar{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#0E0F0C;color:#EBEAE2}
.player-bar[hidden]{display:none}
.player-btn{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;padding:0;border:0;border-radius:8px;background:none;color:inherit;cursor:pointer;flex:none}
.player-btn:hover{background:rgb(235 234 226/.12)}
.player-btn .i{width:20px;height:20px}
.player-btn .i+.i,.player-btn.is-playing .i:first-child,.player-btn.is-muted .i:first-child{display:none}
.player-btn.is-playing .i+.i,.player-btn.is-muted .i+.i{display:inline}
.chap-track{position:relative;flex:1;min-width:0;display:flex;gap:3px;align-items:center;height:28px;cursor:pointer;touch-action:none}
/* the track is 4.58:1 on the bar (non-text 3:1) */
.chap-seg{position:relative;flex:1 1 0;min-width:4px;height:6px;border-radius:2px;background:rgb(235 234 226/.5);overflow:hidden;transition:height .12s}
.chap-track:hover .chap-seg,.chap-track:focus-visible .chap-seg{height:10px}
.chap-fill{position:absolute;inset:0;background:var(--tape);transform-origin:left center;transform:scaleX(0)}
.chap-tip{position:absolute;bottom:30px;transform:translateX(-50%);padding:4px 8px;border-radius:6px;background:var(--raised);color:var(--ink);font-size:.8rem;white-space:nowrap;box-shadow:var(--lift-2);pointer-events:none}
.player-time{font-size:.85rem;font-variant-numeric:tabular-nums;white-space:nowrap}
.chap-head{font:600 .85rem/1.2 var(--sans);letter-spacing:0;color:var(--ink-3);margin:0 0 8px}
.chapters{list-style:none;padding:0;margin:0;display:grid;gap:0;border-bottom:1px solid var(--rule)}
.chapters li{border-top:1px solid var(--rule)}
.chapters a{display:flex;gap:14px;align-items:baseline;padding:11px 10px;color:var(--ink-2);text-decoration:none}
.chapters a:hover{color:var(--ink);background:color-mix(in srgb,var(--ink) 5%,transparent)}
.chapters a[aria-current]{color:var(--ink);font-weight:600;background:color-mix(in srgb,var(--ink) 7%,transparent)}
.chap-time{min-width:3em;color:var(--ink-3);font-weight:500;font-variant-numeric:tabular-nums}
.chapters a[aria-current] .chap-time{color:var(--ink-2)}
@media (max-width:1080px){.tool-clip .showcase{grid-template-columns:minmax(0,1fr);grid-template-rows:none;gap:10px}.tool-clip .player,.tool-clip .chap-list,.tool-clip .showcase>figcaption{grid-column:1;grid-row:auto}.tool-clip .chap-list{order:1;margin-top:14px}.tool-clip .showcase>figcaption{order:2}}
@media (max-width:520px){.player-time{display:none}.player-bar{gap:4px;padding:4px 6px}}
/* What it does: each feature a line on the page, its state in words at the end (green when a run ticked it) */
.about .fit{font:500 1.1rem/1.5 var(--sans);letter-spacing:0;color:var(--ink-2);margin:0 0 16px;max-width:62ch}
.feat-list{list-style:none;padding:0;margin:0;display:grid;gap:0;border-bottom:1px solid var(--rule)}
.feat-list>li{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:11px 2px;border-top:1px solid var(--rule)}
.feat-list>li:has(.how-to[open]){align-items:start}
.feat-state{display:inline-flex;align-items:center;gap:6px;font:600 .88rem/1.3 var(--sans);white-space:nowrap}
.feat-state .i{width:15px;height:15px;stroke-width:2.2}
.feat-ok .feat-state{color:var(--pass)}
.feat-open .feat-state{color:var(--ink-3);cursor:help}
.feat-fail .feat-state{color:var(--fail);cursor:help}
.feat-state[data-tip]{text-decoration:underline dotted;text-decoration-color:var(--line-ctl);text-underline-offset:4px}
.feat-state:focus-visible{outline:3px solid var(--stitch);outline-offset:2px}
.feat-state[data-tip]{position:relative}
.feat-state[data-tip]:hover::after,.feat-state[data-tip]:focus::after{content:attr(data-tip);position:absolute;left:auto;right:0;bottom:calc(100% + 6px);z-index:3;padding:6px 9px;border-radius:6px;background:var(--ink);color:var(--paper);font:600 .78rem/1.3 var(--sans);width:max-content;max-width:260px;white-space:normal;pointer-events:none}
.feat-open .feat-title{color:var(--ink-2)}
@media (hover:none){.feat-state[data-tip]{cursor:default}}
.feat-check summary{font-size:var(--t-small);color:var(--pass);font-weight:600}
.feat-check code{display:block;margin-top:6px;padding:8px 10px;border-radius:8px;background:var(--code-bg);color:var(--ink);font-size:.8rem;overflow-x:auto;white-space:pre}
.side a{overflow-wrap:anywhere}
.uses{columns:2;column-gap:32px}.uses li{break-inside:avoid;margin-bottom:6px}
.run-card{background:var(--tag);border-radius:var(--r-card);padding:22px 24px;box-shadow:var(--lift-1);margin-bottom:20px}
.run-video{margin:14px 0 16px}
.run-video video{display:block;width:100%;max-width:720px;height:auto;border-radius:var(--r-ctl);background:#000}
.run-video figcaption{margin-top:8px;font-size:var(--t-small);color:var(--ink-2);max-width:720px}
.run-video .raw ul{list-style:none;padding:0;margin:6px 0 0;display:grid;gap:6px}
.run-video .hash{overflow-wrap:anywhere;word-break:break-all;font-size:.8rem}
/* A web app's "Open it": the address in a quiet frame on the card, the one yellow button at its end */
.run-card .web-bar{background:transparent;box-shadow:inset 0 0 0 1px var(--rule);border-radius:var(--r-ctl)}
.run-card .web-bar .btn{border-radius:var(--r-ctl)}
.run-card .web-facts-grid .i,.run-card .web-facts-grid .yes .i,.run-card .web-facts-grid .no .i{padding:0;background:none}
/* How far pickfit got, Good for and How pickfit tested it: below how to use it, quieter, still open to read */
.tool-more{padding-top:36px;border-top:1px solid var(--rule)}
.tool-more:empty{display:none}
.tool-more .block{margin-bottom:36px}
.tool-more .block>h2{font-size:1.25rem;margin-bottom:12px}
.progress-row{margin-bottom:14px}
.progress-more[hidden]{display:none}
.progress-more{margin:0 0 14px}
.progress-more>summary{display:inline-flex;align-items:center;gap:6px;list-style:none;font:600 var(--t-small)/1.4 var(--sans);color:var(--ink-2)}
.progress-more>summary::-webkit-details-marker{display:none}
.progress-more>summary:hover{color:var(--ink)}
.progress-more>summary .i{order:-1;width:16px;height:16px;transition:transform .25s var(--ease-out)}
.progress-more[open]>summary .i{transform:rotate(180deg)}
.progress-more[open]>summary{margin-bottom:12px}
.progress-sys{display:flex;align-items:center;gap:8px;margin:0 0 8px;font-weight:600}
.progress-sys .arch{font-weight:500;color:var(--ink-3);font-size:.9rem}
.prog-stages{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:6px 10px;max-width:none}
.prog-stage{display:flex;flex-direction:column;gap:8px;font-size:.9rem;text-align:left;margin:0}
.prog-bar{display:block;height:4px;border-radius:2px;background:var(--rule)}
.prog-done .prog-bar{background:var(--pass)}
.prog-warn .prog-bar{background:var(--caution)}
.prog-label{display:flex;align-items:flex-start;gap:6px;color:var(--ink-2)}
.prog-done .prog-label{color:var(--ink)}
.prog-warn .prog-label{color:var(--caution)}
.prog-label .i{display:none}
.feat-title{font-weight:600}
.how-to{margin-top:2px}
.how-to summary{font-size:var(--t-small);color:var(--ink-2);cursor:pointer}
.how-to ol{margin:8px 0 4px;padding-left:20px;font-size:.95rem}
.how-to li{margin-bottom:4px}
.watch{display:inline-block;font-size:var(--t-small);margin-top:4px;color:var(--ink);text-decoration-color:var(--line-ctl)}
.watch:hover{text-decoration-color:var(--stitch)}
.open-hint{display:flex;gap:8px;align-items:flex-start;margin:14px 0 0}
.open-hint .i{flex:none;margin-top:3px;color:var(--pass)}
.prereq{margin-bottom:16px}
.prereq h4{margin-top:0}
.tested>summary{display:flex;align-items:center;justify-content:flex-start;gap:10px;cursor:pointer;list-style:none}
.tested>summary::-webkit-details-marker{display:none}
.tested>summary h2{font-size:1.25rem;margin:0}
.tested>summary .i{order:-1;color:var(--ink-2);transition:transform .25s var(--ease-out)}
.tested[open]>summary .i{transform:rotate(180deg)}
.tested-run{padding:16px 0;border-top:1px solid var(--rule)}
.tested-run h3{display:flex;align-items:center;gap:8px;margin:0 0 8px}
.raw-list{list-style:none;padding:0;display:grid;gap:6px}
.raw-list .hash,.tested .hash{overflow-wrap:anywhere;word-break:break-all;font-size:.8rem}
.run-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;align-items:center}
.run-head h3{display:flex;align-items:center;gap:10px;font-size:1.25rem}
.run-head .arch{font:500 .9rem/1 var(--sans);color:var(--ink-2)}
.empty{display:flex;align-items:center;gap:20px;padding:24px;border-radius:var(--r-card);background:var(--tag);box-shadow:var(--lift-1)}
.empty .fitz{flex:none}
.empty p{margin:0}
.empty h2{font-size:var(--t-head);margin-bottom:6px}
/* compare: the same grammar as the rest: plain-text facts, quiet readings, pills only for the system switch */
.cmp-pick{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:20px}
.cmp-pick input[list],.cmp-pick input[type=text]{min-height:44px;padding:0 14px;border:0;border-radius:var(--r-ctl);background:var(--tag);color:var(--ink);font:500 1rem var(--sans);min-width:min(320px,100%);box-shadow:inset 0 0 0 1px var(--line-ctl)}
.cmp-pick input::placeholder{color:var(--ink-3)}
.cmp-table thead th,.cmp-table thead td{background:var(--tag)}
.cmp-table th[scope=col]{min-width:200px}
.cmp-table th[scope=col] a{font:700 1.1rem/1.2 var(--display);color:var(--ink);text-decoration:none}
.cmp-table th[scope=col] a:hover{text-decoration:underline}
.cmp-table th[scope=col] .small{margin-top:2px;font-weight:500;color:var(--ink-3)}
.cmp-table .kind .i,.cmp-table .yes .i,.cmp-table .no .i,.cmp-table .cmp-level .i,.cmp-table .badge .i,.best .i{display:none}
.cmp-table .badge{padding:0;background:none;border-radius:0;font:500 .85rem/1.4 var(--sans);color:var(--ink-3)}
.cmp-table tbody th{font:500 .88rem/1.3 var(--sans);color:var(--ink-2)}
.cmp-table .grp th{background:none;padding:22px 16px 8px;font:600 .8rem/1.2 var(--sans);letter-spacing:0;color:var(--ink-2)}
.best{font:600 .78rem/1 var(--sans)}
.cmp-table .meter{min-width:170px}
.cmp-table .meter .tape{height:8px}
.cmp-table .meter-read{font:600 1.05rem/1 var(--sans)}
.cmp-table .meter .meter-wide,.cmp-table .meter-none .meter-read{font:500 var(--t-small)/1.3 var(--sans);color:var(--ink-2)}
.cmp-table .meter-label{display:none}
.cmp-table th[scope=col] a.cmp-remove{color:var(--ink-2)}
.cmp-table th[scope=col] a.cmp-remove .i{width:16px;height:16px}
.cmp-links{display:inline-flex;gap:8px}
.icon-link{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:8px;background:transparent;box-shadow:inset 0 0 0 1px var(--line-ctl);color:var(--ink)}
.icon-link:hover{background:color-mix(in srgb,var(--ink) 6%,transparent)}
.icon-link .i{width:17px;height:17px}
body.has-tray{padding-bottom:72px}
/* Remove sits in the column head's top-right corner (the sticky head anchors it); the name keeps clear of it. */
.cmp-remove{position:absolute;top:8px;right:8px;display:grid;place-items:center;width:28px;height:28px;border-radius:50%;color:var(--ink-2)}
.cmp-table th[scope=col]:has(.cmp-remove){padding-right:44px}
.cmp-remove[data-tip]:hover::after{bottom:auto;top:calc(100% + 4px);left:auto;right:0}
.cmp-remove:hover{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink)}
.cmp-table thead td{position:sticky;top:0}
.cmp-table .same td{color:var(--ink-2)}
.same-tag{display:inline-block;margin-left:10px;color:var(--ink-3);font:500 .8rem/1.5 var(--sans)}
.yes{color:var(--pass);font-weight:600}.no{color:var(--caution);font-weight:600}
.yes .i,.no .i{margin-right:6px;vertical-align:-.2em}
.run-line{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:2px}
.run-line .i{width:13px;height:13px}

/* browse */
.sec-tight{padding-top:40px}
.layout-browse{grid-template-columns:250px minmax(0,1fr)}
.side-left{top:20px}
/* The filters are switches, so pills; their names are words, no marks */
.filters{display:grid;gap:22px}
.filters fieldset{border:0;padding:0;margin:0;display:grid;gap:8px}
.filters legend{font:600 .85rem/1 var(--sans);color:var(--ink-3);margin-bottom:10px;padding:0}
.filters .chips{display:flex;flex-wrap:wrap;gap:6px}
.filters .chip{min-height:34px;padding:0 12px;font-size:.86rem}
.find-in{display:flex;align-items:center;gap:8px;min-height:44px;padding:0 14px;border-radius:var(--r-ctl);background:var(--tag);box-shadow:inset 0 0 0 1px var(--line-ctl)}
.find-in .i{color:var(--ink-3)}
.find-in input{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font:500 1rem var(--sans)}
.find-in input::placeholder{color:var(--ink-3)}
.find-in input:focus{outline:none}
.find-in:focus-within{outline:3px solid var(--stitch);outline-offset:2px}
/* A card answers three things: what it is, where pickfit ran it (three stitches and the green OS marks), and whether it costs money */
.cat-grid{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.cat-card{position:relative;display:flex;flex-direction:column;gap:6px;padding:18px 20px 14px;background:var(--tag);border-radius:var(--r-card);box-shadow:var(--lift-1);transition:box-shadow .2s}
.cat-card:hover{box-shadow:var(--lift-1),0 0 0 1px var(--line-ctl)}
.cat-card h3{font-size:1.1rem}
.cat-card h3 a{text-decoration:none}
.cat-card h3 a::after{content:"";position:absolute;inset:0;border-radius:var(--r-card)}
.cat-card p{margin:0;color:var(--ink-2);font-size:.92rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cat-card p.small{color:var(--ink-3);font-size:.86rem;margin-bottom:4px}
.cat-card .kind .i{display:none}
.cat-card .row{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin-top:auto;padding-top:4px;min-height:32px}
.cat-card .row .badge{position:relative;z-index:1;padding:0;background:none;border-radius:0;font:600 .85rem/1.3 var(--sans)}
.cat-card .badge-pass{color:var(--pass)}
.cat-card .badge-gem{color:var(--ink-3)}
/* The gem is the badge's only content (its name is the tooltip and the label); a little larger than a text icon. */
.cat-card .badge-gem .i{width:17px;height:17px;stroke-width:1.75}
.cat-card .badge-free{color:var(--ink-2)}
.cat-card .badge-quiet{color:var(--ink-3);font-weight:500}
.cat-card .badge-quiet .i{display:none}
/* Compare: an icon-only switch at the row's end, shown on hover or keyboard focus (always on touch, and once ticked) */
.cat-card .chip-compare{position:relative;z-index:1;margin-left:auto;width:32px;min-height:32px;padding:0;justify-content:center;border-radius:8px;opacity:0;transition:opacity .15s}
.cat-card .chip-compare span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.cat-card:hover .chip-compare,.cat-card:focus-within .chip-compare,.cat-card .chip-compare:has(input:checked){opacity:1}
@media (hover:none){.cat-card .chip-compare{opacity:1}}
/* Ticked, the icon-only button shows the check in place of its mark. */
.cat-card .chip-compare:has(input:checked) .i{display:none}
.cat-card .chip-compare::before{margin:0}
@media (hover:hover){.cat-card .chip-compare:hover::after{content:"Compare";left:auto;right:0}}
.cat-card .seam{width:31px;margin:8px 0 0;animation:none}
.cat-card.unverified{background:transparent;box-shadow:none;border:2px dashed var(--rule)}
.cat-count{color:var(--ink-3);margin:0 0 16px}
.js .cat-card.later{display:none}.js .filtering .cat-card.later{display:flex}
.more-filters>summary{font:600 .9rem/1 var(--sans);color:var(--ink-2);padding:6px 0;cursor:pointer}
.more-filters>summary:hover{color:var(--ink)}
.more-filters[open]>summary{margin-bottom:14px}
.more-filters{display:grid;gap:18px}
.pager{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:32px}
/* how + agents (reading pages) */
.prose{max-width:72ch}
.prose h2{margin:56px 0 14px}
.prose h3{margin:28px 0 8px}
.prose li{margin-bottom:6px}
.levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;list-style:none;padding:0;margin:20px 0}
.levels li{background:var(--tag);border-radius:var(--r-card);padding:16px 18px;box-shadow:var(--lift-1)}
.levels b{display:flex;align-items:center;gap:8px;font:700 1.05rem/1.3 var(--display);margin-bottom:6px}
.tip{position:relative;margin:56px 0 24px;padding:22px 24px 20px;border-radius:var(--r-card);background:var(--tag);box-shadow:var(--lift-1)}
.tip .fitz-peek{position:absolute;top:-52px;right:28px;width:94px;height:auto}
.tip h3{margin-bottom:6px}
.nf{display:grid;place-items:center;text-align:center;gap:16px;padding:48px 0}
`;

const MOTION = `
@keyframes rise{from{transform:translateY(14px)}to{transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes hop-in{0%{transform:translateY(28px) scale(.97)}60%{transform:translateY(-6px) scale(1.01)}100%{transform:none}}
@keyframes unroll{from{clip-path:inset(0 92% 0 0)}to{clip-path:inset(0 2% 0 0)}}
@keyframes shimmer{from{background-position:100% 0}to{background-position:-50% 0}}
@keyframes pop-in{from{opacity:.4;transform:translateY(6px) scale(.98)}to{opacity:1;transform:none}}
@keyframes tray-in{from{transform:translateY(100%)}to{transform:none}}
@keyframes toast{0%{opacity:0;transform:translateY(10px)}12%,82%{opacity:1;transform:none}100%{opacity:0}}
@keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
::view-transition-old(root),::view-transition-new(root){animation-duration:.35s;animation-timing-function:var(--ease-out)}
@media (prefers-reduced-motion:reduce){
*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}
::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important}
.unroll::after{clip-path:inset(0 40% 0 0)}}
`;

const RESPONSIVE = `
/* home hero, mid widths: Fitz beside the headline, the form, examples and proof line across the full row so each stays one row */
@media (min-width:901px) and (max-width:1240px){
body:not(.is-results) .hero-grid{grid-template-columns:minmax(0,1fr) auto;grid-template-rows:1fr;gap:0 32px}
body:not(.is-results) .hero-main{display:contents}
body:not(.is-results) .hero-main>*{grid-column:1/-1}
body:not(.is-results) .hero h1,body:not(.is-results) .hero .lede{grid-column:1}
body:not(.is-results) .hero h1{align-self:end}
body:not(.is-results) .hero-fitz{grid-column:2;grid-row:1/3;align-self:end;margin:0 0 20px;translate:none}
body:not(.is-results) .hero-fitz .fitz{width:clamp(150px,16vw,220px)}
}
@media (max-width:1080px){
.stages{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:none;gap:32px 20px}
.stages::before{display:none}
.stage{display:flex;flex-direction:column;align-items:center;grid-row:auto;gap:6px}
.layout,.layout-browse{grid-template-columns:minmax(0,1fr)}
.side{position:static;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));align-items:start}
}
@media (max-width:900px){
.nav{display:none}.menu{display:block}
.lang-switch{padding-left:0;border-left:0}
.hero-grid{grid-template-columns:minmax(0,1fr)}
.hero-fitz{order:-1;justify-self:start;margin:0;translate:none}
.hero-fitz .fitz{width:150px}
body.is-results .hero-fitz{display:none}
.t-body,.record{grid-template-columns:minmax(0,1fr)}
.record .mine{grid-column:1;grid-row:auto}
.t-top{grid-template-columns:minmax(0,1fr)}
.t-top .badges{justify-content:flex-start;max-width:none}
.fresh,.care,.nofit,.best-free{grid-template-columns:minmax(0,1fr)}
.agents-band{grid-template-columns:minmax(0,1fr)}
.foot-row{grid-template-columns:minmax(0,1fr)}
.res-head{grid-template-columns:minmax(0,1fr)}.res-tools{justify-content:flex-start}
.head-row{grid-template-columns:minmax(0,1fr)}
.head .fitz{display:none}
}
@media (max-width:640px){
.wrap{padding-left:16px;padding-right:16px}
/* Stacked, the request is the full width of the card and grows to show the whole sentence (flex:none lets the script's height apply). */
.ask{flex-direction:column;align-items:stretch;gap:10px}
.ask label{font-size:1.1rem}
.ask textarea{flex:none;width:100%;font-size:1.2rem;padding-top:2px;min-height:2.6em}
.ask-meta{display:grid;grid-template-columns:minmax(0,1fr)}.ask-go{align-items:stretch;margin-left:0}
.ask-meta .btn-primary{width:100%}
.seg{width:100%;justify-content:space-between}.seg label{flex:1;justify-content:center;padding:0 8px}
.stages{gap:28px 12px}
.stage-fitz{height:100px}.stage-fitz .fitz{height:90px}
.stage h3{font-size:1.1rem}.stage>p{font-size:.9rem}
.pick,.picks .pick:first-child{padding:22px 18px 18px}
.picks .pick:first-child .fit{font-size:1.1rem}
.t-install .cmd pre{font-size:.85rem;padding:12px 12px 12px calc(12px + 2ch)}
.res-head .says{align-items:flex-start;gap:8px}
.res-head .fitz{width:72px}
.t-name{font-size:1.35rem}
.glance{grid-template-columns:1fr 1fr}
.gl{padding:11px 12px}
.gl-value{font-size:.88rem}
.legend div{grid-template-columns:minmax(0,1fr);gap:4px}
.uses{columns:1}
.says{flex-direction:column;align-items:flex-start}
.bubble::before,.bubble::after{display:none}
.notice{flex-direction:column;align-items:flex-start}
.tray-list{display:none}
.tray-note{flex:1}
.toasts{bottom:96px}
.label-tag{transform:none;padding:26px 22px}
.readme-vs li{grid-template-columns:minmax(0,1fr);gap:2px}
.dt th,.dt td{padding:10px 12px}
.cmp-table th[scope=col]{min-width:150px}
.dt tbody th{white-space:normal;min-width:84px}
.cmp-pick input[type=text],.cmp-pick input[list],.cmp-pick .combo{min-width:0;flex:1}
.hero-fitz .fitz{width:96px}
.hero{padding-top:16px}
}
`;

export const CSS = TOKENS + BASE + COMPONENTS + RESULTS + PAGES + MOTION + RESPONSIVE;

/**
 * Added after CSS on the zh-TW pages only (shell.ts), so the English page is untouched. Chinese needs
 * more leading, no negative tracking (it crowds the glyphs), no breaks inside short labels, and wraps
 * that avoid a lone character on the last line; a line that opens with 「 drops its half-width blank.
 */
export const CSS_ZH = `
body{line-height:1.7;line-break:strict}
h1,h2,h3,h4{letter-spacing:0;text-spacing-trim:trim-start;font-synthesis-weight:none}
h1{letter-spacing:0;line-height:1.18}
.hero .lede{max-width:none}
h2{line-height:1.3}
p,li,dd,summary,.lede,.st span{text-wrap:pretty}
.gl-value{text-wrap:balance}
.ask label,.ask textarea,.fit{letter-spacing:0}
.fit{line-height:1.5}
.nav a,.menu-nav a,.seg label,.chip,.btn,.res-tools .btn,.tries a,.proof li{white-space:nowrap}
.stage>p{max-width:15em;text-wrap:balance}
.record-title{letter-spacing:.02em}
@media (hover:hover){.cat-card .chip-compare:hover::after{content:"比較"}}
/* the taller Chinese head: the clip gives up the difference, so its bar stays in the first view */
.showcase video{max-height:max(280px,calc(100svh - 372px))}
`;
