import { useCallback, useEffect, useState } from 'react';
import { usePersona } from './persona';
import { readError } from './submissions';

export type ReviewStatus = 'open' | 'acknowledged' | 'accepted';

export interface DqReview {
  study_id: string;
  domain: string;
  rule_id: string;
  usubjid: string;
  status: ReviewStatus;
  comment: string | null;
  reviewed_by: string | null;
  reviewed_at: string;
}

// Rule IDs such as DT01 or REF01 exist in several domains, so a rule is identified by domain + rule_id.
export function ruleKey(domain: string, ruleId: string): string {
  return `${domain.toUpperCase()}.${ruleId}`;
}

export function issueKey(domain: string, ruleId: string, usubjid: string): string {
  return `${ruleKey(domain, ruleId)}|${usubjid}`;
}

export function coverageLabel(clean: unknown, received: unknown, quarantined: unknown): string | null {
  if (received == null || clean == null) return null;
  const q = Number(quarantined ?? Number(received) - Number(clean));
  return `${Number(clean).toLocaleString()} of ${Number(received).toLocaleString()} subjects clean · ${q.toLocaleString()} quarantined`;
}

export function useDqReviews(studyId: string) {
  const { apiFetch } = usePersona();
  const [reviews, setReviews] = useState<Map<string, DqReview>>(new Map());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/dq-reviews?study_id=${encodeURIComponent(studyId)}`);
      if (!res.ok) throw new Error(await readError(res));
      const rows = (await res.json()) as DqReview[];
      setReviews(new Map(rows.map((r) => [issueKey(r.domain, r.rule_id, r.usubjid), r])));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [apiFetch, studyId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = useCallback(
    async (issue: { domain: string; rule_id: string; usubjid: string }, status: ReviewStatus, comment?: string) => {
      const res = await apiFetch('/api/dq-reviews', {
        method: 'POST',
        body: JSON.stringify({ study_id: studyId, ...issue, status, comment }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const saved = (await res.json()) as DqReview;
      setReviews((prev) => new Map(prev).set(issueKey(saved.domain, saved.rule_id, saved.usubjid), saved));
    },
    [apiFetch, studyId]
  );

  return { reviews, error, save, refresh };
}
