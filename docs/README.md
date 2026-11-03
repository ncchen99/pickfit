# docs

Start with **[REPORT.md](REPORT.md)**, the full English write-up of pickfit: origin, hypotheses, the system, experiments, iterations and the designs that keep the catalogue honest. Most of the working documents below are in Traditional Chinese, the language the project was planned in. Times are Taipei time (UTC+8).

## The project

| File | What it is |
|---|---|
| [REPORT.md](REPORT.md) | Final report (English), the one document to read |
| [brief.md](brief.md) | What we set out to build, for whom, and the scope |
| [plan.md](plan.md) | Task list, spending rules, and the status log (section 7): every merge, result and cost, in order |
| [hackathon-rules.md](hackathon-rules.md) | The hackathon's rules and how this repo follows them |
| [research/architecture.md](research/architecture.md) | Architecture and the hypotheses the design rested on |
| [research/channels.md](research/channels.md) · [research/notes/](research/notes/) | Where software comes from, plus notes from each probe and comparison |

## Experiments and pilots

| File | What it is |
|---|---|
| [usability-proposal.md](usability-proposal.md) · [usability-pilot.md](usability-pilot.md) | Ease-of-use scoring: pre-registered pilot, two rounds that missed the bar, the visual-defect deduction that did ship |
| [security-pilot.md](security-pilot.md) · [security-score-changes.md](security-score-changes.md) | Known-vulnerability check: the read-only pilot and the score changes it caused |
| [demo-candidates.md](demo-candidates.md) · [demo-shortlist.md](demo-shortlist.md) | How the demo tools were picked and re-tested |
| [source-terms.md](source-terms.md) | Terms checked before adding Flathub, Homebrew Cask and web-app sources |
| [discovery/](discovery/) | Discovery inputs kept for reproducibility |

Experiments that were tried and not merged live on as git tags: `git tag -l 'archive/*' -n3`.

## Submission

| File | What it is |
|---|---|
| [submission/story.md](submission/story.md) | The story and how claims are worded (measured, small sample, hypothesis) |
| [submission/README.draft.md](submission/README.draft.md) | Earlier English README draft, folded into REPORT.md |
| [submission/VIDEO.draft.md](submission/VIDEO.draft.md) | Set-aside video draft; the final video is in [../video/](../video/) |

## Elsewhere in the repo

| Path | What it is |
|---|---|
| [../pickfit/](../pickfit/) | Python pipeline: discovery, prescreen, extraction, sandbox verification, scoring, security, publish |
| [../worker/](../worker/) | Cloudflare Worker: the MCP server and the website at pickfit.app |
| [../data/software/](../data/software/) | The catalogue, one JSON record per tool |
| [../eval/](../eval/) | Frozen evaluation questions, runner and results |
| [../brand/](../brand/) | Fitz the mascot, share cards and screenshots |
| [../video/](../video/) | The 3-minute demo video's script, scenes and build scripts |
| [../spikes/](../spikes/) | Early probes from day one; not product code |
| [../DESIGN.md](../DESIGN.md) · [../PRODUCT.md](../PRODUCT.md) | Design system and product context for UI work |
