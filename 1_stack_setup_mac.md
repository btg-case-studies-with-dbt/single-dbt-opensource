# 1 — Mac Setup

## What you need
- Mac (Intel or Apple Silicon)
- 10 GB free disk space
- Internet connection

## Decide before you start

**Database name:** `btg_resource_utilization`
Hard to change later — baked into Airflow, Metabase, dbt, and Git history. Use underscores not hyphens.

**Project folder:** `~/Documents/btg-case-studies-with-dbt/single-dbt-opensource/`
Substitute everywhere if you use a different name.

---

## Step 1 — Git

```bash
git --version
```

Already installed → move to Step 2.

Not installed → a popup appears, click **Install**, wait, then re-run `git --version`.

**Checkpoint:** `git version 2.x.x`

---

## Step 2 — Docker Desktop

```bash
docker --version
```

Already installed → confirm 🐳 whale is in your menu bar → move to Step 3.

Not installed:
1. Go to [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Click **Download for Mac**
   - Apple M1/M2/M3 → choose **Apple Silicon**
   - Intel → choose **Intel Chip**
3. Open the `.dmg` → drag Docker to Applications
4. Open Docker → enter password if asked
5. Wait for 🐳 whale in menu bar to stop animating
6. Re-run `docker --version`

**Checkpoint:** `Docker version 29.x.x` and 🐳 whale in menu bar

---

## Step 3 — VS Code

```bash
code --version
```

Already installed → move to Step 4.

Not installed:
1. Go to [code.visualstudio.com](https://code.visualstudio.com)
2. Click **Download for Mac**
3. Open the `.zip` → drag VS Code to Applications
4. Open VS Code → press `⌘ + Shift + P` → type `shell command` → click **Install 'code' command in PATH**
5. Close and reopen Terminal → re-run `code --version`

**Checkpoint:** `1.9x.x`

Install VS Code extensions — open VS Code, click the Extensions icon (four squares), search and install:
- **dbt Power User** by Altimate AI
- **Python** by Microsoft
- **Docker** by Microsoft
- **Remote - SSH** by Microsoft
- **Claude Code** by Anthropic

---

## Step 4 — GitHub CLI

```bash
gh --version
```

Already installed → move to Step 5.

Not installed:
```bash
brew install gh
```

**Checkpoint:** `gh version 2.x.x`

Log in to GitHub:
```bash
gh auth login
```

Choose: `GitHub.com → HTTPS → Login with a web browser` → follow the prompts.

**Checkpoint:** `✓ Logged in to github.com account yourname`

---

## Step 5 — uv

```bash
uv --version
```

Already installed → move to Step 6.

Not installed:
```bash
brew install uv
```

**Checkpoint:** `uv 0.x.x`

---

## Step 6 — dbt

dbt runs natively on your Mac for development. It also runs inside the Airflow container for scheduled automation — both are needed and serve different purposes.

```bash
cd ~
uv venv .dbt-venv
source .dbt-venv/bin/activate
uv pip install dbt-core dbt-postgres
dbt --version
```

**Checkpoint:** `Core: 1.x.x`

Activate virtual environment every time you start to work on any dbt project:

```bash
source ~/.dbt-venv/bin/activate
```

---

## Step 7 — Configure Git

```bash
git config --global init.defaultBranch main
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

> If you skip this step, your first commit will fail with "Author identity unknown."

---

## Step 8 — Create project folder and initialize Git

```bash
cd ~/Documents/btg-case-studies-with-dbt
git clone https://github.com/btg-case-studies-with-dbt/single-dbt-opensource
cd single-dbt-opensource
git checkout dev
git pull origin dev
```

> **Path 1 readers** — you already cloned this repo. If not, run the above.
> **Path 2 readers** — clone and run, skip to Runbook 2.

Confirm you are in the right folder:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource && pwd
```

**Checkpoint:** `.../single-dbt-opensource`

---

## Step 9 — Create .gitignore

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
cat > .gitignore << 'EOF'
# Secrets — never commit these
.env

# dbt — credentials
dbt/profiles.yml

# dbt — generated files
dbt/target/
dbt/dbt_packages/
dbt/logs/

# Airflow — runtime logs
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

git add .gitignore
git commit -m "add .gitignore"
git push origin dev
```

**Checkpoint:** `git status` — `.gitignore` committed, no other files tracked.

---

## Step 10 — Create environment file

> **What is a `.env` file?** Holds private settings — passwords, port numbers — that Docker needs to start the stack. Lives only on your Mac, blocked by `.gitignore` so it never goes to GitHub.
>
> **What is `.env.example`?** A safe template with the same variable names but no real passwords. Committed to Git so teammates know exactly what to fill in.

Confirm you are in the right folder:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource && pwd
```

Create the example template:

```bash
cat > .env.example << 'EOF'
# PostgreSQL — your data warehouse
POSTGRES_USER=mds_user
POSTGRES_PASSWORD=mds_password
POSTGRES_DB=btg_resource_utilization
POSTGRES_PORT=5432

# Airflow — your pipeline scheduler
AIRFLOW_UID=50000
AIRFLOW__WEBSERVER__SECRET_KEY=changeme123
EOF
```

Copy it to create the real `.env`:

```bash
cp .env.example .env
```

Commit the template — not the real `.env`:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add .env.example
git commit -m "add environment variable template"
git push origin dev
```

**Checkpoint:** Run `git status` — `.env` does not appear anywhere. Only `.env.example` is tracked.

---

## Step 11 — Create Dockerfile

> **What is a Dockerfile?** A recipe for building a custom Docker image. The official Airflow image has Airflow but not dbt. We install dbt inside the Airflow container so Cosmos can run dbt models as Airflow tasks automatically.
>
> dbt is installed here **for Airflow automation only** — you run dbt manually using the native installation from Step 6.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
cat > Dockerfile << 'EOF'
FROM apache/airflow:2.11.2

# Install dbt in its own virtual environment inside the container
# Keeps dbt and Airflow dependencies separate — no version conflicts
USER root
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir \
    dbt-core \
    dbt-postgres

# Switch back to airflow user — never run production software as root
USER airflow

# Install Airflow Python packages from requirements.txt
COPY airflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EOF
```

---

## Step 12 — Create airflow/requirements.txt

> **What is requirements.txt?** A list of Python packages for Airflow. Installs everything at once when Docker builds the image.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
mkdir -p airflow/dags airflow/logs airflow/plugins

cat > airflow/requirements.txt << 'EOF'
# Official Airflow connector for PostgreSQL
# Without this, Airflow cannot talk to a PostgreSQL database
apache-airflow-providers-postgres

# Cosmos — the bridge between dbt and Airflow
# Turns every dbt model into an individual Airflow task for fine-grained visibility
# Installed but NOT used yet — see Runbook 4 for why.
# Uncomment when you are ready to use Cosmos:
# astronomer-cosmos==1.13.1
EOF
```

---

## Step 13 — Create docker-compose.yml

> **What is a `.yml` file?** YAML — structured settings in plain text. Two spaces per level, never tabs.
>
> **What is docker-compose.yml?** The blueprint for your entire stack. Tells Docker which services to run, how to configure them, and how they connect.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
cat > docker-compose.yml << 'EOF'
services:

  # ── PostgreSQL ──────────────────────────────────────────────
  # Your data warehouse. Stores all project data.
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

  # ── Airflow Init ─────────────────────────────────────────────
  # Runs once on startup: sets up the database and creates admin user
  # Exits automatically when done — this is expected behaviour
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

  # ── Airflow Webserver ─────────────────────────────────────────
  # Serves the Airflow UI at localhost:8080
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
      - ${HOME}/Documents/btg-case-studies-with-dbt/common/database_scripts:/opt/airflow/database_scripts
    command: webserver

  # ── Airflow Scheduler ─────────────────────────────────────────
  # Watches for DAGs to trigger and runs tasks
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
      - ${HOME}/Documents/btg-case-studies-with-dbt/common/database_scripts:/opt/airflow/database_scripts
    command: scheduler

  # ── Metabase ──────────────────────────────────────────────────
  # BI tool — turns your data into charts and dashboards
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

  # ── pgAdmin ───────────────────────────────────────────────────
  # Visual interface for browsing your PostgreSQL database
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

> **Email addresses in YAML must be quoted.** The `@` symbol confuses the YAML parser — always wrap values containing `@` in double quotes.
>
> **`depends_on: condition: service_started`** — tells Docker not to start this service until the named service has started. Airflow needs PostgreSQL running first.
>
> **`./database_scripts:/opt/airflow/database_scripts`** — links your local `database_scripts/` folder into the Airflow container so DAGs can read the JSON config files.
>
> **Airflow env vars are hardcoded** — variables with double underscores like `AIRFLOW__CORE__EXECUTOR` conflict with how Docker Compose reads `.env` files. Write these directly in the compose file.

Commit everything:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
git add .
git commit -m "add Dockerfile, docker-compose, requirements"
git push origin dev
```

---

## Step 14 — Build and start the stack

Two commands — build then start. Because Airflow uses a custom Dockerfile, Docker must build the image first.

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose build
```

> Takes 3–5 minutes. Docker downloads Airflow and installs dbt inside it. Wait for the prompt to return.

```bash
docker compose up -d
```

> First run takes 5–10 minutes pulling PostgreSQL, Metabase, and pgAdmin images.

If you see "Found orphan containers":
```bash
docker compose up -d --remove-orphans
```



> When you restart you machine and get the docker up and running follow these steps.

```bash
open -a Docker
```

> First run takes 5–10 minutes pulling PostgreSQL, Metabase, and pgAdmin images.

If you see "Found orphan containers":
```bash
docker compose up -d
```
---

## Step 15 — Verify everything is running

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose ps
```

Every container must show `Up`:

```
NAME                    STATUS
btg-airflow-scheduler   Up
btg-airflow-webserver   Up   0.0.0.0:8080->8080/tcp
btg-pgadmin             Up   0.0.0.0:5050->80/tcp
metabase                Up   0.0.0.0:3000->3000/tcp
postgres                Up   0.0.0.0:5432->5432/tcp
```

> `btg-airflow-init` not in the list is normal — it runs once then exits cleanly.

If any container shows `Exit` or `Restarting`:

```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose logs airflow-webserver --tail=30
# Replace airflow-webserver with the failing service name
```

Verify dbt is installed inside the Airflow container:

```bash
docker exec btg-airflow-scheduler \
  /usr/local/airflow/dbt_venv/bin/dbt --version
```

**Checkpoint:** `Core: 1.x.x`

Create the Metabase database:

```bash
docker exec postgres psql -U mds_user \
  -d btg_resource_utilization \
  -c "CREATE DATABASE metabase;"

docker compose restart metabase
```

---

## Step 16 — Open Airflow and Metabase

| Tool | URL | Login |
|---|---|---|
| Airflow | [localhost:8080](http://localhost:8080) | admin / admin |
| Metabase | [localhost:3000](http://localhost:3000) | set up on first visit |
| pgAdmin | [localhost:5050](http://localhost:5050) | admin@admin.com / admin |

---

## Stopping and starting the stack

```bash
# Stop (data is saved)
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose stop

# Start again
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose start

# ⚠️ LAST RESORT ONLY — wipes ALL data including the database
# You will need to re-run resource_utilization.sql and reload all bronze data
# cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
# docker compose down -v
```

---

## Troubleshooting

**Container shows Exit instead of Up**
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose logs airflow-webserver --tail=30
```

**Port already in use**
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose stop && docker compose up -d
```

**Metabase stuck on loading screen**
```bash
cd ~/Documents/btg-case-studies-with-dbt/single-dbt-opensource
docker compose logs metabase --tail=20
# If you see "database metabase does not exist":
docker exec postgres psql -U mds_user -d btg_resource_utilization \
  -c "CREATE DATABASE metabase;"
docker compose restart metabase
```

**"cannot use SQLite with LocalExecutor" in Airflow logs**
Check that `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` is hardcoded in `docker-compose.yml` — not read from `.env`.

**dbt command not found**
```bash
source ~/.zshrc
```

---

## Done — verify all tools

```bash
git --version
docker --version
code --version
gh --version
uv --version
dbt --version
docker compose ps
```

Continue to **Runbook 2 — Project Setup**.
