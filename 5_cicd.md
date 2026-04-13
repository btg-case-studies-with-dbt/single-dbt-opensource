# 5 — Team Workflow & CI/CD

## Before you start
- Completed Runbooks 3a, 3b, 3c, 3d, 4
- Stack running, Airflow DAGs running on schedule
- GitHub account, repo pushed to GitHub

---

## Pre-flight check

```bash
# Check 1 — yourname replaced in profiles.yml
grep "yourname" ~/.dbt/profiles.yml
# Must return nothing

# Check 2 — dbt shell function active
type dbt
# Must show: dbt is a shell function

# Check 3 — stack running
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
# All 5 containers Up

# Check 4 — self-hosted runner active
ls ~/actions-runner/
# Must show runner files including run.sh
```

---

## The full flow

```
Personal schema → Feature branch → Pull Request → CI runs → Code review
→ Merge to dev → PR to main → CI runs again → Production (Airflow)
```

| Step | Step Details | Git Commands | Command Explanation |
|---|---|---|---|
| 1a | New engineer Alex joins the team today | `git clone https://github.com/kanjasaha/btg-case-studies-with-dbt` | Copy the entire repo to Alex's laptop |
| 1b | Switch to the dev branch | `git checkout dev` | Switch to the dev branch |
| 1c | Get the latest changes from GitHub | `git pull origin dev` | Download the latest dev changes from GitHub |
| 1d | Task: add `revenue_tier` column to `customer_revenue_monthly.sql` — create feature branch | `git checkout -b feature/add-revenue-tier` | Create a new branch from dev and switch to it |
| 2a | Open `customer_revenue_monthly.sql`, add `revenue_tier` column logic, build and verify in pgAdmin under `dbt_alex_mart_gold` | `dbt build --target personal --select customer_revenue_monthly` | Build only `customer_revenue_monthly` in Alex's personal schema |
| 2b | Looks good — stage the changed file | `git add dbt/models/marts/revenue/customer_revenue_monthly.sql` | Stage only the changed model file |
| 2c | Save a snapshot of changes locally | `git commit -m "feat: add revenue_tier column to customer_revenue_monthly"` | Save changes locally with a descriptive message |
| 3 | Test against dev environment — simulate exactly what CI will run | `dbt build --select state:modified+ --defer --state ./prod-state/` | Build all modified models and their downstream dependents — same selector CI uses |
| 4a | Push branch to GitHub | `git push origin feature/add-revenue-tier` | Upload the feature branch to GitHub |
| 4b | Open PR to dev | `gh pr create --base dev --title "feat: add revenue_tier to customer_revenue_monthly"` | Ask team to review the new column before merging into dev |
| 5 | CI automatically runs — builds modified models and tests | Automatic — no command needed | GitHub Actions runs `dbt build --select state:modified+` — picks up `customer_revenue_monthly` and downstream models, runs all tests |
| 6a | Manager reviews — checks `revenue_tier` logic, test coverage, and CI passed | GitHub UI — click Merge | Human approves and merges `feature/add-revenue-tier` into dev |
| 6b | `pipeline_dev` triggers automatically | `pipeline_dev` Airflow DAG triggers | Airflow runs `dbt build --target dev` — `dev_mart_gold.customer_revenue_monthly` now has `revenue_tier` column |
| 7 | Coworker Maya follows the same process on her own task tomorrow | `git checkout dev` `git pull origin dev` `git checkout -b feature/her-task` | Maya gets the latest dev including Alex's `revenue_tier` change, starts her own feature branch |
| 8a | Release manager pulls latest dev and opens PR to main | `git checkout dev` `git pull origin dev` | Get latest dev — includes Alex's and Maya's merged changes |
| 8b | Open PR from dev to main | `gh pr create --base main --title "release: add revenue_tier and Maya's changes"` | Ask for final review before prod deployment |
| 9 | CI runs full test suite against main | Automatic — no command needed | GitHub Actions runs full CI — verifies `customer_revenue_monthly` with `revenue_tier` passes all tests against main |
| 10a | Release manager approves and clicks merge | GitHub UI — click Merge | Human approves — merges dev into main |
| 10b | `pipeline_daily` triggers automatically | `pipeline_daily` Airflow DAG triggers | Airflow runs `dbt build --target prod` — `prod_mart_gold.customer_revenue_monthly` in `prod_resource_utilization_postgres` now has `revenue_tier` column live in production |

Nobody runs `dbt build --target prod` manually. Ever.

---

## Git — day to day workflow

Always start from a clean dev branch before creating a feature branch:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git checkout dev
git fetch origin
git pull origin dev
```

Create a feature branch for your task:

```bash
git checkout -b feature/my-task
```

Make changes, commit by concern — not everything at once:

```bash
# Stage specific files
git add airflow/dags/pipeline_daily.py
git commit -m "feat: add pipeline_daily DAG"

git add dbt/dbt_project.yml
git commit -m "feat: add package schemas to dbt_project.yml"

