# pickfit

**A neutral software advisor for people, delivered through their AI agent—discovering lesser-known software, installing and testing it in sandboxes, and recommending what actually fits.**

AI coding agents have made building software cheap, sparking an explosion of indie tools across GitHub, Show HN, Flathub, and the web. Yet finding the right tool is harder than ever: search engines and directories reward marketing budgets rather than personal fit, foundation models are blind to projects shipped after their training cutoff, and small repositories often have incomplete or broken installation instructions. As a result, people keep reinventing the wheel—paying ongoing maintenance time and AI token costs to rebuild tools that already exist. **pickfit** answers a simple desire: *"I want an AI that helps me find the right software that already exists, instead of building everything myself."* Acting as an independent advisor not tied to any single vendor ecosystem, pickfit continuously discovers lesser-known tools (developer CLIs, local AI/LLM tools, MCP servers, desktop GUI apps, and web apps), installs and exercises them inside isolated sandboxes, scores quality separately from popularity, and gives any AI agent—or human on the web—verified recommendations and replay-tested installation guides.

---

## Try It

- **Web App (Natural-Language Search & Catalog)**: `https://pickfit.app/`
  - Also includes `/browse` (verified catalog), `/compare` (side-by-side comparison), `/how` (methodology & scoring), `/agents` (MCP setup), and `/tool/<slug>` (full per-tool profile and verification log).
- **MCP Endpoint (Stateless Streamable HTTP)**: `https://pickfit.app/mcp`

### Add pickfit to Claude Code

```bash
claude mcp add --transport http pickfit https://pickfit.app/mcp
```

Or configure `mcpServers` in Claude Desktop, Cursor, or any MCP client:

```json
{
  "mcpServers": {
    "pickfit": {
      "type": "http",
      "url": "https://pickfit.app/mcp"
    }
  }
}
```

When running headless `claude` from a shell inside the Claude desktop app, clear inherited environment variables with `env -i`:

```bash
echo '{"mcpServers":{"pickfit":{"type":"http","url":"https://pickfit.app/mcp","headers":{"X-Pickfit-Reporter":"dev"}}}}' > /tmp/pickfit-mcp.json
env -i HOME="$HOME" PATH="$PATH" ANTHROPIC_API_KEY=... claude -p "Find a free offline macOS CLI to audit my MCP config" \
  --strict-mcp-config --mcp-config /tmp/pickfit-mcp.json \
  --allowedTools "mcp__pickfit__find_software,mcp__pickfit__find_alternatives,mcp__pickfit__get_install_guide,mcp__pickfit__report_outcome,mcp__pickfit__submit_software"
```

### Exposed MCP Tools

| Tool | Purpose |
|---|---|
| `find_software` | Matches a user's need and constraints (OS, CPU arch, budget, local/offline, no API key) to 1–3 verified tools, with evidence-backed reasons (`how_we_know`), `best_free`, `no_install_option`, or an unverified `well_known_option`. |
| `find_alternatives` | Finds alternatives to a current tool given `current_software`, `pain_points`, and `must_keep` features (or recommends `keep_current` when nothing clearly beats it). |
| `get_install_guide` | Returns **only** sandbox-replayed or human-verified installation commands for the user's OS/arch, MCP client config snippets (`mcp_client_config`), and opt-in retention `check_in` instructions. |
| `report_outcome` | Records installation, first-run, and long-term retention outcomes (`installed`, `install_failed`, `first_run_succeeded`, `first_run_failed`, `still_using`, `replaced`, `abandoned`); real failures queue automated sandbox re-verification. |
| `submit_software` | Queues a repository (and web app URLs on the P5.8 branch) for automated discovery, sandbox verification, scoring, and publication via `pickfit watch`. |

---

## What Was Built During the Hackathon vs. Before

This project was built for the **Meta Global AI Developer Hackathon** (development window: 2026-10-27 to 2026-11-04 ET, Indie Developer track).

