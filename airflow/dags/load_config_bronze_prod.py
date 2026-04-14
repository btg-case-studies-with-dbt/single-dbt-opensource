"""
load_config_bronze_prod.py
One-time DAG to load static JSON config files into prod bronze tables.
Trigger manually from the Airflow UI — never runs on a schedule.

Files:
  database_scripts/model_configuration.json
    → raw_bronze.config_model_dimensions (20 records)
  database_scripts/model_region_availability.json
    → raw_bronze.config_model_region_availability (41 records)

Target database: prod_resource_utilization_postgres
"""

import json
import os
from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

DB_CONN = {
    "host":     "postgres",
    "port":     5432,
    "dbname":   "prod_resource_utilization_postgres",
    "user":     "mds_user",
    "password": "mds_password",
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
    dag_id="load_config_bronze_prod",
    description="One-time load of model config JSON files into prod bronze tables",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze", "config", "one-time", "prod"],
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