# Review before pushing — confirm no profiles.yml or secrets
git status
```

Push your branch and open a PR to dev:

```bash
git push origin feature/my-task
gh pr create --base dev --title "feat: my task description"
```

**Never commit:** `dbt/profiles.yml` (passwords), `*.code-workspace` (machine-specific), `dbt/target/`, `dbt/dbt_packages/`.

**Never push directly to `dev` or `main`** — always use a PR.

---

## Branch setup

```bash
# Create dev branch if it doesn't exist
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
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
gh api --method POST repos/kanjasaha/btg-case-studies-with-dbt/actions/runners/registration-token \
  --jq .token

# Create runner folder and download
mkdir ~/actions-runner && cd ~/actions-runner

# Apple Silicon
curl -o actions-runner-osx-arm64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-osx-arm64-2.322.0.tar.gz
tar xzf ./actions-runner-osx-arm64.tar.gz

# Configure — replace TOKEN with token from above
./config.sh --url https://github.com/kanjasaha/btg-case-studies-with-dbt --token TOKEN
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

---

## Step 1 — GitHub Actions and branch protection

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
mkdir -p .github/workflows
touch .github/workflows/.gitkeep

# Enable branch protection on dev
gh api repos/kanjasaha/btg-case-studies-with-dbt/branches/dev/protection \
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

# Enable branch protection on main
gh api repos/kanjasaha/btg-case-studies-with-dbt/branches/main/protection \
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
gh secret set DBT_HOST     --body "localhost"                --repo kanjasaha/btg-case-studies-with-dbt
gh secret set DBT_PORT     --body "5432"                     --repo kanjasaha/btg-case-studies-with-dbt
gh secret set DBT_USER     --body "mds_user"                 --repo kanjasaha/btg-case-studies-with-dbt
gh secret set DBT_PASSWORD --body "mds_password"             --repo kanjasaha/btg-case-studies-with-dbt
gh secret set DBT_DBNAME   --body "btg_resource_utilization" --repo kanjasaha/btg-case-studies-with-dbt
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
      - 'dbt/models/**'
      - 'dbt/tests/**'
      - 'dbt/macros/**'
      - 'dbt/seeds/**'
      - 'dbt/snapshots/**'

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
          docker compose -f docker-compose.yml \
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
            docker compose -f docker-compose.yml \
              run --rm airflow-scheduler bash -c \
              "cd /opt/airflow/dbt && /usr/local/airflow/dbt_venv/bin/dbt build \
              --select state:modified+ \
              --defer \
              --state /opt/airflow/prod-state/ \
              --target ci \
              --profiles-dir ."
          else
            echo "No prod manifest — running full build"
            docker compose -f docker-compose.yml \
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
          path: dbt/target/manifest.json
          retention-days: 7
```

Slim CI: `state:modified+` builds only changed models and their downstream dependents. `--defer` reads unchanged upstream models from prod — no rebuild needed. Output lands in `ci_*` schemas, not prod.

Use `docker compose run` not plain `dbt` — the runner shell does not load `~/.zshrc`, so the `dbt` shell function is unavailable.

---

## Step 4 — Production workflow

On merge to main — GitHub Actions triggers Airflow `pipeline_daily` DAG which runs `dbt build --target prod`. GitHub Actions does NOT run dbt directly against prod.

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

jobs:
  trigger-airflow:
    name: dbt Production — trigger Airflow pipeline_daily
    runs-on: self-hosted
    steps:
      - name: Trigger pipeline_daily DAG
        run: |
          docker exec btg-airflow-scheduler \
            airflow dags trigger pipeline_daily

      - name: Wait for DAG completion
        run: |
          sleep 30
          docker exec btg-airflow-scheduler \
            airflow dags list-runs --dag-id pipeline_daily --limit 1

      - name: Save production manifest
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: dbt-manifest
          path: dbt/target/manifest.json
          retention-days: 7
```

Commit and push via feature branch:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git checkout -b feature/add-github-actions
git add .github/
git commit -m "add CI and production GitHub Actions workflows"
git push origin feature/add-github-actions
gh pr create --base dev --title "feat: add GitHub Actions CI/CD workflows"
```

---

## When CI fails — recovery cycle

```
Developer pushes to feature branch
→ PR opened → CI triggers (dbt build --select state:modified+ --defer --state prod-state/)
→ Model fails → CI status = ERROR or FAIL → PR merge button locked
→ Developer fixes code, pushes again → CI re-runs automatically
→ CI passes → PR approved → merge to dev
→ CD triggers on merge to main → Airflow pipeline_daily triggers
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
      - 'dbt/models/**'

jobs:
  cleanup:
    runs-on: self-hosted
    steps:
      - name: Drop CI schemas
        run: |
          docker compose -f docker-compose.yml \
            run --rm airflow-scheduler bash -c "
            psql -h postgres -U \$DBT_USER -d \$DBT_DBNAME -c '
            DROP SCHEMA IF EXISTS ci_staging_silver CASCADE;
            DROP SCHEMA IF EXISTS ci_mart_gold CASCADE;
            DROP SCHEMA IF EXISTS ci_seeds CASCADE;
            DROP SCHEMA IF EXISTS ci_snapshots CASCADE;
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

**`Could not find profile named 'resource_utilization_postgres'`:**
The `dbt/profiles.yml` was not committed or gitignored. Force-add it:
```bash
git add -f dbt/profiles.yml
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
Runbook 5 complete — CI/CD pipeline is live. You are done.
