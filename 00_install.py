# Databricks notebook source
# MAGIC %md
# MAGIC # Clinical Study Hub — Install
# MAGIC
# MAGIC Run this notebook **from the Git Folder root** after cloning the repo.
# MAGIC
# MAGIC 1. Fill the widgets — at minimum set **warehouse_id**
# MAGIC 2. **Run All** (about 10–20 minutes; most of that is the sample study jobs)
# MAGIC 3. Copy the **App URL** from the last cell
# MAGIC
# MAGIC Order of work:
# MAGIC 1. Platform bundle (schema, volumes, Lakeflow Declarative Pipelines, job)
# MAGIC 2. Upload sample zips
# MAGIC 3. Process **ONC-101** and **CARD-202** so the portfolio is not empty
# MAGIC 4. Lakebase (approvals state)
# MAGIC 5. Genie space on Gold tables
# MAGIC 6. Study Hub app
# MAGIC
# MAGIC **RESP-303** is uploaded to `samples/` but **not** processed, so you can run a live onboarding demo.

# COMMAND ----------

dbutils.widgets.text("catalog", "clinical_demo", "1. Catalog")
dbutils.widgets.text("schema", "study_onboarding", "2. Schema")
dbutils.widgets.text("warehouse_id", "", "3. SQL warehouse ID (required)")
dbutils.widgets.text("llm_endpoint", "databricks-claude-sonnet-4-5", "4. LLM endpoint")
dbutils.widgets.dropdown("create_lakebase", "yes", ["yes", "no"], "5. Create Lakebase?")
dbutils.widgets.dropdown("create_genie", "yes", ["yes", "no"], "6. Create Genie space?")
dbutils.widgets.dropdown("deploy_app", "yes", ["yes", "no"], "7. Deploy Study Hub app?")
dbutils.widgets.dropdown("seed_studies", "yes", ["yes", "no"], "8. Process ONC-101 + CARD-202?")
dbutils.widgets.text("lakebase_project", "study-hub", "9. Lakebase project id")
dbutils.widgets.text("genie_title", "Study Insights", "10. Genie space title")

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint").strip()
CREATE_LAKEBASE = dbutils.widgets.get("create_lakebase") == "yes"
CREATE_GENIE = dbutils.widgets.get("create_genie") == "yes"
DEPLOY_APP = dbutils.widgets.get("deploy_app") == "yes"
SEED_STUDIES = dbutils.widgets.get("seed_studies") == "yes"
LAKEBASE_PROJECT = dbutils.widgets.get("lakebase_project").strip() or "study-hub"
GENIE_TITLE = dbutils.widgets.get("genie_title").strip() or "Study Insights"

if not WAREHOUSE_ID:
    raise ValueError(
        "warehouse_id is required. SQL Warehouses → copy the ID → paste into the widget, then re-run."
    )

print(f"catalog={CATALOG} schema={SCHEMA} warehouse={WAREHOUSE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Locate repo + workspace auth

# COMMAND ----------

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()


# ---- STAGE BEGIN ----
# Serverless workspace-file FUSE mounts return Input/output error on random reads
# (seen on databricks.yml, resources/*.yml and notebooks during `bundle validate`).
# Pull the Git Folder through the Workspace REST API instead, into local disk,
# and run every CLI command from that copy.
import base64

from databricks.sdk.service.workspace import ExportFormat, ObjectType

NOTEBOOK_EXT = {"PYTHON": ".py", "SQL": ".sql", "SCALA": ".scala", "R": ".r"}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".bundle", ".databricks", ".vscode"}


def notebook_folder() -> str:
    nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    return str(Path(nb).parent)  # e.g. /Users/<user>/clinical-study-hub


