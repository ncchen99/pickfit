# pickfit: product context for design work

Written 2026-11-01 for the web redesign. Product truth lives in [docs/brief.md](docs/brief.md); this file keeps only what design decisions need. The visual system is in [DESIGN.md](DESIGN.md).

## What pickfit is

A neutral software advisor for a person, delivered through their AI agent (MCP) and through this web page. It matches software to what the person needs, **installs it in a fresh sandbox before suggesting it**, and hands over the steps that worked. The web page and the MCP are two doors to the same brain: the page runs the MCP's own `find_software` and `get_install_guide`.

Unique mechanism, in one sentence: *nothing is suggested until pickfit has installed it, and every claim on screen points at the field or run it rests on.*

## Who comes to the page

- **Developers and AI-agent users** looking for a CLI tool, a local AI tool or an MCP server. They read READMEs for a living and distrust marketing; they skim, compare and copy commands. Often on a laptop, often in dark mode.
- **Hackathon judges** who open the link once and must understand the product in seconds, then try a search.
- **Authors of small tools** checking whether their project is listed and what the run found.

## What they must believe

1. pickfit understood my need (the fit sentence, the reasons and where each came from).
2. pickfit actually ran it (where, when, what passed, what the README got wrong).
3. pickfit is on my side (no ads, ranks by fit not stars, says "built-in is enough" and "not verified" plainly).

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

- **Truth first.** Every score, label and comparison comes from the catalog or the run record. Nothing unverified is presented as fact; the well-known option is marked "not verified" and gets no stitching, badge, steps or link.
- **No account, no tracking.** No query string carries the need (request URLs reach logs). Compare selections live in the visitor's own browser.
- **Strict CSP.** Inline styles and scripts only under a per-response nonce; no inline `style=` attributes. Images, fonts and the mascot are served from this Worker.
- **Works without JavaScript.** The form posts and the server renders; JavaScript adds the in-place results, copy buttons, the compare tray and motion.
- **Accessibility.** WCAG AA contrast, keyboard paths for every control, visible focus, `prefers-reduced-motion` and `prefers-color-scheme` respected.
- **Language.** The page is English (global hackathon). The voice is plain, specific and a little warm, like Fitz: picky, honest, never hype.
