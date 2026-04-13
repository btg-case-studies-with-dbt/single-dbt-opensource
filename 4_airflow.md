# 4 — Airflow & Cosmos

## Before you start
- Completed Runbooks 3a, 3b, 3c, 3d
- Stack running, dbt build passes in personal schema with no failures
- Cosmos installed — included in `airflow/requirements.txt` from Runbook 1
- `generate_schema_name.sql` macro deleted (`git rm dbt/macros/generate_schema_name.sql`)

---

## Pre-flight check

```bash
# Check 1 — stack running
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
# All 5 containers must show Up

# Check 2 — Cosmos installed
docker exec btg-airflow-scheduler python -c "import cosmos; print(cosmos.__version__)"
# Must print a version number — warnings about urllib3 are normal

# Check 3 — personal schema built
cd dbt && dbt build
# Must complete with no failures
```

---

## CI/CD — where Airflow fits

| Environment | Who builds | How | Database |
|---|---|---|---|
| Personal (`dbt_kanja_*`) | You | Manually: `dbt build --target personal` | `btg_resource_utilization` |
| Dev (`dev_*`) | Airflow `pipeline_dev` | Daily at midnight + on merge to dev | `btg_resource_utilization` |
| CI (`ci_*`) | GitHub Actions | On every Pull Request | `btg_resource_utilization` |
| Production (`prod_*`) | Airflow `pipeline_daily` | Daily at 2:00am + on merge to main | `prod_resource_utilization_postgres` |

Two Airflow DAGs — one per environment. Neither is triggered manually in production. Both are triggered automatically by schedule or CI/CD.

---

## Full cleanup and restart

If you need to reset the entire database and rebuild from scratch:

```bash
# 1. Run cleanup script — drops all schemas, tables, and roles (dev database)
docker exec -i postgres psql -U mds_user -d btg_resource_utilization < resource_utilization_db_cleanup.sql

# 2. Run setup script — recreates raw_bronze schema, roles, grants, loads bronze data
docker exec -i postgres psql -U mds_user -d btg_resource_utilization < resource_utilization_db_setup.sql

# 3. Load config bronze data — trigger load_config_bronze DAG from Airflow UI
#    Or from terminal:
docker exec btg-airflow-scheduler airflow dags trigger load_config_bronze
# Verify:
docker exec postgres psql -U mds_user -d btg_resource_utilization -c "
SELECT COUNT(*) FROM raw_bronze.config_model_dimensions;
SELECT COUNT(*) FROM raw_bronze.config_model_region_availability;"
# Must return 20 and 41

# 4. Build personal schema
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/dbt
dbt build

# 5. Set up prod database — see Step 1 below
# 6. Load config bronze data into prod — trigger load_config_bronze_prod DAG
# 7. Enable DAG schedules — see Step 4 below
```

---

## Step 1 — Create the prod database and schemas

```bash
# Create the prod database (must run as postgres superuser)
docker exec postgres psql -U postgres -c "
CREATE DATABASE prod_resource_utilization_postgres OWNER mds_user;"

# Connect to prod database and run the prod setup section
# Open resource_utilization_db_setup.sql — uncomment the PRODUCTION DATABASE SETUP section at the bottom
# Run it against prod_resource_utilization_postgres in pgAdmin query tool
```

**Checkpoint:** Connect to `prod_resource_utilization_postgres` in pgAdmin — confirm schemas exist: `raw_bronze`, `prod_staging_silver`, `prod_mart_gold`, `prod_seeds`, `prod_snapshots`, `prod_elementary`, `prod_dbt_project_evaluator`.

Copy bronze data from dev to prod:

```bash
# Dump raw_bronze from dev and restore into prod
docker exec postgres pg_dump -U mds_user -d btg_resource_utilization -n raw_bronze > /tmp/raw_bronze.sql
docker exec -i postgres psql -U mds_user -d prod_resource_utilization_postgres < /tmp/raw_bronze.sql
```

**Checkpoint:** Connect to `prod_resource_utilization_postgres` in pgAdmin — confirm `raw_bronze` has 12 tables with data.

---

## Step 2 — Update `dbt/profiles.yml`

`dbt/profiles.yml` is the Airflow-specific profiles file — uses `host: postgres` (Docker container name). Add both `dev` and `prod` targets:

```yaml
# dbt/profiles.yml — used by Airflow inside Docker only
resource_utilization_postgres:
  target: prod
  outputs:
    dev:
      type: postgres
      host: postgres
      port: 5432
      user: mds_user
      password: mds_password
      dbname: btg_resource_utilization
      schema: dev
      threads: 4
    prod:
      type: postgres
      host: postgres
      port: 5432
      user: mds_user
      password: mds_password
      dbname: prod_resource_utilization_postgres
      schema: prod
      threads: 4
```

This file is gitignored — never committed. Airflow reads it via the Docker volume mount `./dbt:/opt/airflow/dbt`.

---

## Step 3 — Add the DAG files

Remove any old DAG files (`silver_layer_staging.py`, `gold_layer_marts_daily.py`, `pipeline_6hours.py`).

Three DAG files go in `airflow/dags/`:

### `pipeline_daily.py` — prod pipeline (triggered by CI/CD on merge to main)

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator

DBT_PROJECT_PATH = "/opt/airflow/dbt"
DBT_EXECUTABLE   = "/usr/local/airflow/dbt_venv/bin/dbt"

