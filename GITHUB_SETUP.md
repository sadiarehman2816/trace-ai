# TRACE-AI — Freeze & GitHub Guide (v0.8-core-stable)

You're freezing the stable core and moving all future work onto branches so a
failed experiment can never break the working version.

## 1. One-time: create a PRIVATE GitHub repo

On github.com → New repository → name `trace-ai` → **Private** → Create.
Do NOT initialise with a README (you already have files).

## 2. Initialise git locally (run inside the trace_ai folder)

```
cd ~/Downloads/trace_ai
git init
git add .
git commit -m "TRACE-AI v0.8-core-stable — frozen core engine"
```

## 3. Connect to GitHub and push

Replace YOUR-USERNAME with your GitHub username:

```
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/trace-ai.git
git push -u origin main
```

## 4. Tag the stable release

```
git tag -a v0.8-core-stable -m "Frozen stable core"
git push origin v0.8-core-stable
```

Now `main` is your protected stable line. The tag is a permanent snapshot you
can always return to.

## 5. Branch discipline — never code on main

For every new piece of work, branch from main first:

```
git checkout main
git pull
git checkout -b hybrid-themes        # or reference-checker, pdf-highlighter, etc.
```

Work, commit, push the branch:

```
git add .
git commit -m "Add LLM theme synthesis"
git push -u origin hybrid-themes
```

When (and only when) a branch is tested and good, merge it into main:

```
git checkout main
git merge hybrid-themes
git push
```

If an experiment fails, just delete the branch — main is untouched:

```
git checkout main
git branch -D hybrid-themes
```

## Planned branches

| branch             | purpose                                   |
|--------------------|-------------------------------------------|
| `main`             | stable v0.8 — never code directly here    |
| `hybrid-themes`    | enable LLM theme synthesis (API key)      |
| `reference-checker`| citation / reference verification         |
| `pdf-highlighter`  | further PDF viewer improvements           |
| `premium-features` | gated capabilities                        |

## Before each commit

- Run the tests: `python3 -m tests.test_smoke` → must print ALL SMOKE TESTS PASSED
- Never commit an API key. `.gitignore` already excludes `.env` and `*.key`.