def stage_from_workspace_api(ws_root: str, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    copied, pending = 0, [ws_root]
    while pending:
        current = pending.pop()
        for obj in w.workspace.list(current):
            rel = obj.path[len(ws_root):].lstrip("/")
            if not rel or any(part in SKIP_DIRS for part in rel.split("/")):
                continue
            if obj.object_type == ObjectType.DIRECTORY:
                pending.append(obj.path)
                continue
            if obj.object_type == ObjectType.NOTEBOOK:
                lang = str(obj.language or "PYTHON").split(".")[-1]
                target = dest / (rel + NOTEBOOK_EXT.get(lang, ".py"))
                fmt = ExportFormat.SOURCE
            elif obj.object_type == ObjectType.FILE:
                target = dest / rel
                fmt = ExportFormat.AUTO
            else:
                continue
            resp = w.workspace.export(obj.path, format=fmt)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(resp.content))
            copied += 1
    return copied


WS_ROOT = notebook_folder()
if not w.workspace.get_status(f"{WS_ROOT}/databricks.yml"):
    raise FileNotFoundError(f"databricks.yml not found in {WS_ROOT} - run 00_install.py from the Git Folder root.")

ROOT = Path("/tmp/study_hub_bundle")
n_files = stage_from_workspace_api(WS_ROOT, ROOT)
os.chdir(ROOT)
print("source root:", WS_ROOT)
print("staged root:", ROOT, f"({n_files} files)")
# ---- STAGE END ----


def workspace_env() -> dict:
    env = os.environ.copy()
    ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    env["DATABRICKS_HOST"] = ctx.apiUrl().get()
    env["DATABRICKS_TOKEN"] = ctx.apiToken().get()
    env.pop("DATABRICKS_CONFIG_PROFILE", None)
    return env


ENV = workspace_env()


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    if cmd and cmd[0] == "databricks":
        cmd = [DATABRICKS_BIN, *cmd[1:]]
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd or ROOT), env=ENV, text=True, capture_output=True, check=False)


def require_ok(r: subprocess.CompletedProcess, msg: str) -> subprocess.CompletedProcess:
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        # Put the CLI error in the exception text so it shows up in the job run's error field.
        detail = (r.stderr or r.stdout or "").strip()[-1500:]
        raise RuntimeError(f"{msg}: {detail}")
    return r


