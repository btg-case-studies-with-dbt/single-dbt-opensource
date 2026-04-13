# 5 — Team Workflow & CI/CD

## Before you start
- Completed Runbooks 3a, 3b, 3c, 4
- Stack running, Airflow pipeline running on schedule
- GitHub account, repo pushed to GitHub

---

## Pre-flight check

```bash
# Check 1 — yourname replaced in profiles.yml
grep "yourname" dbt/profiles.yml
# Must return nothing

# Check 2 — dbt shell function active
type dbt
# Must show: dbt is a shell function

# Check 3 — stack running
docker compose ps
# All 5 containers Up

# Check 4 — self-hosted runner active
ls ~/actions-runner/
# Must show runner files including run.sh
# If runner not running: cd ~/actions-runner && ./run.sh → confirm "Listening for Jobs"
```

---

## The full flow

```
Personal schema → Feature branch → Pull Request → CI runs → Code review
→ Merge to dev → PR to main → CI runs again → Production (Airflow)
```

| Step | Who |
|---|---|
| Write code, test locally | You |
| Create branch, push, open PR | You |
| CI runs, dev build runs | GitHub Actions (automatic) |
| Code review | Teammate |
| Merge to main, prod deployment | Airflow (automatic) |

Nobody runs `dbt build --target prod` manually. Ever.

---

## Git — push code to GitHub

```bash
cd ~/Documents/btg-case-studies

# Sync local with remote before starting any work
git fetch origin
git pull origin dev           # fetch + merge dev into local

# Add to .gitignore before staging
echo "resource-utilization/dbt/models/staging/sources.yml.backup" >> .gitignore
echo "resource-utilization/*.html" >> .gitignore
echo "*.code-workspace" >> .gitignore

# Stage
git add resource-utilization/airflow/dags/pipeline_daily.py
git add resource-utilization/dbt/models/
git add resource-utilization/dbt/seeds/
git add resource-utilization/dbt/snapshots/
git add resource-utilization/dbt/dbt_project.yml
git add .gitignore

# Review — confirm no profiles.yml, no .code-workspace, no backup files
git status

git commit -m "add dbt models, DAG, seeds, snapshots"
git push origin main
```

**Never commit:** `dbt/profiles.yml` (passwords), `*.code-workspace` (machine-specific), `*.html` files in resource-utilization/.

---

## Branch setup

```bash
# Create dev branch if it doesn't exist
cd ~/Documents/btg-case-studies
git checkout main && git pull
git checkout -b dev
git push origin dev
```

Branch rules: `main` = production, `dev` = shared integration, `feature/*` = your working branch. Never push directly to `main` or `dev`.

---

## Step 0 — Set up self-hosted runner

Cloud runners cannot reach `localhost:5432` — self-hosted runner required.

```bash
# Install GitHub CLI
brew install gh
gh auth status
# Must show: Logged in to github.com — scopes must include repo and workflow

# Get registration token (expires in 1 hour)
gh api --method POST repos/YOUR-USERNAME/btg-case-studies/actions/runners/registration-token \
  --jq .token

# Create runner folder and download
mkdir ~/actions-runner && cd ~/actions-runner

# Apple Silicon
curl -o actions-runner-osx-arm64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-osx-arm64-2.322.0.tar.gz
tar xzf ./actions-runner-osx-arm64.tar.gz

# Configure — replace TOKEN with token from above
./config.sh --url https://github.com/YOUR-USERNAME/btg-case-studies --token TOKEN
# Press Enter for all three prompts (accept defaults)
# Must show: Runner successfully added + Runner connection is good
```

Start runner in a **dedicated terminal tab** — leave it open:

```bash
cd ~/actions-runner
./run.sh
# Must show: Listening for Jobs
```

**Verify:** GitHub → Settings → Actions → Runners — Mac appears with green dot, status Idle.

Commit CI-safe `profiles.yml`:

```bash
cd ~/Documents/btg-case-studies

# Force-add (overrides .gitignore)
git add -f resource-utilization/dbt/profiles.yml
git status resource-utilization/dbt/profiles.yml
# Must show: new file: resource-utilization/dbt/profiles.yml

git commit -m "add CI-safe profiles.yml for GitHub Actions"
git push origin feature/test-ci
```

CI-safe `profiles.yml` uses `env_var()` references — no hardcoded passwords.

---

## Step 1 — GitHub Actions and branch protection

```bash
cd ~/Documents/btg-case-studies
mkdir -p .github/workflows
touch .github/workflows/.gitkeep

# Enable branch protection on main
gh api repos/YOUR-USERNAME/btg-case-studies/branches/main/protection \
  --method PUT \
  --header "Content-Type: application/json" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["dbt CI — build modified models and run tests"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null
}
EOF
```