- **What existed before the hackathon (outside this repo)**: Problem formulation, user and market research, decision notes, draft data field ideas, draft evaluation questions, and a placeholder icon (created starting 2026-10-05). Per official hackathon rules, **none of those pre-competition files are in this repository**, and none of that pre-competition work is presented as hackathon work.
- **What was built during the hackathon (everything in this repo; first commit 2026-10-28 03:23 Taipei, i.e. 10/27 ET)**:
  - The complete Python discovery, prescreening, extraction, verification, replay, and scoring pipeline (`pickfit/`).
  - Multi-platform sandbox runners: local `DockerBox`, cloud `ModalBox` (`gvisor` and `vm` with Xvfb virtual displays), macOS `Tart` VM (`macOS 26` arm64 with `softnet` isolation), and Windows 11 Enterprise evaluation VM on VirtualBox behind an Alpine router VM.
  - The canonical software dataset (`data/software/*.json`: 689 software profiles across `dev_cli`, `local_ai`, and `mcp_server`, plus desktop GUI apps as of 2026-11-01; `TODO(verify: final total profile count and verified count across all categories including web_app after 11/3 12:00 freeze)`).
  - The Cloudflare Worker stateless MCP server, D1 outcome/submission/budget tables, and the server-rendered web application (`worker/`), plus original artwork for the **Fitz the tailorbird** mascot (`brand/mascot/`).
  - The pre-registered evaluation suite (20 primary questions drafted and frozen on 2026-10-28 in commit `5ac62ca` before any data collection, plus 12 B-suite questions sampled from public community posts and frozen in commit `dec4cb9`) and automated L2 container/VM execution harness.

---

## How Meta Models Are Used

Every decision in the pickfit product pipeline and runtime is powered by Meta models through `call_meta` (`pickfit/meta.py`) and the Worker's `callMeta` (`worker/src/meta.ts`), with strict cost accounting and budget caps:

| Stage | Meta Model | What It Does |
|---|---|---|
| **Candidate Prescreening** | `meta-models/muse-spark-open-1026` (Baseten) + `muse-spark-1.3` (Meta API audit) | Filters candidate repositories (`reasoning_effort: low`, forced tool calling) to reject libraries, benchmarks, demos, and templates (~1–2s, ~$0.004/repo). Low-confidence or contradictory outputs and a fixed 5% sample are audited by `muse-spark-1.3` (matching 34/34 in P2.4 and 100/100 in the expanded batch). |
| **Structured Extraction** | `muse-spark-1.3` (Meta API; `-contributor` in dev only on public data) | Reads READMEs and release notes wrapped in `<source>` tags and outputs a strict 11.7 KB JSON schema (`software.v1`). Every claim requires a verbatim source quote verified programmatically against the raw text; API facts (license, releases, stars) are filled deterministically from APIs, never guessed by the model. |
| **Verification Agent** | `muse-spark-1.3` (Meta API) & `Muse Spark Open` (Baseten) | Runs multi-turn tool-calling loops (`list_dir`, `read_file`, `run_command`, `run_background`, `launch_gui`, `operate_gui`, `finish`) with `reasoning.effort: medium` and encrypted reasoning replay to install tools in sandboxes, diagnose broken README instructions, recover from missing flags/dependencies, and exercise advertised features. |
| **Multimodal Screen, Output & Docs Judges** | `muse-spark-1.3` (Meta API, vision + strict JSON schema) | Independently inspects terminal outputs and redrawn PNG screenshots (returning normalized `0–1000` evidence bounding boxes), crops of Xvfb/VM GUI windows (`main_ui`, `first_run`, `sign_in_wall`, `crash_or_error`), and feature smoke-test outputs. Also grades README installation docs against an 8-item rubric (`install_docs`) with verbatim quote verification. |
| **GUI Operator** | `Muse Spark Open` (Baseten & Modal shared endpoint) | Views virtual-display screenshots (a numbered UI element list from MIT-licensed `cua-driver` is being trialled) and proposes step-by-step GUI actions (`click` in `0–1000` coordinates, `type`, `key`, `scroll`, `wait`, `done`, `give_up`) executed via `xdotool`. |
| **Web App Operator** | `Muse Spark Open` (Modal/Baseten) / `muse-spark-1.3` | Drives open-source `browser-use` inside a sandboxed browser to open web apps, exercise core features, and test offline PWA reloads (P3.12 branch). |
| **Live Matching & Query Expansion** | `muse-spark-1.3` (Meta API in Cloudflare Worker) | When >60 verified candidates pass hard filters, a fast call (`effort: minimal`, ≤5s) expands multilingual/conversational queries into 6–15 English keywords for BM25 shortlisting (50 by relevance + 10 by treasure score). A main call (`effort: low`, strict JSON schema with candidate `slug` enum) selects 1–3 picks and cites exact card fields/values verified by a deterministic guard. |