def ensure_bundle_cli() -> str:
    """Need the Go Databricks CLI (`databricks bundle`), not the legacy PyPI databricks-cli."""
    candidates = []
    which = shutil.which("databricks")
    if which:
        candidates.append(which)
    candidates.extend(
        [
            str(Path.home() / ".local" / "bin" / "databricks"),
            "/tmp/databricks-cli-bin/databricks",
            "/usr/local/bin/databricks",
        ]
    )
    def is_real_cli(path: str) -> bool:
        # Serverless notebook compute ships a stub at /usr/local/bin/databricks that only
        # prints "only supported for interactive use" and exits. Reject anything that is not
        # the Go CLI with a working `bundle` command.
        ver = subprocess.run([path, "version"], capture_output=True, text=True)
        out = (ver.stdout or "") + (ver.stderr or "")
        if ver.returncode != 0 or "Databricks CLI" not in out or "only supported" in out:
            return False
        probe = subprocess.run([path, "bundle", "-h"], capture_output=True, text=True)
        return probe.returncode == 0 and "only supported" not in (probe.stdout + probe.stderr)

    for path in candidates:
        if not Path(path).exists():
            continue
        if is_real_cli(path):
            return path
    dest = Path("/tmp/databricks-cli-bin")
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "cli.zip"
    import platform

    arch = "arm64" if platform.machine().lower() in ("aarch64", "arm64") else "amd64"
    url = f"https://github.com/databricks/cli/releases/download/v1.17.0/databricks_cli_1.17.0_linux_{arch}.zip"
    print("Installing Databricks CLI 1.17.0 from GitHub…")
    subprocess.run(["curl", "-fsSL", "-L", "-o", str(zip_path), url], check=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    bin_path = dest / "databricks"
    bin_path.chmod(0o755)
    if not is_real_cli(str(bin_path)):
        raise RuntimeError("Failed to install Databricks CLI with `bundle` support")
    os.environ["PATH"] = f"{dest}:{os.environ.get('PATH', '')}"
    return str(bin_path)


DATABRICKS_BIN = ensure_bundle_cli()
ENV["PATH"] = f"{Path(DATABRICKS_BIN).parent}:{ENV.get('PATH', '')}"
print(subprocess.run([DATABRICKS_BIN, "--version"], capture_output=True, text=True).stdout.strip())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Platform bundle

# COMMAND ----------

var_args: list[str] = []
for v in [
    f"catalog={CATALOG}",
    f"schema={SCHEMA}",
    f"warehouse_id={WAREHOUSE_ID}",
    f"llm_endpoint={LLM_ENDPOINT}",
]:
    var_args += ["--var", v]

require_ok(run(["databricks", "bundle", "validate", "-t", "dev", *var_args]), "platform bundle validate failed")
require_ok(run(["databricks", "bundle", "deploy", "-t", "dev", *var_args]), "platform bundle deploy failed")

r = require_ok(run(["databricks", "bundle", "summary", "-t", "dev", "-o", "json", *var_args]), "bundle summary failed")
summary = json.loads(r.stdout)
JOB_ID = None
try:
    JOB_ID = str(summary["resources"]["jobs"]["study_onboarding_job"]["id"])
except Exception:
    m = re.search(r"study_onboarding_job.*?(\d{10,})", r.stdout, re.S)
    JOB_ID = m.group(1) if m else None
if not JOB_ID:
    raise RuntimeError("Could not resolve study_onboarding_job id")
print("job_id=", JOB_ID)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Upload sample + live-demo zips

# COMMAND ----------

samples_vol = f"/Volumes/{CATALOG}/{SCHEMA}/samples"
uploaded: list[str] = []
for folder in (ROOT / "data" / "samples", ROOT / "demo_assets"):
    if not folder.exists():
        continue
    for z in sorted(folder.glob("*.zip")):
        dest = f"{samples_vol}/{z.name}"
        print(f"upload {z.name} → {dest}")
        r = run(["databricks", "fs", "cp", "--overwrite", str(z), f"dbfs:{dest}"])
        if r.returncode != 0:
            with z.open("rb") as f:
                w.files.upload(dest, f, overwrite=True)
        uploaded.append(z.name)
print("uploaded:", uploaded)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Seed ONC-101 and CARD-202 (skip RESP-303 for the live demo)

# COMMAND ----------

SEED = [
    ("ONC-101", f"{samples_vol}/ONC-101_study_package.zip"),
    ("CARD-202", f"{samples_vol}/CARD-202_study_package.zip"),
]


def wait_run(run_id: int, timeout_s: int = 2400) -> None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        run = w.jobs.get_run(run_id)
        state = run.state
        life = state.life_cycle_state if state else None
        result = state.result_state if state else None
        label = f"{life}/{result}"
        if label != last:
            print(f"  run {run_id}: {label}")
            last = label
        if str(life) in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"} or (
            life is not None and getattr(life, "value", str(life)) in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}
        ):
            ok = str(result) in {"SUCCESS", "SUCCESS_WITH_FAILURES"} or getattr(result, "value", "") in {
                "SUCCESS",
                "SUCCESS_WITH_FAILURES",
            }
            if not ok:
                raise RuntimeError(f"Job run {run_id} ended {label}")
            return
        time.sleep(20)
    raise TimeoutError(f"Job run {run_id} still running after {timeout_s}s")


def gold_has(study_id: str) -> bool:
    try:
        res = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=(
                f"SELECT 1 FROM {CATALOG}.{SCHEMA}.gold_study_overview "
                f"WHERE study_id = '{study_id.replace(chr(39), '')}' LIMIT 1"
            ),
            wait_timeout="30s",
        )
        rows = getattr(getattr(res, "result", None), "data_array", None) or []
        return len(rows) > 0
    except Exception as e:
        print("gold lookup skipped:", e)
        return False


if SEED_STUDIES:
    for study_id, zip_path in SEED:
        if gold_has(study_id):
            print(f"{study_id} already in gold_study_overview — skip job")
            continue
        submission_id = f"SEED-{study_id}"
        print(f"Trigger onboarding job for {study_id}")
        waiter = w.jobs.run_now(
            job_id=int(JOB_ID),
            job_parameters={
                "submission_id": submission_id,
                "study_id": study_id,
                "zip_path": zip_path,
                "catalog": CATALOG,
                "schema": SCHEMA,
                "llm_endpoint": LLM_ENDPOINT,
            },
        )
        run_id = getattr(waiter, "run_id", None) or getattr(getattr(waiter, "response", None), "run_id", None)
        if run_id is None:
            raise RuntimeError(f"Could not resolve run id from run_now for {study_id}")
        wait_run(int(run_id))
    print("Seed studies published.")
