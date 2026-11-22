# pickfit: product context for design work

Written 2026-11-01 for the web redesign; updated 2026-11-22 to align with [docs/brief.md](docs/brief.md) Section 15 (post-hackathon positioning). Product truth lives in the brief; this file keeps only what design decisions need. The visual system is in [DESIGN.md](DESIGN.md).

## What pickfit is

The place an AI agent checks **before it builds**: what already exists, and whether it was verified to work *recently* and is still maintained. pickfit installs and exercises each tool in a fresh sandbox, records the commands and results, and hands over the steps that worked. Agents query it over MCP; this web page is the second door to the same brain (it runs the MCP's own `find_software` and `get_install_guide`), for people who don't use an agent yet.

What a model alone can't give, in three parts:

1. **Fresh run evidence**: these commands installed it in a clean box this week, this action produced this result.
2. **Outcomes pooled across agents**: installed or not, still in use, replaced by what.
3. **Neutrality**: free, local or a competitor's tool is fine to recommend, and so is "you don't need this" or "build it yourself".

Unique mechanism, in one sentence: *nothing is recommended until pickfit has run it recently, and every claim on screen points at the field or run it rests on.*

## Who queries, who uses

Two separate questions. **Who queries pickfit**: by default an agent, increasingly on a person's behalf. **Who uses the tool it recommends**: a person or an agent, and every record says which.

People who come to the page:

- **AI agents and the people behind them**, checking what exists before writing new code. The page shows the same evidence the MCP returns.
- **Developers** looking for a CLI tool, a local AI tool or an MCP server. They read READMEs for a living and distrust marketing; they skim, compare and copy commands. Often on a laptop, often in dark mode.
- **Makers** of small web apps, games and local tools, and people looking for one to use.
- **Authors of tools** checking whether their project is listed and what the latest run found.

## Three tracks

| | A. Capabilities agents use | B. Web apps people use, where the UI is the value | C. Creative and document tools people and agents share |
|---|---|---|---|
| Examples | CLI, TUI, MCP server, API, self-hosted service | Maps, multiplayer and real-world games, local tools | Image and video editing, documents, slides |
| What is checked | Installs, features work, permissions, outbound connections, prompt-injection risk | Works at phone size, core flow completes, load speed, trackers, data freshness | Agent produces a file via MCP or script, the GUI opens, edits and saves it |
| Evidence shown | Verification record (commands and output) | A few seconds of screen preview | Verification record plus one screenshot |

Track A grows fastest and suits the Linux sandbox. B and C start small with a high bar: every objective check must pass. **No new tutorial screen recordings**; existing videos stay, and new evidence is machine-readable records plus short previews or a screenshot for B and C. A preview is not a tutorial.

## What they must believe

1. pickfit understood my need (the fit sentence, the reasons and where each came from).
2. pickfit actually ran it, and recently (where, when, what passed, what the README got wrong, how many days since the last pass).
3. pickfit is on my side (no ads, ranks by fit not stars, says "built-in is enough", "build it yourself" and "not verified" plainly).

## Freshness and build-vs-reuse

- **Last passing verification, not last commit.** Finished software that never changes is fine; what drops out is software nobody maintains that fails re-verification.
- **Re-verify on demand.** When a record is queried and its verification is stale, say "last verified N days ago" and queue a re-run. Re-verification cycles follow how fast the dependencies move.
- **Admit wide, recommend strictly.** Recommend only what passed function checks and survived a few re-verification cycles. New work is labelled "new" with lower confidence.
- **Broken is shown, not deleted.** "Used to work, fails now" stays visible as not recommended, so agents don't waste a try.
- **Every recommendation says how to reuse it**: use it as is, extend it through its plugin or config interface, use it as a reference to build your own, or the built-in option is enough.
- **Agent safety for track A**: permission scope, outbound connections and prompt-injection risk are first-class facts, not footnotes.

## Surfaces and modes (Impeccable)

| Route | Mode | Job |
|---|---|---|
| `/` | Persuade | Understand the offer in five seconds and start a search from the first viewport |
| `/search` (POST) | Operate | Scan picks, see the evidence, compare, copy the install steps |
| `/tool/<slug>` | Read | Everything pickfit knows about one tool, so nobody has to open the README |
| `/compare?tools=a,b,c` | Operate | The same facts side by side |
| `/browse` | Operate | Explore the verified catalog by kind, OS and hidden gems |
| `/how` | Read | How verification, matching and scoring work, and what each label means |
| `/agents` | Read | Connect an agent over MCP |
| `/submit`, `/submit/<id>` | Operate | Recommend a repository or web app, then follow its run or come back by link |

## Constraints that shape the design

- **Truth first.** Every score, label and comparison comes from the catalog or the run record. Nothing unverified is presented as fact; the well-known option is marked "not verified" and gets no stitching, badge, steps or link. A stale verification shows its age.
- **No account, no tracking.** No query string carries the need (request URLs reach logs). Compare selections live in the visitor's own browser.
- **Strict CSP.** Inline styles and scripts only under a per-response nonce; no inline `style=` attributes. Images, fonts and the mascot are served from this Worker.
- **Works without JavaScript.** The form posts and the server renders; JavaScript adds the in-place results, copy buttons, the compare tray and motion.
- **Accessibility.** WCAG AA contrast, keyboard paths for every control, visible focus, `prefers-reduced-motion` and `prefers-color-scheme` respected.
- **Language.** The page is English (a global audience). The voice is plain, specific and a little warm, like Fitz: picky, honest, never hype.