### Built with Muse Spark Open

pickfit uses Meta's open-weight **Muse Spark Open** model across two inference partners:

1. **Baseten (`meta-models/muse-spark-open-1026`)**: Powers high-volume candidate prescreening, the GUI vision-action operator, synthetic benchmark query generation, third-grader evaluation, and the multi-turn verification agent for the MCP server expansion and feature-coverage batches. Before adopting it for verification, we ran a 20-repository head-to-head benchmark against `muse-spark-1.3`: Muse Spark Open achieved a **0.92 verification pass ratio** (11/20 vs. 12/20, with all invalid claims caught by deterministic command-log guards), whereas extraction field agreement was 62–71% (below our 90% threshold). We therefore deployed a hybrid architecture: Muse Spark Open runs the multi-turn sandbox agent and GUI operator, while `muse-spark-1.3` handles extraction, multimodal judging, and scoring.
2. **Modal Shared Endpoint (`pickfit-spark-open` serving `meta-models/Muse-Spark-Open-816B-A42B`)**: Configured via OpenAI-compatible workspace proxy authentication, verified on text, screenshot reading (image input), `tool_choice: required`, and strict JSON schema output, it powers GUI screenshot operation and `browser-use` web app verification using hackathon Modal credits.

**Model Usage & Spend Summary**: As of 2026-11-01 in `docs/plan.md`, the pipeline had logged ~$114.66 on the Meta Model API (with an earlier P5.5 snapshot recording 1,429 requests at an 80% dev-cache hit rate and a median sandbox verification time of 73–91s). Final totals across all sessions: `TODO(verify: final request counts, token totals, cache hit rates, and USD spend across Meta Model API, Baseten Muse Spark Open, and Modal Shared Endpoint from scripts/meta_usage.py and ~/.pickfit/ledger.sqlite after freeze)`.

---

## How Verification Works

1. **Isolated Sandboxes (`Box`)**: Every candidate runs as an unprivileged user (`sbx`) with no API keys in its environment and cloud metadata (`169.254.0.0/16`) and private networks blocked:
   - **Linux CLI / Local AI / MCP**: `ModalBox` (`runtime="gvisor"`) and local `DockerBox`.
   - **Linux Desktop GUI**: `ModalBox` (`runtime="vm"`) with an Xvfb virtual display, `seccomp` blocking `AF_VSOCK` and `io_uring`, disabled user namespaces, and screenshot capture isolated under a separate display UID into a `0700` directory with a stdin nonce so the app under test cannot forge window evidence.
   - **macOS (`arm64`)**: `Tart` VM (`macOS 26`) with host-side `softnet` blocking LAN/multicast traffic and host-state health probes.
   - **Windows (`x86_64`)**: VirtualBox Windows 11 Enterprise evaluation VM behind an Alpine Linux router VM, running commands in PowerShell 7 as standard user `sbx`.
2. **Deterministic Verification Levels (`verdict.py`)**: A tool's verification level is computed strictly from the recorded command log (commands whose exit codes were masked by `|| true`, `; echo`, or trailing `| head` / `| tail` are stripped or rejected) and capped by the independent screen judge:
   - **`install`**: Clean installation and basic launch/`--version`/`--help` check (or for a desktop GUI app, launching its own window and rendering `main_ui` or `first_run` on the virtual display; for an MCP server, `install` alone does not count as passed).
   - **`function`**: Executes a real task from the README on sample inputs with exit code 0 and expected output (for MCP servers: completes a stdio `initialize` + `tools/list` handshake via `mcp_probe.py`; for GUI apps: passes an `operate_gui` interaction check).
   - **`service`**: Starts a background daemon/server and responds to a live local request (for MCP servers: completes the handshake plus a real account-free `tools/call` without `isError`).
   - **`inference`**: A local AI tool loads a real small weight file (e.g., `stories260K` GGUF or `SmolLM2-135M-Instruct`) in the sandbox and returns a completion over `/v1/chat/completions` or `/api/generate`.
