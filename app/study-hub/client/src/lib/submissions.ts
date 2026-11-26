import { useCallback, useEffect, useState } from 'react';
import { usePersona } from './persona';

export type SubmissionStatus =
  | 'UPLOADING'
  | 'PENDING_APPROVAL'
  | 'REJECTED'
  | 'PROCESSING'
  | 'PUBLISHED'
  | 'AWAITING_MANUAL_MODELLING'
  | 'FAILED';

export type AiScenario = 'pass' | 'recover' | 'fail';
export const AI_SCENARIO_LABEL: Record<AiScenario, string> = {
  pass: 'Normal: AI accuracy meets the threshold',
  recover: 'Recover: below threshold, fixed on retry 2',
  fail: 'Fail: below threshold after 3 retries, manual fallback',
};

export interface ManifestEntry {
  path: string;
  size: number;
  domain: string | null;
}

export interface RunTask {
  task_key: string;
  state?: string;
  result?: string;
}

export interface Submission {
  submission_id: string;
  study_id: string;
  study_title: string | null;
  phase: string | null;
  indication: string | null;
  therapeutic_area: string | null;
  sponsor: string | null;
  file_name: string;
  file_size: number | null;
  zip_path: string;
  upload_path: string;
  manifest: ManifestEntry[] | null;
  notes: string | null;
  status: SubmissionStatus;
  submitted_by: string | null;
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  run_id: number | null;
  run_url: string | null;
  run_state: string | null;
  run_tasks: RunTask[] | null;
  completed_at: string | null;
}

export interface SubmissionEvent {
  event: string;
  actor: string | null;
  detail: string | null;
  created_at: string;
}

export async function readError(res: Response): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { error?: string };
  return body.error ?? `HTTP ${res.status}`;
}

export function useSubmissions(pollMs = 10000) {
  const { apiFetch } = usePersona();
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch('/api/submissions');
      if (!res.ok) throw new Error(await readError(res));
      setSubmissions((await res.json()) as Submission[]);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(t);
  }, [refresh, pollMs]);

  return { submissions, loading, error, refresh };
}

export function formatBytes(n: number | null | undefined): string {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDateTime(s: string | null | undefined): string {
  if (!s) return '\u2014';
  return new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export const DOMAIN_LABEL: Record<string, string> = {
  dm: 'Demographics (DM)',
  ae: 'Adverse Events (AE)',
  vs: 'Vital Signs (VS)',
  ex: 'Exposure (EX)',
  ds: 'Disposition (DS)',
  sv: 'Subject Visits (SV)',
  lb: 'Central Lab (LB)',
  meta: 'Protocol metadata',
};

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

export function domainForPath(path: string): string | null {
  const file = path.split('/').pop() ?? '';
  const stem = file.replace(/\.[^.]+$/, '').toLowerCase();
  return DOMAIN_BY_STEM[stem] ?? null;
}
