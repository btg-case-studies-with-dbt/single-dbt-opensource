# 2 — Project Setup

## Before you start
Complete Runbook 1 first. Your stack must be running — all containers showing `Up`:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
```

All 5 containers must show `Up`: `btg-airflow-scheduler`, `btg-airflow-webserver`, `btg-pgadmin`, `metabase`, `postgres`. If any show `Exit` — go back to Runbook 1 troubleshooting before continuing.

---

## The medallion architecture

| Schema | Layer | What lives here | Who writes tables |
|---|---|---|---|
| `raw_bronze` | Bronze | Raw data exactly as it arrived — never modified | Ingestion scripts, Airflow DAGs |
| `seeds` | Seeds | Static CSV lookup tables | `dbt seed` only |
| `staging_silver` | Silver | Cleaned, standardized data | dbt models only |
| `staging_silver_ds` | Silver DS | Data science model outputs | Data scientists only |
| `mart_gold` | Gold | Business-ready aggregations and metrics | dbt models only |

**The most important rule — bronze is append-only.** Bronze data is never updated or deleted. New data is always added as new rows. You always have a full history and can always rebuild downstream from bronze.

```
btg_resource_utilization (your PostgreSQL database)
├── raw_bronze
│   ├── config_model_dimensions         ← Airflow DAG from JSON
│   ├── config_model_region_availability  ← Airflow DAG from JSON
│   ├── customer_details
│   ├── inference_user_token_usage_open_source
│   ├── inference_user_token_usage_proprietary
│   ├── resource_accelerator_inventory
│   ├── resource_model_utilization
│   ├── resource_model_instance_allocation
│   ├── quota_default_rate_limits
│   └── quota_customer_rate_limit_adjustments
├── seeds
│   └── region_mapping
├── staging_silver
├── staging_silver_ds
└── mart_gold
```

---

## Before you start — confirm pgAdmin is connected

Open pgAdmin: [localhost:5050](http://localhost:5050) — email: `admin@admin.com` | password: `admin`

If not yet registered, add the server:
1. Right-click **Servers** → **Register** → **Server**
2. **General tab** — Name: `btg-local`
3. **Connection tab:** Host `localhost`, Port `5432`, Database `btg_resource_utilization`, Username `mds_user`, Password `mds_password`
4. Check **Save password** → **Save**

**Checkpoint:** `btg-local` → `Databases` → `btg_resource_utilization` visible.

---

## Step 1 — Create the dbt folder structure

Run these commands from inside `single-dbt-opensource/` — not the parent folder:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource && pwd
```

Confirm you see `.../single-dbt-opensource`.

First — add dbt entries to `.gitignore`:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
cat >> .gitignore << 'EOF'

# dbt — credentials (contains your database password)
dbt/profiles.yml

# dbt — generated files, never commit these
dbt/target/
dbt/dbt_packages/
dbt/logs/
EOF
```

> `>>` appends to the existing file. `>` overwrites it entirely. Using `>>` preserves the entries already in `.gitignore` and adds the dbt entries below them.

Verify the full `.gitignore` contains both sets of entries:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
cat .gitignore
```

**Checkpoint:** You see both the original entries (`.env`, `airflow/logs/`) and the new dbt entries (`dbt/profiles.yml`, `dbt/target/`, `dbt/dbt_packages/`, `dbt/logs/`).

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add .gitignore
git commit -m "add dbt entries to gitignore"
```

Now create the dbt folder structure:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
mkdir -p dbt/models/staging
mkdir -p dbt/models/intermediate
mkdir -p dbt/models/marts
mkdir -p dbt/tests
mkdir -p dbt/seeds
mkdir -p dbt/macros
mkdir -p dbt/snapshots
mkdir -p dbt/dbt_packages
```

