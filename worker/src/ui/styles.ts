/**
 * The stylesheet, in the order DESIGN.md lays the system out: tokens, base,
 * components, then page layouts. One string, sent inline under the CSP nonce.
 */

const TOKENS = `
@font-face{font-family:"Bricolage Grotesque";src:url(/assets/fonts/bricolage-grotesque.woff2) format("woff2");font-weight:400 800;font-display:swap}
:root{
--mat:#1D3D2A;--mat-deep:#132A1C;--mat-line:rgb(244 241 222/.055);--mat-line-2:rgb(244 241 222/.11);--on-mat:#F4F1DE;--on-mat-2:#C9D3B4;
--paper:#F4F5EC;--sunk:#E9ECDD;--tag:#FFFEF7;--ink:#17231A;--ink-2:#4B584E;--rule:#D5DAC6;
--tape:#F5C243;--tape-deep:#D9A21B;--tape-ink:#3A2905;--stitch:#C4552D;--fitz-ink:#4A2E22;
--pass:#2E7A35;--caution:#8A5300;--fail:#B23A26;--info:#28698A;
--pass-soft:color-mix(in srgb,var(--pass) 14%,var(--tag));--caution-soft:color-mix(in srgb,#E09A1E 18%,var(--tag));
--fail-soft:color-mix(in srgb,var(--fail) 12%,var(--tag));--info-soft:color-mix(in srgb,var(--info) 12%,var(--tag));
--code:#16231A;--code-ink:#E7EEDC;
--lift-1:0 1px 2px rgb(23 40 28/.06),0 6px 18px -10px rgb(23 40 28/.28);
--lift-2:0 2px 4px rgb(23 40 28/.08),0 18px 36px -16px rgb(23 40 28/.36);
--lift-3:0 4px 10px rgb(10 25 15/.14),0 30px 60px -20px rgb(10 25 15/.5);
--r-card:14px;--r-ctl:10px;
--display:"Bricolage Grotesque",ui-sans-serif,system-ui,sans-serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
--t-display:clamp(2.5rem,5.2vw,4.4rem);--t-title:clamp(1.6rem,2.6vw,2.2rem);--t-head:1.25rem;--t-lead:1.15rem;--t-small:.875rem;
--ease-out:cubic-bezier(.16,1,.3,1);--ease-io:cubic-bezier(.65,0,.35,1);
--gap:clamp(64px,9vw,128px)}
@media (prefers-color-scheme:dark){:root{
--mat:#16301F;--mat-deep:#0E2015;--paper:#101A13;--sunk:#0B140E;--tag:#18241B;--ink:#ECEFE3;--ink-2:#B4BEB0;--rule:#2A382D;
--stitch:#E07A4F;--pass:#7CCB7A;--caution:#F0B45A;--fail:#F08A73;--info:#86C4E6;
--pass-soft:color-mix(in srgb,var(--pass) 16%,var(--tag));--caution-soft:color-mix(in srgb,var(--caution) 16%,var(--tag));
--fail-soft:color-mix(in srgb,var(--fail) 16%,var(--tag));--info-soft:color-mix(in srgb,var(--info) 14%,var(--tag));
--code:#0A120C;--lift-1:0 1px 2px rgb(0 0 0/.3),0 6px 18px -10px rgb(0 0 0/.6);--lift-2:0 2px 4px rgb(0 0 0/.3),0 18px 36px -16px rgb(0 0 0/.7)}}
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
h1{font-size:var(--t-display);font-weight:800;letter-spacing:-.03em;line-height:1.02;font-variation-settings:"opsz" 96}
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
/* mat: the cutting mat. Its grid is a measuring surface, so it may carry one. */
.mat{background-color:var(--mat);color:var(--on-mat);
background-image:linear-gradient(var(--mat-line-2) 1px,transparent 1px),linear-gradient(90deg,var(--mat-line-2) 1px,transparent 1px),
linear-gradient(var(--mat-line) 1px,transparent 1px),linear-gradient(90deg,var(--mat-line) 1px,transparent 1px);
background-size:160px 160px,160px 160px,32px 32px,32px 32px;background-position:-1px -1px}
.mat a:not(.btn-primary){color:var(--on-mat)}
.mat .quiet,.mat .on-mat-2{color:var(--on-mat-2)}
.ruler{height:22px;background:
repeating-linear-gradient(90deg,var(--mat-line-2) 0 1px,transparent 1px 8px) bottom/100% 7px no-repeat,
repeating-linear-gradient(90deg,var(--on-mat-2) 0 1.5px,transparent 1.5px 40px) bottom/100% 14px no-repeat}

/* header */
.top{position:relative;z-index:5}
.top-row{display:flex;align-items:center;justify-content:space-between;gap:16px;height:72px}
/* The band under the header continues the header's mat: its grid starts 72px further down. */
.mat.after-top{background-position:-1px -73px}
.brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font:800 1.45rem/1 var(--display);letter-spacing:-.03em}
.brand img{width:32px;height:32px}
.i-dot{position:relative}
.i-dot::after{content:"";position:absolute;left:50%;top:.02em;width:.26em;height:.26em;border-radius:50%;background:var(--stitch);transform:translateX(-50%);box-shadow:0 0 0 .07em var(--mat)}
.foot .i-dot::after{box-shadow:0 0 0 .07em var(--mat-deep)}
.nav{display:flex;gap:4px}
.nav a,.menu-nav a{display:inline-flex;align-items:center;gap:6px;text-decoration:none;padding:8px 12px;border-radius:999px;font:600 .95rem/1 var(--display);color:var(--on-mat-2);transition:background .2s,color .2s}
.nav a:hover,.menu-nav a:hover{color:var(--on-mat);background:rgb(244 241 222/.08)}
.nav a[aria-current=page],.menu-nav a[aria-current=page]{color:var(--on-mat);background:rgb(244 241 222/.14)}
.count{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:var(--tape);color:var(--tape-ink);font:700 .75rem/20px var(--display);text-align:center}
.menu{display:none;position:relative}
.menu summary{list-style:none;cursor:pointer;padding:10px;border-radius:var(--r-ctl);color:var(--on-mat)}
.menu summary::-webkit-details-marker{display:none}
.menu-nav{position:absolute;right:0;top:calc(100% + 6px);display:flex;flex-direction:column;min-width:220px;padding:8px;background:var(--mat-deep);border-radius:var(--r-card);box-shadow:var(--lift-3)}
.menu-nav a{padding:12px 14px;border-radius:var(--r-ctl)}

/* buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 20px;border:0;border-radius:var(--r-ctl);
font:700 1rem/1 var(--display);letter-spacing:-.01em;text-decoration:none;cursor:pointer;white-space:nowrap;
transition:transform .12s var(--ease-out),box-shadow .2s var(--ease-out),background-color .2s}
.btn:hover{text-decoration:none}
.btn:active{transform:translateY(1px)}
.btn[disabled],.btn[aria-disabled=true]{opacity:.55;cursor:not-allowed;transform:none}
.btn-primary{background:var(--tape);color:var(--tape-ink);box-shadow:0 1px 0 var(--tape-deep),0 6px 14px -8px rgb(120 80 0/.6)}
.btn-primary:hover{background:color-mix(in srgb,var(--tape) 88%,#fff);box-shadow:0 1px 0 var(--tape-deep),0 10px 20px -10px rgb(120 80 0/.7)}
.btn-quiet{background:var(--tag);color:var(--ink);box-shadow:var(--lift-1)}
.btn-quiet:hover{box-shadow:var(--lift-2)}
.btn-ghost{background:transparent;color:inherit}
.btn-ghost:hover{background:color-mix(in srgb,currentColor 8%,transparent)}
.btn-on-mat{background:rgb(244 241 222/.1);color:var(--on-mat)}
.btn-on-mat:hover{background:rgb(244 241 222/.18)}
.btn-sm{min-height:36px;padding:0 14px;font-size:.9rem}
.btn-icon{padding:0;width:44px}
.btn[aria-busy=true]{cursor:progress}
.btn[aria-busy=true] .btn-label::after{content:"";display:inline-block;width:1.2em;text-align:left;animation:dots 1.2s steps(4) infinite}

/* chips, segmented control, selects */
.chip{position:relative;display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 14px;border-radius:999px;cursor:pointer;
font:600 .9rem/1 var(--display);background:var(--sunk);color:var(--ink);transition:background .2s,color .2s,box-shadow .2s;user-select:none}
.chip input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.chip:hover{background:color-mix(in srgb,var(--ink) 10%,var(--sunk))}
.chip:has(input:checked){background:var(--ink);color:var(--paper)}
.chip:has(input:focus-visible){outline:3px solid var(--stitch);outline-offset:2px}
.chip .i,.chip .os{width:1em;height:1em}
a.chip{text-decoration:none}
.chip.on{background:var(--ink);color:var(--paper)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip-tick{display:none}.chip:has(input:checked) .chip-tick{display:inline}
.seg{display:inline-flex;padding:4px;gap:2px;border-radius:999px;background:var(--sunk)}
.seg label{position:relative;display:inline-flex;align-items:center;min-height:34px;padding:0 14px;border-radius:999px;cursor:pointer;font:600 .9rem/1 var(--display);color:var(--ink-2);transition:background .2s,color .2s}
.seg input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.seg label:has(input:checked){background:var(--tag);color:var(--ink);box-shadow:var(--lift-1)}
.seg label:has(input:focus-visible){outline:3px solid var(--stitch);outline-offset:1px}
.select{appearance:none;font:600 .9rem/1 var(--display);color:var(--ink);background:var(--sunk) no-repeat right 12px center/14px;min-height:40px;padding:0 34px 0 14px;border:0;border-radius:999px;cursor:pointer;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234B584E' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")}
.select:hover{background-color:color-mix(in srgb,var(--ink) 10%,var(--sunk))}

/* badges */
.badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:0;border-radius:999px;font:700 .8rem/1.1 var(--display);letter-spacing:0;white-space:nowrap}
button.badge{cursor:help}
.badge .i{width:.95em;height:.95em;stroke-width:2.2}
.badge-pass{background:var(--pass-soft);color:var(--pass)}
.badge-gem{background:var(--tape);color:var(--tape-ink)}
.badge-free{background:var(--info-soft);color:var(--info)}
.badge-caution{background:var(--caution-soft);color:var(--caution)}
.badge-fail{background:var(--fail-soft);color:var(--fail)}
.badge-info{background:var(--info-soft);color:var(--info)}
.badge-quiet{background:var(--sunk);color:var(--ink-2)}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:0}
.badge-short{gap:6px;padding:5px 8px}
.os{width:1.05em;height:1.05em;flex:none;fill:currentColor}
/* marks for facts every card repeats: kind, OSes, a system, a run */
.kind,.sys,.oses{display:inline-flex;align-items:center;gap:5px;vertical-align:-.15em}
.kind .i{width:1.05em;height:1.05em}
.oses{gap:6px}.oses .os{width:1.1em;height:1.1em}
.oses-pass{color:var(--pass)}.oses-caution{color:var(--caution)}.oses-quiet{color:var(--ink-2)}
.run-facts{list-style:none;display:flex;flex-wrap:wrap;gap:6px 18px;padding:0;margin:2px 0 10px;font-size:.9rem;color:var(--ink-2);max-width:none}
.rf{display:inline-flex;align-items:center;gap:6px}
.rf .i,.rf .os{width:15px;height:15px}
.rf-yes{color:var(--pass);font-weight:600}.rf-no{color:var(--caution);font-weight:600}
.sprite{position:absolute;overflow:hidden}
@media (hover:hover){
[data-tip]{position:relative}
[data-tip]:hover::after{content:attr(data-tip)}
[data-tip]:hover::after,.cat-card .chip-compare:hover::after{position:absolute;left:0;bottom:calc(100% + 6px);z-index:3;padding:6px 9px;border-radius:6px;background:var(--ink);color:var(--paper);font:600 .78rem/1.3 var(--sans);width:max-content;max-width:220px;pointer-events:none}
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
.tape-fill{fill:var(--tape)}
.meter-quiet .tape-fill{fill:color-mix(in srgb,var(--ink) 28%,var(--sunk))}
.tape-ticks{stroke:color-mix(in srgb,var(--tape-ink) 55%,transparent);stroke-width:1.2;vector-effect:non-scaling-stroke}
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
.bubble{position:relative;background:var(--tag);color:var(--ink);border:2px solid var(--fitz-ink);border-radius:18px 18px 18px 6px;padding:14px 18px;box-shadow:var(--lift-1);margin-bottom:18px;max-width:62ch}
/* The tail: an outline triangle, and a fill triangle inset 2px from its outer edges that also covers the bubble's border where they meet */
.bubble::before,.bubble::after{content:"";position:absolute;left:-18px;bottom:4px;width:20px;height:20px}
.bubble::before{background:var(--fitz-ink);clip-path:polygon(18px 2.2px,18px 15.6px,0 20px)}
.bubble::after{background:var(--tag);clip-path:polygon(20px 3px,20px 12.9px,6.1px 16.2px)}
.bubble p:last-child{margin-bottom:0}
.bubble h2,.bubble h3{margin-bottom:4px}
@media (prefers-color-scheme:dark){.bubble{border-color:var(--on-mat-2)}.bubble::before{background:var(--on-mat-2)}}

/* seam: stitching on verified evidence */
.seam{height:2px;margin:20px 0;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.seam-sample{display:inline-block;width:34px;height:2px;vertical-align:middle;margin-right:8px;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.tape-sample,.cov-sample{display:inline-block;width:34px;height:10px;border-radius:2px;vertical-align:middle;margin-right:8px;background:var(--tape)}
.cov-sample{background:linear-gradient(90deg,var(--pass) 0 50%,var(--fail) 50% 62%,color-mix(in srgb,var(--ink) 18%,var(--sunk)) 62%)}

/* commands */
.cmd{display:flex;align-items:flex-start;background:var(--code);color:var(--code-ink);border-radius:var(--r-ctl);margin:6px 0 10px;min-width:0}
.cmd pre{flex:1;min-width:0;margin:0;padding:12px 14px;overflow-x:auto;line-height:1.55;white-space:pre;scrollbar-color:rgb(231 238 220/.3) transparent}
.copy{display:none;align-items:center;gap:6px;flex:none;font:600 .8rem/1 var(--display);color:var(--code-ink);background:rgb(231 238 220/.12);border:0;border-radius:8px;padding:7px 10px;margin:6px 6px 0 0;cursor:pointer;transition:background .2s,color .2s}
.js .copy{display:inline-flex}
.copy:hover{background:var(--tape);color:var(--tape-ink)}
.copy.done{background:var(--pass);color:#fff}

/* notices */
.notice{display:flex;align-items:center;gap:18px;border-radius:var(--r-card);padding:18px 22px;margin:28px 0;background:var(--tag);box-shadow:var(--lift-1)}
.notice h2{font-size:var(--t-head);margin-bottom:4px}
.notice p{margin:0}
.notice.busy{background:var(--caution-soft)}
.notice.busy h2{color:var(--caution)}
.notice.error{background:var(--fail-soft)}
.notice.error h2{color:var(--fail)}
.notice .fitz{flex:none}

/* popovers and the legend dialog */
.pop{margin:0;inset:auto;position:fixed;width:min(340px,calc(100vw - 32px));padding:16px 40px 14px 16px;border:0;border-radius:var(--r-card);background:var(--tag);color:var(--ink);box-shadow:var(--lift-3);font-size:var(--t-small)}
.pop:popover-open{animation:pop-in .2s var(--ease-out)}
.pop p{margin:0 0 8px}.pop p:last-child{margin:0}
.pop-title{font:700 1rem/1.2 var(--display)}
.pop-close{position:absolute;top:8px;right:8px;display:grid;place-items:center;width:30px;height:30px;border:0;border-radius:8px;background:transparent;color:var(--ink-2);cursor:pointer}
.pop-close:hover{background:var(--sunk)}
.help{display:inline-grid;place-items:center;width:24px;height:24px;margin:-4px 0;padding:0;border:0;border-radius:50%;background:transparent;color:var(--ink-2);cursor:help}
.help:hover{background:var(--sunk);color:var(--ink)}
.help .i{width:16px;height:16px}
.sheet{width:min(640px,calc(100vw - 32px));max-height:calc(100dvh - 48px);padding:28px;border:0;border-radius:20px;background:var(--tag);color:var(--ink);box-shadow:var(--lift-3)}
.sheet::backdrop{background:rgb(10 22 14/.55);backdrop-filter:blur(2px)}
.sheet[open]{animation:pop-in .25s var(--ease-out)}
.sheet-close{position:absolute;top:12px;right:12px;margin:0}
.sheet-head{display:flex;align-items:center;gap:14px;margin-bottom:18px}
.legend{margin:0;display:grid;gap:14px}
.legend div{display:grid;grid-template-columns:200px minmax(0,1fr);gap:16px;align-items:start}
.legend dt{font:600 .95rem/1.3 var(--display)}
.legend dd{margin:0;color:var(--ink-2);font-size:.95rem}
.legend dt:has(.mark-sample){display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.mark-sample{display:inline-flex;align-items:center;gap:6px;color:var(--ink-2)}
.mark-sample.rf .i{width:18px;height:18px}
.mark-sample .oses .os{width:18px;height:18px}

/* compare tray and toasts */
.tray{position:fixed;left:0;right:0;bottom:0;z-index:20;padding:10px 0;background:var(--mat-deep);color:var(--on-mat);box-shadow:0 -12px 30px -18px rgb(0 0 0/.6);animation:tray-in .35s var(--ease-out)}
.tray[hidden]{display:none}
.tray-row{display:flex;align-items:center;gap:12px}
.tray-list{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0;margin:0;flex:1;min-width:0}
.tray-list li{display:inline-flex;align-items:center;gap:4px;padding:4px 6px 4px 12px;border-radius:999px;background:rgb(244 241 222/.12);font:600 .85rem/1 var(--display)}
.tray-list button{display:grid;place-items:center;width:24px;height:24px;border:0;border-radius:50%;background:transparent;color:var(--on-mat-2);cursor:pointer}
.tray-list button:hover{background:rgb(244 241 222/.16);color:var(--on-mat)}
.tray-note{font-size:var(--t-small);color:var(--on-mat-2)}
.tray .btn-ghost{color:var(--on-mat-2)}
.toasts{position:fixed;left:50%;bottom:84px;z-index:40;display:flex;flex-direction:column;align-items:center;gap:8px;transform:translateX(-50%);pointer-events:none}
.toast{padding:10px 16px;border-radius:999px;background:var(--ink);color:var(--paper);font:600 .9rem/1.2 var(--display);box-shadow:var(--lift-2);animation:toast 2.4s var(--ease-out) both}

/* skeleton */
.skel{border-radius:var(--r-card);background:var(--tag);box-shadow:var(--lift-1);padding:22px;display:grid;gap:12px}
.skel i{display:block;height:12px;border-radius:6px;background:linear-gradient(90deg,var(--sunk) 0 40%,color-mix(in srgb,var(--sunk) 40%,var(--tag)) 50%,var(--sunk) 60%) 0 0/300% 100%;animation:shimmer 1.6s linear infinite}
.skel i:nth-child(1){width:38%;height:20px}.skel i:nth-child(2){width:86%}.skel i:nth-child(3){width:72%}.skel i:nth-child(4){width:54%}

/* fact sheets */
.facts-dl{margin:0;display:grid;gap:0}
.facts-dl div{display:grid;grid-template-columns:minmax(110px,40%) minmax(0,1fr);gap:12px;padding:9px 0;border-bottom:1px solid var(--rule)}
.facts-dl div:last-child{border-bottom:0}
.facts-dl dt{color:var(--ink-2);font-size:var(--t-small)}
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
.sec-head p{margin:10px 0 0;color:var(--ink-2);font-size:var(--t-lead)}
.more{display:inline-flex;align-items:center;gap:6px;font:700 1rem/1 var(--display);text-decoration:none;white-space:nowrap}
.more:hover .i{transform:translateX(3px)}
.more .i{transition:transform .2s var(--ease-out)}

/* page head band (every page but home): mat, Fitz, title */
.head{padding:28px 0 0;position:relative;overflow:hidden}
.head-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:24px;padding-bottom:28px}
.head h1{font-size:clamp(2.1rem,4.2vw,3.4rem)}
.head .lede{font-size:var(--t-lead);color:var(--on-mat-2);margin:12px 0 0;max-width:60ch}
.head .fitz{margin-bottom:-6px}
.head .badges{margin-top:14px}
.crumbs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 14px;font:600 .9rem/1 var(--display);color:var(--on-mat-2)}
.crumbs a{color:var(--on-mat-2);text-decoration:none}.crumbs a:hover{color:var(--on-mat);text-decoration:underline}
.crumbs .i{width:14px;height:14px}

/* footer */
.foot{margin-top:var(--gap);background-color:var(--mat-deep);padding-top:64px}
.foot-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr);gap:40px}
.foot-brand p{color:var(--on-mat-2);margin-top:14px;max-width:40ch}
.foot-links{display:flex;flex-direction:column;gap:10px}
.foot-links a{color:var(--on-mat);text-decoration:none}
.foot-links a:hover{text-decoration:underline;text-decoration-color:var(--tape)}
.foot-h{font:700 .85rem/1 var(--display);color:var(--on-mat-2);margin:0 0 6px}
.foot-notes{display:grid;grid-template-columns:1fr 1fr;gap:32px;padding-top:48px;padding-bottom:28px}
.foot-notes p{font-size:var(--t-small);color:var(--on-mat-2);margin:0}
.foot .ruler{opacity:.9}
`;

