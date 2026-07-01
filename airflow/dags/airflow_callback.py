"""on_failure_callback for pipeline_daily / pipeline_dev (TRD-02 SS4.1).

Writes a 'pending' row to agent_triggers so the dbt Debug Agent
(dbt-debug-agent/agent.py) can pick it up. model_name is left NULL: both
DAGs run a single whole-project `dbt build` task, so the failing model(s)
can only be identified by scanning dbt.log -- the debug agent's
read_dbt_logs tool does that when model_name is missing.
"""

import psycopg2

# Same host/credentials as profiles.yml's prod target -- "postgres" is the
# docker-compose service name, reachable from inside the Airflow containers.
CONN_PARAMS = dict(
    host="postgres",
    port=5432,
    user="mds_user",
    password="mds_password",
    dbname="btg_resource_utilization",
)

# Both DAGs run dbt --target prod: this profile's "ci" target needs
# DBT_HOST/DBT_PORT/etc env vars that only exist in GitHub Actions, and
# there is no "dev" target at all -- inside this Docker setup, "prod"
# (host=postgres, db=btg_resource_utilization, schema=prod) is the only
# usable target. Kept as a dict so a real non-prod target can be added later.
TARGET_BY_DAG = {
    "pipeline_daily": "prod",
    "pipeline_dev": "prod",
}


def dbt_debug_failure_callback(context):
    """Insert a pending agent_triggers row on task failure."""
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    execution_date = context.get("logical_date") or context.get("execution_date")
    target = TARGET_BY_DAG.get(dag_id, "prod")

    try:
        conn = psycopg2.connect(**CONN_PARAMS)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_triggers (dag_id, task_id, model_name, target, execution_date)
                    VALUES (%s, %s, NULL, %s, %s)
                    """,
                    (dag_id, task_id, target, execution_date),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        # Never let the callback itself fail the DAG run further.
        print(f"[dbt_debug_failure_callback] failed to write agent_triggers row: {exc}")
