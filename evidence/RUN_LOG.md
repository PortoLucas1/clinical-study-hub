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
| Quarantine-first data quality (2026-11-26) | Deployed; 6 of 6 checks at zero failures; every staged row reconciles; 143 subjects quarantined, none dropped | see "Quarantine-first data quality" below |
| Genie contamination check | 8 of 8 probe questions: no quarantined subject in any answer | [`genie_eval.md`](genie_eval.md) |
| DQ visibility and fallbacks (2026-11-26) | Deployed and exercised: job alerts, AI modelling gate with retries and human fallback, threshold status, dashboard, SQL alert, remediation job | see "Visibility and fallbacks" below |
| Unit tests and typecheck | 11 of 11 app tests and 15 of 15 Python tests pass; typecheck clean; lint 0 errors | [`tests.txt`](tests.txt) |

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

This table is from the first run, before quarantine-first data quality. At that point KPIs counted every received subject. See "Quarantine-first data quality" below for the current, clean-only numbers.

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

## Quarantine-first data quality (2026-11-26)

Same workspace, redeployed with the quarantine-first design: every record that fails a quarantine rule, and every record of its subject, moves to a `silver_<domain>_quarantine` table. No row is dropped. Gold, the AI insights, Genie and the portfolio read only clean subjects. The rules live in one registry (`src/pipeline/dq_rules.py`, 40 rules), published as the `dq_rules` table.

### Steps

| Step | Result | ID |
|---|---|---|
| Root bundle deploy and pipeline update (Lakeflow Declarative Pipelines) | `COMPLETED`; new tables `silver_*_quarantine`, `silver_subject_status`, `dq_rules`, `dq_study_coverage`, `dq_reconciliation`, event log published to Unity Catalog | pipeline update `6275f802-3428-423a-90b9-91f1d34aa8b3` |
| AI insights for 4 studies, then publish | `SUCCESS`. The first attempt failed because the notebook required the staging task's value when run alone; fixed, then repaired | run `1086605723025120`, repair `76590853762191` |
| Lakebase synced table | Recreated for the new coverage columns; app grants re-applied; `ONLINE` | `study_hub_lakebase.serving.study_portfolio` |
| Genie space | Updated to clean tables only (`gold_dq_issues` and the AI summary removed) | space `01f1e8f14e48158f971d172374654eba` |
| Study Hub app | Deployed; `App started successfully`; new Quarantine tab, coverage tiles, staging report, issue reviews (`study_hub.dq_issue_reviews` in Lakebase) | app `study-hub` |
| Live onboarding DERM-404 through the app API | `PUBLISHED`; job run `SUCCESS` (4 of 4 tasks); staging report shows 8 files staged, none flagged | submission `SUB-20261126142546-HJ4D`, job run `341990709145072` |
| Package check | An incomplete package (no adverse events or labs) is rejected by the server with `400 Package is missing required domain files: ae, lb` | |

### Before and after (KPIs on clean subjects only)

| Study | Enrolled before | Subjects received | Clean (KPIs) | Quarantined | % clean | Records quarantined |
|---|---|---|---|---|---|---|
| CARD-202 | 236 | 236 | 168 | 68 | 71.2 | 5,836 |
| DERM-404 | not onboarded | 88 | 64 | 24 | 72.7 | 1,959 |
| ONC-101 | 124 | 124 | 97 | 27 | 78.2 | 2,346 |
| RESP-303 | 88 | 88 | 64 | 24 | 72.7 | 1,959 |

Sources: [`query_results/dq_study_coverage.csv`](query_results/dq_study_coverage.csv), [`query_results/study_portfolio.csv`](query_results/study_portfolio.csv). The generator plants issues on purpose (implausible vitals, missing or non-numeric lab results, dates after the cutoff, missing consent dates, out-of-range ages, AEs ending before onset), so a large share of subjects is quarantined. DERM-404 is a re-keyed copy of RESP-303, which is why their numbers match.

### Verification

- [`scripts/verify_dq.sql`](../scripts/verify_dq.sql): 6 of 6 checks return zero failures ([`query_results/verify_dq.csv`](query_results/verify_dq.csv)). No quarantined or unknown subject appears in a clean Silver or Gold table, and `subjects_received = subjects_clean + subjects_quarantined`.
- Reconciliation: for all 28 study and domain pairs, staged rows = Bronze rows = clean rows + quarantine rows ([`query_results/dq_reconciliation.csv`](query_results/dq_reconciliation.csv)). `dq_reconciliation` also carries a `rows_balanced` expectation, so an imbalance shows up in the pipeline event log.
- AI insights: all 4 briefings pass output validation and state their coverage, for example "These metrics cover 97 clean subjects (78.2% of 124 received)" ([`query_results/study_ai_summary_validation.csv`](query_results/study_ai_summary_validation.csv)). The model receives data quality as counts only.
- Genie: [`scripts/genie_eval.py`](../scripts/genie_eval.py) asked 8 probe questions, including "List every subject in ONC-101" (97 rows, the clean count) and "Show me the quarantined subjects". No answer contained any of the 143 quarantined subject IDs. Genie declines to list quarantined subjects and points to the app ([`genie_eval.md`](genie_eval.md)). Its text answers do not always restate coverage, but the result tables include the received and quarantined counts.