Use `--input -` with heredoc, not `--field` — the branch protection API requires JSON objects.

---

## Step 2 — Add GitHub Secrets

```bash
gh secret set DBT_HOST     --body "localhost"                  --repo YOUR-USERNAME/btg-case-studies
gh secret set DBT_PORT     --body "5432"                       --repo YOUR-USERNAME/btg-case-studies
gh secret set DBT_USER     --body "mds_user"                   --repo YOUR-USERNAME/btg-case-studies
gh secret set DBT_PASSWORD --body "mds_password"               --repo YOUR-USERNAME/btg-case-studies
gh secret set DBT_DBNAME   --body "btg_resource_utilization"   --repo YOUR-USERNAME/btg-case-studies
```

`DBT_HOST=localhost` works because the self-hosted runner is a process on your Mac — localhost hits Docker PostgreSQL directly.

---

## Step 3 — CI workflow

```bash
code .github/workflows/dbt_ci.yml
```

```yaml
# .github/workflows/dbt_ci.yml
name: dbt CI
on:
  pull_request:
    branches: [dev, main]
    paths:
      - 'resource-utilization/dbt/models/**'
      - 'resource-utilization/dbt/tests/**'
      - 'resource-utilization/dbt/macros/**'
      - 'resource-utilization/dbt/seeds/**'
      - 'resource-utilization/dbt/snapshots/**'

env:
  DBT_HOST:     ${{ secrets.DBT_HOST }}
  DBT_PORT:     ${{ secrets.DBT_PORT }}
  DBT_USER:     ${{ secrets.DBT_USER }}
  DBT_PASSWORD: ${{ secrets.DBT_PASSWORD }}
  DBT_DBNAME:   ${{ secrets.DBT_DBNAME }}

jobs:
  dbt-ci:
    name: dbt CI — build modified models and run tests
    runs-on: self-hosted
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Install dbt packages
        run: |
          docker compose -f resource-utilization/docker-compose.yml \
            run --rm airflow-scheduler bash -c \
            "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt deps"

      - name: Download production manifest for Slim CI
        uses: actions/download-artifact@v4
        with:
          name: dbt-manifest
          path: ./prod-state/
        continue-on-error: true
        # First run will not have a manifest — full build runs instead

      - name: Run Slim CI — modified models only
        run: |
          if [ -f "prod-state/manifest.json" ]; then
            echo "Prod manifest found — running Slim CI"
            docker compose -f resource-utilization/docker-compose.yml \
              run --rm airflow-scheduler bash -c \
              "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt build \
              --select state:modified+ \
              --defer \
              --state /opt/airflow/prod-state/ \
              --target ci \
              --profiles-dir ."
          else
            echo "No prod manifest — running full build"
            docker compose -f resource-utilization/docker-compose.yml \
              run --rm airflow-scheduler bash -c \
              "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt build \
              --target ci \
              --profiles-dir ."
          fi

      - name: Save manifest for next CI run
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: dbt-manifest
          path: resource-utilization/dbt/target/manifest.json
          retention-days: 7
```

Slim CI: `state:modified+` builds only changed models and their downstream dependents. `--defer` reads unchanged upstream models from prod — no rebuild needed. Output lands in `ci_*` schemas, not prod.

Use `docker compose run` not plain `dbt` — the runner shell does not load `~/.zshrc`, so the `dbt` shell function is unavailable.

---

## Step 4 — Production workflow

```bash
code .github/workflows/dbt_prod.yml
```

```yaml
# .github/workflows/dbt_prod.yml
name: dbt Production
on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  DBT_HOST:     ${{ secrets.DBT_HOST }}
  DBT_PORT:     ${{ secrets.DBT_PORT }}
  DBT_USER:     ${{ secrets.DBT_USER }}
  DBT_PASSWORD: ${{ secrets.DBT_PASSWORD }}
  DBT_DBNAME:   ${{ secrets.DBT_DBNAME }}

jobs:
  dbt-prod:
    name: dbt Production — full build and test
    runs-on: self-hosted
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Install dbt packages
        run: |
          docker compose -f resource-utilization/docker-compose.yml \
            run --rm airflow-scheduler bash -c \
            "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt deps"

      - name: Run full production build
        run: |
          docker compose -f resource-utilization/docker-compose.yml \
            run --rm airflow-scheduler bash -c \
            "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt build \
            --target prod \
            --profiles-dir ."

      - name: Save production manifest
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: dbt-manifest
          path: resource-utilization/dbt/target/manifest.json
          retention-days: 7
```

The prod workflow saves `manifest.json` after each successful run. CI downloads it on the next PR to enable Slim CI.

