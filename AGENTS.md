# Repository instructions

ai-dev-digest collects official announcements about AI development and shows them as a daily digest. The idea and its requirements are in yutotamura55/my-software-ideas#21.

## Merging pull requests

The assistant may merge a pull request into the repository's default branch (check it with `gh repo view --json defaultBranchRef`) itself when all of these hold:

1. At least one CI check ran on the pull request's head commit, and every check passed. When CI cannot run, or no check ran, do not merge.
2. The self-review and an independent review by a model of a different family are done, their Important findings are fixed, and the fixes were reviewed again.
3. The pull request targets the default branch. A pull request built on another pull request's branch waits until that one is merged and its base is changed to the default branch.
4. The change is not "critical risk" (below).
5. Items 1, 2, and 4 apply to the pull request's current head commit. After any new commit, redo them. Merge with `gh pr merge --match-head-commit <that commit>` (on older gh, `gh api -X PUT repos/<owner>/<repo>/pulls/<number>/merge -f sha=<that commit>`) so that only the judged revision is merged.

Choices listed under "確認してほしいこと" in the pull request body are merged as the assistant chose them; the user reviews them after the merge and changes them in a new pull request. A choice that a revert cannot undo makes the change critical risk.

A change is **critical risk** when it cannot be undone, harms people or money outside the repository, could break without any test noticing, or changes the safeguards themselves. In particular:

- payments, billing, or anything that costs money;
- authentication, authorization, sessions, rate limits, or cryptography;
- destructive changes to persistent data or its formats (dropping, renaming, or retyping columns or tables, bulk updates or deletes, backup and restore formats); adding a column or table only is not;
- production infrastructure, deployment, or secret and environment settings;
- publishing a release or changing signing;
- safeguards: CI workflows, branch protection, `AGENTS.md` and other agent rules, agent permissions;
  One change is exempt: increasing `fail_under` in `backend/pyproject.toml` or the coverage `thresholds` in `frontend/vitest.config.mts` to the coverage percentage (two decimals, truncated) that a successful full run of `scripts/check.sh` reported, as "Checks before committing" requires, without narrowing the test or coverage scope and without changing any other check setting. It tightens the check and involves no judgment. Lowering it, or any other change to the check configuration, is a change to a safeguard (the user decided this for shipkeep on 2026-11-04, and this repository uses the same rules);
- handling of secrets or personal data, and history rewriting;
- irreversible external operations (sending messages to other people, deleting external resources, changing repository visibility);
- license or other legal texts;
- a new dependency, unless all of these hold: it exists in the official registry under exactly that name; it is established and maintained; its license is compatible; it runs no install script, or its script was read and found safe; its version and hash are pinned in the lockfile; and it passes the dependency audit. Lockfile-only changes count as dependency changes;
- a major dependency update, unless every breaking change in its changelog was traced to the code that uses it and verified by tests or by running it. When that investigation is large, do the update in a separate Issue.

Judge the risk as the highest of three judgments, none of which can lower another: the path and content rules, the implementing agent, and the different-family reviewer, which must give file, line, and reason. The path and content rules come from the maintainer's `pr_risk.py`, which lives outside this repository; when it is not available, check every changed path (both sides of a rename) and the changed lines of every file, including migrations and lockfiles, against the list above by hand, and say so in the pull request body. When the reviewer cannot run, treat the change as critical risk. Write the three judgments in the pull request body. When in doubt, treat the change as critical risk.

Leave a critical-risk pull request for the user to merge, and say why at the top of its body. Only an explicit request from the user to merge that specific pull request authorizes the assistant to merge it; general instructions such as "continue", "proceed", "OK", 「続けてください」, or 「進めてください」 do not.

Never push directly to the default branch, enable auto-merge, enqueue a pull request, or bypass branch protection (for example with `gh pr merge --admin`). Use the merge method this repository already uses. After merging, confirm that CI on the default branch passed and, where a merge deploys to production, that the deployment succeeded; if either fails, open a revert pull request and merge it under the same rules. Report every merged pull request to the user with its URL, its open choices, and the risk judgments.

## Branches

- Create one branch per Issue from the latest `origin/main`, named `feat/<issue-number>-<short-purpose>`, `fix/<issue-number>-<short-purpose>`, or `chore/<issue-number>-<short-purpose>`.
- Keep a branch focused on one Issue.

## Checks before committing

- Run `scripts/check.sh` in the dev container before each commit, and commit only when it passes. README "開発" shows how. It runs every check that CI runs: Ruff (format, lint, security rules), mypy strict, vulture, pytest with coverage against the Firestore emulator, pip-audit, Prettier, ESLint, `tsc --noEmit`, Knip, Vitest with coverage, npm audit, hadolint, ShellCheck, actionlint, zizmor, Semgrep CE, and diff-cover for the lines changed since `origin/main`.
- Do not silence a failure with a suppression comment or by relaxing the configuration. When an exception is unavoidable, explain it in a code comment and in the pull request.
- When tests raise coverage, raise the floor (`fail_under` in `backend/pyproject.toml`, `thresholds` in `frontend/vitest.config.mts`) to the new measured value; never lower it to make a change pass.

## Using the shipkeep skills

This repository is developed with the shipkeep skills (yutotamura55/shipkeep) and is their first real trial.

- `shipkeep-quality-tools`: when adding or changing quality tools (formatter, linter, type checker, tests and coverage, dependency audit, CI).
- `shipkeep-publish-check`: before the first pull request of a feature that adds files, settings, or secrets handling, and before each release.
- `shipkeep-refactor`: after the minimum feature (#2) and deployment (#3), to restructure files that change often and have grown complex.

When a skill's steps are missing something or are wrong, keep working and fill the gap by hand, then record it as a comment on the shipkeep Issue: yutotamura55/shipkeep#9 for `shipkeep-quality-tools`, yutotamura55/shipkeep#10 for `shipkeep-refactor`, and a new shipkeep Issue for `shipkeep-publish-check`. Say what you tried to do, which step fell short and where, and how you filled the gap. Fix the skill in a separate shipkeep pull request, never in this repository.

## Rules specific to this repository

- This repository is public. Do not write personal information (email addresses other than the GitHub noreply address, local user names, local paths) or business information in code, tests, commits, Issues, or pull requests.
- Never commit secrets. Put local values in `.env` (ignored by Git; `.env.example` lists the names). Pass the LLM API key and GCP credentials as environment variables.
- Write code comments and docstrings in Japanese. Text that a program prints (log messages, errors) stays in English.
- Read `frontend/AGENTS.md` before changing the frontend: this Next.js version differs from older ones, and its documentation is in `frontend/node_modules/next/dist/docs/`.