Verify:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
find dbt -type d
```

**Checkpoint:** You see: `dbt`, `dbt/models`, `dbt/models/staging`, `dbt/models/intermediate`, `dbt/models/marts`, `dbt/tests`, `dbt/seeds`, `dbt/macros`, `dbt/snapshots`, `dbt/dbt_packages`.

Add `.gitkeep` placeholders so Git tracks the empty folders:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
touch dbt/models/staging/.gitkeep
touch dbt/models/intermediate/.gitkeep
touch dbt/models/marts/.gitkeep
touch dbt/tests/.gitkeep
touch dbt/seeds/.gitkeep
touch dbt/macros/.gitkeep
touch dbt/snapshots/.gitkeep
```

> Do NOT add a `.gitkeep` to `dbt/dbt_packages/`. It is in `.gitignore` — Git sees the folder but never tracks anything inside it. The folder gets real content when `dbt deps` runs in Step 4.

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add .
git commit -m "add dbt folder structure"
```

---

## Step 2 — Set environment variables and create profiles.yml

`profiles.yml` contains your database password — **NEVER commit it to GitHub**. It is blocked by `.gitignore` from Step 1.

> **`profiles.yml` lives in `~/.dbt/`** — its full path is `/Users/kanjasaha/.dbt/profiles.yml`. Keeping it outside the project folder means it can never accidentally be committed to Git.

```bash
mkdir -p ~/.dbt
code ~/.dbt/profiles.yml
```

Replace `yourname` with your actual first name (lowercase, no spaces). Then save with `⌘ + S`:

```yaml
# profiles.yml
# Tells dbt how to connect to PostgreSQL for each environment.
# NEVER commit this file — it contains your password.
#
# Credentials sourced from .env via ~/.zshrc (set up in Step 4a).
# Only DBT_SCHEMA is dbt-specific — all others come from .env.

resource_utilization_postgres:

  target: personal

  outputs:

    # ── PERSONAL ─────────────────────────────────────────────────────
    personal:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: "{{ env_var('DBT_SCHEMA') }}"
      threads: 4

    # ── CI ───────────────────────────────────────────────────────────
    ci:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: ci
      threads: 4

    # ── DEV ──────────────────────────────────────────────────────────
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: dev
      threads: 4

    # ── PRODUCTION ───────────────────────────────────────────────────
    prod:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: prod
      threads: 4
```

Verify the env vars are being read:

```bash
grep "env_var" ~/.dbt/profiles.yml
```

**Checkpoint:** You see `env_var('POSTGRES_USER')`, `env_var('POSTGRES_PASSWORD')` etc. — credentials sourced from `.env`, never hardcoded.

Now create the safe template to share with teammates (this one IS committed):

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/profiles.yml.example
```

Type this exactly, then save with `⌘ + S`:

```yaml
# profiles.yml.example
# Safe template — copy this to ~/.dbt/profiles.yml
# This file IS committed to GitHub. profiles.yml is NOT.
#
# Steps:
#   1. cp dbt/profiles.yml.example ~/.dbt/profiles.yml
#   2. Add to ~/.zshrc:
#        export $(grep -v '^#' ~/path/to/single-dbt-opensource/.env | xargs)
#        export DBT_SCHEMA=dbt_yourname   # replace yourname with your first name
#   3. source ~/.zshrc

resource_utilization_postgres:
  target: personal
  outputs:
    personal:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: "{{ env_var('DBT_SCHEMA') }}"
      threads: 4
    ci:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: ci
      threads: 4
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: dev
      threads: 4
    prod:
      type: postgres
      host: localhost
      port: 5432
      user: "{{ env_var('POSTGRES_USER') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB') }}"
      schema: prod
      threads: 4
```

Verify `profiles.yml` is NOT visible to Git:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git status
```

**Checkpoint:** `dbt/profiles.yml.example` shows as untracked. `profiles.yml` does NOT appear anywhere. If it does appear — check `.gitignore` has `dbt/profiles.yml` on its own line.

Commit only the example:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/profiles.yml.example
git commit -m "add profiles.yml.example template"
```

---

## Step 3 — Create dbt_project.yml

