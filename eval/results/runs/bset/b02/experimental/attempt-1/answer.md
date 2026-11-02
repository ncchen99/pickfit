I recommend **git-spice**. It's the closest free replacement for how you use Graphite. Like `gt`, it tracks each branch's parent, restacks the branches above when you change one, and opens one PR per branch with links to the rest of the stack. It's open source (GPL-3.0), runs locally, needs no account or server beyond your GitHub login, and works on macOS.

I'm assuming you're on macOS with GitHub and want to keep working one branch per PR, the way you do with `gt`.

A note on pricing: I couldn't confirm the "$100/month for 5 seats minimum" on Graphite's own site. Third-party pricing sites list per-seat Starter and Team plans, and the 5-seat language appears in an older Graphite FAQ. So check [Graphite's official pricing](https://withgraphite.notion.site/External-FAQ-Updates-to-Graphite-pricing-plans-2abdc87583e348989936b039df30e825) before you cancel, in case a cheaper solo plan exists.

## git-spice: install and first run

```bash
# Install (Homebrew core)
brew install git-spice

# The docs use "gs" as shorthand. Note: if Ghostscript is installed, it also uses "gs".
# An alias in ~/.zshrc takes precedence in interactive shells:
alias gs=git-spice

# In your repo (once per repo): choose the trunk branch and remote
cd your-repo
gs repo init

# Log in to GitHub (choose OAuth, a token, or reuse the gh CLI's login)
gs auth login
```

Your usual Graphite commands translate like this:

| Graphite | git-spice |
|---|---|
| `gt create -m "msg"` | `gs branch create feat1` (`gs bc`). Or use `git checkout -b feat1` followed by `gs branch track` |
| `gt modify` | `gs commit create -m ...` / `gs commit amend` (restacks the branches above for you) |
| `gt restack` | `gs stack restack` (or `gs branch restack` for one branch) |
| `gt submit --stack` | `gs stack submit` (`gs ss`), or `gs branch submit` for one branch |
| `gt sync` | `gs repo sync` (pulls trunk, removes branches that were merged) |
| `gt log short` / `up` / `down` | `gs log short` (`gs ls`), `gs up`, `gs down` |

A first task to try: in a scratch repo, run `gs bc a`, commit, run `gs bc b`, commit, then `gs ss`. You should get two PRs, with b's PR targeting a's branch. Next, amend something in `a` and confirm that `b` gets restacked.

To migrate your existing Graphite stacks: as far as I know, git-spice can't read Graphite's metadata. Check out each branch from the bottom of the stack up and run `gs branch track`, which records each branch's parent. Easiest is to switch once your current stacks have merged.

## Other options

- **[git-town](https://www.git-town.com/)** (`brew install git-town`): Free and mature. Commands include `git town hack`/`append` to create branches, `sync` to update them, and `propose` to open PRs. It works with branches and pushes a sync-first workflow, but submitting a whole stack in one step is clunkier than in git-spice.
- **av** from Aviator (`brew install aviator-co/tap/av`): Open-source CLI, also very close to Graphite: `av branch`, `av sync`, `av pr`. Aviator's paid service is optional.
- **spr** (`brew install ejoffe/tap/spr`) or **ghstack**: Here each *commit* becomes its own PR. You keep one local branch and run `git spr update`. That suits you if you like one commit per PR, but it's a different workflow from Graphite's.
- **Sapling** (`sl pr submit`) or **Jujutsu (jj)**: Good at stacking, but they replace the git client itself. That's a bigger change than you need.

## If you just want scripts

Plain git now covers most of the restacking:

```bash
git config --global rebase.updateRefs true   # Git ≥ 2.38
```

With this setting, rebasing the top branch of a stack (`git rebase -i main` from the top) also moves every branch below it. Push the stack with `git push --force-with-lease origin a b c`. Then open the PRs with `gh pr create --base a --head b`, and so on. Plain git can't remember which branch is whose parent, keep PR targets right after merges, or add the stack links to PR descriptions. That's the work git-spice or git-town saves you.

A note on how I checked these: pickfit (a recommendation service I queried) has no tested options for stacked branches. It named git-town but hasn't verified it. I checked git-spice's install method and commands in its docs. The other tools' commands come from my general knowledge and haven't been checked. I didn't run anything on your machine.

Sources:
- [git-spice docs](https://abhinav.github.io/git-spice/)
- [git-spice install page](https://abhinav.github.io/git-spice/start/install/)
- [Graphite pricing FAQ](https://withgraphite.notion.site/External-FAQ-Updates-to-Graphite-pricing-plans-2abdc87583e348989936b039df30e825)
- [PricingSaaS – Graphite](https://pricingsaas.com/companies/graphite)
- [Costbench – Graphite price history](https://costbench.com/software/ai-code-review/graphite/price-history/)