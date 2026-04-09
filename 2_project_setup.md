# 2 — Project Setup

## Before you start
- Completed `common/setup/1_stack_setup_mac.md`
- Docker Desktop is running (🐳 whale in menu bar)
- dbt virtual environment is active — your prompt shows `(.dbt-venv)`

---

## Step 1 — Create your project folder

```bash
mkdir ~/Documents/single-dbt-opensource
cd ~/Documents/single-dbt-opensource
git init
```

**Checkpoint:** `Initialized empty Git repository in .../single-dbt-opensource/.git/`

---

## Step 2 — Create .gitignore

```bash
cat > .gitignore << 'EOF'
# Secrets
.env

# dbt
dbt/target/
dbt/dbt_packages/
dbt/logs/
dbt/profiles.yml

# Airflow
airflow/logs/

# Python
__pycache__/
*.pyc
.venv/
venv/

# OS
.DS_Store
*.swp
*.swo

# IDE
.vscode/
.idea/

# Docker
*.log
EOF
```

```bash
git add .gitignore
git commit -m "initial project setup"
```

---

## Step 3 — Create GitHub repo and connect

```bash
gh repo create btg-case-studies-with-dbt/single-dbt-opensource \
  --public \
  --source=. \
  --remote=origin \
  --push
```

> If the repo already exists on GitHub, connect to it instead:
> ```bash
> git remote add origin https://github.com/btg-case-studies-with-dbt/single-dbt-opensource.git
> git push -u origin main
> ```

**Checkpoint:** `✓ Created repository` and `✓ Pushed commits`

Create dev branch:
```bash
git checkout -b dev
git push origin dev
```

---

## Step 4 — Create folder structure

```bash
mkdir -p database_scripts
mkdir -p airflow/dags
mkdir -p airflow/logs
mkdir -p airflow/plugins
mkdir -p dbt/models/staging
mkdir -p dbt/models/intermediate
mkdir -p dbt/models/marts
mkdir -p dbt/seeds
mkdir -p dbt/macros
mkdir -p dbt/snapshots
mkdir -p .github/workflows
```

Add `.gitkeep` to empty folders:
```bash
touch airflow/logs/.gitkeep
touch airflow/plugins/.gitkeep
touch dbt/models/staging/.gitkeep
touch dbt/models/intermediate/.gitkeep
touch dbt/models/marts/.gitkeep
touch dbt/seeds/.gitkeep
touch dbt/macros/.gitkeep
touch dbt/snapshots/.gitkeep
touch .github/workflows/.gitkeep
```

```bash
git add .
git commit -m "add folder structure"
git push origin dev
```

---

## Step 5 — Create .env.example

```bash
cat > .env.example << 'EOF'
# PostgreSQL
POSTGRES_USER=mds_user
POSTGRES_PASSWORD=mds_password
POSTGRES_DB=btg_resource_utilization
POSTGRES_PORT=5432

# Airflow
AIRFLOW_UID=50000
AIRFLOW__WEBSERVER__SECRET_KEY=changeme123
EOF
```

Copy to create your local `.env`:
```bash
cp .env.example .env
```

```bash
git add .env.example
git commit -m "add environment variable template"
git push origin dev
```

**Checkpoint:** `git status` — `.env` does not appear. Only `.env.example` is tracked.

---

## Step 6 — Create Dockerfile

```bash
cat > Dockerfile << 'EOF'
FROM apache/airflow:2.11.2

USER root
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir \
    dbt-core \
    dbt-postgres

USER airflow
COPY airflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EOF
```

---

## Step 7 — Create airflow/requirements.txt

```bash
cat > airflow/requirements.txt << 'EOF'
apache-airflow-providers-postgres
# astronomer-cosmos==1.13.1
EOF
```

---

## Step 8 — Create docker-compose.yml