`dbt_project.yml` is the main configuration file. Every dbt project must have exactly one in the `dbt/` root folder.

> YAML is indentation-sensitive. Use 2 spaces per level — never tabs.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/dbt_project.yml
```

Type this exactly, then save with `⌘ + S`:

```yaml
# dbt_project.yml
# Main configuration file. Every dbt project must have exactly one.

# Project name — must match profile: in profiles.yml
name: 'resource_utilization'
version: '1.0.0'

# Format version — always 2 for modern dbt
config-version: 2

# Which connection profile to use — defined in profiles.yml
profile: 'resource_utilization'

# Where dbt looks for each type of file
model-paths:    ["models"]
test-paths:     ["tests"]
seed-paths:     ["seeds"]
macro-paths:    ["macros"]
snapshot-paths: ["snapshots"]

# Where dbt writes compiled SQL — gitignored, never commit
target-path: "target"
clean-targets:
  - "target"
  - "dbt_packages"

# Seed configuration
seeds:
  resource_utilization:
    +schema: seeds
    +post-hook:
      - "GRANT SELECT ON {{ this }} TO analytics_engineer"
      - "GRANT SELECT ON {{ this }} TO data_scientist"

# Model configuration
models:
  resource_utilization:

    staging:
      +schema: staging_silver
      +materialized: view
      +post-hook:
        - "GRANT SELECT ON {{ this }} TO analytics_engineer"
        - "GRANT SELECT ON {{ this }} TO data_scientist"

    intermediate:
      +schema: staging_silver
      +materialized: incremental
      +post-hook:
        - "GRANT SELECT ON {{ this }} TO analytics_engineer"
        - "GRANT SELECT ON {{ this }} TO data_scientist"

    marts:
      +schema: mart_gold
      +materialized: table
      +post-hook:
        - "GRANT SELECT ON {{ this }} TO analytics_engineer"
        - "GRANT SELECT ON {{ this }} TO business_user"
```

> **`name` and `profile` must match each other.** dbt looks up the project name in `profiles.yml` like a phonebook — if they don't match, dbt cannot find its connection credentials.

> **The `+` prefix** means the setting is a configuration that applies to all models in that folder — not a subfolder name.

> **`{{ this }}`** refers to the exact table or view just created by the current model. After `stg_customer_details` builds, dbt automatically runs `GRANT SELECT ON staging_silver.stg_customer_details TO analytics_engineer`.

> **How schemas get named:** dbt combines your `schema` from `profiles.yml` with the `+schema` from `dbt_project.yml`:
> - `personal (dbt_kanja)` + `staging_silver` → `dbt_kanja_staging_silver`
> - `personal (dbt_kanja)` + `mart_gold` → `dbt_kanja_mart_gold`
> - `prod` + `staging_silver` → `prod_staging_silver`

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/dbt_project.yml
git commit -m "add dbt_project.yml"
```

---

## Step 4 — Test connection and install packages

### Step 4a — Set dbt environment variables

dbt credentials should never be hardcoded in `profiles.yml`. The `.env` file you created in Runbook 1 already has the PostgreSQL credentials — source it in `~/.zshrc` so dbt can read them via `env_var()`. Add only `DBT_SCHEMA` separately since that is dbt-specific.

```bash
cat >> ~/.zshrc << 'EOF'

# Source .env so dbt can read PostgreSQL credentials via env_var()
export $(grep -v '^#' ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/.env | xargs)

# dbt personal schema — replace yourname with your first name
export DBT_SCHEMA=dbt_kanja
EOF

source ~/.zshrc
```

Verify they are set:

```bash
echo $POSTGRES_USER
echo $POSTGRES_PASSWORD
echo $POSTGRES_DB
echo $DBT_SCHEMA
```

**Checkpoint:** All four return values — `mds_user`, `mds_password`, `btg_resource_utilization`, `dbt_kanja`.

