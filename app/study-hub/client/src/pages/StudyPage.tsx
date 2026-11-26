import {
  BarChart,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  LineChart,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { AlertTriangle, ArrowLeft, Lightbulb, ShieldAlert, Sparkles } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { BrandHeading, EmptyBlock, ErrorBlock, KpiTile, LoadingBlock } from '../components/common';
import { StudyGenie } from '../components/StudyGenie';
import { usePersona } from '../lib/persona';
import { pivot } from '../lib/pivot';
import { coverageLabel, issueKey, ruleKey, useDqReviews, type ReviewStatus } from '../lib/quality';
import { formatDateTime } from '../lib/submissions';

interface Finding {
  category?: string;
  severity?: string;
  title?: string;
  detail?: string;
}

function parseJson<T>(raw: unknown, fallback: T): T {
  if (raw == null || raw === '') return fallback;
  if (typeof raw !== 'string') return raw as T;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function severityClass(sev: string | undefined) {
  const s = (sev ?? '').toLowerCase();
  if (s === 'high' || s === 'critical') return 'bg-destructive/15 text-destructive';
  if (s === 'medium') return 'bg-warning/20 text-warning-foreground';
  return 'bg-muted text-muted-foreground';
}

function SeverityBadge({ severity }: { severity?: string }) {
  return (
    <Badge variant="outline" className={`border-transparent capitalize ${severityClass(severity)}`}>
      {(severity ?? 'info').toLowerCase()}
    </Badge>
  );
}

function ActionBadge({ action }: { action?: string }) {
  return action === 'quarantine' ? (
    <Badge variant="outline" className="border-destructive/40 text-destructive">
      quarantine
    </Badge>
  ) : (
    <Badge variant="outline" className="text-muted-foreground">
      observe
    </Badge>
  );
}

function Section({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function QueryState({ loading, error, empty, children }: { loading: boolean; error: string | null; empty: boolean; children: ReactNode }) {
  if (loading) return <LoadingBlock rows={4} />;
  if (error) return <ErrorBlock message={error} />;
  if (empty) return <EmptyBlock title="No data for this study" />;
  return <>{children}</>;
}

function useStudyParams(studyId: string) {
  return useMemo(() => ({ study_id: sql.string(studyId) }), [studyId]);
}

function InsightsTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const overview = useAnalyticsQuery('study_overview', params);
  const summary = useAnalyticsQuery('study_ai_summary', params);
  const o = overview.data?.[0];
  const s = summary.data?.[0];
  const findings = parseJson<Finding[]>(s?.findings_json, []);
  const actions = parseJson<(string | { action?: string; title?: string })[]>(s?.recommended_actions_json, []);

  return (
    <div className="space-y-6">
      {overview.loading ? (
        <LoadingBlock rows={1} height="h-24" />
      ) : overview.error ? (
        <ErrorBlock message={overview.error} />
      ) : o ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile
            label="Enrollment"
            value={`${o.enrolled}`}
            unit={`/ ${o.planned_enrollment}`}
            context={`${o.pct_enrollment_target}% of target · ${o.active_sites} sites in ${o.countries} countries`}
          />
          <KpiTile
            label="Subject status"
            value={o.ongoing}
            unit="ongoing"
            context={`${o.completed} completed · ${o.discontinued} discontinued (${o.discontinuation_rate_pct}%)`}
          />
          <KpiTile
            label="SAE subject rate"
            value={`${o.sae_subject_rate_pct}%`}
            tone={Number(o.sae_subject_rate_pct) >= 20 ? 'watch' : 'default'}
            context={`${o.total_saes} SAEs · ${o.grade3plus_aes} grade ≥3 · ${o.fatal_aes} fatal`}
          />
          <KpiTile
            label="Clean subjects"
            value={o.subjects_clean}
            unit={`/ ${o.subjects_received}`}
            tone={Number(o.subjects_quarantined) > 0 ? 'watch' : 'good'}
            context={`${o.subjects_quarantined} quarantined for review · ${o.dq_issues} DQ issues`}
          />
        </div>
      ) : null}

      <Card className="overflow-hidden">
        <div className="brand-bar h-1" />
        <CardHeader>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-primary">
            <Sparkles className="h-3.5 w-3.5" /> AI study brief
          </div>
          {summary.loading ? (
            <LoadingBlock rows={1} height="h-8" />
          ) : (
            <CardTitle className="text-xl leading-snug">{s?.headline ?? 'No AI brief generated yet'}</CardTitle>
          )}
        </CardHeader>
        <CardContent className="space-y-6">
          {summary.error && <ErrorBlock message={summary.error} />}
          {s?.summary && <p className="text-sm leading-relaxed text-foreground">{s.summary}</p>}

          {findings.length > 0 && (
            <div className="grid gap-3 md:grid-cols-2">
              {findings.map((f) => (
                <div key={`${f.category}-${f.title}`} className="rounded-lg border p-4">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{f.category}</span>
                    <SeverityBadge severity={f.severity} />
                  </div>
                  <div className="font-medium">{f.title}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{f.detail}</p>
                </div>
              ))}
            </div>
          )}

          {actions.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Lightbulb className="h-4 w-4 text-primary" /> Recommended actions
              </div>
              <ul className="space-y-1.5">
                {actions.map((a, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                      {i + 1}
                    </span>
                    <span>{typeof a === 'string' ? a : a.action ?? a.title}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {s && (
            <p className="text-[11px] text-muted-foreground">
              Generated by {s.model} on {formatDateTime(s.generated_at)} from the clean Gold tables of submission{' '}
              {s.submission_id}
              {s.subjects_received != null
                ? ` (${s.subjects_clean} of ${s.subjects_received} subjects; quarantined records are excluded)`
                : ''}
              .
              {s.validation_status && s.validation_status !== 'valid'
                ? ' The model output failed validation, so it was not shown.'
                : ''}{' '}
              AI-generated content — verify against source data before making clinical decisions.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EnrollmentTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const enrollment = useAnalyticsQuery('enrollment_by_month', params);
  const disposition = useAnalyticsQuery('disposition', params);
  const cumulative = useMemo(
    () => pivot(enrollment.data ?? [], 'month', 'arm', 'cumulative_subjects', { fill: 'forward' }),
    [enrollment.data],
  );
  const monthly = useMemo(() => pivot(enrollment.data ?? [], 'month', 'arm', 'new_subjects'), [enrollment.data]);
  const dispo = useMemo(() => pivot(disposition.data ?? [], 'disposition_status', 'category', 'subjects'), [disposition.data]);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Cumulative enrollment by arm" description="Subjects randomized over time" className="lg:col-span-2">
        <QueryState loading={enrollment.loading} error={enrollment.error} empty={cumulative.data.length === 0}>
          <LineChart data={cumulative.data} xKey="month" yKey={cumulative.series} height={320} showLegend />
        </QueryState>
      </Section>
      <Section title="New subjects per month">
        <QueryState loading={enrollment.loading} error={enrollment.error} empty={monthly.data.length === 0}>
          <BarChart data={monthly.data} xKey="month" yKey={monthly.series} stacked height={280} showLegend />
        </QueryState>
      </Section>
      <Section title="Subject disposition">
        <QueryState loading={disposition.loading} error={disposition.error} empty={dispo.data.length === 0}>
          <BarChart data={dispo.data} xKey="disposition_status" yKey={dispo.series} stacked orientation="horizontal" height={280} showLegend />
        </QueryState>
      </Section>
    </div>
  );
}

function SafetyTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const byArm = useAnalyticsQuery('ae_by_arm', params);
  const bySoc = useAnalyticsQuery('ae_by_soc', params);
  const top = useAnalyticsQuery('top_aes', params);
  const soc = useMemo(() => pivot(bySoc.data ?? [], 'system_organ_class', 'arm', 'subjects'), [bySoc.data]);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Safety profile by arm" description="% of subjects in each arm" className="lg:col-span-2">
        <QueryState loading={byArm.loading} error={byArm.error} empty={(byArm.data ?? []).length === 0}>
          <div className="grid gap-6 lg:grid-cols-2">
            <BarChart data={byArm.data ?? []} xKey="arm" yKey={['pct_with_ae', 'pct_with_sae', 'pct_grade3plus']} height={280} showLegend />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Arm</TableHead>
                  <TableHead className="text-right">N</TableHead>
                  <TableHead className="text-right">Any AE</TableHead>
                  <TableHead className="text-right">SAE</TableHead>
                  <TableHead className="text-right">Grade ≥3</TableHead>
                  <TableHead className="text-right">D/C due to AE</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(byArm.data ?? []).map((r) => (
                  <TableRow key={r.arm}>
                    <TableCell className="font-medium">{r.arm}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.subjects_in_arm}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.pct_with_ae}%</TableCell>
                    <TableCell className="text-right tabular-nums">{r.pct_with_sae}%</TableCell>
                    <TableCell className="text-right tabular-nums">{r.pct_grade3plus}%</TableCell>
                    <TableCell className="text-right tabular-nums">{r.discontinued_due_to_ae}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </QueryState>
      </Section>
      <Section title="Subjects with AEs by system organ class">
        <QueryState loading={bySoc.loading} error={bySoc.error} empty={soc.data.length === 0}>
          <BarChart data={soc.data} xKey="system_organ_class" yKey={soc.series} orientation="horizontal" height={360} showLegend />
        </QueryState>
      </Section>
      <Section title="Most frequent adverse events">
        <QueryState loading={top.loading} error={top.error} empty={(top.data ?? []).length === 0}>
          <div className="max-h-[360px] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Preferred term</TableHead>
                  <TableHead className="text-right">Subjects</TableHead>
                  <TableHead className="text-right">Events</TableHead>
                  <TableHead className="text-right">Serious</TableHead>
                  <TableHead className="text-right">Max grade</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(top.data ?? []).map((r) => (
                  <TableRow key={r.preferred_term}>
                    <TableCell>
                      <div className="font-medium">{r.preferred_term}</div>
                      <div className="text-xs text-muted-foreground">{r.system_organ_class}</div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{r.subjects}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.events}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.serious_events}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.max_grade}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </QueryState>
      </Section>
    </div>
  );
}

function LabsTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const abnormal = useAnalyticsQuery('lab_abnormal_by_test', params);
  const tests = useMemo(() => [...new Set((abnormal.data ?? []).map((r) => r.lab_test))].sort(), [abnormal.data]);
  const [selectedTest, setSelectedTest] = useState<string | null>(null);
  const labTest = selectedTest ?? (tests.includes('ALT') ? 'ALT' : tests[0] ?? 'ALT');
  const trendParams = useMemo(() => ({ study_id: sql.string(studyId), lab_test: sql.string(labTest) }), [studyId, labTest]);
  const trend = useAnalyticsQuery('lab_trend', trendParams);

  const abn = useMemo(() => pivot(abnormal.data ?? [], 'lab_test', 'arm', 'pct_abnormal'), [abnormal.data]);
  const trendRows = useMemo(() => [...(trend.data ?? [])].sort((a, b) => a.visitnum - b.visitnum), [trend.data]);
  const mean = useMemo(() => pivot(trendRows, 'visit', 'arm', 'mean_value'), [trendRows]);
  const first = trendRows[0];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Abnormal results by test" description="% of results outside the reference range, by arm" className="lg:col-span-2">
        <QueryState loading={abnormal.loading} error={abnormal.error} empty={abn.data.length === 0}>
          <BarChart data={abn.data} xKey="lab_test" yKey={abn.series} height={300} showLegend />
        </QueryState>
      </Section>
      <Card className="lg:col-span-2">
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">Mean {labTest} by visit</CardTitle>
            <CardDescription>
              {first ? `Reference range ${first.ref_low}–${first.ref_high} ${first.unit ?? ''}` : 'Trend over scheduled visits'}
            </CardDescription>
          </div>
          <Select value={labTest} onValueChange={setSelectedTest}>
            <SelectTrigger className="w-40" aria-label="Lab test">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {tests.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          <QueryState loading={trend.loading} error={trend.error} empty={mean.data.length === 0}>
            <LineChart data={mean.data} xKey="visit" yKey={mean.series} height={300} showLegend />
          </QueryState>
        </CardContent>
      </Card>
    </div>
  );
}

function SitesTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const sites = useAnalyticsQuery('site_performance', params);
  const rows = sites.data ?? [];
  return (
    <div className="space-y-6">
      <Section title="Enrollment and discontinuation by site">
        <QueryState loading={sites.loading} error={sites.error} empty={rows.length === 0}>
          <BarChart data={rows} xKey="site_id" yKey={['enrolled', 'discontinued']} height={300} showLegend />
        </QueryState>
      </Section>
      <Section
        title="Site operations scorecard"
        description="Metrics cover clean subjects. Out-of-window visits, DQ issues and quarantined subjects highlight sites that may need monitoring attention"
      >
        <QueryState loading={sites.loading} error={sites.error} empty={rows.length === 0}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Site</TableHead>
                <TableHead>Country</TableHead>
                <TableHead className="text-right">Enrolled</TableHead>
                <TableHead className="text-right">D/C rate</TableHead>
                <TableHead className="text-right">SAEs</TableHead>
                <TableHead className="text-right">Visits</TableHead>
                <TableHead className="text-right">Out of window</TableHead>
                <TableHead className="text-right">DQ issues</TableHead>
                <TableHead className="text-right">Quarantined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.site_id}>
                  <TableCell className="font-medium">{r.site_id}</TableCell>
                  <TableCell>{r.country}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.enrolled}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.discontinuation_rate_pct}%</TableCell>
                  <TableCell className="text-right tabular-nums">{r.saes}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.visits_completed}</TableCell>
                  <TableCell className={`text-right tabular-nums ${Number(r.pct_visits_out_of_window) >= 10 ? 'font-semibold text-warning' : ''}`}>
                    {r.pct_visits_out_of_window}%
                  </TableCell>
                  <TableCell
                    className={`text-right tabular-nums ${Number(r.dq_issues) >= 5 ? 'font-semibold text-destructive' : ''}`}
                  >
                    {r.dq_issues}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {r.subjects_quarantined} / {r.subjects_received}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </QueryState>
      </Section>
    </div>
  );
}

function DataQualityTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const summary = useAnalyticsQuery('dq_summary', params);
  const issues = useAnalyticsQuery('dq_issues', params);
  const [rule, setRule] = useState<string>('all');
  const filtered = (issues.data ?? []).filter((r) => rule === 'all' || ruleKey(r.domain, r.rule_id) === rule);

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Section
        title="Checks summary"
        description="Automated rules run on every submission. Quarantine rules move the record and its subject to quarantine; observe rules keep real data and report it."
        className="lg:col-span-2"
      >
        <QueryState loading={summary.loading} error={summary.error} empty={(summary.data ?? []).length === 0}>
          <div className="space-y-2">
            {(summary.data ?? []).map((r) => {
              const key = ruleKey(r.domain, r.rule_id);
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setRule(rule === key ? 'all' : key)}
                  className={`w-full rounded-md border p-3 text-left transition-colors ${rule === key ? 'border-primary bg-accent' : 'hover:bg-muted'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{key}</span>
                    <span className="flex gap-1">
                      <ActionBadge action={r.action} />
                      <SeverityBadge severity={r.severity} />
                    </span>
                  </div>
                  <div className="mt-1 text-sm">{r.rule_description}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {r.issue_count} issues · {r.subjects_affected} subjects · {r.sites_affected} sites
                  </div>
                </button>
              );
            })}
          </div>
        </QueryState>
      </Section>
      <Card className="lg:col-span-3">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Issue listing</CardTitle>
            <CardDescription>
              {rule === 'all' ? 'All rules' : `Filtered to ${rule}`} · {filtered.length} records
              {(issues.data ?? []).length >= 1000 ? ' (first 1,000)' : ''}
            </CardDescription>
          </div>
          {rule !== 'all' && (
            <Button variant="ghost" size="sm" onClick={() => setRule('all')}>
              Clear filter
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <QueryState loading={issues.loading} error={issues.error} empty={filtered.length === 0}>
            <div className="max-h-[560px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rule</TableHead>
                    <TableHead>Subject</TableHead>
                    <TableHead>Site</TableHead>
                    <TableHead>Detail</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((r, i) => (
                    <TableRow key={`${issueKey(r.domain, r.rule_id, r.usubjid)}-${i}`}>
                      <TableCell className="font-mono text-xs">{ruleKey(r.domain, r.rule_id)}</TableCell>
                      <TableCell className="font-mono text-xs">{r.usubjid}</TableCell>
                      <TableCell className="text-xs">{r.site_id}</TableCell>
                      <TableCell className="text-xs">{r.detail}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </QueryState>
        </CardContent>
      </Card>
    </div>
  );
}

const REVIEW_LABEL: Record<ReviewStatus, string> = { open: 'Open', acknowledged: 'Acknowledged', accepted: 'Accepted' };

function QuarantineTab({ studyId }: { studyId: string }) {
  const params = useStudyParams(studyId);
  const coverage = useAnalyticsQuery('dq_coverage', params);
  const recon = useAnalyticsQuery('dq_reconciliation', params);
  const subjects = useAnalyticsQuery('quarantine_subjects', params);
  const issues = useAnalyticsQuery('dq_issues', params);
  const { reviews, error: reviewError, save } = useDqReviews(studyId);
  const [subject, setSubject] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const c = coverage.data?.[0];
  const quarantined = (issues.data ?? []).filter(
    (r) => r.action === 'quarantine' && (!subject || r.usubjid === subject)
  );
  const reviewed = [...reviews.values()].filter((r) => r.status !== 'open').length;

  const setStatus = async (r: { domain: string; rule_id: string; usubjid: string }, status: ReviewStatus) => {
    setSaveError(null);
    try {
      await save(r, status);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-6">
      {coverage.loading ? (
        <LoadingBlock rows={1} height="h-24" />
      ) : coverage.error ? (
        <ErrorBlock message={coverage.error} />
      ) : c ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile
            label="Subjects received"
            value={c.subjects_received}
            context={`${Number(c.records_received).toLocaleString()} records in the latest submission`}
          />
          <KpiTile
            label="Clean subjects"
            value={c.subjects_clean}
            tone="good"
            context={`${c.pct_subjects_clean ?? 0}% · used by KPIs, AI insights and Genie`}
          />
          <KpiTile
            label="Quarantined subjects"
            value={c.subjects_quarantined}
            tone={Number(c.subjects_quarantined) > 0 ? 'watch' : 'good'}
            context={`${reviewed} issue reviews recorded`}
          />
          <KpiTile
            label="Records quarantined"
            value={Number(c.records_quarantined).toLocaleString()}
            context="Kept in full, never deleted"
          />
        </div>
      ) : null}

      <Section
        title="Row reconciliation"
        description="Every staged row lands in exactly one place: the clean tables or quarantine. Nothing is dropped."
      >
        <QueryState loading={recon.loading} error={recon.error} empty={(recon.data ?? []).length === 0}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Domain</TableHead>
                <TableHead className="text-right">Staged</TableHead>
                <TableHead className="text-right">Bronze</TableHead>
                <TableHead className="text-right">Clean</TableHead>
                <TableHead className="text-right">Quarantine</TableHead>
                <TableHead className="text-right">Balanced</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(recon.data ?? []).map((r) => (
                <TableRow key={r.domain}>
                  <TableCell className="font-mono text-xs uppercase">{r.domain}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.staged_rows}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.bronze_rows}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.clean_rows}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.quarantine_rows}</TableCell>
                  <TableCell
                    className={`text-right text-xs font-semibold ${String(r.balanced) === 'true' ? 'text-success' : 'text-destructive'}`}
                  >
                    {String(r.balanced) === 'true' ? 'Yes' : 'No'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </QueryState>
      </Section>

      <div className="grid gap-6 lg:grid-cols-5">
        <Section
          title="Quarantined subjects"
          description="A subject is quarantined when any of its records fails a quarantine rule. All of its records wait here until a corrected package is resubmitted."
          className="lg:col-span-2"
        >
          <QueryState loading={subjects.loading} error={subjects.error} empty={(subjects.data ?? []).length === 0}>
            <div className="max-h-[560px] space-y-2 overflow-auto">
              {(subjects.data ?? []).map((r) => (
                <button
                  key={r.usubjid}
                  type="button"
                  onClick={() => setSubject(subject === r.usubjid ? null : r.usubjid)}
                  className={`w-full rounded-md border p-3 text-left transition-colors ${subject === r.usubjid ? 'border-primary bg-accent' : 'hover:bg-muted'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{r.usubjid}</span>
                    <span className="text-xs text-muted-foreground">
                      Site {r.site_id} · {r.country}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[11px] text-muted-foreground">{r.failed_rules}</div>
                  <div className="mt-1 text-xs">{r.records_quarantined} records failed a rule</div>
                </button>
              ))}
            </div>
          </QueryState>
        </Section>
        <Card className="lg:col-span-3">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Failed records and review</CardTitle>
              <CardDescription>
                {subject ? `Filtered to ${subject}` : 'All quarantined subjects'} · {quarantined.length} failures.
                Record a review decision per failure; data is corrected by resubmitting the package.
              </CardDescription>
            </div>
            {subject && (
              <Button variant="ghost" size="sm" onClick={() => setSubject(null)}>
                Clear filter
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {(reviewError || saveError) && (
              <ErrorBlock title="Reviews unavailable" message={saveError ?? reviewError ?? ''} />
            )}
            <QueryState loading={issues.loading} error={issues.error} empty={quarantined.length === 0}>
              <div className="max-h-[560px] overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rule</TableHead>
                      <TableHead>Subject</TableHead>
                      <TableHead>Detail</TableHead>
                      <TableHead>Review</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {quarantined.map((r, i) => {
                      const review = reviews.get(issueKey(r.domain, r.rule_id, r.usubjid));
                      return (
                        <TableRow key={`${issueKey(r.domain, r.rule_id, r.usubjid)}-${i}`}>
                          <TableCell className="font-mono text-xs" title={r.rule_description}>
                            {ruleKey(r.domain, r.rule_id)}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{r.usubjid}</TableCell>
                          <TableCell className="text-xs">{r.detail}</TableCell>
                          <TableCell>
                            <Select
                              value={review?.status ?? 'open'}
                              onValueChange={(v) => void setStatus(r, v as ReviewStatus)}
                            >
                              <SelectTrigger
                                className="h-7 w-36 text-xs"
                                aria-label={`Review ${r.rule_id} for ${r.usubjid}`}
                              >
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {(Object.keys(REVIEW_LABEL) as ReviewStatus[]).map((s) => (
                                  <SelectItem key={s} value={s}>
                                    {REVIEW_LABEL[s]}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {review && review.status !== 'open' && (
                              <div className="mt-1 text-[10px] text-muted-foreground">
                                {review.reviewed_by} · {formatDateTime(review.reviewed_at)}
                              </div>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </QueryState>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function StudyPage() {
  const { studyId = '' } = useParams();
  const { email } = usePersona();
  const params = useStudyParams(studyId);
  const overview = useAnalyticsQuery('study_overview', params);
  const o = overview.data?.[0];

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <div>
        <Link to="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3 w-3" /> Study portfolio
        </Link>
        <div className="mt-2 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-3xl">
                <BrandHeading text={studyId} />
              </h2>
              {o?.phase && <Badge variant="outline">{o.phase}</Badge>}
              {o?.therapeutic_area && <Badge variant="secondary">{o.therapeutic_area}</Badge>}
              {o?.nct_id && <Badge variant="outline">{o.nct_id}</Badge>}
            </div>
            <p className="mt-1 max-w-4xl text-sm text-muted-foreground">
              {overview.loading ? 'Loading study…' : o?.title ?? 'Study not found in the hub'}
            </p>
          </div>
          {o && (
            <div className="text-right text-xs text-muted-foreground">
              <div>{o.sponsor}</div>
              <div>
                Arms: {o.arms_label} · Data cut-off {o.data_cutoff_date}
              </div>
              {coverageLabel(o.subjects_clean, o.subjects_received, o.subjects_quarantined) && (
                <div className="mt-1 inline-flex items-center gap-1 rounded-md bg-accent px-2 py-0.5 font-medium text-accent-foreground">
                  <ShieldAlert className="h-3 w-3" />
                  Metrics use clean subjects only:{' '}
                  {coverageLabel(o.subjects_clean, o.subjects_received, o.subjects_quarantined)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {!overview.loading && !overview.error && !o ? (
        <EmptyBlock icon={<AlertTriangle />} title="Study not published" description="This study has no processed data yet. Check the approval queue for its submission status." />
      ) : (
        <Tabs defaultValue="insights" className="space-y-4">
          <TabsList className="flex-wrap">
            <TabsTrigger value="insights">Insights</TabsTrigger>
            <TabsTrigger value="enrollment">Enrollment</TabsTrigger>
            <TabsTrigger value="safety">Safety</TabsTrigger>
            <TabsTrigger value="labs">Labs</TabsTrigger>
            <TabsTrigger value="sites">Sites &amp; Ops</TabsTrigger>
            <TabsTrigger value="dq">Data Quality</TabsTrigger>
            <TabsTrigger value="quarantine">
              <ShieldAlert className="mr-1 h-3.5 w-3.5" /> Quarantine
            </TabsTrigger>
            <TabsTrigger value="genie">
              <Sparkles className="mr-1 h-3.5 w-3.5" /> Ask Genie
            </TabsTrigger>
          </TabsList>
          <TabsContent value="insights">
            <InsightsTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="enrollment">
            <EnrollmentTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="safety">
            <SafetyTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="labs">
            <LabsTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="sites">
            <SitesTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="dq">
            <DataQualityTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="quarantine">
            <QuarantineTab studyId={studyId} />
          </TabsContent>
          <TabsContent value="genie">
            <StudyGenie studyId={studyId} email={email} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