3. **Clean-Room Offline Replay (`replay.py`)**: Before any installation steps are written to a software profile, a brand-new sandbox replays the exact recorded install commands online with **no model involved**, then severs the network (and DNS, including inside Xvfb's namespace) and runs all smoke tests offline. If a check fails offline, the network is restored and retested to record whether `works_offline` is `true` or `false`. `get_install_guide` only serves steps that passed replay.
4. **GUI Operate-and-Check (`gui_operate.py`)**: To reach `function` level on desktop apps, the GUI operator views settled Xvfb screenshots (a numbered UI element list via MIT-licensed `cua-driver` is being trialled) and executes actions (`click`, `type`, `key`, `scroll`, `wait`) via `xdotool`. Each run injects a fresh random `{nonce}` word into the goal and input files. Afterward, **pickfit** (never the app) checks the result: reading the X11 clipboard, having the screen judge read back text from the final screenshot, or having `root` inspect a newly written regular file after stopping all user processes. Replay re-runs the recorded actions with a fresh nonce, falling back to the live operator loop if window coordinates shift. `TODO(verify: final count of GUI apps reaching install and function levels on Linux and macOS after 11/3 12:00 freeze)`.
5. **Web Apps with `browser-use` (P3.12 / P5.8 branch)**: For hosted `web_app` entries that require no account for core use and allow automation in `robots.txt`/ToS, a sandboxed browser driven by open-source `browser-use` (MIT) and Muse Spark verifies that the app loads (`install`), completes a core task with a checkable result (`function`), and reloads offline if it is a PWA (`works_offline`), while logging account walls, ads, third-party trackers, and whether user inputs leave the browser—without submitting side-effectful forms or registering accounts. `TODO(verify: final web_app profile count and verification breakdown after P5.8 merge)`.
6. **GPU Sandbox & Simulated Microphone (P3.13 branch)**: For tools that require a GPU or audio input, pickfit runs Modal GPU sandboxes (T4/L4 with virtual display) and a Linux virtual microphone that plays synthesized speech containing a fresh random word per run—passing only when that exact word appears in the tool's output. `TODO(verify: final GPU and simulated microphone verification counts after P3.13 merge)`.
7. **What "Unverified Because of Our Environment" Means**: The automated pipeline **never** marks a tool as `failed` (`failed` is reserved for human-confirmed broken artifacts such as an empty PyPI wheel). When a tool or advertised feature cannot be exercised because of sandbox limits, pickfit records a structured `UnverifiedReason` or `FeatureGap` (`needs_gpu`, `needs_hardware`, `model_too_large`, `needs_more_resources`, `needs_account`, `needs_service`, `needs_root`, `needs_container`, `macos_only`, `windows_only`, `apple_silicon_only`) and states plainly in both MCP responses and the web UI that *pickfit's test environment lacked that resource*, rather than claiming the software is broken.

---

## Why This Is Not RAG

A standard RAG pipeline retrieves text chunks from static documentation and paraphrases them. For long-tail software, that fails—across 328 passed verification runs in `docs/plan.md`, README instructions were wrong or incomplete 88 times (`readme_wrong`: missing flags, renamed binaries, undeclared build dependencies, or scripts requiring root). pickfit differs fundamentally from RAG:

1. **Active Agentic Execution, Not Passive Text Retrieval**: Instead of trusting README prose, pickfit's verification agent spins up a real sandbox, runs the installation, reads compiler/runtime errors, repairs broken steps, and tests advertised features.
2. **Deterministic Replay Ground Truth**: `get_install_guide` makes **zero model calls** (`matched_by: "rules"`). It serves only the exact command sequence that succeeded in a clean-room replay sandbox, paired with verified MCP tool lists and GUI screenshots.
3. **Closed-Loop Real-World Outcome Feedback**: When an agent reports `install_failed` or `first_run_failed` via `report_outcome` with a valid `rec_id`, `pickfit reverify` queues a fresh sandbox run and produces a `git diff` of fixed steps (holding any step that introduces unapproved package names or URLs for human review). Seven to 120 days after install, `get_install_guide`'s `check_in` prompts the agent to ask user consent before running read-only local checks (`command -v`, package manager single-tool queries, macOS `kMDItemLastUsedDate`) to report `still_using`, `replaced`, or `abandoned`—storing only coarse recency buckets (`this_week`, `this_month`, `older`, `unknown`) and never raw command output, file paths, or IP addresses.

---

## The Treasure Score: Quality and Popularity Scored Separately

Rather than ranking software by GitHub stars, formula `b3.v5` (`pickfit/score.py`) computes **Quality (`0–100`)** and **Popularity (`0–100`)** independently:

- **Quality (`0–100`)**: Weighted mean of six components (missing components drop out of the denominator and reduce `confidence`):
  - **Sandbox Verification (`40%`)**: Best passed run's category depth (`function` for CLI, `service` for MCP, `inference` for local AI) × install-action step tier (`≤3` actions: `1.0`, `4–6`: `0.85`, `>6`: `0.7`) × `0.85` per genuine `readme_wrong` fix.
  - **Installation Docs Rubric (`25%`)**: `muse-spark-1.3` grades the README against an 8-item rubric (`0/1/2` each); every non-zero item must cite a verbatim source quote verified in the source text.
  - **Maintenance (`10%`)**: Recency of last push (`0.35`), last release (`0.35`), and ≥2 releases in the past year (`0.30`).
  - **Responsiveness (`10%`)**: External issue close rate and mean time to close (when ≥2 external issues exist).
  - **Engineering Hygiene (`5%`)**: CI workflows, tests, OSI-approved license, changelog/release notes, and lockfile.
  - **Usage Outcomes (`10%+`)**: Activated once a tool accumulates ≥3 external `report_outcome` events (taking weight proportionally from the four non-sandbox components).
  - **Hard Caps**: Quality is capped at `30` if archived, `40` if human-confirmed `failed`, `50` if not an end-user tool kind, and `69` if `unverified`.
- **Popularity (`0–100`)**: Log-normalized mean of GitHub stars, forks, release downloads, monthly package downloads (npm, PyPI, crates.io), registry count, and top Hacker News story score relative to the 95th percentile of the category candidate pool, plus star velocity for repos ≥3 months old.
- **Treasure (`is_treasure` & `treasure_score`)**: A tool is marked a **Treasure** only if it is verified, achieves **`quality >= 80`**, and remains lesser-known with **`popularity <= 45`**. Treasures are ordered by `T = quality * (1 - popularity / 100)`.

---

## Data Sources and Licenses

Full third-party software, font, icon, and data attributions are documented in [`NOTICE`](NOTICE) and [`docs/source-terms.md`](docs/source-terms.md):

- **What pickfit uses**:
  - **GitHub REST API**: Repository metadata, releases, issues, and short verbatim quotes (≤300 chars) from READMEs and release notes cited as field evidence (each record lists source URLs; quoted text remains under the upstream project's license).
  - **Show HN**: Read via the Algolia HN Search API and official Hacker News API (MIT). Only story ID, HN URL, title, link, points, comment count, and timestamp are stored locally; post text and comments are never copied into records.
  - **Flathub AppStream Catalog**: Downloaded once per run from the flatpak repository catalog (`dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz`), whose metadata is under permissive AppStream-approved licenses (FSFAP, CC0, MIT, CC-BY, etc.).
  - **Homebrew & Homebrew Cask**: Definitions from `formulae.brew.sh` (`Homebrew/homebrew-cask`, BSD-2-Clause). Public 30d/90d/365d install counts are used solely as transient candidate sampling signals and are never stored or redistributed in profiles.
  - **Package Registries**: Public download counts from npm (`api.npmjs.org`), PyPI (`pypistats.org`), and `crates.io`.
  - **Direct Submissions & Web Apps**: Repositories submitted via `submit_software`, plus web apps whose `robots.txt` and Terms of Service permit automated access.
- **What is deliberately NOT used**:
  - **Product Hunt, AlternativeTo, and Reddit API**: Excluded because their Terms of Service prohibit scraping, building competing directories, or commercial/directory reuse without written permission.
  - **Flathub Website (`flathub.org`), Flathub HTTP API (`flathub.org/api`), and Flathub Install Statistics (`/stats`)**: Excluded because the website Terms and Conditions prohibit reproducing or scraping any portion of the service without written consent and do not license install statistics; pickfit uses upstream GitHub stars instead.
  - **`ecosyste.ms`, GitLab.com, and Codeberg**: Excluded from product code due to API bulk-collection terms and `robots.txt` restrictions.

---

## Evaluation

Before collecting any candidate repositories or writing any software profiles, we drafted and git-frozen a primary evaluation benchmark of **20 realistic software-seeking questions** (commit `5ac62ca` on 2026-10-28), followed by a secondary **B-suite of 12 questions** sampled with a pre-committed random seed from pre-hackathon public community threads on GitHub Discussions, Hacker News, and Stack Exchange (commit `dec4cb9`). The pre-registered protocol (`docs/plan.md` P6) compares **three isolated arms** running headless Claude Code (`claude-opus-5-5`, plus a secondary `claude-haiku-5-5` comparison) in clean temporary `HOME` directories (`--strict-mcp-config`) against frozen read-only Worker deployments (`TOOLS=readonly`): (1) **Control** (web search and fetch only, no MCP), (2) **Experimental — pickfit AI** (`pickfit-eval` with `muse-spark-1.3` matching), and (3) **Experimental — pickfit Rules-Only** (`pickfit-eval-rules` with `MATCH_MODE=off`, $0 model cost, ~5ms latency). Every recommended tool is evaluated both through blinded pairwise human/model grading (with Muse Spark Open as a third descriptive grader) and by executing the recommended installation commands and functional tasks inside clean, network-controlled Linux containers and macOS Tart VMs (L2 verification). Quantitative results across all three arms (including questions where pickfit loses) and system funnel metrics: `TODO(verify: results after P6)`.

---

## Limitations

- **Focused Long-Tail Scope**: Discovery targets lesser-known repositories (≤300 GitHub stars) across `dev_cli`, `local_ai`, `mcp_server`, and smaller batches of desktop GUI and web apps. When a well-known tool is a better fit, `find_software` can surface one `well_known_option` from model knowledge, explicitly labeled `verified: false` with no install guide.
- **Sandbox Hardware & OS Constraints**: Most automated runs execute on Linux (`ModalBox` gVisor/VM), with smaller verified subsets on macOS `arm64` (`Tart` VM, 66 tools as of 2026-11-01) and Windows `x86_64` (VirtualBox VM, 9 tools as of 2026-11-01). Tools requiring multi-GB weights, external paid accounts/API keys, root/containers, or specialized hardware cannot always be exercised in sandboxes and are labeled `unverified` or `not_checked` with explicit environment-limit reason codes.
- **Cold-Start Outcome Data**: Because software adoption is low-frequency and pickfit launched during this hackathon week, external `report_outcome` and 7-day `check_in` retention reports have not yet reached the ≥3 external-report threshold per tool needed to activate the `usage_outcomes` score component (0 external reports synced as of 2026-11-01).
- **Re-Verification & Query Boundaries**: Automated `pickfit reverify` currently re-runs failed reports in Linux sandboxes and holds modified steps for human review if they introduce new package names or URLs; `submit_software` in `main` currently accepts GitHub repositories (`web_app` URLs are on the P5.8 branch, and Threads links are not yet implemented); very broad Chinese queries with >300 passing candidates can occasionally hit the 25s Worker timeout and fall back to rules ranking (`degraded: true`), and rules-only Chinese matching relies on a static ~260-word lexicon.

---

## License

Third-party software dependencies, sandbox container packages, web fonts (`Bricolage Grotesque`, SIL Open Font License 1.1), icons (`Lucide`, ISC License), and public data sources are documented in [`NOTICE`](NOTICE). Original artwork for **Fitz the tailorbird** (`brand/mascot/`) was created during the hackathon. pickfit's own code is under the [MIT License](LICENSE).