const RESULTS = `
/* the request: where you talk to Fitz */
.ask-card{position:relative;background:var(--tag);color:var(--ink);border:2px solid var(--fitz-ink);border-radius:20px;padding:18px 20px 16px;box-shadow:var(--lift-3)}
@media (prefers-color-scheme:dark){.ask-card{border-color:#0A140D}}
.ask{display:flex;align-items:baseline;gap:12px;padding-bottom:12px;border-bottom:3px solid var(--sunk);transition:border-color .2s}
.ask:focus-within{border-bottom-color:var(--tape)}
.ask label{font:700 1.5rem/1.3 var(--display);letter-spacing:-.02em;color:var(--ink-2);white-space:nowrap}
.ask textarea{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font:600 1.5rem/1.3 var(--display);letter-spacing:-.02em;resize:none;padding:0;overflow:hidden}
.ask textarea::placeholder{color:color-mix(in srgb,var(--ink-2) 75%,transparent);font-weight:500}
.ask textarea:focus-visible{outline:none}
.ask-meta{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:12px;margin-top:14px}
.ask-opts{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px}
.ask-go{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.ask-meta .label{font:600 .85rem/1 var(--display);color:var(--ink-2);margin-right:2px}
.ask-meta .grow{flex:1}
.ask-meta .btn-primary{min-height:48px;padding:0 24px;font-size:1.05rem}
.counter{font:500 .8rem/1 var(--sans);color:var(--ink-2);font-variant-numeric:tabular-nums}
.counter.over{color:var(--fail);font-weight:700}
.tries{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:16px}
.tries .label{font:600 .9rem/1 var(--display);color:var(--on-mat-2);margin-right:4px}
.try{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 14px;border:1px solid var(--mat-line-2);border-radius:999px;background:rgb(244 241 222/.06);color:var(--on-mat);font:500 .9rem/1.2 var(--sans);text-align:left;cursor:pointer;transition:background .2s,border-color .2s}
.try:hover{background:rgb(244 241 222/.14);border-color:var(--on-mat-2)}

/* results area */
.results{padding-top:8px}
.results:focus{outline:none}
.results:empty{display:none}
.res-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px 32px;align-items:end;margin:40px 0 24px}
.results-title{font-size:var(--t-title)}
.match-line{color:var(--ink-2);margin:6px 0 0;font-size:var(--t-small)}
.res-tools{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}
.ask-note,.aside{background:var(--tag);border-radius:var(--r-card);padding:18px 22px;margin:20px 0;box-shadow:var(--lift-1);max-width:none}
.ask-note{display:flex;gap:14px;align-items:center;background:var(--info-soft)}
.ask-note .fitz{flex:none}
.ask-note p{margin:0}
.aside h3{margin-bottom:8px}
.lead-in{font-weight:700;font-family:var(--display)}
.picks{display:grid;grid-template-columns:minmax(0,1fr);gap:28px}

/* a pick: the fitting ticket */
.pick{position:relative;background:var(--tag);border-radius:var(--r-card);box-shadow:var(--lift-1);padding:26px 28px 22px;transition:box-shadow .25s var(--ease-out),transform .25s var(--ease-out);animation:rise .6s var(--ease-out) both}
.pick:nth-child(2){animation-delay:.08s}.pick:nth-child(3){animation-delay:.16s}
.pick:hover{box-shadow:var(--lift-2)}
.pick:target{box-shadow:0 0 0 3px var(--stitch),var(--lift-2)}
.pick::before{content:"";position:absolute;top:22px;left:-7px;width:14px;height:14px;border-radius:50%;background:var(--paper);box-shadow:inset 0 2px 3px rgb(0 0 0/.12)}
.t-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 16px;align-items:start}
.t-name{font-size:1.6rem;letter-spacing:-.025em}
.t-name a{text-decoration:none}.t-name a:hover{text-decoration:underline;text-decoration-color:var(--stitch)}
.t-kind{font:600 .85rem/1.3 var(--display);color:var(--ink-2);margin:2px 0 0}
.t-top .badges{justify-content:flex-end;max-width:320px}
.summary{color:var(--ink-2);margin:14px 0 0}
.fit{font:600 1.3rem/1.4 var(--display);letter-spacing:-.015em;margin:12px 0 20px;max-width:56ch;text-wrap:pretty}
.t-glance{margin:0 0 22px}
.t-glance{grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:0}
.gl-value small{display:block;font:500 .8rem/1.3 var(--sans);color:var(--ink-2)}
.pick .seam{margin:18px 0 16px}
.t-install-label{display:flex;align-items:center;gap:8px;font:700 .9rem/1.3 var(--display);margin:0 0 6px}
.t-install .cmd{margin:0}
.t-fix{display:flex;gap:8px;align-items:flex-start;margin:10px 0 0;font-size:var(--t-small);color:var(--ink-2);max-width:none}
.t-fix span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.t-fix .i{color:var(--stitch);margin-top:2px}
.t-fix b{font-family:var(--display);color:var(--ink)}
.t-install .cmd pre{font-size:.95rem;padding:14px 16px}
.t-more{margin-top:16px;border-radius:var(--r-ctl)}
.t-more>summary{display:inline-flex;align-items:center;gap:8px;list-style:none;padding:8px 0;font:700 .95rem/1.3 var(--display);color:var(--ink-2)}
.t-more>summary::-webkit-details-marker{display:none}
.t-more>summary:hover{color:var(--ink)}
.t-more>summary .i{transition:transform .25s var(--ease-out)}
.t-more[open]>summary .i{transform:rotate(180deg)}
.t-more-body{padding-top:12px;display:grid;grid-template-columns:minmax(0,1fr);gap:20px}
.t-more-body .record{padding-top:20px;border-top:1px solid var(--rule)}
.t-links{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0}
.t-links a{display:inline-flex;align-items:center;gap:6px;font:600 .9rem/1 var(--display)}
.t-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:28px 40px}
.t-body h4:first-child{margin-top:0}
.t-measure{display:grid;gap:18px;align-content:start;align-self:start;padding:18px;border-radius:var(--r-ctl);background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.coverage{color:var(--ink-2);font-size:var(--t-small)}
.why{list-style:none;padding:0;margin:0 0 8px}
.why li{position:relative;padding-left:30px;margin-bottom:12px}
.why li::before{content:"";position:absolute;left:2px;top:2px;width:18px;height:18px;border-radius:50%;background:var(--pass-soft) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232E7A35' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E") center/12px no-repeat}
.cite{display:block;font-size:var(--t-small);color:var(--ink-2);margin-top:2px}
.why-marks li{display:grid;grid-template-columns:22px minmax(0,1fr);gap:10px;padding-left:0;margin-bottom:10px}
.why-marks li::before{content:none}
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
.record-title{display:flex;align-items:center;gap:8px;font:700 .8rem/1 var(--display);letter-spacing:.06em;text-transform:uppercase;color:var(--stitch);margin:0 0 10px}
.mine{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:var(--r-ctl);font-weight:600;max-width:none}
.mine .i{margin-top:2px}
.mine-yes{background:var(--pass-soft);color:var(--pass)}
.mine-no{background:var(--caution-soft);color:var(--caution)}
.mine-unknown{background:var(--sunk);color:var(--ink)}
details>summary{cursor:pointer}
.how summary{font:600 var(--t-small)/1.4 var(--display);color:var(--ink-2);margin-top:4px}
.how p{font-size:var(--t-small);color:var(--ink-2);margin-top:6px}
.install{margin:16px 0 0;border-radius:var(--r-ctl);background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.install>summary{display:flex;align-items:center;gap:10px;list-style:none;padding:14px 16px;font:700 1rem/1.3 var(--display)}
.install>summary::-webkit-details-marker{display:none}
.install>summary .i:last-child{margin-left:auto;transition:transform .25s var(--ease-out)}
.install[open]>summary .i:last-child{transform:rotate(180deg)}
.install-body{padding:0 16px 14px}
.install-body h4{font:700 .95rem/1.3 var(--display);margin:18px 0 6px}
.steps{padding-left:24px;margin:0}.steps li{margin-bottom:12px}.steps li::marker{font:700 .9rem var(--display);color:var(--ink-2)}.steps li p{margin-bottom:4px}
.caution{color:var(--caution)}
.issues{list-style:none;padding:0}.issues li{padding:10px 12px;margin-bottom:8px;border-radius:var(--r-ctl);background:var(--tag)}
.t-foot{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;margin-top:18px}
.t-foot a{display:inline-flex;align-items:center;gap:6px;font:600 .95rem/1 var(--display)}
.t-foot .grow{flex:1}
.chip-compare{min-height:36px;background:var(--sunk)}
.outside{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 18px;margin:36px 0 0;padding:22px;border-radius:var(--r-card);border:2px dashed var(--rule);color:var(--ink-2);max-width:none}
.outside>.i{grid-row:1/5;width:28px;height:28px;color:var(--ink-2)}
.outside h3{font:600 1.1rem/1.35 var(--sans);letter-spacing:0;color:var(--ink);margin-bottom:6px}
.unchecked{display:inline-block;background:var(--caution-soft);color:var(--caution);border-radius:var(--r-ctl);padding:8px 12px;font-weight:600;max-width:none}
.nofit{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:40px;align-items:start}
.nofit .outside{margin:0}
.best-free{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px 40px;align-items:start}
.best-free>p:first-child{grid-row:span 2}
.sbs{margin-top:32px}
.sbs>summary{display:inline-flex;align-items:center;gap:8px;list-style:none;font:700 1.05rem/1 var(--display);padding:12px 16px;border-radius:var(--r-ctl);background:var(--tag);box-shadow:var(--lift-1)}
.sbs>summary::-webkit-details-marker{display:none}
.sbs[open]>summary{margin-bottom:16px}
.loading{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;margin-top:32px}
.loading .bubble h2{font-size:var(--t-head)}
.loading ol{color:var(--ink-2);padding-left:20px;margin:6px 0 0;font-size:.95rem}
.unroll{height:14px;border-radius:3px;background:var(--sunk);overflow:hidden;position:relative;max-width:420px}
.unroll::after{content:"";position:absolute;inset:0;background:var(--tape) linear-gradient(90deg,transparent 0 calc(100% - 2px),color-mix(in srgb,var(--tape-ink) 55%,transparent) 0) 0 0/20px 60% repeat-x;transform-origin:left;animation:unroll 2.2s var(--ease-io) infinite}
`;