else:
    print("Skipping seed studies — portfolio will be empty until you onboard a package.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lakebase

# COMMAND ----------

POSTGRES_BRANCH = f"projects/{LAKEBASE_PROJECT}/branches/production"
POSTGRES_DATABASE = f"projects/{LAKEBASE_PROJECT}/branches/production/databases/databricks-postgres"

if CREATE_LAKEBASE:
    r = run(["databricks", "postgres", "get-project", f"projects/{LAKEBASE_PROJECT}"])
    if r.returncode != 0:
        print("Creating Lakebase project", LAKEBASE_PROJECT)
        r = run(
            [
                "databricks",
                "postgres",
                "create-project",
                LAKEBASE_PROJECT,
                "--json",
                json.dumps({"spec": {"display_name": "Clinical Study Hub"}}),
            ]
        )
        print(r.stdout or r.stderr)
        if r.returncode != 0:
            print("Lakebase create warning — create it in the UI if needed:", r.stderr)
    else:
        print("Lakebase project exists:", LAKEBASE_PROJECT)
else:
    print("Skipping Lakebase")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lakebase synced table (Unity Catalog → Lakebase serving)
# MAGIC
# MAGIC Registers the Lakebase project as a Unity Catalog catalog, then creates a synced table from
# MAGIC `study_portfolio` so the app's portfolio page is served from Postgres. Safe to re-run.

# COMMAND ----------

LAKEBASE_CATALOG = "study_hub_lakebase"
PORTFOLIO_SYNCED = f"{LAKEBASE_CATALOG}.serving.study_portfolio"
PORTFOLIO_SOURCE = f"{CATALOG}.{SCHEMA}.study_portfolio"
SYNC_STATUS = "skipped"

if CREATE_LAKEBASE:
    r = run(["databricks", "postgres", "get-catalog", LAKEBASE_CATALOG])
    if r.returncode != 0:
        r = run(
            [
                "databricks", "postgres", "create-catalog", LAKEBASE_CATALOG,
                "--json", json.dumps({
                    "spec": {
                        "postgres_database": "databricks_postgres",
                        "branch": POSTGRES_BRANCH,
                    }
                }),
            ]
        )
        print(r.stdout or r.stderr)
    r = run(["databricks", "postgres", "get-synced-table", f"synced_tables/{PORTFOLIO_SYNCED}"])
    if r.returncode != 0:
        spec = {
            "spec": {
                "source_table_full_name": PORTFOLIO_SOURCE,
                "primary_key_columns": ["study_id"],
                "scheduling_policy": "TRIGGERED",
                "branch": POSTGRES_BRANCH,
                "postgres_database": "databricks_postgres",
                "create_database_objects_if_missing": True,
                "new_pipeline_spec": {"storage_catalog": CATALOG, "storage_schema": SCHEMA},
            }
        }
        r = run(["databricks", "postgres", "create-synced-table", PORTFOLIO_SYNCED, "--json", json.dumps(spec)])
        print(r.stdout or r.stderr)
        if r.returncode != 0:
            print("Synced table create warning: check Catalog Explorer and retry this cell")
            SYNC_STATUS = "failed"
        else:
            SYNC_STATUS = "created"
    else:
        print("Synced table exists:", PORTFOLIO_SYNCED)
        SYNC_STATUS = "exists"
else:
    print("Skipping Lakebase synced table")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Genie space (after Gold tables exist)

# COMMAND ----------

GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")
FQ = f"{CATALOG}.{SCHEMA}"

if CREATE_GENIE:
    env = ENV.copy()
    env["WAREHOUSE_ID"] = WAREHOUSE_ID
    env["CATALOG"] = CATALOG
    env["SCHEMA"] = SCHEMA
    env["GENIE_TITLE"] = GENIE_TITLE
    env["PROFILE"] = ""
    env["PATH"] = ENV["PATH"]
    if GENIE_SPACE_ID:
        env["GENIE_SPACE_ID"] = GENIE_SPACE_ID
    else:
        env.pop("GENIE_SPACE_ID", None)
    helper = ROOT / "scripts" / "create_genie_space.py"
    r = subprocess.run([sys.executable, str(helper)], cwd=str(ROOT), env=env, text=True, capture_output=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        raise RuntimeError(
            "Genie space create failed. Gold tables must exist (seed_studies=yes) "
            "and you need permission to create Genie spaces."
        )
    GENIE_SPACE_ID = (r.stdout or "").strip().splitlines()[-1].strip().strip('"') or GENIE_SPACE_ID
    print("genie_space_id=", GENIE_SPACE_ID)
    if not GENIE_SPACE_ID:
        raise RuntimeError("Genie space created but id was empty")
else:
    print("Skipping Genie")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Study Hub app (variables passed on the CLI — no REPLACE_ME in git)

# COMMAND ----------

APP_URL = ""
APP_DIR = ROOT / "app" / "study-hub"

# The app's SQL (config/queries/*.sql), app.yaml and server defaults name the demo catalog
# explicitly, and AppKit resolves those tables at build time. Bind them to the catalog chosen
# for this install. This only touches the staged copy under /tmp, never the Git Folder.
APP_DEFAULT_CATALOG = "clinical_demo"
if CATALOG != APP_DEFAULT_CATALOG:
    rebound = []
    for f in APP_DIR.rglob("*"):
        if not f.is_file() or "node_modules" in f.parts or f.suffix not in {".sql", ".yaml", ".yml", ".ts", ".tsx", ".env", ".example"}:
            continue
        text = f.read_text()
        if APP_DEFAULT_CATALOG in text:
            f.write_text(text.replace(APP_DEFAULT_CATALOG, CATALOG))
            rebound.append(str(f.relative_to(ROOT)))
    print(f"Bound app to catalog {CATALOG} in {len(rebound)} files")

APP_VARS = [
    f"sql_warehouse_id={WAREHOUSE_ID}",
    f"files_path=/Volumes/{CATALOG}/{SCHEMA}/landing",
    f"files_id={CATALOG}.{SCHEMA}.landing",
    f"job_id={JOB_ID}",
    f"postgres_branch={POSTGRES_BRANCH}",
    f"postgres_database={POSTGRES_DATABASE}",
    f"genie_space_id={GENIE_SPACE_ID or 'none'}",
    f"genie_space_name={GENIE_TITLE}",
]
app_var_args: list[str] = []
for v in APP_VARS:
    app_var_args += ["--var", v]

APP_NAME = "study-hub"


def grant_app_read(principal_id: str) -> None:
    """The app's service principal reads the Gold tables through the SQL warehouse.
    Grant schema-level read so the app build (AppKit type generation) and runtime can query."""
    p = f"`{principal_id}`"
    for sql in [
        f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO {p}",
        f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO {p}",
        f"GRANT SELECT ON SCHEMA `{CATALOG}`.`{SCHEMA}` TO {p}",
    ]:
        res = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=sql, wait_timeout="50s")
        state = str(getattr(res.status.state, "value", res.status.state))
        if state != "SUCCEEDED":
            raise RuntimeError(f"Grant failed ({state}): {sql}: {res.status.error}")
        print("granted:", sql)


def grant_lakebase_read(principal_id: str) -> None:
    """The app reads the synced `serving` schema in Lakebase through its service principal's
    Postgres role. Run as the installing user (project owner), per the Lakebase app guidance."""
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psycopg[binary]"], text=True, capture_output=True)
    if pip.returncode != 0:
        raise RuntimeError(f"pip install psycopg[binary] failed: {pip.stderr[-800:]}")
    import psycopg

    ep = f"projects/{LAKEBASE_PROJECT}/branches/production/endpoints/primary"

    def cli_json(args: list[str], label: str) -> dict:
        # Parse silently: this output can contain a short-lived credential, so it is never printed.
        r = run(["databricks", *args, "-o", "json"])
        if r.returncode != 0:
            raise RuntimeError(f"{label} failed: {(r.stderr or '').strip()[-800:]}")
        return json.loads(r.stdout)

    host = cli_json(["postgres", "get-endpoint", ep], "get-endpoint")["status"]["hosts"]["host"]
    token = cli_json(["postgres", "generate-database-credential", ep], "generate-database-credential")["token"]
    user = w.current_user.me().user_name
    conn = psycopg.connect(host=host, dbname="databricks_postgres", user=user, password=token, sslmode="require", autocommit=True)
    with conn.cursor() as cur:
        for sql in [
            f'GRANT USAGE ON SCHEMA serving TO "{principal_id}"',
            f'GRANT SELECT ON ALL TABLES IN SCHEMA serving TO "{principal_id}"',
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA serving GRANT SELECT ON TABLES TO "{principal_id}"',
        ]:
            cur.execute(sql)
            print("lakebase granted:", sql)
    conn.close()


def get_app() -> dict:
    # Raw REST call: works on every SDK version the serverless runtime ships.
    return w.api_client.do("GET", f"/api/2.0/apps/{APP_NAME}")


def active_app_deployment() -> tuple[str, str]:
    dep = get_app().get("active_deployment") or {}
    status = dep.get("status") or {}
    return str(status.get("state", "NONE")), str(status.get("message", ""))


if DEPLOY_APP:
    if CREATE_GENIE and not GENIE_SPACE_ID:
        raise RuntimeError("Cannot deploy the app: Genie space id is missing")
    require_ok(run(["databricks", "bundle", "validate", *app_var_args], cwd=APP_DIR), "app bundle validate failed")

    # Pass 1 creates the app and its service principal. Its build can fail until that
    # principal can read the Gold tables, so this pass is allowed to report a build failure.
    first = run(["databricks", "bundle", "deploy", *app_var_args], cwd=APP_DIR)
    print((first.stdout or "")[-1500:], (first.stderr or "")[-1500:])
    sp_id = get_app()["service_principal_client_id"]
    print("app service principal:", sp_id)
    grant_app_read(sp_id)
    grant_lakebase_read(sp_id)

    # Pass 2 redeploys now that the grants exist, which triggers a fresh build.
    require_ok(run(["databricks", "bundle", "deploy", *app_var_args], cwd=APP_DIR), "app bundle deploy failed")
    r = run(["databricks", "bundle", "run", "app", *app_var_args], cwd=APP_DIR)
    print(r.stdout or r.stderr)
    state, message = active_app_deployment()
    print("active app deployment:", state, message)
    if state != "SUCCEEDED":
        raise RuntimeError(f"App deployment did not succeed ({state}): {message}")
    APP_URL = get_app().get("url") or ""
else:
    print("Skipping app deploy")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

summary_md = f"""
### Install complete

| Item | Value |
|------|-------|
| Catalog.schema | `{CATALOG}.{SCHEMA}` |
| SQL warehouse | `{WAREHOUSE_ID}` |
| Onboarding job id | `{JOB_ID}` |
| Landing volume | `/Volumes/{CATALOG}/{SCHEMA}/landing` |
| Samples volume | `/Volumes/{CATALOG}/{SCHEMA}/samples` |
| Seeded studies | `ONC-101`, `CARD-202` (skipped RESP-303) |
| Lakebase | `projects/{LAKEBASE_PROJECT}` |
| Lakebase synced table | `{PORTFOLIO_SYNCED}` ({SYNC_STATUS}) |
| Genie space | `{GENIE_SPACE_ID or '(skipped)'}` |
| App URL | {APP_URL or '(Apps list → study-hub)'} |

### Live demo
1. Open the App URL (warehouse is already warm from the seed jobs).
2. Portfolio should already show ONC-101 and CARD-202.
3. **Onboard a Study** with `demo_assets/RESP-303_study_package.zip`.
4. Admin → Approvals → Approve & process → insights + Ask Genie.
"""
print(summary_md)
try:
    displayHTML("<pre style='white-space:pre-wrap'>" + summary_md.replace("<", "&lt;") + "</pre>")
except NameError:
    pass
