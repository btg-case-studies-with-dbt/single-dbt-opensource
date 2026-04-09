FROM apache/airflow:2.11.2

USER root
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir \
    dbt-core \
    dbt-postgres

USER airflow
COPY airflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