### Issue found during the run

The first validation run quarantined every DERM-404 lab row with `REF01` (subject not in demographics). The cause was in the mock package: its lab spreadsheet still carried RESP-303 subject IDs. The same was true of NEURO-505 and IMMUNO-606. The quarantine design surfaced the defect instead of silently dropping 3,808 rows. The three packages were re-keyed, and the live DERM-404 onboarding above uses the fixed package.


## Visibility and fallbacks (2026-11-26)

The data is synthetic and the AI data modelling step is a mock: the validator and the accuracy maths are real, and the proposed mapping comes from a scenario (`pass`, `recover`, `fail`). Alerts go to the user who deployed (the address is a deploy variable, not stored in the repo).

| Scenario | What happened | Evidence |
|---|---|---|
| `pass` (NEURO-505, IMMUNO-606) | Attempt 1 at 100%, gate passes, the pipeline, threshold check, insights and publish run; `manual_modelling_handoff` is skipped | job runs `97107776281824`, `444387311223696`, `597690362808408` |
| `recover` (NEURO-505) | 98.881%, then 99.056%, then 100% on the third attempt; gate passes | job run `601185859125141`, [`query_results/ai_modelling_runs.csv`](query_results/ai_modelling_runs.csv) |
| `fail` (IMMUNO-606) | 99.553% on every attempt (1 try plus 3 retries); the gate sends the run to `manual_modelling_handoff`, which succeeds (its success email is configured for the alert recipient; delivery was not checked here); the pipeline, insights and publish are skipped (the job result is `SUCCESS`, the app shows "Awaiting manual modelling") | job run `799479514420692` |
| Manual fallback | `manual-data-modelling` applies the approved mapping, runs the pipeline, threshold check, insights and publish; recorded as actor `human` | job run `429504701985912` |
| Threshold status | 5 of 6 studies critical (27.3 to 28.8% of subjects quarantined against a critical limit of 25), ONC-101 warn | [`query_results/dq_threshold_status.csv`](query_results/dq_threshold_status.csv), [`query_results/dq_study_status.csv`](query_results/dq_study_status.csv), [`query_results/dq_run_history.csv`](query_results/dq_run_history.csv) |
| SQL alert `dq_critical_alert` | Evaluated every 15 minutes, state `TRIGGERED` (critical studies > 0), with the alert recipient as subscriber (delivery was not checked here) | alert `679146278986661` |
| Dashboard `Study Hub - data quality` | Deployed and published; all 7 dataset queries return rows | dashboard `01f1e9ac1c061f48a4c76ee562321406` |
| Remediation | Two accepted reviews (ONC-101, rule DM01) became waivers; `quarantine-remediation` returned them to Gold: clean 97 to 99, quarantined 27 to 25, 0 unbalanced domains | job run `1115261776312950`, [`query_results/dq_waivers.csv`](query_results/dq_waivers.csv), [`query_results/dq_remediation_log.csv`](query_results/dq_remediation_log.csv) |
| `scripts/verify_dq.sql` | 8 of 8 checks at zero failures (two new: waived issues are not quarantined, threshold statuses are known) | [`query_results/verify_dq.csv`](query_results/verify_dq.csv) |

### Issues found during the run

- A job run started from a notebook could not import `src/lib/modelling.py` (`ModuleNotFoundError`): the notebook path is absolute, so joining it to `/Workspace` dropped the prefix. Fixed, and the AI task is set to `max_retries: 0` because serverless otherwise retried the task by itself on top of the notebook's own attempts.
- The app failed to start with `Unknown job "default"`: AppKit only auto-discovers `DATABRICKS_JOB_ID` when no other job is bound. `server.ts` now names both jobs.
- The IMMUNO-606 and NEURO-505 packages in the `samples` volume were the older copies whose lab spreadsheets carried RESP-303 subject IDs (see the previous section). A first threshold run showed it as a `top_rule_share_pct` of 676.9 (every lab row quarantined). The volume was refreshed from `demo_assets/`, and both studies now match DERM-404 (88 received, 64 clean, 24 quarantined).
- The dashboard's remediation dataset failed until `dq_remediation_log` existed, so the staging task now creates it.
