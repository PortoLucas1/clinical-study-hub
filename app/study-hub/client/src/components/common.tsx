import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Card,
  CardContent,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Skeleton,
} from '@databricks/appkit-ui/react';
import { AlertTriangle, CheckCircle2, CircleDashed, Clock, Hand, Inbox, Loader2, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import type { RunTask, SubmissionStatus } from '../lib/submissions';

const STATUS_STYLE: Record<SubmissionStatus, { label: string; className: string; icon: ReactNode }> = {
  UPLOADING: { label: 'Uploading', className: 'bg-muted text-muted-foreground', icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  PENDING_APPROVAL: { label: 'Pending approval', className: 'bg-warning/20 text-warning-foreground', icon: <Clock className="h-3 w-3" /> },
  REJECTED: { label: 'Rejected', className: 'bg-destructive/15 text-destructive', icon: <XCircle className="h-3 w-3" /> },
  PROCESSING: { label: 'Processing', className: 'bg-accent text-accent-foreground', icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  PUBLISHED: { label: 'Published', className: 'bg-success/15 text-success', icon: <CheckCircle2 className="h-3 w-3" /> },
  AWAITING_MANUAL_MODELLING: {
    label: 'Manual modelling needed',
    className: 'bg-warning/20 text-warning-foreground',
    icon: <Hand className="h-3 w-3" />,
  },
  FAILED: { label: 'Failed', className: 'bg-destructive/15 text-destructive', icon: <AlertTriangle className="h-3 w-3" /> },
};

export type ThresholdStatus = 'ok' | 'warn' | 'critical';

const THRESHOLD_STYLE: Record<ThresholdStatus, { label: string; className: string }> = {
  ok: { label: 'DQ within thresholds', className: 'bg-success/15 text-success' },
  warn: { label: 'DQ warning', className: 'bg-warning/20 text-warning-foreground' },
  critical: { label: 'DQ critical', className: 'bg-destructive/15 text-destructive' },
};

/** Data quality threshold status (dq_study_status): ok, warn or critical. */
export function ThresholdBadge({ status, title }: { status: unknown; title?: string }) {
  const key = (['ok', 'warn', 'critical'].includes(String(status)) ? String(status) : 'ok') as ThresholdStatus;
  const s = THRESHOLD_STYLE[key];
  return (
    <Badge variant="outline" title={title} className={`gap-1 border-transparent ${s.className}`}>
      {key === 'ok' ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
      {s.label}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: SubmissionStatus }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.UPLOADING;
  return (
    <Badge variant="outline" className={`gap-1 border-transparent ${s.className}`}>
      {s.icon}
      {s.label}
    </Badge>
  );
}

export function KpiTile({
  label,
  value,
  unit,
  context,
  tone = 'default',
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  context?: ReactNode;
  tone?: 'default' | 'good' | 'watch' | 'bad';
}) {
  const toneClass =
    tone === 'good' ? 'text-success' : tone === 'watch' ? 'text-warning' : tone === 'bad' ? 'text-destructive' : 'text-primary';
  return (
    <Card className="gap-1 border-l-4 border-l-primary py-4">
      <CardContent className="px-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className={`mt-1 text-3xl font-light tabular-nums ${toneClass}`}>
          {value}
          {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
        </div>
        {context && <div className="mt-1 text-xs text-muted-foreground">{context}</div>}
      </CardContent>
    </Card>
  );
}

export function LoadingBlock({ rows = 3, height = 'h-6' }: { rows?: number; height?: string }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`${height} w-full`} />
      ))}
    </div>
  );
}

export function ErrorBlock({ title = 'Could not load data', message }: { title?: string; message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

export function EmptyBlock({ title, description, icon }: { title: string; description?: string; icon?: ReactNode }) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">{icon ?? <Inbox />}</EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description && <EmptyDescription>{description}</EmptyDescription>}
      </EmptyHeader>
    </Empty>
  );
}

const STEPS: { key: string; alt?: string; label: string }[] = [
  { key: 'unzip_and_stage', label: 'Unzip & stage' },
  { key: 'ai_data_modelling', alt: 'apply_manual_modelling', label: 'AI data modelling' },
  { key: 'declarative_pipeline', label: 'Bronze \u2192 Silver \u2192 Gold' },
  { key: 'dq_threshold_check', label: 'Quality thresholds' },
  { key: 'study_insights', label: 'AI insights' },
  { key: 'publish_portfolio', label: 'Publish to Lakebase' },
];

export function PipelineProgress({ tasks, status }: { tasks: RunTask[] | null; status: SubmissionStatus }) {
  const byKey = new Map((tasks ?? []).map((t) => [t.task_key, t]));
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs">
      {STEPS.map((step, i) => {
        const t = byKey.get(step.key) ?? (step.alt ? byKey.get(step.alt) : undefined);
        const awaiting = status === 'AWAITING_MANUAL_MODELLING' && step.key === 'ai_data_modelling';
        const done = !awaiting && (t?.result === 'SUCCESS' || status === 'PUBLISHED');
        const failed = t?.result && t.result !== 'SUCCESS' && t.result !== 'EXCLUDED';
        const running = !done && !failed && (t?.state === 'RUNNING' || t?.state === 'PENDING' || t?.state === 'QUEUED');
        const icon = awaiting ? (
          <Hand className="h-3.5 w-3.5 text-warning" />
        ) : done ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-success" />
        ) : failed ? (
          <XCircle className="h-3.5 w-3.5 text-destructive" />
        ) : running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        ) : (
          <CircleDashed className="h-3.5 w-3.5 text-muted-foreground" />
        );
        return (
          <li key={step.key} className="flex items-center gap-1.5">
            {icon}
            <span className={done || awaiting ? 'text-foreground' : 'text-muted-foreground'}>
              {awaiting ? 'AI data modelling: manual review needed' : step.label}
            </span>
            {i < STEPS.length - 1 && <span className="mx-1 text-muted-foreground">/</span>}
          </li>
        );
      })}
    </ol>
  );
}

export function BrandHeading({ text, className = '', everyWord = false }: { text: string; className?: string; everyWord?: boolean }) {
  return (
    <span className={`brand-heading ${className}`}>
      {text.split(' ').map((word, i) => (
        <span key={`${word}-${i}`}>
          {i > 0 && ' '}
          {i === 0 || everyWord ? (
            <>
              <span className="initial">{word.charAt(0)}</span>
              {word.slice(1)}
            </>
          ) : (
            word
          )}
        </span>
      ))}
    </span>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        {eyebrow && <div className="text-xs font-semibold uppercase tracking-widest text-primary">{eyebrow}</div>}
        <h2 className="mt-1 text-3xl text-foreground">
          <BrandHeading text={title} />
        </h2>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
