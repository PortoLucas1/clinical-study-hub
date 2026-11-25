# Run log: Clinical Study Hub on a fresh Databricks workspace

This log records one end-to-end deployment and one live onboarding on a fresh Field Engineering sandbox workspace (AWS, serverless compute, 2026-11-25). Every ID below comes from the Databricks Jobs, Apps, Lakebase, Genie and SQL APIs. The workspace host is redacted, and the sandbox catalog name is shown as `<catalog>`.

The data is synthetic. Sponsors are fictional (Synthetic Biopharma Inc., Synthetic Cardio Therapeutics, Synthetic Airway Sciences). NCT IDs contain `0SYN`.

## Result summary

| Step | Result | Evidence |
|---|---|---|
| Platform bundle (Lakeflow Declarative Pipelines, volumes, onboarding job) | Deployed (`clinical_study_onboarding`, target `dev`) | [`notebooks/00_install_run_929386086547667.ipynb`](notebooks/00_install_run_929386086547667.ipynb) |
| Seed study ONC-101 (Phase 2, oncology) | Published by job run `531289358317811` (`SUCCESS`) | [`query_results/study_portfolio.csv`](query_results/study_portfolio.csv) |
| Seed study CARD-202 (Phase 3, cardiovascular) | Published by job run `458814753742976` (`SUCCESS`) | [`query_results/study_portfolio.csv`](query_results/study_portfolio.csv) |
| Live onboarding RESP-303 (submission `SUB-20261125171513-IYLA`) | Submitted, approved by admin, `PUBLISHED`; job run `447908370512864` `SUCCESS` (4 of 4 tasks) | [`api/submission_RESP-303.json`](api/submission_RESP-303.json), [`notebooks/`](notebooks/) |
| Lakebase synced table `study_hub_lakebase.serving.study_portfolio` | `SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE` | see "Lakebase" below |
| Portfolio API served from Lakebase | `source: lakebase`, 3 rows | [`api/portfolio_response_summary.json`](api/portfolio_response_summary.json), [`query_results/lakebase_serving_study_portfolio.csv`](query_results/lakebase_serving_study_portfolio.csv) |
| Genie space "Study Insights" | Created; 5 of 5 test questions answered, and the answers match the tables | [`genie_qa.md`](genie_qa.md) |
| Study Hub app | `RUNNING`; last deployment `SUCCEEDED` | see "App" below |
| Unit tests and typecheck | 3 of 3 tests pass; typecheck clean | [`tests.txt`](tests.txt) |

## Timeline (UTC, 2026-11-25)

| Time | Event | ID |
|---|---|---|
| 16:48:37 | ONC-101 onboarding job starts | run `531289358317811` |
| 16:52:21 | CARD-202 onboarding job starts | run `458814753742976` |
| 16:57 | Lakebase project `study-hub` created; Genie space "Study Insights" created | project `projects/study-hub`, space `01f1e8f14e48158f971d172374654eba` |
| 17:00:01 | First app deployment; build fails (Gold tables not readable by the app principal) | deployment `01f1e8f1a7071a388623e183811e1c30` |
| 17:03:14 | Install run with the catalog rebinding; reports `SUCCESS`, but the app build failed (see the issues table) | run `43061151829284` |
| 17:09:34 | Install run where the app principal gets its grants and the app deployment succeeds (`App started successfully`, 17:10:32) | run `596658451340581` |
| 17:15:13 | RESP-303 submitted through the app API | `SUB-20261125171513-IYLA` |
| 17:15:18 | Admin approval; onboarding job starts | job run `447908370512864` |
| 17:19:51 | RESP-303 job ends: `SUCCESS` (4 of 4 tasks) | |
| 17:20:34 | Submission status reaches `PUBLISHED` | |
| 17:20:54 | Install run with the Lakebase grants; `SUCCESS` (an earlier run in this window printed a Lakebase credential; fixed, see below) | run `42258549682990` |
| Later | Install run after the credential-output fix; `SUCCESS`. This is the run the committed notebook comes from | run `929386086547667` (task run `298397350191689`) |

## Live onboarding: RESP-303

1. **Create.** `POST /api/submissions` with the package manifest and the study metadata from `study_metadata.json`.
2. **Upload.** The zip is uploaded to the landing volume (app `files` resource, `WRITE_VOLUME`).
3. **Submit.** Status moves to `PENDING_APPROVAL`.
4. **Approve.** The admin persona approves with the comment "Package complete, approved for processing". Status moves to `PROCESSING`, and the app starts job `study-onboarding`.
5. **Run.** All four tasks are `SUCCESS`:
   - `unzip_and_stage` (task run `120361128175980`): stages 7 domain files, including `dm`, `ae`, `vs`, `ex` and `ds`. Output in [`notebooks/01_unzip_and_stage_RESP-303.ipynb`](notebooks/01_unzip_and_stage_RESP-303.ipynb).
   - `declarative_pipeline` (task run `25928860252078`): Lakeflow Declarative Pipelines for Bronze, Silver and Gold.
   - `study_insights` (task run `758474233350556`): `ai_query` headline and summary with `databricks-claude-sonnet-4-5`. Output in [`notebooks/03_study_insights_RESP-303.ipynb`](notebooks/03_study_insights_RESP-303.ipynb).
   - `publish_portfolio` (task run `341905016014586`): writes `study_portfolio` (Change Data Feed on), then refreshes the Lakebase synced table. Output in [`notebooks/04_publish_portfolio_RESP-303.ipynb`](notebooks/04_publish_portfolio_RESP-303.ipynb).