with DAG(
    dag_id="pipeline_daily",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",   # every day at 2:00am
    catchup=False,
    tags=["daily", "prod"],
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    check_freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=(
            f"cd {DBT_PROJECT_PATH} && "
            f"{DBT_EXECUTABLE} source freshness "
            f"--target prod "
            f"--profiles-dir {DBT_PROJECT_PATH}"
        ),
    )

    run_pipeline = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_PROJECT_PATH} && "
            f"{DBT_EXECUTABLE} build "
            f"--target prod "
            f"--profiles-dir {DBT_PROJECT_PATH}"
        ),
    )

    start >> check_freshness >> run_pipeline >> end
```

> **Automating freshness checks:** `check_freshness` runs before `dbt_build` — if any source errors, the build task never starts. Full implementation covered in Runbook 3c.

### `pipeline_dev.py` — dev pipeline (triggered by CI/CD on merge to dev)

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator

DBT_PROJECT_PATH = "/opt/airflow/dbt"
DBT_EXECUTABLE   = "/usr/local/airflow/dbt_venv/bin/dbt"

with DAG(
    dag_id="pipeline_dev",
    start_date=datetime(2026, 1, 1),
    schedule="0 0 * * *",   # every day at midnight
    catchup=False,
    tags=["daily", "dev"],
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    check_freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=(
            f"cd {DBT_PROJECT_PATH} && "
            f"{DBT_EXECUTABLE} source freshness "
            f"--target dev "
            f"--profiles-dir {DBT_PROJECT_PATH}"
        ),
    )

    run_pipeline = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_PROJECT_PATH} && "
            f"{DBT_EXECUTABLE} build "
            f"--target dev "
            f"--profiles-dir {DBT_PROJECT_PATH}"
        ),
    )

    start >> check_freshness >> run_pipeline >> end
```

### `load_config_bronze_prod.py` — one-time prod bronze load

Copy `load_config_bronze_prod.py` from the outputs folder to `airflow/dags/`. This DAG loads the config JSON files into `prod_resource_utilization_postgres.raw_bronze`. Trigger once after setting up the prod database.

Syntax check all three DAG files:

```bash
docker exec btg-airflow-scheduler python /opt/airflow/dags/pipeline_daily.py
docker exec btg-airflow-scheduler python /opt/airflow/dags/pipeline_dev.py
docker exec btg-airflow-scheduler python /opt/airflow/dags/load_config_bronze_prod.py
# No errors and no traceback — startup warnings are normal
```

---

## Step 4 — Verify DAGs appear and enable schedules

```bash
# Wait 30 seconds then check
docker exec btg-airflow-scheduler airflow dags list

# If DAGs do not appear after 60 seconds
docker exec btg-airflow-scheduler airflow dags reserialize

# Enable schedules
docker exec btg-airflow-scheduler airflow dags unpause pipeline_daily
docker exec btg-airflow-scheduler airflow dags unpause pipeline_dev

# Confirm next execution times
docker exec btg-airflow-scheduler airflow dags next-execution pipeline_daily
docker exec btg-airflow-scheduler airflow dags next-execution pipeline_dev
```

`catchup=False` — Airflow runs one catch-up run at the next interval if the stack was down, not a backlog.

**Note:** `load_config_bronze_prod` has `schedule=None` — it only runs when manually triggered. Trigger it once now to load config data into prod:

```bash
docker exec btg-airflow-scheduler airflow dags trigger load_config_bronze_prod
# Verify:
docker exec postgres psql -U mds_user -d prod_resource_utilization_postgres -c "
SELECT COUNT(*) FROM raw_bronze.config_model_dimensions;
SELECT COUNT(*) FROM raw_bronze.config_model_region_availability;"
# Must return 20 and 41
```

---

## Why plain `dbt build` instead of Cosmos

Cosmos converts each dbt model into its own Airflow task — useful for large-scale visibility, but breaks dbt's natural test ordering. With Cosmos, a staging model's tests can fire before the mart models it references are built, causing `relation does not exist` errors on relationship tests. Plain `dbt build` lets dbt handle ordering internally. Consider Cosmos when pipeline takes longer than 10 minutes and you need model-level retry.

---

## Troubleshooting

**DAG does not appear after 60 seconds:**
```bash
docker exec btg-airflow-scheduler airflow dags list-import-errors
docker exec btg-airflow-scheduler python /opt/airflow/dags/pipeline_daily.py
docker exec btg-airflow-scheduler airflow dags reserialize
docker compose restart airflow-scheduler   # last resort
```

**Task fails with "could not connect to server":**
```bash
docker exec btg-airflow-scheduler cat /opt/airflow/dbt/profiles.yml | grep host
# All targets must show host: postgres — not localhost
```

**Task fails with "profiles.yml not found":**
```bash
docker exec btg-airflow-scheduler ls /opt/airflow/dbt/profiles.yml
# If missing — check docker-compose.yml has ./dbt:/opt/airflow/dbt in volumes
```

**Task fails with "Could not find profile named":**
Check `dbt_project.yml` profile name matches `dbt/profiles.yml` profile name — both must be `resource_utilization_postgres`.

**Source freshness failing:**
```bash
# Check loaded_at timestamps in raw_bronze
docker exec postgres psql -U mds_user -d btg_resource_utilization -c "
SELECT 'quota_default_rate_limits', MAX(loaded_at) FROM raw_bronze.quota_default_rate_limits;"
# If stale — update loaded_at
docker exec postgres psql -U mds_user -d btg_resource_utilization -c "
UPDATE raw_bronze.quota_default_rate_limits SET loaded_at = CURRENT_TIMESTAMP;"
```

**Relationship test failing with "relation does not exist":**
Move the `relationships` test from the staging `schema.yml` to the mart `schema.yml` — staging should not reference downstream mart tables in tests.

---

## Next
Continue to **Runbook 5 — CI/CD**.