### Step 4b — Test the dbt connection

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt debug
```

**Checkpoint:** The last line says `All checks passed!`

If you see `could not connect to server` — PostgreSQL is not running:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
docker compose start postgres
```

Verify your env vars are loaded:

```bash
echo $POSTGRES_USER
echo $DBT_SCHEMA
```

**Checkpoint:** Returns `mds_user` and your personal schema name e.g. `dbt_kanja`. If empty — re-run `source ~/.zshrc`.

### Step 4b — Create packages.yml and install packages

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code dbt/packages.yml
```

Type this exactly, then save with `⌘ + S`:

```yaml
packages:
  # --- Core Development & Utilities ---
  - package: dbt-labs/dbt_utils
    version: [">=1.1.0", "<1.2.0"]
  
  - package: dbt-labs/codegen
    version: [">=0.12.1", "<0.13.0"]

  - package: dbt-labs/audit_helper
    version: [">=0.12.0", "<0.13.0"]

  # --- Dimensional Modeling ---
  - package: godatadriven/dbt_date
    version: [">=0.9.0", "<1.0.0"]

  # --- Data Quality & Observability ---
  - package: metaplane/dbt_expectations
    version: [">=0.10.1", "<0.11.0"]

  - package: elementary-data/elementary
    version: [">=0.23.0", "<0.24.0"]

  - git: "https://github.com/EqualExperts/dbt-unit-testing.git"
    revision: "v0.4.20"

  # --- Governance & Best Practices ---
  - package: dbt-labs/dbt_project_evaluator
    version: [">=0.8.0", "<0.9.0"]

  - package: brooklyn-data/dbt_artifacts
    version: [">=2.10.0", "<2.11.0"]
```

Verify:

```bash
cat ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt/packages.yml
```

**Checkpoint:** All 9 packages listed across four sections.

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add dbt/packages.yml
git commit -m "add dbt packages.yml"
```

Install the packages:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt deps
```

**Checkpoint:** 9 packages installed with no errors.

> `dbt/dbt_packages/` is in `.gitignore` — never commit it. Anyone who clones the repo runs `dbt deps` once to install locally — identical to how `node_modules/` works in JavaScript.

---

## Step 5 — Create schemas, roles, bronze tables and populate data

The three database scripts live in the `common` repo on GitHub — not inside `single-dbt-opensource`. They are mounted directly into the Airflow container via `docker-compose.yml`.

Create the folder and download the files:

```bash
mkdir -p ~/Documents/btg-case-studies-with-dbt/common/database_scripts
```

Open [github.com/btg-case-studies-with-dbt/common](https://github.com/btg-case-studies-with-dbt/common) in your browser, navigate to `database_scripts/` and download these three files into `~/Documents/btg-case-studies-with-dbt/common/database_scripts/`:

- `resource_utilization.sql`
- `model_configuration.json`
- `model_region_availability.json`

Confirm the files are there:

```bash
ls ~/Documents/btg-case-studies-with-dbt/common/database_scripts/
```

**Checkpoint:** You see all three files.

> These files stay in `common/database_scripts/` — never copy them into `single-dbt-opensource`. The `docker-compose.yml` mounts this folder directly into the Airflow container at `/opt/airflow/database_scripts`.

Run the script:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker exec -i postgres psql \
  -U mds_user \
  -d btg_resource_utilization \
  < database_scripts/resource_utilization.sql
```

**Checkpoint:** No errors. Refresh pgAdmin — you should see all schemas under `btg_resource_utilization` → Schemas.

Verify bronze tables:

```bash
docker exec -it postgres psql -U mds_user -d btg_resource_utilization \
  -c "SELECT tablename FROM pg_tables WHERE schemaname = 'raw_bronze' ORDER BY tablename;"
```

**Checkpoint:** 10 tables listed in `raw_bronze` (not including `config_model_dimensions` and `config_model_region_availability` — those come from the Airflow DAG in Step 6).

---

## Step 6 — Load JSON config files via Airflow