const PAGES = `
/* home: hero on the mat */
.hero{padding:36px 0 0;overflow:hidden}
.hero-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,340px);gap:24px 48px;align-items:end}
.hero h1{max-width:13ch}
.hero h1 em{font-style:normal;color:var(--tape)}
.hero .lede{font-size:clamp(1.05rem,1.6vw,1.25rem);color:var(--on-mat-2);margin:20px 0 28px;max-width:56ch}
.hero-fitz{position:relative;align-self:end;justify-self:center;margin-bottom:-10px}
.hero-fitz .fitz{width:clamp(200px,24vw,320px);height:auto;display:block;animation:hop-in .9s .1s var(--ease-out) both}
.hero-form{max-width:860px}
.proof{display:flex;flex-wrap:wrap;gap:6px 22px;margin:28px 0 0;padding:0;list-style:none;color:var(--on-mat-2);font-size:.95rem}
.proof li{display:inline-flex;align-items:center;gap:8px}
.proof strong{color:var(--on-mat);font-family:var(--display);font-variant-numeric:tabular-nums}
.proof .i{color:var(--tape)}
.hero .ruler{margin-top:40px}
body.is-results .hero{padding-top:12px}
body.is-results .hero-grid{grid-template-columns:minmax(0,1fr) auto}
body.is-results .hero h1,body.is-results .hero .lede,body.is-results .proof,body.is-results .tries{display:none}
.res-status{list-style:none;padding:0;margin:-8px 0 28px;display:grid;gap:8px;max-width:86ch}
.st{display:flex;gap:10px;align-items:flex-start;font-size:var(--t-small);color:var(--ink-2)}
.st .i{margin-top:2px;flex:none}
.st strong{font-family:var(--display);color:var(--ink)}
.st-busy .i{color:var(--caution)}.st-caution .i,.st-caution summary{color:var(--caution)}.st-info .i{color:var(--info)}
.st details summary{cursor:pointer;font-weight:600}
.st details[open] summary{margin-bottom:4px}
body.is-results .hero-fitz .fitz{width:110px;animation:none}
body.is-results .hero .ruler{margin-top:24px}
body.is-results .home-only{display:none}

/* stages: one real tool through the four steps */
.stages{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:auto auto auto;column-gap:24px;list-style:none;padding:0;margin:0;position:relative}
.stages::before{content:"";position:absolute;left:4%;right:4%;top:84px;height:2px;background:linear-gradient(90deg,var(--stitch) 0 7px,transparent 7px 12px) repeat-x 0 0/12px 2px}
.stage{display:grid;grid-template-rows:subgrid;grid-row:span 3;row-gap:8px;position:relative;text-align:center;justify-items:center}
.stage-fitz{height:150px;display:flex;align-items:flex-end;justify-content:center;position:relative;z-index:1}
.stage-fitz .fitz{height:130px;width:auto;background:var(--paper);border-radius:50%;padding:0 6px}
.stage h3{font-size:1.3rem}
.stage>p{color:var(--ink-2);margin:0;max-width:24ch}
.stage-ui{background:var(--tag);border-radius:var(--r-card);padding:14px 16px;box-shadow:var(--lift-1);font-size:var(--t-small);min-height:180px}
.stage-ui .ui-title{font:700 .85rem/1.3 var(--display);color:var(--ink-2);margin-bottom:10px}
.stage-ui dl{margin:0}.stage-ui dl div{display:grid;grid-template-columns:84px minmax(0,1fr);gap:8px;padding:3px 0}
.stage-ui dt{color:var(--ink-2)}.stage-ui dd{margin:0}
.stage-ui pre{background:var(--code);color:var(--code-ink);border-radius:8px;padding:8px 10px;margin:0 0 8px;overflow-x:auto;white-space:pre;font-size:.8rem}
.stage-ui .why li{margin-bottom:8px}
.stage-ui .level{font-size:.9rem}
.diff{display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;margin:8px 0 0}

/* fresh runs */
.fresh{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:40px;align-items:start}
.fix-card{background:var(--tag);border-radius:var(--r-card);padding:20px 22px;box-shadow:var(--lift-1)}
.fix-card h3{margin-bottom:10px}
.fix-kicker{display:flex;align-items:center;gap:8px;font:700 .85rem/1.2 var(--display);color:var(--stitch);margin:0 0 6px}
.fix-card pre{background:var(--code);color:var(--code-ink);border-radius:8px;padding:9px 12px;margin:10px 0 0;overflow-x:auto;white-space:pre;font-size:.85rem}
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
.label-tag{position:relative;background:var(--tag);border-radius:6px;padding:32px 32px;box-shadow:var(--lift-2);transform:rotate(-1.2deg)}
.label-tag::before{content:"";position:absolute;inset:10px;border:2px dashed color-mix(in srgb,var(--stitch) 70%,transparent);border-radius:3px;pointer-events:none}
.label-tag h3{font-size:1.1rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:16px;text-align:center}
.rules{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.rules li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:12px;align-items:center}
.rules .i{width:24px;height:24px;color:var(--stitch)}
.rules b{display:block;font-family:var(--display)}
.rules span{color:var(--ink-2);font-size:.95rem}

/* agents band */
.agents-band{border-radius:20px;padding:clamp(28px,4vw,48px);display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px 40px;align-items:center}
.agents-band h2{color:var(--on-mat)}
.agents-band p{color:var(--on-mat-2);font-size:var(--t-lead)}
.agents-band .cmd{max-width:780px;margin-top:18px}

/* detail and compare */
.layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:40px;align-items:start;margin-top:40px}
.side{position:sticky;top:20px;display:grid;gap:20px}
.panel{background:var(--tag);border-radius:var(--r-card);padding:20px 22px;box-shadow:var(--lift-1)}
.panel h2,.panel h3{font-size:1.1rem;margin-bottom:12px}
.panel-measure{margin-top:16px}
.sources>summary{font:700 1.05rem/1.2 var(--display);cursor:pointer}
.sources[open]>summary{margin-bottom:10px}
.block{margin-bottom:48px}
.block>h2{font-size:1.6rem;margin-bottom:16px}
.block h3{margin:24px 0 8px}
.block .run-card h3,.block .run-head h3{margin:0}
.feat-list{list-style:none;padding:0;margin:0;display:grid;gap:10px}
.feat-list li{display:grid;grid-template-columns:24px minmax(0,1fr);gap:10px;padding:12px 14px;border-radius:var(--r-ctl);background:var(--tag);box-shadow:var(--lift-1)}
.feat-list .i{width:20px;height:20px;margin-top:2px}
.feat-ok .i{color:var(--pass)}.feat-fail .i{color:var(--fail)}.feat-open .i{color:var(--ink-2)}
.feat-check summary{font-size:var(--t-small);color:var(--pass);font-weight:600}
.feat-check code{display:block;margin-top:6px;padding:8px 10px;border-radius:8px;background:var(--code);color:var(--code-ink);font-size:.8rem;overflow-x:auto;white-space:pre}
.side a{overflow-wrap:anywhere}
.feat-list small{display:block;color:var(--ink-2);margin-top:2px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.uses{columns:2;column-gap:32px}.uses li{break-inside:avoid;margin-bottom:6px}
.run-card{background:var(--tag);border-radius:var(--r-card);padding:22px 24px;box-shadow:var(--lift-1);margin-bottom:20px}
.run-card .install{background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.run-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;align-items:center}
.run-head h3{display:flex;align-items:center;gap:10px;font-size:1.25rem}
.run-head .arch{font:500 .9rem/1 var(--sans);color:var(--ink-2)}
.empty{display:flex;align-items:center;gap:20px;padding:24px;border-radius:var(--r-card);background:var(--tag);box-shadow:var(--lift-1)}
.empty .fitz{flex:none}
.empty p{margin:0}
.cmp-pick{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:20px}
.cmp-pick input[list],.cmp-pick input[type=text]{min-height:44px;padding:0 14px;border:0;border-radius:var(--r-ctl);background:var(--tag);color:var(--ink);font:500 1rem var(--sans);min-width:min(320px,100%);box-shadow:var(--lift-1)}
.cmp-table th[scope=col]{min-width:200px}
.cmp-table th[scope=col] a{font:700 1.1rem/1.2 var(--display);color:var(--ink);text-decoration:none}
.cmp-table th[scope=col] a:hover{text-decoration:underline}
.cmp-table .meter{min-width:170px}
.cmp-table .meter-label{display:none}
.cmp-table th[scope=col] a.cmp-remove{color:var(--ink-2)}
.cmp-table th[scope=col] a.cmp-remove .i{width:16px;height:16px}
.cmp-links{display:inline-flex;gap:8px}
.icon-link{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:50%;background:var(--sunk);color:var(--ink)}
.icon-link:hover{background:color-mix(in srgb,var(--ink) 10%,var(--sunk))}
.icon-link .i{width:17px;height:17px}
body.has-tray{padding-bottom:72px}
/* Remove sits in the column head's top-right corner (the sticky head anchors it); the name keeps clear of it. */
.cmp-remove{position:absolute;top:8px;right:8px;display:grid;place-items:center;width:28px;height:28px;border-radius:50%;color:var(--ink-2)}
.cmp-table th[scope=col]:has(.cmp-remove){padding-right:44px}
.cmp-remove[data-tip]:hover::after{bottom:auto;top:calc(100% + 4px);left:auto;right:0}
.cmp-remove:hover{background:var(--sunk);color:var(--ink)}
.cmp-same{margin-top:20px;padding:18px 22px;border-radius:var(--r-card);background:color-mix(in srgb,var(--sunk) 55%,var(--tag))}
.cmp-same-title{font:700 .95rem/1.2 var(--display);margin:0 0 8px}
.yes{color:var(--pass);font-weight:600}.no{color:var(--caution);font-weight:600}
.yes .i,.no .i{margin-right:6px;vertical-align:-.2em}
.run-line{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:2px}
.run-line .i{width:13px;height:13px}

/* browse */
.sec-tight{padding-top:40px}
.layout-browse{grid-template-columns:270px minmax(0,1fr)}
.side-left{top:20px}
.filters{display:grid;gap:18px}
.filters fieldset{border:0;padding:0;margin:0;display:grid;gap:8px}
.filters legend{font:700 .85rem/1 var(--display);color:var(--ink-2);margin-bottom:8px;padding:0}
.filters .chips{display:flex;flex-wrap:wrap;gap:6px}
.find-in{display:flex;align-items:center;gap:8px;min-height:44px;padding:0 14px;border-radius:var(--r-ctl);background:var(--tag);box-shadow:var(--lift-1)}
.find-in input{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font:500 1rem var(--sans)}
.find-in input:focus{outline:none}
.find-in:focus-within{box-shadow:0 0 0 3px var(--stitch)}
.cat-grid{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.cat-card{position:relative;display:flex;flex-direction:column;gap:8px;padding:18px 18px 14px;background:var(--tag);border-radius:var(--r-card);box-shadow:var(--lift-1);transition:box-shadow .2s,transform .2s var(--ease-out)}
.cat-card:hover{box-shadow:var(--lift-2);transform:translateY(-2px)}
.cat-card h3{font-size:1.1rem}
.cat-card h3 a{text-decoration:none}
.cat-card h3 a::after{content:"";position:absolute;inset:0;border-radius:var(--r-card)}
.cat-card p{margin:0;color:var(--ink-2);font-size:.92rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cat-card .row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:auto;padding-top:8px}
.cat-card .row .badge{position:relative;z-index:1}
.cat-card .chip-compare{position:relative;z-index:1;margin-left:auto;min-height:32px;padding:0 12px;font-size:.8rem}
/* A narrow card keeps its badges and Compare on one line: Compare shows as its icon, named on hover. */
.cat-card{container-type:inline-size}
@container (max-width:280px){
.cat-card .chip-compare{padding:0 10px}
.cat-card .chip-compare span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
@media (hover:hover){.cat-card .chip-compare:hover::after{content:"Compare";left:auto;right:0}}
}
.cat-card .seam{margin:4px 0 2px;animation:none}
.cat-card.unverified{background:transparent;box-shadow:none;border:2px dashed var(--rule)}
.cat-count{color:var(--ink-2);margin:0 0 16px}
.js .cat-card.later{display:none}.js .filtering .cat-card.later{display:flex}
.more-filters>summary{font:700 .9rem/1 var(--display);color:var(--ink-2);padding:6px 0;cursor:pointer}
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
@keyframes unroll{0%{transform:scaleX(0)}55%{transform:scaleX(1)}100%{transform:scaleX(1);opacity:0}}
@keyframes shimmer{from{background-position:100% 0}to{background-position:-50% 0}}
@keyframes pop-in{from{opacity:.4;transform:translateY(6px) scale(.98)}to{opacity:1;transform:none}}
@keyframes tray-in{from{transform:translateY(100%)}to{transform:none}}
@keyframes toast{0%{opacity:0;transform:translateY(10px)}12%,82%{opacity:1;transform:none}100%{opacity:0}}
@keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
::view-transition-old(root),::view-transition-new(root){animation-duration:.35s;animation-timing-function:var(--ease-out)}
@media (prefers-reduced-motion:reduce){
*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}
::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important}
.unroll::after{transform:scaleX(.6)}}
`;

