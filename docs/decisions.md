# Decisions and trade-offs

Each decision lists the alternative we did not take, and why.

## Lakeflow Declarative Pipelines for Bronze, Silver and Gold

- **Chosen:** a Lakeflow Declarative Pipeline (`src/pipeline/transformations/`) with data quality expectations and lineage.
- **Alternative:** plain notebooks that write Delta tables.
- **Why:** expectations, lineage and incremental refresh come with the pipeline, so the quality story is part of the
  platform, not custom code. Notebooks would have to re-implement all three.

## Quarantine tables instead of dropping or flagging bad records

- **Chosen:** the quarantine pattern from the Lakeflow Declarative Pipelines docs. Each domain has a private
  `silver_<d>_checked` table with every row and its rule failures, then two outputs: `silver_<d>` (clean) and
  `silver_<d>_quarantine` (everything else, with `quarantine_reason`). Expectations are warn-only, so they record
  metrics in the event log and never drop a row.
- **Alternatives:** `expect_or_drop`, which loses the record and the evidence of why; or keeping flagged rows in the
  clean tables with a flag column, which lets bad values reach Gold, Genie and the AI briefing unless every reader
  remembers to filter.
- **Why:** in a clinical study nothing may silently disappear, and nothing unverified should reach an analysis.
  Quarantine meets both: every staged row is in exactly one place (`dq_reconciliation` proves it per study and
  domain), and the clean tables are clean by construction.

## Subject-level quarantine

- **Chosen:** if any record of a subject fails a quarantine rule, all of that subject's records go to quarantine
  (`SUBJECT_CASCADE`), and `silver_subject_status` records why.
- **Alternative:** quarantine only the failing record.
- **Why:** record-level removal produces partial subjects, for example a patient with labs but no demographics or
  an AE without its consent date, which skew rates and denominators without any visible sign. Per-subject KPIs
  stay honest when the denominator is "clean subjects", and the app reports coverage next to every KPI
  ("97 of 124 subjects clean, 27 quarantined").
- **Trade-off:** a single bad value removes a whole subject from the KPIs until a corrected package is resubmitted.
  The planted issues quarantine 22 to 29% of subjects per study, which is visible on purpose.

## One rules registry, two actions

- **Chosen:** `src/pipeline/dq_rules.py` holds every rule (ID, domain, severity, action, valid condition, detail).
  The Silver expectations, the quarantine logic, the Gold issue tables and the `dq_rules` table are all generated
  from it. A rule's action is `quarantine` (the data is wrong) or `observe` (real data worth reporting, such as an
  out-of-window visit or an AE before randomization, which stays in the clean tables).
- **Alternative:** checks written inline in each table definition and a separate list for the app.
- **Why:** one place to review and change a rule, the "portable and reusable expectations" pattern from the docs.
  Protocol deviations are real events, so quarantining them would hide real data.

## Only clean data reaches Genie and the AI briefing

- **Chosen:** the Genie space exposes the Gold marts, `silver_ae`, `silver_lb` and `gold_dq_summary` (counts only).
  Quarantine tables, `gold_dq_issues` (its details contain the offending values) and the AI briefing text are left
  out. The AI briefing gets clean metrics plus coverage counts, and its output is validated before it is stored.
- **Alternative:** expose everything and rely on Genie instructions to filter.
- **Why:** instructions are guidance, not a boundary. Leaving the tables out is a hard boundary.
  `scripts/genie_eval.py` checks it by asking probe questions and searching the answers for quarantined subject IDs.

## AppKit (React and Express) instead of Streamlit

- **Chosen:** a Databricks App on AppKit, with a typed Express server and a React client.
- **Alternative:** a Streamlit or Gradio app.
- **Why:** the app needs a multi-step approval workflow, role-based views and a Lakebase connection. A server with
  routes is easier to test (`vitest`) and to evolve than a single-script app.

## ai_query inside the job instead of a served agent

- **Chosen:** `ai_query` in `src/notebooks/03_study_insights.py`, one call per study, output stored in a Gold table.
- **Alternative:** a served model or agent endpoint that the app calls on each page view.
- **Why:** the briefing is generated once per study and is part of the governed data. Every reader sees the same
  text, and there is no per-page-view model cost or latency. A served agent would make sense for interactive
  follow-up questions, which Genie covers.

## Lakebase for workflow state and a synced table for the portfolio

- **Chosen:** Lakebase holds submissions and approvals (OLTP writes). `study_portfolio` is a Delta table, and a
  Lakebase synced table serves it to the app.
- **Alternative:** the app queries the SQL warehouse for every page view, or keeps all state in Delta.
- **Why:** approval writes are transactional and frequent, which suits Postgres. The portfolio is read-heavy, which
  suits a synced copy. The SQL warehouse stays for analytics and Genie, so it is not on the hot path of every page.
- **Trade-off:** the synced table adds a refresh lag (triggered mode). The portfolio page falls back to the SQL query
  if the synced table is empty or unavailable.

## Genie Agent instead of a custom text-to-SQL layer

- **Chosen:** a Genie space over the clean Gold and Silver tables, with instructions on coverage and the data quality
  rules.
- **Alternative:** our own prompt-to-SQL service.
- **Why:** Genie handles SQL generation, permissions and conversation history on the platform. Our effort goes to
  the instructions and the sample questions, which are the parts that are specific to the domain.

## Synthetic data generated by a committed script

- **Chosen:** `src/data_gen/generate_studies.py` produces the three sample packages and the demo packages. The output
  is committed. Regenerating it produces the same file names and identical CSV and JSON contents as the committed zips.
- **Alternative:** public clinical datasets, or hand-made CSVs.
- **Why:** public clinical datasets have licence and realism issues for a demo, and hand-made files cannot be
  regenerated. The generator also plants known data quality problems (out-of-range ages, missing consent dates), so the
  quality checks have something real to find. The live-demo packages DERM-404, NEURO-505 and IMMUNO-606 are re-keyed
  copies of RESP-303.

## Package checks at three points

- **Chosen:** the same required domains (demographics, adverse events, labs) are checked in the browser, by the
  server route and by the staging task, which also records missing columns. Unrecognized files are copied to
  `raw/<study>/unrecognized/` and listed in the staging report instead of being skipped.
- **Alternative:** check only in the browser.
- **Why:** the browser check is for convenience; the server and the staging task are the ones that can be trusted.

## Approval gate before every run

- **Chosen:** a submission is uploaded, reviewed by an Admin, and only then runs the job.
- **Alternative:** a watched landing folder that starts a run on upload.
- **Why:** a sponsor package should not be processed before a person has checked it is the right study and is complete.
