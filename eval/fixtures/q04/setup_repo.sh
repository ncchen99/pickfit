#!/bin/sh
# Create developer A's starting repository for eval q04.
#
#   sh setup_repo.sh REPO_DIR
#
# The repo has one commit (README.md, app.sh) on branch main. It has no
# .gitignore, so ignoring .env is left to the answer's steps. The plaintext
# .env is written afterwards by make_env.py (untracked at that point).
# Uses the git identity already configured in the sandbox; if none is set,
# sets a repo-local identity for developer A.
# POSIX sh + git.
set -eu
if [ $# -ne 1 ]; then
  echo "usage: setup_repo.sh REPO_DIR" >&2
  exit 2
fi
repo=$1
if [ -e "$repo" ]; then
  echo "setup_repo: $repo already exists" >&2
  exit 2
fi
mkdir -p "$repo"
cd "$repo"
git init -q
git symbolic-ref HEAD refs/heads/main
if ! git config user.email >/dev/null 2>&1; then
  git config user.name "Developer A"
  git config user.email "dev-a@example.test"
fi
cat > README.md <<'EOF'
# team-app

Small service used by the q04 evaluation. Settings come from a .env file.
EOF
cat > app.sh <<'EOF'
#!/bin/sh
# Reads its settings from the environment (see .env).
echo "team-app starting"
EOF
chmod +x app.sh
git add README.md app.sh
git commit -q -m "Initial commit"
echo "setup_repo: created $repo at $(git rev-parse --short HEAD)"