const RESPONSIVE = `
@media (max-width:1080px){
.stages{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:none;gap:32px 20px}
.stages::before{display:none}
.stage{display:flex;flex-direction:column;align-items:center;grid-row:auto;gap:6px}
.layout,.layout-browse{grid-template-columns:minmax(0,1fr)}
.side{position:static;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));align-items:start}
}
@media (max-width:900px){
.nav{display:none}.menu{display:block}
.hero-grid{grid-template-columns:minmax(0,1fr)}
.hero-fitz{order:-1;justify-self:start;margin:0}
.hero-fitz .fitz{width:150px}
body.is-results .hero-fitz{display:none}
.t-body,.record{grid-template-columns:minmax(0,1fr)}
.record .mine{grid-column:1;grid-row:auto}
.t-top{grid-template-columns:minmax(0,1fr)}
.t-top .badges{justify-content:flex-start;max-width:none}
.fresh,.care,.nofit,.best-free{grid-template-columns:minmax(0,1fr)}
.agents-band{grid-template-columns:minmax(0,1fr)}
.foot-grid{grid-template-columns:1fr 1fr}.foot-brand{grid-column:1/-1}
.foot-notes{grid-template-columns:1fr}
.res-head{grid-template-columns:minmax(0,1fr)}.res-tools{justify-content:flex-start}
.head-row{grid-template-columns:minmax(0,1fr)}
.head .fitz{display:none}
}
@media (max-width:640px){
.wrap{padding-left:16px;padding-right:16px}
.ask{flex-direction:column;gap:4px}
.ask label{font-size:1.1rem}
.ask textarea{font-size:1.2rem}
.ask-meta{grid-template-columns:minmax(0,1fr)}.ask-go{align-items:stretch}
.ask-meta .btn-primary{width:100%}
.seg{width:100%;justify-content:space-between}.seg label{flex:1;justify-content:center;padding:0 8px}
.stages{gap:28px 12px}
.stage-fitz{height:100px}.stage-fitz .fitz{height:90px}
.stage h3{font-size:1.1rem}.stage>p{font-size:.9rem}
.pick{padding:22px 18px 18px}
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
.tray .fitz{display:none}
.toasts{bottom:96px}
.label-tag{transform:none;padding:26px 22px}
.readme-vs li{grid-template-columns:minmax(0,1fr);gap:2px}
.dt th,.dt td{padding:10px 12px}
.cmp-table th[scope=col]{min-width:150px}
.dt tbody th{white-space:normal;min-width:84px}
.cmp-pick input[type=text],.cmp-pick input[list]{min-width:0;flex:1}
.hero-fitz .fitz{width:96px}
.hero{padding-top:16px}
}
`;

export const CSS = TOKENS + BASE + COMPONENTS + RESULTS + PAGES + MOTION + RESPONSIVE;
