import type { Application, Request } from 'express';
import type { JobAPI } from '@databricks/appkit';
import { z } from 'zod';

interface StudyHubAppKit {
  lakebase: {
    query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
  };
  server: {
    extend(fn: (app: Application) => void): void;
  };
  jobs: (key: string) => JobAPI;
}

type SubmissionStatus =
  | 'UPLOADING'
  | 'PENDING_APPROVAL'
  | 'REJECTED'
  | 'PROCESSING'
  | 'PUBLISHED'
  | 'AWAITING_MANUAL_MODELLING'
  | 'FAILED';

const SCHEMA_SQL = [
  `CREATE SCHEMA IF NOT EXISTS study_hub`,
  `CREATE TABLE IF NOT EXISTS study_hub.submissions (
    submission_id TEXT PRIMARY KEY,
    study_id TEXT NOT NULL,
    study_title TEXT,
    phase TEXT,
    indication TEXT,
    therapeutic_area TEXT,
    sponsor TEXT,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    zip_path TEXT NOT NULL,
    upload_path TEXT NOT NULL,
    manifest JSONB,
    notes TEXT,
    status TEXT NOT NULL,
    submitted_by TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_comment TEXT,
    run_id BIGINT,
    run_url TEXT,
    run_state TEXT,
    run_tasks JSONB,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`,
  `CREATE TABLE IF NOT EXISTS study_hub.submission_events (
    id SERIAL PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES study_hub.submissions(submission_id),
    event TEXT NOT NULL,
    actor TEXT,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )`,
  `CREATE TABLE IF NOT EXISTS study_hub.dq_issue_reviews (
    study_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    usubjid TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'accepted')),
    comment TEXT,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (study_id, domain, rule_id, usubjid)
  )`,
];

const ReviewStatus = z.enum(['open', 'acknowledged', 'accepted']);
const DqReviewBody = z.object({
  study_id: z.string().regex(/^[A-Za-z0-9-]{2,40}$/),
  domain: z.string().regex(/^[a-z]{2,5}$/),
  rule_id: z.string().regex(/^[A-Z0-9_]{2,20}$/),
  usubjid: z.string().min(1).max(100),
  status: ReviewStatus,
  comment: z.string().max(2000).optional(),
});

const SUBMISSION_COLUMNS = `submission_id, study_id, study_title, phase, indication, therapeutic_area, sponsor,
  file_name, file_size, zip_path, upload_path, manifest, notes, status, submitted_by, submitted_at,
  reviewed_by, reviewed_at, review_comment, run_id, run_url, run_state, run_tasks, completed_at, updated_at`;

const ManifestEntry = z.object({ path: z.string(), size: z.number(), domain: z.string().nullable() });

// Same required domains as the browser pre-check and the staging task (01_unzip_and_stage.py).
export const REQUIRED_DOMAINS = ['dm', 'ae', 'lb'];
const DOMAIN_BY_STEM: Record<string, string> = {
  demographics: 'dm',
  adverse_events: 'ae',
  vital_signs: 'vs',
  exposure: 'ex',
  disposition: 'ds',
  site_visits: 'sv',
  central_lab_results: 'lb',
  labs: 'lb',
  study_metadata: 'meta',
};

export function missingDomains(paths: string[]): string[] {
  const present = new Set(
    paths.map((p) => DOMAIN_BY_STEM[(p.split('/').pop() ?? '').replace(/\.[^.]+$/, '').toLowerCase()]).filter(Boolean)
  );
  return REQUIRED_DOMAINS.filter((d) => !present.has(d));
}

const CreateSubmissionBody = z.object({
  study_id: z.string().regex(/^[A-Za-z0-9-]{2,40}$/, 'Study ID may only contain letters, numbers and hyphens'),
  file_name: z.string().min(1).max(200),
  file_size: z.number().int().nonnegative(),
  study_title: z.string().max(500).optional(),
  phase: z.string().max(50).optional(),
  indication: z.string().max(200).optional(),
  therapeutic_area: z.string().max(100).optional(),
  sponsor: z.string().max(200).optional(),
  notes: z.string().max(2000).optional(),
  manifest: z.array(ManifestEntry).max(500),
});