6. **Published.** Status `PUBLISHED`; run state `SUCCESS`.

### Portfolio after RESP-303

| Study | Phase | Planned | Enrolled | % of target | Sites | Countries | SAE subject rate % | DQ issues (high) |
|---|---|---|---|---|---|---|---|---|
| CARD-202 | 3 | 300 | 236 | 78.7 | 12 | 5 | 26.7 | 127 (46) |
| ONC-101 | 2 | 150 | 124 | 82.7 | 8 | 4 | 24.2 | 74 (21) |
| RESP-303 | 2 | 120 | 88 | 73.3 | 6 | 3 | 29.5 | 57 (13) |

Source: [`query_results/study_portfolio.csv`](query_results/study_portfolio.csv).

## Lakebase

- Project `study-hub`, branch `production`, database `databricks_postgres`, endpoint `primary` (`ACTIVE`).
- Lakebase catalog `study_hub_lakebase` (registered, `ACTIVE`).
- Synced table `study_hub_lakebase.serving.study_portfolio`. Source: `<catalog>.study_onboarding.study_portfolio`, TRIGGERED, primary key `study_id`. Status `SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE`.
- Read path: `GET /api/portfolio` returns `{"source":"lakebase","table":"serving.study_portfolio"}` with 3 rows. The SQL warehouse is used only as a fallback if Lakebase is unavailable.
- Access: the install notebook grants the app service principal `USAGE` on schema `serving` and `SELECT` on its tables, plus default privileges for future tables. The first portfolio call returned `permission denied for schema serving` before this grant existed. The final install run applies it.

## App

- Name `study-hub`. Its service principal has `USE CATALOG`, `USE SCHEMA` and `SELECT` on the study schema (granted by the install notebook).
- Latest deployment `SUCCEEDED`; app state `RUNNING`.
- Catalog binding: the app's SQL in `config/queries`, `app.yaml` and the server defaults name the demo catalog. The install notebook rewrites those names to the catalog chosen for the install, in the staged copy under `/tmp`. The Git Folder is not modified.

## Issues found and fixed during the run

The install notebook went through several iterations before the final green run. They are recorded here because they are part of the reproducibility story.

| Run | Problem | Fix |
|---|---|---|
| `331047002895416` | `/usr/local/bin/databricks` on serverless is a web-terminal stub | Probe the CLI (`version`, `bundle -h`); download the real CLI for the host architecture |
| `157292225521979` | Error message hidden behind a generic wrapper | Include stderr in the raised error |
| `941819875756094`, `830675017567641` | Workspace-file mount returned `Input/output error` on `resources/*.yml` and notebooks during `bundle validate` and staging | Read the repo through the Workspace API into `/tmp`; run all CLI commands from that copy |
| `505251058200245` | App build failed: SQL and `app.yaml` pointed at the demo catalog name | Bind app SQL, `app.yaml` and defaults to the install catalog (staged copy) |
| `43061151829284` | Job reported `SUCCESS` while the app build had failed: the app principal had no `SELECT` on Gold tables, and `bundle run` was not checked | Grant the app principal schema-level access; deploy the app in two passes; the job now fails unless the active app deployment is `SUCCEEDED` |
| `1081749397815933` | The serverless SDK has no `AppsAPI.get` | Use the REST endpoint `GET /api/2.0/apps/{name}` |
| `42258549682990` | The grant helper printed the CLI output, which included a short-lived Lakebase credential, into the notebook output | The helper now parses CLI output silently and never prints it. The committed notebook copy is checked for credential-shaped strings. |
| Portfolio route (app runtime) | `permission denied for schema serving` on the Lakebase read | Postgres `USAGE` and `SELECT` on schema `serving` for the app principal, in the install notebook (applied by run `929386086547667`) |

## Final install notebook run

- Run `929386086547667` (task run `298397350191689`), `SUCCESS`. Notebook view exported as [`notebooks/00_install_run_929386086547667.ipynb`](notebooks/00_install_run_929386086547667.ipynb).
- Printed in the run: `Bound app to catalog <catalog> in 17 files`, the three Unity Catalog `GRANT` statements, the three Lakebase `GRANT` statements, and `active app deployment: SUCCEEDED App started successfully`.
- The seed studies were already present, so the notebook reported `ONC-101 already in gold_study_overview — skip job` and the same for CARD-202. This is the idempotent path.
- The Lakebase catalog already existed, so the notebook reported `Catalog 'study_hub_lakebase' already exists` and continued. This is expected.