Commit and push:

```bash
cd ~/Documents/btg-case-studies
git add .github/
git commit -m "add CI and production GitHub Actions workflows"
git push origin dev
```

---

## When CI fails — recovery cycle

```
Developer pushes to feature branch
→ PR opened → CI triggers (dbt build --select state:modified+ --defer --state prod-state/)
→ Model fails → CI status = ERROR or FAIL → PR merge button locked
→ Developer fixes code, pushes again → CI re-runs automatically
→ CI passes → PR approved → merge to dev
→ CD triggers on merge to main → dbt build --target prod
→ Prod manifest saved → available for next CI cycle
```

**`fail` vs `error` in run_results.json — not the same thing:**

| Status | Meaning |
|---|---|
| `fail` | Test ran, assertion failed — e.g. `not_null` found nulls |
| `error` | Node could not execute — SQL syntax error, missing relation, compile error |

A model `error` skips all downstream dependents. A test `fail` does not block downstream models unless `severity: error` is set. Use result selectors to target each:

```bash
dbt build --select result:error+   # retry errored models + downstream
dbt build --select result:fail     # retry failed tests only
```

---

```bash
cd ~/Documents/btg-case-studies
git checkout dev
git pull
git checkout -b feature/add-revenue-tier

# Make a change — add revenue_tier to customer_revenue_monthly
code resource-utilization/dbt/models/marts/revenue/customer_revenue_monthly.sql

git add resource-utilization/dbt/
git commit -m "add revenue_tier classification to customer_revenue_monthly"
git push origin feature/add-revenue-tier
```

---

## Step 6 — Open a Pull Request

```bash
gh pr create \
  --base dev \
  --title "Add revenue_tier to customer_revenue_monthly" \
  --body "Adds Platinum/Gold/Silver/Bronze tier classification based on monthly net revenue."
```

---

## Step 7 — Watch CI run

```bash
# Watch from terminal
gh run watch

# Or check status
gh run list --limit 5
```

CI runs `state:modified+` — only `customer_revenue_monthly` and its downstream dependents rebuild. If any test fails, the PR merge button stays locked.

---

## Step 8 — Merge to dev then main

```bash
# After CI passes and review approved
gh pr merge --squash

# Open PR from dev to main for release
git checkout dev && git pull
gh pr create \
  --base main \
  --title "Release: add revenue_tier" \
  --body "Merging dev to main — triggers prod deployment."

# After CI passes on the dev→main PR
gh pr merge --squash
# prod workflow triggers automatically — dbt build --target prod runs
```

---

## Cleanup workflow — drop CI schemas after PR closes

```bash
code .github/workflows/dbt_cleanup.yml
```

```yaml
name: dbt CI — cleanup schemas
on:
  pull_request:
    types: [closed]
    paths:
      - 'resource-utilization/dbt/models/**'

jobs:
  cleanup:
    runs-on: self-hosted
    steps:
      - name: Drop CI schemas
        run: |
          docker compose -f resource-utilization/docker-compose.yml \
            run --rm airflow-scheduler bash -c "
            psql -h postgres -U \$DBT_USER -d \$DBT_DBNAME -c '
            DROP SCHEMA IF EXISTS ci_staging_silver CASCADE;
            DROP SCHEMA IF EXISTS ci_mart_gold CASCADE;
            '"
        env:
          DBT_USER:   ${{ secrets.DBT_USER }}
          DBT_DBNAME: ${{ secrets.DBT_DBNAME }}
```

Always use `DROP SCHEMA IF EXISTS` — if CI failed before creating schemas, a plain `DROP` errors and marks the cleanup job failed.

---

## Troubleshooting

**`dbt: command not found` in CI:**
The runner shell does not load `~/.zshrc`. Use `docker compose run` with the full binary path `/usr/local/airflow/dbt_venv/bin/dbt`.

**`Could not find profile named 'resource_utilization'`:**
The CI-safe `profiles.yml` was not committed. Run:
```bash
git add -f resource-utilization/dbt/profiles.yml
git commit -m "add CI-safe profiles.yml"
git push
```

**CI fails with "relation does not exist" on relationship test:**
A staging `schema.yml` has a `relationships` test pointing to a mart table that doesn't exist yet in the CI schema. Move the test to the mart `schema.yml`.

**Runner not picking up jobs:**
```bash
cd ~/actions-runner && ./run.sh
# Must show: Listening for Jobs
# Check GitHub → Settings → Actions → Runners — must show Idle (green dot)
```

**Branch protection blocking push to main:**
This is correct — open a PR from dev to main instead of pushing directly.

---

## Next
Continue to **Runbook 4 — Airflow** if not already completed, or you are done.