// `ai_demo_scenario` drives the mock AI data modelling step (src/notebooks/02_ai_data_modelling.py).
export const AI_SCENARIOS = ['pass', 'recover', 'fail'] as const;
const ReviewBody = z.object({
  comment: z.string().max(2000).optional(),
  ai_demo_scenario: z.enum(AI_SCENARIOS).optional(),
});

/** The onboarding run succeeded but stopped at the manual fallback: nothing was published yet. */
export function statusFromRun(
  lifecycle: string | undefined,
  resultState: string | undefined,
  tasks: { task_key: string; result?: string }[],
): SubmissionStatus {
  if (lifecycle !== 'TERMINATED' && lifecycle !== 'INTERNAL_ERROR' && lifecycle !== 'SKIPPED') return 'PROCESSING';
  if (resultState !== 'SUCCESS') return 'FAILED';
  const handoff = tasks.find((t) => t.task_key === 'manual_modelling_handoff');
  return handoff?.result === 'SUCCESS' ? 'AWAITING_MANUAL_MODELLING' : 'PUBLISHED';
}

function actorOf(req: Request): string {
  return req.header('x-forwarded-email') ?? req.header('x-forwarded-user') ?? 'local-developer';
}

function isAdmin(req: Request): boolean {
  return req.header('x-demo-persona') === 'admin';
}