Two bronze tables are populated by an Airflow DAG — not by the SQL script:
- `raw_bronze.config_model_dimensions` — 20 records from `model_configuration.json`
- `raw_bronze.config_model_region_availability` — 41 records from `model_region_availability.json`

### Step 6a — Confirm JSON files are in place

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
ls database_scripts/
```

**Checkpoint:** You see `model_configuration.json` and `model_region_availability.json` alongside `resource_utilization.sql`.

### Step 6b — Create the Airflow DAG

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
code airflow/dags/load_config_bronze.py
```

Type this exactly, then save with `⌘ + S`:

```python
"""
load_config_bronze.py
One-time DAG to load static JSON config files into bronze tables.
Trigger manually from the Airflow UI — never runs on a schedule.

Files:
  database_scripts/model_configuration.json
    → raw_bronze.config_model_dimensions (20 records)
  database_scripts/model_region_availability.json
    → raw_bronze.config_model_region_availability (41 records)
"""

import json
import os
from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

import os

DB_CONN = {
    "host":     "postgres",
    "port":     int(os.environ.get("POSTGRES_PORT", 5432)),
    "dbname":   os.environ.get("POSTGRES_DB"),
    "user":     os.environ.get("POSTGRES_USER"),
    "password": os.environ.get("POSTGRES_PASSWORD"),
}

# Mapped from docker-compose volume: ./database_scripts → /opt/airflow/database_scripts
CONFIG_DIR = "/opt/airflow/database_scripts"


def load_model_configuration():
    """Load model_configuration.json → raw_bronze.config_model_dimensions"""

    filepath = os.path.join(CONFIG_DIR, "model_configuration.json")
    with open(filepath) as f:
        data = json.load(f)

    models = data["models"]
    print(f"Loading {len(models)} records...")

    conn = psycopg2.connect(**DB_CONN)
    cur = conn.cursor()
    inserted = skipped = 0

    for m in models:
        cur.execute("""
            INSERT INTO raw_bronze.config_model_dimensions (
                publisher_name, model_display_name, model_resource_name,
                model_family, model_variant, model_version,
                model_task, inference_scope, is_open_source,
                replicas, max_concurrency, ideal_concurrency, max_rps,
                accelerator_type, accelerators_per_replica, memory_gb,
                endpoint, tokens_per_second, avg_tokens_per_request,
                avg_latency_seconds, snapshot_date, source_file
            ) VALUES (
                %(publisher_name)s, %(model_display_name)s, %(model_resource_name)s,
                %(model_family)s, %(model_variant)s, %(model_version)s,
                %(model_task)s, %(inference_scope)s, %(is_open_source)s,
                %(replicas)s, %(max_concurrency)s, %(ideal_concurrency)s, %(max_rps)s,
                %(accelerator_type)s, %(accelerators_per_replica)s, %(memory_gb)s,
                %(endpoint)s, %(tokens_per_second)s, %(avg_tokens_per_request)s,
                %(avg_latency_seconds)s, %(snapshot_date)s, 'model_configuration.json'
            )
            ON CONFLICT (model_variant, snapshot_date) DO NOTHING
        """, m)
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done — inserted: {inserted}, skipped (already exists): {skipped}")


def load_model_region_availability():
    """Load model_region_availability.json → raw_bronze.config_model_region_availability"""

    filepath = os.path.join(CONFIG_DIR, "model_region_availability.json")
    with open(filepath) as f:
        data = json.load(f)

    records = data["model_region_availability"]
    print(f"Loading {len(records)} records...")

    conn = psycopg2.connect(**DB_CONN)
    cur = conn.cursor()
    inserted = skipped = 0

    for r in records:
        cur.execute("""
            INSERT INTO raw_bronze.config_model_region_availability (
                model_variant, source_region, deployed_at,
                is_active, snapshot_date, source_file
            ) VALUES (
                %(model_variant)s, %(source_region)s, %(deployed_at)s,
                %(is_active)s, %(snapshot_date)s, 'model_region_availability.json'
            )
            ON CONFLICT (model_variant, source_region, snapshot_date) DO NOTHING
        """, r)
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done — inserted: {inserted}, skipped (already exists): {skipped}")


with DAG(
    dag_id="load_config_bronze",
    description="One-time load of model config JSON files into bronze tables",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze", "config", "one-time"],
) as dag:

    task_models = PythonOperator(
        task_id="load_model_configuration",
        python_callable=load_model_configuration,
    )

    task_regions = PythonOperator(
        task_id="load_model_region_availability",
        python_callable=load_model_region_availability,
    )

    task_models >> task_regions
```

