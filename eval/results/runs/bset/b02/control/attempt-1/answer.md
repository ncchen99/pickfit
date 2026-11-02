I'd switch to **[git-spice](https://abhinav.github.io/git-spice/)** (`gs`). It's a free, open-source CLI built for the same workflow you use Graphite for: you create stacked branches, it restacks them when a lower branch changes, it opens one PR per branch with the right base, and it updates those PRs. It doesn't need a web dashboard, an account or a paid plan. It works with GitHub and GitLab, and its commands are close enough to `gt` that you'll pick it up in an afternoon.

I'm assuming you're on GitHub with a Mac and Homebrew. I haven't checked Graphite's pricing change myself. A third-party comparison from this year still lists a free Hobby tier with the CLI, so it's worth confirming whether you really lose CLI access before you switch.

## git-spice: install and first run

**Install**
```sh
brew install git-spice
```
Ghostscript also installs a command called `gs`. If you have it, the two will clash. Check the git-spice install docs for the alternate binary name, or set up an alias.

**First run, inside a repo**
```sh
gs repo init          # pick trunk (main) and remote (origin)
gs auth login         # GitHub login: browser/device flow, a token, or reuse the gh CLI
```

**Bring over your existing Graphite stacks.** Your branches and PRs are plain git and GitHub objects, so nothing is lost. Check out each branch from the bottom of the stack up and run:
```sh
gs branch track       # (gs bt) it'll ask for or guess the base branch
```
Starting new stacks may be easier than migrating ones that are nearly done. You can finish those with `gt` while you still have it.

**Daily commands mapped to `gt`**

| What you do | Graphite | git-spice |
|---|---|---|
| New branch on top of the current one | `gt create` | `gs branch create name` (`gs bc`) |
| Commit and restack the branches above | `gt modify` | `gs commit create -m ...` (`gs cc`) / `gs commit amend` (`gs ca`) |
| Push and create/update the PRs | `gt submit --stack` | `gs stack submit` (`gs ss`); one branch: `gs bs` |
| Pull trunk and clean up merged branches | `gt sync` | `gs repo sync` (`gs rs`) |
| Rebase the stack | `gt restack` | `gs stack restack` (`gs sr`), `gs upstack restack` (`gs usr`) |
| Move around the stack | `gt up/down/top/bottom` | `gs up` / `gs down` / `gs top` / `gs bottom` |
| See the stack | `gt log short` | `gs log short` (`gs ls`), `gs ll` |

Run `gs --help` or see the docs for the full list. Command names and aliases sometimes change between releases.

## Other options

- **Aviator's `av` CLI.** Open source and also branch-per-PR, with commands like `av stack sync` and `av pr`. It's the closest match to Graphite after git-spice. It only supports GitHub.
- **git-town** (`brew install git-town`). Mature, and it works with GitHub, GitLab, Bitbucket and Gitea. It handles syncing stacks very well (`git town append`, `git town sync`). PR creation (`propose`) is lighter-weight than Graphite's.
- **Commit-per-PR tools: `spr` (ejoffe/spr), `ghstack`.** You keep one branch and each commit becomes its own PR. This is a different way of working. Try it only if you like it, and note that ghstack PRs don't merge cleanly through the normal GitHub UI.
- **Jujutsu (`jj`) or Sapling (`sl`).** Version-control tools that work with git repos and make stacks feel native. jj especially makes rebasing a stack almost free. Of everything here, this would change your workflow the most.
- **GitHub's native stacked PRs.** Reportedly entered private preview in April 2026 with a waitlist. That claim comes from a vendor's comparison, so check it yourself. Keep an eye on it, but don't plan around it yet.

## If you'd rather use plain git and a few scripts

Modern git covers much of what Graphite does:

1. **`rebase.updateRefs`** (git 2.38 or newer). This handles restacking. Rebase the top branch of the stack onto `main` and git moves every branch in between with it:
   ```sh
   git config --global rebase.updateRefs true
   git config --global rerere.enabled true   # remembers how you resolved repeated conflicts
   git checkout top-of-stack && git rebase main
   ```
2. **Pushing.** Loop over the branches with `git push --force-with-lease origin <branch>`.
3. **PRs.** Use `gh pr create --base <parent-branch> --head <branch>` for each branch. After the bottom PR merges, use `gh pr edit <n> --base main` to retarget the next one.

Plain git is missing two things Graphite gives you. First, it doesn't record which branch is each branch's parent, so you'd need a naming convention or a small file to track that. Second, it won't clean up automatically after a squash-merge. You'd soon be writing those yourself, and git-spice already does both. My suggestion is to try git-spice first and fall back to scripts only if you want zero tooling.

Sources:
- [git-spice docs](https://abhinav.github.io/git-spice/)
- [LinuxLinks – git-spice listing](https://www.linuxlinks.com/tag/pull-request/)
- [Smithery – git-spice skill](https://smithery.ai/skills/alexeldeib/git-spice)
- [DEV – Graphite alternatives in 2026](https://dev.to/pyor/graphite-alternatives-in-2026-an-honest-comparison-2p52)
- [GitHub stacked PRs vs Graphite vs Origin](https://www.learncursor.dev/compare/github-stacked-prs-vs-graphite-vs-origin)
- [Toolradar – Graphite alternatives](https://toolradar.com/tools/graphite/alternatives)
- [ToolQuestor – open-source Graphite alternatives](https://toolquestor.com/open-source/alternative/graphite)