function newSubmissionId(): string {
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  return `SUB-${ts}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

function safeFileName(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, '_');
}

export async function setupStudyHubRoutes(appkit: StudyHubAppKit) {
  const volumePath = (process.env.DATABRICKS_VOLUME_FILES ?? '').replace(/\/+$/, '');
  const catalog = process.env.STUDY_CATALOG ?? 'clinical_demo';
  const schema = process.env.STUDY_SCHEMA ?? 'study_onboarding';
  const job = appkit.jobs('default');
  // Human-in-the-loop fallback job (DATABRICKS_JOB_MANUAL_MODELLING); optional so older deployments keep working.
  const manualJob = process.env.DATABRICKS_JOB_MANUAL_MODELLING ? appkit.jobs('manual_modelling') : null;
  const portfolioTable = process.env.PORTFOLIO_TABLE ?? 'serving.study_portfolio';
  if (!/^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(portfolioTable)) throw new Error(`Invalid PORTFOLIO_TABLE: ${portfolioTable}`);

  try {
    for (const stmt of SCHEMA_SQL) await appkit.lakebase.query(stmt);
    console.log('[study-hub] Lakebase schema ready');
  } catch (err) {
    console.warn('[study-hub] Lakebase setup failed:', (err as Error).message);
  }

  async function logEvent(submissionId: string, event: string, actor: string, detail?: string) {
    await appkit.lakebase.query(
      'INSERT INTO study_hub.submission_events (submission_id, event, actor, detail) VALUES ($1, $2, $3, $4)',
      [submissionId, event, actor, detail ?? null],
    );
  }

  async function getSubmission(id: string) {
    const { rows } = await appkit.lakebase.query(
      `SELECT ${SUBMISSION_COLUMNS} FROM study_hub.submissions WHERE submission_id = $1`,
      [id],
    );
    return rows[0];
  }

  async function refreshRun(row: Record<string, unknown>) {
    const runId = Number(row.run_id);
    if (!runId) return;
    const result = await job.getRun(runId);
    if (!result.ok) return;
    const run = result.data;
    const lifecycle = run.state?.life_cycle_state;
    const resultState = run.state?.result_state;
    const tasks = (run.tasks ?? []).map((t) => ({
      task_key: t.task_key,
      state: t.state?.life_cycle_state,
      result: t.state?.result_state,
    }));
    const status = statusFromRun(lifecycle, resultState, tasks);
    await appkit.lakebase.query(
      `UPDATE study_hub.submissions
         SET status = $2, run_state = $3, run_tasks = $4::jsonb, run_url = COALESCE($5, run_url),
             completed_at = CASE WHEN $2 IN ('PUBLISHED', 'FAILED', 'AWAITING_MANUAL_MODELLING') THEN NOW() ELSE completed_at END,
             updated_at = NOW()
       WHERE submission_id = $1`,
      [row.submission_id, status, resultState ?? lifecycle ?? null, JSON.stringify(tasks), run.run_page_url ?? null],
    );
    if (status !== 'PROCESSING') {
      await logEvent(String(row.submission_id), status, 'lakeflow-job', `Run ${runId} finished: ${resultState ?? lifecycle}`);
    }
  }

  appkit.server.extend((app) => {
    app.get('/api/whoami', (req, res) => {
      res.json({
        email: req.header('x-forwarded-email') ?? null,
        user: req.header('x-forwarded-user') ?? null,
      });
    });

    app.get('/api/config', (_req, res) => {
      res.json({ catalog, schema, volumePath });
    });

    app.get('/api/portfolio', async (_req, res) => {
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT study_id, title, phase, indication, therapeutic_area, sponsor, planned_enrollment, enrolled,
                  pct_enrollment_target, active_sites, countries, discontinuation_rate_pct, sae_subject_rate_pct,
                  dq_issues, dq_high_issues, data_cutoff_date, headline, insights_generated_at,
                  subjects_received, subjects_clean, subjects_quarantined, pct_subjects_clean, records_quarantined
             FROM ${portfolioTable} ORDER BY study_id`
        );
        res.json({ source: 'lakebase', table: portfolioTable, rows });
      } catch (err) {
        res.status(503).json({ source: 'unavailable', error: (err as Error).message });
      }
    });

    app.get('/api/dq-reviews', async (req, res) => {
      const studyId = typeof req.query.study_id === 'string' ? req.query.study_id : '';
      if (!/^[A-Za-z0-9-]{2,40}$/.test(studyId)) {
        res.status(400).json({ error: 'study_id is required' });
        return;
      }
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT study_id, domain, rule_id, usubjid, status, comment, reviewed_by, reviewed_at
             FROM study_hub.dq_issue_reviews WHERE study_id = $1`,
          [studyId]
        );
        res.json(rows);
      } catch (err) {
        console.error('[study-hub] list dq reviews failed', err);
        res.status(500).json({ error: 'Failed to load reviews' });
      }
    });

    app.post('/api/dq-reviews', async (req, res) => {
      const parsed = DqReviewBody.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({ error: parsed.error.issues.map((i) => i.message).join('; ') });
        return;
      }
      const b = parsed.data;
      try {
        const { rows } = await appkit.lakebase.query(
          `INSERT INTO study_hub.dq_issue_reviews (study_id, domain, rule_id, usubjid, status, comment, reviewed_by, reviewed_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
           ON CONFLICT (study_id, domain, rule_id, usubjid)
           DO UPDATE SET status = EXCLUDED.status, comment = EXCLUDED.comment,
                         reviewed_by = EXCLUDED.reviewed_by, reviewed_at = NOW()
           RETURNING study_id, domain, rule_id, usubjid, status, comment, reviewed_by, reviewed_at`,
          [b.study_id, b.domain, b.rule_id, b.usubjid, b.status, b.comment ?? null, actorOf(req)]
        );
        res.json(rows[0]);
      } catch (err) {
        console.error('[study-hub] save dq review failed', err);
        res.status(500).json({ error: 'Failed to save review' });
      }
    });

    app.get('/api/submissions', async (_req, res) => {
      try {
        const processing = await appkit.lakebase.query(
          `SELECT submission_id, run_id FROM study_hub.submissions WHERE status = 'PROCESSING'`,
        );
        await Promise.all(processing.rows.map((r) => refreshRun(r).catch((e) => console.warn('[study-hub] refresh failed', e))));
        const { rows } = await appkit.lakebase.query(
          `SELECT ${SUBMISSION_COLUMNS} FROM study_hub.submissions ORDER BY submitted_at DESC LIMIT 200`,
        );
        res.json(rows);
      } catch (err) {
        console.error('[study-hub] list submissions failed', err);
        res.status(500).json({ error: 'Failed to list submissions' });
      }
    });

    app.get('/api/submissions/:id', async (req, res) => {
      try {
        const row = await getSubmission(req.params.id);
        if (!row) {
          res.status(404).json({ error: 'Submission not found' });
          return;
        }
        if (row.status === 'PROCESSING') await refreshRun(row);
        const { rows: events } = await appkit.lakebase.query(
          'SELECT event, actor, detail, created_at FROM study_hub.submission_events WHERE submission_id = $1 ORDER BY created_at',
          [req.params.id],
        );
        res.json({ ...(await getSubmission(req.params.id)), events });
      } catch (err) {
        console.error('[study-hub] get submission failed', err);
        res.status(500).json({ error: 'Failed to load submission' });
      }
    });

    app.post('/api/submissions', async (req, res) => {
      const parsed = CreateSubmissionBody.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({ error: parsed.error.issues.map((i) => i.message).join('; ') });
        return;
      }
      const body = parsed.data;
      if (!body.file_name.toLowerCase().endsWith('.zip')) {
        res.status(400).json({ error: 'Study packages must be .zip files' });
        return;
      }
      if (!body.manifest.some((m) => m.path.endsWith('study_metadata.json'))) {
        res.status(400).json({ error: 'Package must contain study_metadata.json' });
        return;
      }
      const missing = missingDomains(body.manifest.map((m) => m.path));
      if (missing.length > 0) {
        res.status(400).json({ error: `Package is missing required domain files: ${missing.join(', ')}` });
        return;
      }
      try {
        const id = newSubmissionId();
        const uploadPath = `${id}__${safeFileName(body.file_name)}`;
        const actor = actorOf(req);
        await appkit.lakebase.query(
          `INSERT INTO study_hub.submissions
             (submission_id, study_id, study_title, phase, indication, therapeutic_area, sponsor,
              file_name, file_size, zip_path, upload_path, manifest, notes, status, submitted_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13, 'UPLOADING', $14)`,
          [
            id, body.study_id, body.study_title ?? null, body.phase ?? null, body.indication ?? null,
            body.therapeutic_area ?? null, body.sponsor ?? null, body.file_name, body.file_size,
            `${volumePath}/${uploadPath}`, uploadPath, JSON.stringify(body.manifest), body.notes ?? null, actor,
          ],
        );
        await logEvent(id, 'CREATED', actor, `${body.file_name} (${body.manifest.length} files)`);
        res.status(201).json({ submission_id: id, upload_path: uploadPath });
      } catch (err) {
        console.error('[study-hub] create submission failed', err);
        res.status(500).json({ error: 'Failed to create submission' });
      }
    });

    app.post('/api/submissions/:id/submit', async (req, res) => {
      try {
        const { rows } = await appkit.lakebase.query(
          `UPDATE study_hub.submissions SET status = 'PENDING_APPROVAL', updated_at = NOW()
           WHERE submission_id = $1 AND status = 'UPLOADING' RETURNING submission_id`,
          [req.params.id],
        );
        if (rows.length === 0) {
          res.status(409).json({ error: 'Submission is not awaiting upload' });
          return;
        }
        await logEvent(req.params.id, 'SUBMITTED_FOR_APPROVAL', actorOf(req));
        res.json(await getSubmission(req.params.id));
      } catch (err) {
        console.error('[study-hub] submit failed', err);
        res.status(500).json({ error: 'Failed to submit for approval' });
      }
    });

    app.post('/api/submissions/:id/approve', async (req, res) => {
      if (!isAdmin(req)) {
        res.status(403).json({ error: 'Only an Admin can approve study packages' });
        return;
      }
      const body = ReviewBody.safeParse(req.body ?? {});
      if (!body.success) {
        res.status(400).json({ error: body.error.issues.map((i) => i.message).join('; ') });
        return;
      }
      const comment = body.data.comment ?? null;
      const scenario = body.data.ai_demo_scenario ?? 'pass';
      try {
        const row = await getSubmission(req.params.id);
        if (!row) {
          res.status(404).json({ error: 'Submission not found' });
          return;
        }
        if (row.status !== 'PENDING_APPROVAL' && row.status !== 'FAILED') {
          res.status(409).json({ error: `Cannot approve a submission in status ${String(row.status)}` });
          return;
        }
        const actor = actorOf(req);
        const run = await job.runNow({
          job_parameters: {
            submission_id: String(row.submission_id),
            study_id: String(row.study_id),
            zip_path: String(row.zip_path),
            catalog,
            schema,
            ai_demo_scenario: scenario,
          },
        });
        if (!run.ok || !run.data.run_id) {
          res.status(502).json({ error: `Failed to start onboarding job${run.ok ? '' : `: ${run.message}`}` });
          return;
        }
        await appkit.lakebase.query(
          `UPDATE study_hub.submissions
             SET status = 'PROCESSING', reviewed_by = $2, reviewed_at = NOW(), review_comment = $3,
                 run_id = $4, run_state = 'PENDING', run_tasks = NULL, completed_at = NULL, updated_at = NOW()
           WHERE submission_id = $1`,
          [row.submission_id, actor, comment, run.data.run_id],
        );
        await logEvent(String(row.submission_id), 'APPROVED', actor, comment ?? undefined);
        await logEvent(
          String(row.submission_id),
          'JOB_TRIGGERED',
          'study-hub',
          `Run ${run.data.run_id}${scenario === 'pass' ? '' : ` (AI modelling simulation: ${scenario})`}`,
        );
        res.json(await getSubmission(req.params.id));
      } catch (err) {
        console.error('[study-hub] approve failed', err);
        res.status(500).json({ error: 'Failed to approve submission' });
      }
    });

    app.post('/api/submissions/:id/manual-modelling', async (req, res) => {
      if (!isAdmin(req)) {
        res.status(403).json({ error: 'Only an Admin can start manual data modelling' });
        return;
      }
      if (!manualJob) {
        res.status(501).json({ error: 'The manual data modelling job is not configured for this app' });
        return;
      }
      try {
        const row = await getSubmission(req.params.id);
        if (!row) {
          res.status(404).json({ error: 'Submission not found' });
          return;
        }
        if (row.status !== 'AWAITING_MANUAL_MODELLING') {
          res.status(409).json({ error: `Manual modelling is only available while awaiting it, not in status ${String(row.status)}` });
          return;
        }
        const actor = actorOf(req);
        const run = await manualJob.runNow({
          job_parameters: {
            submission_id: String(row.submission_id),
            study_id: String(row.study_id),
            reviewer: actor,
            catalog,
            schema,
          },
        });
        if (!run.ok || !run.data.run_id) {
          res.status(502).json({ error: `Failed to start manual modelling job${run.ok ? '' : `: ${run.message}`}` });
          return;
        }
        await appkit.lakebase.query(
          `UPDATE study_hub.submissions
             SET status = 'PROCESSING', run_id = $2, run_state = 'PENDING', run_tasks = NULL, completed_at = NULL, updated_at = NOW()
           WHERE submission_id = $1`,
          [row.submission_id, run.data.run_id],
        );
        await logEvent(String(row.submission_id), 'MANUAL_MODELLING_STARTED', actor, `Run ${run.data.run_id}`);
        res.json(await getSubmission(req.params.id));
      } catch (err) {
        console.error('[study-hub] manual modelling failed', err);
        res.status(500).json({ error: 'Failed to start manual modelling' });
      }
    });

    app.post('/api/submissions/:id/reject', async (req, res) => {
      if (!isAdmin(req)) {
        res.status(403).json({ error: 'Only an Admin can reject study packages' });
        return;
      }
      const comment = ReviewBody.safeParse(req.body ?? {}).data?.comment ?? null;
      try {
        const actor = actorOf(req);
        const { rows } = await appkit.lakebase.query(
          `UPDATE study_hub.submissions
             SET status = 'REJECTED', reviewed_by = $2, reviewed_at = NOW(), review_comment = $3, updated_at = NOW()
           WHERE submission_id = $1 AND status = 'PENDING_APPROVAL' RETURNING submission_id`,
          [req.params.id, actor, comment],
        );
        if (rows.length === 0) {
          res.status(409).json({ error: 'Only pending submissions can be rejected' });
          return;
        }
        await logEvent(req.params.id, 'REJECTED', actor, comment ?? undefined);
        res.json(await getSubmission(req.params.id));
      } catch (err) {
        console.error('[study-hub] reject failed', err);
        res.status(500).json({ error: 'Failed to reject submission' });
      }
    });
  });
}
