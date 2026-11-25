import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from '@databricks/appkit-ui/react';
import { CheckCircle2, ExternalLink, Loader2, ShieldCheck, XCircle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { EmptyBlock, ErrorBlock, LoadingBlock, PageHeader, PipelineProgress, StatusBadge } from '../components/common';
import { usePersona } from '../lib/persona';
import {
  DOMAIN_LABEL,
  formatBytes,
  formatDateTime,
  readError,
  useSubmissions,
  type Submission,
  type SubmissionEvent,
} from '../lib/submissions';

function ReviewPanel({ submission, onDone }: { submission: Submission; onDone: () => Promise<void> }) {
  const { apiFetch } = usePersona();
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<SubmissionEvent[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setEvents(null);
    setComment('');
    setError(null);
    apiFetch(`/api/submissions/${submission.submission_id}`)
      .then((r) => r.json())
      .then((d: { events?: SubmissionEvent[] }) => !cancelled && setEvents(d.events ?? []))
      .catch(() => !cancelled && setEvents([]));
    return () => {
      cancelled = true;
    };
  }, [submission.submission_id, submission.status, apiFetch]);

  const act = async (action: 'approve' | 'reject') => {
    setBusy(action);
    setError(null);
    try {
      const res = await apiFetch(`/api/submissions/${submission.submission_id}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ comment: comment.trim() || undefined }),
      });
      if (!res.ok) throw new Error(await readError(res));
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const domains = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of submission.manifest ?? []) if (m.domain) counts.set(m.domain, (counts.get(m.domain) ?? 0) + 1);
    return [...counts.entries()];
  }, [submission.manifest]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2">
              {submission.study_id}
              <StatusBadge status={submission.status} />
            </CardTitle>
            <CardDescription className="mt-1">{submission.study_title ?? 'Untitled study'}</CardDescription>
          </div>
          <span className="font-mono text-xs text-muted-foreground">{submission.submission_id}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-4">
          {[
            ['Phase', submission.phase],
            ['Therapeutic area', submission.therapeutic_area],
            ['Indication', submission.indication],
            ['Sponsor', submission.sponsor],
            ['Package', `${submission.file_name} (${formatBytes(submission.file_size)})`],
            ['Submitted by', submission.submitted_by],
            ['Submitted at', formatDateTime(submission.submitted_at)],
            ['Files', String(submission.manifest?.length ?? 0)],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-muted-foreground">{k}</dt>
              <dd className="truncate font-medium">{v ?? '\u2014'}</dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-wrap gap-2">
          {domains.map(([d, n]) => (
            <Badge key={d} variant="secondary">
              {DOMAIN_LABEL[d] ?? d}
              {n > 1 ? ` ×${n}` : ''}
            </Badge>
          ))}
        </div>

        {submission.notes && (
          <Alert>
            <AlertTitle>Submitter notes</AlertTitle>
            <AlertDescription>{submission.notes}</AlertDescription>
          </Alert>
        )}

        <div className="max-h-48 overflow-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Domain</TableHead>
                <TableHead className="text-right">Size</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(submission.manifest ?? []).map((m) => (
                <TableRow key={m.path}>
                  <TableCell className="font-mono text-xs">{m.path}</TableCell>
                  <TableCell className="text-xs">{m.domain ? DOMAIN_LABEL[m.domain] ?? m.domain : 'Unmapped'}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{formatBytes(m.size)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {submission.status === 'PENDING_APPROVAL' ? (
          <div className="space-y-3 rounded-lg border bg-muted/40 p-4">
            <div className="space-y-1.5">
              <Label htmlFor="review-comment">Review comment</Label>
              <Textarea
                id="review-comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Optional for approval, recommended when rejecting"
              />
            </div>
            {error && <ErrorBlock title="Action failed" message={error} />}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => void act('reject')} disabled={busy !== null}>
                {busy === 'reject' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <XCircle className="mr-2 h-4 w-4" />}
                Reject
              </Button>
              <Button onClick={() => void act('approve')} disabled={busy !== null}>
                {busy === 'approve' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                Approve &amp; process
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Approving starts the onboarding job: unzip &amp; stage, then the Bronze → Silver → Gold pipeline, then AI insights.
            </p>
          </div>
        ) : (
          <div className="space-y-2 rounded-lg border p-4">
            {(submission.status === 'PROCESSING' || submission.status === 'PUBLISHED' || submission.status === 'FAILED') && (
              <PipelineProgress tasks={submission.run_tasks} status={submission.status} />
            )}
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              {submission.reviewed_by && (
                <span>
                  Reviewed by {submission.reviewed_by} · {formatDateTime(submission.reviewed_at)}
                </span>
              )}
              {submission.run_url && (
                <a className="inline-flex items-center gap-1 text-primary hover:underline" href={submission.run_url} target="_blank" rel="noreferrer">
                  View job run <ExternalLink className="h-3 w-3" />
                </a>
              )}
              {submission.status === 'PUBLISHED' && (
                <Link className="text-primary hover:underline" to={`/studies/${submission.study_id}`}>
                  Open study insights →
                </Link>
              )}
            </div>
            {submission.review_comment && <p className="text-sm">“{submission.review_comment}”</p>}
          </div>
        )}

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Audit trail</div>
          {events === null ? (
            <LoadingBlock rows={2} height="h-4" />
          ) : events.length === 0 ? (
            <p className="text-xs text-muted-foreground">No events recorded.</p>
          ) : (
            <ol className="space-y-1.5 border-l pl-4">
              {events.map((e) => (
                <li key={`${e.event}-${e.created_at}`} className="text-xs">
                  <span className="font-medium">{e.event}</span>
                  <span className="text-muted-foreground"> · {e.actor ?? 'system'} · {formatDateTime(e.created_at)}</span>
                  {e.detail && <div className="text-muted-foreground">{e.detail}</div>}
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function ApprovalsPage() {
  const { persona } = usePersona();
  const { submissions, loading, error, refresh } = useSubmissions(5000);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const pending = submissions.filter((s) => s.status === 'PENDING_APPROVAL');
  const history = submissions.filter((s) => s.status !== 'PENDING_APPROVAL' && s.status !== 'UPLOADING');
  const selected = submissions.find((s) => s.submission_id === selectedId) ?? pending[0] ?? history[0] ?? null;

  if (persona !== 'admin') {
    return (
      <div className="mx-auto w-full max-w-3xl pt-10">
        <EmptyBlock
          icon={<ShieldCheck />}
          title="Admin access required"
          description="Switch the persona to Admin in the header to review and approve study packages."
        />
      </div>
    );
  }

  const row = (s: Submission) => (
    <button
      key={s.submission_id}
      type="button"
      onClick={() => setSelectedId(s.submission_id)}
      className={`w-full rounded-md border p-3 text-left transition-colors ${
        selected?.submission_id === s.submission_id ? 'border-primary bg-accent' : 'hover:bg-muted'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{s.study_id}</span>
        <StatusBadge status={s.status} />
      </div>
      <div className="mt-1 truncate text-xs text-muted-foreground">{s.study_title ?? s.file_name}</div>
      <div className="mt-1 text-xs text-muted-foreground">
        {s.submitted_by ?? 'unknown'} · {formatDateTime(s.submitted_at)}
      </div>
    </button>
  );

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Governance"
        title="Approval queue"
        description="Review incoming study packages before they are processed into the clinical data hub. Every decision is recorded in the audit trail."
      />
      {loading ? (
        <LoadingBlock rows={4} height="h-16" />
      ) : error ? (
        <ErrorBlock message={error} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Pending ({pending.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {pending.length === 0 ? <p className="text-sm text-muted-foreground">Nothing waiting for review.</p> : pending.map(row)}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Recent decisions</CardTitle>
              </CardHeader>
              <CardContent className="max-h-[480px] space-y-2 overflow-auto">
                {history.length === 0 ? <p className="text-sm text-muted-foreground">No decisions yet.</p> : history.slice(0, 20).map(row)}
              </CardContent>
            </Card>
          </div>
          <div className="lg:col-span-2">
            {selected ? (
              <ReviewPanel submission={selected} onDone={refresh} />
            ) : (
              <EmptyBlock title="No submissions" description="Study packages uploaded by Study Managers will appear here for review." />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