> `ON CONFLICT ... DO NOTHING` — safe to run more than once without creating duplicates.
> `host: postgres` — the DAG runs inside the Airflow container where PostgreSQL is reachable by container name.
> `/opt/airflow/database_scripts` — maps to your local `database_scripts/` via the volume mount in `docker-compose.yml`.

Commit:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add airflow/dags/load_config_bronze.py
git commit -m "add Airflow DAG for bronze config loading"
```

### Step 6c — Trigger the DAG

1. Open [localhost:8080](http://localhost:8080) — login: `admin` / `admin`
2. Find `load_config_bronze` in the DAG list
3. Click the **▶** play button → **Trigger DAG**
4. Click the DAG name → click a task circle to view logs

> **DAG not appearing?** Airflow scans every 30 seconds. Wait and refresh. Still missing?
> ```bash
> cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
> docker compose logs airflow-scheduler --tail=20
> ```
> Look for a Python syntax error. Fix and wait 30 seconds.

**Checkpoint:** Both tasks show green. Logs say `inserted: 20` and `inserted: 41`.

Verify:

```bash
docker exec -it postgres psql -U mds_user -d btg_resource_utilization \
  -c "SELECT COUNT(*) FROM raw_bronze.config_model_dimensions;"

docker exec -it postgres psql -U mds_user -d btg_resource_utilization \
  -c "SELECT COUNT(*) FROM raw_bronze.config_model_region_availability;"
```

**Checkpoint:** `20` and `41`.

---

## Step 7 — Verify all data

Open an interactive psql session:

```bash
docker exec -it postgres psql -U mds_user -d btg_resource_utilization
```

Count rows in every bronze table:

```sql
SELECT tablename,
       (xpath('/row/cnt/text()', query_to_xml(
           format('SELECT COUNT(*) AS cnt FROM raw_bronze.%I', tablename),
           false, true, '')))[1]::text::int AS row_count
FROM pg_tables
WHERE schemaname = 'raw_bronze'
ORDER BY tablename;
```

Peek at the config data:

```sql
SELECT publisher_name, model_variant, accelerator_type, replicas
FROM raw_bronze.config_model_dimensions
ORDER BY publisher_name, model_variant
LIMIT 5;
```

Exit:

```sql
\q
```

**Checkpoint:** All 12 bronze tables exist with data. `config_model_dimensions` has 20 rows, `config_model_region_availability` has 41 rows, all other tables have data from the SQL script.

---

## Troubleshooting

**`dbt debug` says "could not connect to server"**
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
docker compose start postgres
```

**DAG task fails with "No such file: /opt/airflow/database_scripts"**

The volume mount is missing from `docker-compose.yml`. Both `airflow-webserver` and `airflow-scheduler` need this in their `volumes` section:
```yaml
- ./database_scripts:/opt/airflow/database_scripts
```
Add it, save, then:
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose down && docker compose up -d
```



**Airflow DAG not appearing in the UI**
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose logs airflow-scheduler --tail=20
```



---

## Final step — push everything to GitHub

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git push origin dev
```

**Checkpoint:** All commits pushed. Open your repo on GitHub and confirm the `dev` branch has all files.

---

## Next

Your database is set up, data is loaded, and dbt is connected. Open **Runbook 3a** to load seed data and run your first dbt models.
