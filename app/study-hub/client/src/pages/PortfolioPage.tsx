import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Progress,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { useEffect, useState } from 'react';
import { ArrowRight, FlaskConical, Plus, Sparkles } from 'lucide-react';
import { Link } from 'react-router';
import { BrandHeading, EmptyBlock, ErrorBlock, KpiTile, LoadingBlock, PipelineProgress, StatusBadge } from '../components/common';
import { useSubmissions } from '../lib/submissions';

export function PortfolioPage() {
  const { data: sqlData, loading: sqlLoading, error } = useAnalyticsQuery('studies', null);
  const [lakebaseRows, setLakebaseRows] = useState<NonNullable<typeof sqlData> | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch('/api/portfolio')
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (!cancelled && body?.rows?.length) setLakebaseRows(body.rows);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const data = lakebaseRows ?? sqlData;
  const loading = sqlLoading && !lakebaseRows;
  const { submissions } = useSubmissions();
  const inFlight = submissions.filter((s) => s.status === 'PENDING_APPROVAL' || s.status === 'PROCESSING');

  const studies = data ?? [];
  const totalEnrolled = studies.reduce((a, s) => a + Number(s.enrolled ?? 0), 0);
  const totalPlanned = studies.reduce((a, s) => a + Number(s.planned_enrollment ?? 0), 0);
  const totalSites = studies.reduce((a, s) => a + Number(s.active_sites ?? 0), 0);
  const totalDq = studies.reduce((a, s) => a + Number(s.dq_high_issues ?? 0), 0);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <section className="grid items-center gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <div className="text-xs font-semibold uppercase tracking-widest text-primary">Clinical Data Hub</div>
          <h2 className="mt-2 text-4xl leading-tight text-foreground md:text-5xl">
            <BrandHeading text="Study Data Ready" everyWord />
            <br />
            <span className="brand-heading">
              <em className="initial not-italic">D</em>
              <em>ays Sooner</em>
            </span>
          </h2>
        </div>
        <div className="brand-hero p-6 md:p-8 lg:col-span-3">
          <p className="text-sm leading-relaxed md:text-base">
            Every study package is harmonized to SDTM-like domains, checked by automated data quality rules, and summarized by AI
            — from zip upload to study insights in minutes, with an approval step before anything is processed.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button asChild variant="secondary" className="bg-white text-primary hover:bg-white/90">
              <Link to="/onboard">
                <Plus className="mr-1 h-4 w-4" /> Onboard a study
              </Link>
            </Button>
            <span className="brand-pill inline-flex items-center rounded-md px-3 text-xs font-semibold">
              Powered by Databricks
            </span>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <LoadingBlock key={i} rows={1} height="h-24" />
          ))}
        </div>
      ) : error ? (
        <ErrorBlock message={error} />
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          <KpiTile
            label="Active studies"
            value={studies.length}
            context={lakebaseRows ? 'Served from Lakebase synced table' : 'Read from the SQL warehouse'}
          />
          <KpiTile
            label="Subjects enrolled"
            value={totalEnrolled.toLocaleString()}
            context={totalPlanned ? `${Math.round((100 * totalEnrolled) / totalPlanned)}% of ${totalPlanned.toLocaleString()} planned` : undefined}
          />
          <KpiTile label="Active sites" value={totalSites} context="Across all studies" />
          <KpiTile label="High-severity DQ issues" value={totalDq} tone={totalDq > 0 ? 'watch' : 'good'} context="Open data quality findings" />
        </div>
      )}

      {inFlight.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">In-flight submissions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {inFlight.map((s) => (
              <div key={s.submission_id} className="flex flex-col gap-2 rounded-md border p-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <span className="font-medium">{s.study_id}</span>
                  <StatusBadge status={s.status} />
                  <span className="hidden text-xs text-muted-foreground md:inline">{s.study_title}</span>
                </div>
                {s.status === 'PROCESSING' ? (
                  <PipelineProgress tasks={s.run_tasks} status={s.status} />
                ) : (
                  <span className="text-xs text-muted-foreground">Awaiting Admin approval</span>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <LoadingBlock key={i} rows={1} height="h-64" />
          ))}
        </div>
      ) : !error && studies.length === 0 ? (
        <EmptyBlock
          icon={<FlaskConical />}
          title="No studies published yet"
          description="Onboard a study package to see it here once it has been approved and processed."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {studies.map((s) => (
            <Card key={s.study_id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="secondary">{s.therapeutic_area}</Badge>
                  <Badge variant="outline">{s.phase}</Badge>
                </div>
                <CardTitle className="mt-2 text-lg">{s.study_id}</CardTitle>
                <CardDescription className="line-clamp-2">{s.title}</CardDescription>
              </CardHeader>
              <CardContent className="flex-1 space-y-4">
                <div>
                  <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                    <span>Enrollment</span>
                    <span className="tabular-nums">
                      {s.enrolled} / {s.planned_enrollment} ({s.pct_enrollment_target}%)
                    </span>
                  </div>
                  <Progress value={Math.min(Number(s.pct_enrollment_target ?? 0), 100)} />
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-lg font-semibold tabular-nums">{s.sae_subject_rate_pct}%</div>
                    <div className="text-[11px] text-muted-foreground">SAE subjects</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold tabular-nums">{s.discontinuation_rate_pct}%</div>
                    <div className="text-[11px] text-muted-foreground">Discontinued</div>
                  </div>
                  <div>
                    <div className={`text-lg font-semibold tabular-nums ${Number(s.dq_high_issues) > 0 ? 'text-warning' : ''}`}>{s.dq_issues}</div>
                    <div className="text-[11px] text-muted-foreground">DQ issues</div>
                  </div>
                </div>
                {s.headline && (
                  <div className="flex gap-2 rounded-md bg-accent p-3 text-xs text-accent-foreground">
                    <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span className="line-clamp-3">{s.headline}</span>
                  </div>
                )}
              </CardContent>
              <CardFooter className="justify-between text-xs text-muted-foreground">
                <span>Data cut-off {s.data_cutoff_date ?? '\u2014'}</span>
                <Button asChild variant="ghost" size="sm">
                  <Link to={`/studies/${s.study_id}`}>
                    Open <ArrowRight className="ml-1 h-3.5 w-3.5" />
                  </Link>
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
