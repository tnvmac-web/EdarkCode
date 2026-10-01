---
name: git-workflow
description: Use when committing, branching, or preparing a pull request.
tags: [git, workflow]
---

# Git workflow

## Before committing
1. `git status` and `git diff` — know exactly what you are about to commit.
2. Make sure you are not committing secrets, build output, or `.venv`.
3. Run the tests and the linter. Do not commit a red tree.

## Commit messages
- Subject line: imperative mood, under ~72 characters.
  `fix: reject paths that escape the workspace root`
- Body: explain *why*, not *what*. The diff already shows what changed.
- One logical change per commit. Do not mix a refactor with a behaviour change.

## Branching and PRs
- Branch from an up-to-date default branch.
- Rebase rather than merge when tidying a local branch; never rewrite shared history.
- The PR description should say: what changed, why, how it was verified, and
  anything left undone.

## Safety
- `git push --force` on a shared branch destroys other people's work. Use
  `--force-with-lease` and only on your own branch.
- Never commit credentials. If you do, rotate them — removing the file from the
  latest commit does not remove it from history.