```bash
cat > docker-compose.yml << 'EOF'
services:

  postgres:
    image: postgres:17
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  airflow-init:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: btg-airflow-init
    depends_on:
      postgres:
        condition: service_started
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://mds_user:mds_password@postgres:5432/btg_resource_utilization
      AIRFLOW__WEBSERVER__SECRET_KEY: changeme123
      _AIRFLOW_DB_MIGRATE: 'true'
      _AIRFLOW_WWW_USER_CREATE: 'true'
      _AIRFLOW_WWW_USER_USERNAME: admin
      _AIRFLOW_WWW_USER_PASSWORD: admin
    command: version
    restart: on-failure

  airflow-webserver:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: btg-airflow-webserver
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_started
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://mds_user:mds_password@postgres:5432/btg_resource_utilization
      AIRFLOW__WEBSERVER__SECRET_KEY: changeme123
    ports:
      - "8080:8080"
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
      - ./airflow/plugins:/opt/airflow/plugins
      - ./dbt:/opt/airflow/dbt
      - ./database_scripts:/opt/airflow/database_scripts
    command: webserver

  airflow-scheduler:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: btg-airflow-scheduler
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_started
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://mds_user:mds_password@postgres:5432/btg_resource_utilization
      AIRFLOW__WEBSERVER__SECRET_KEY: changeme123
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
      - ./airflow/plugins:/opt/airflow/plugins
      - ./dbt:/opt/airflow/dbt
      - ./database_scripts:/opt/airflow/database_scripts
    command: scheduler

  metabase:
    image: metabase/metabase:v0.59.2
    container_name: metabase
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_started
    ports:
      - "3000:3000"
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase
      MB_DB_PORT: 5432
      MB_DB_USER: ${POSTGRES_USER}
      MB_DB_PASS: ${POSTGRES_PASSWORD}
      MB_DB_HOST: postgres
    volumes:
      - metabase_data:/metabase-data

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: btg-pgadmin
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_started
    environment:
      PGADMIN_DEFAULT_EMAIL: "admin@admin.com"
      PGADMIN_DEFAULT_PASSWORD: "admin"
    ports:
      - "5050:80"
    volumes:
      - pgadmin_data:/var/lib/pgadmin

volumes:
  postgres_data:
  metabase_data:
  pgadmin_data:
EOF
```

```bash
git add .
git commit -m "add Dockerfile, docker-compose, requirements"
git push origin dev
```

---

## Step 9 — Add database script

Copy `resource_utilization.sql` from `common/database_scripts/` into your project:

```bash
cp ~/path/to/common/database_scripts/resource_utilization.sql database_scripts/
```

```bash
git add database_scripts/
git commit -m "add resource_utilization bronze layer script"
git push origin dev
```

---

## Step 10 — Build and start the stack

```bash
docker compose build
```

> Takes 3–5 minutes on first build.

```bash
docker compose up -d
```

> First run takes 5–10 minutes pulling images.

**Checkpoint:**
```bash
docker compose ps
```

All containers show `Up`:
```
NAME                    STATUS
btg-airflow-scheduler   Up
btg-airflow-webserver   Up   0.0.0.0:8080->8080/tcp
btg-pgadmin             Up   0.0.0.0:5050->80/tcp
metabase                Up   0.0.0.0:3000->3000/tcp
postgres                Up   0.0.0.0:5432->5432/tcp
```

---

## Step 11 — Run the database script

```bash
docker exec -i postgres psql \
  -U mds_user \
  -d btg_resource_utilization \
  < database_scripts/resource_utilization.sql
```

**Checkpoint:** No errors. Run this to verify tables exist:
```bash
docker exec postgres psql -U mds_user -d btg_resource_utilization \
  -c "\dt raw_bronze.*"
```

---

## Step 12 — Create Metabase database

```bash
docker exec postgres psql -U mds_user \
  -d btg_resource_utilization \
  -c "CREATE DATABASE metabase;"

docker compose restart metabase
```

---

## Step 13 — Verify

| Tool | URL | Login |
|---|---|---|
| Airflow | [localhost:8080](http://localhost:8080) | admin / admin |
| Metabase | [localhost:3000](http://localhost:3000) | set up on first visit |
| pgAdmin | [localhost:5050](http://localhost:5050) | admin@admin.com / admin |

Connect pgAdmin to PostgreSQL:
1. Right-click **Servers** → **Register → Server**
2. Name: `btg-local`
3. Connection: Host `postgres`, Port `5432`, Database `btg_resource_utilization`, Username `mds_user`, Password `mds_password`
4. Click **Save**

**Checkpoint:** `raw_bronze` schema visible in pgAdmin with all tables populated.

---

## Step 14 — Merge dev to main

```bash
gh pr create \
  --base main \
  --head dev \
  --title "initial project setup" \
  --body "Stack, folder structure, database scripts, docker setup."

gh pr merge --squash
```

---

## Done

Your local stack is running and bronze data is loaded.

Continue to **3a — dbt Commands** to build your first dbt models.
