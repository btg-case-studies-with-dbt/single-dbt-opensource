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
