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
  Input,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from '@databricks/appkit-ui/react';
import JSZip from 'jszip';
import { CheckCircle2, FileArchive, Loader2, UploadCloud, XCircle } from 'lucide-react';
import { useCallback, useRef, useState } from 'react';
import { Link } from 'react-router';
import { EmptyBlock, ErrorBlock, LoadingBlock, PageHeader, PipelineProgress, StatusBadge } from '../components/common';
import { usePersona } from '../lib/persona';
import {
  DOMAIN_LABEL,
  domainForPath,
  formatBytes,
  formatDateTime,
  readError,
  useSubmissions,
  type ManifestEntry,
} from '../lib/submissions';

interface StudyMetadata {
  study_id?: string;
  title?: string;
  phase?: string;
  indication?: string;
  therapeutic_area?: string;
  sponsor?: string;
  planned_enrollment?: number;
  arms?: string[];
  sites?: unknown[];
  nct_id?: string;
}

interface ParsedPackage {
  file: File;
  manifest: ManifestEntry[];
  metadata: StudyMetadata | null;
  checks: { label: string; ok: boolean }[];
}

const REQUIRED_DOMAINS = ['dm', 'ae', 'lb'];

async function parsePackage(file: File): Promise<ParsedPackage> {
  const zip = await JSZip.loadAsync(file);
  const manifest: ManifestEntry[] = [];
  let metadata: StudyMetadata | null = null;
  for (const entry of Object.values(zip.files)) {
    if (entry.dir || entry.name.split('/').pop()?.startsWith('.')) continue;
    const content = await entry.async('uint8array');
    manifest.push({ path: entry.name, size: content.byteLength, domain: domainForPath(entry.name) });
    if (entry.name.endsWith('study_metadata.json')) {
      try {
        metadata = JSON.parse(new TextDecoder().decode(content)) as StudyMetadata;
      } catch {
        metadata = null;
      }
    }
  }
  const domains = new Set(manifest.map((m) => m.domain));
  const checks = [
    { label: 'Protocol metadata (study_metadata.json) present', ok: metadata !== null },
    ...REQUIRED_DOMAINS.map((d) => ({ label: `${DOMAIN_LABEL[d]} dataset present`, ok: domains.has(d) })),
    { label: 'All files map to a known SDTM domain', ok: manifest.every((m) => m.domain !== null) },
  ];
  return { file, manifest, metadata, checks };
}

export function OnboardPage() {
  const { apiFetch } = usePersona();
  const { submissions, loading, error, refresh } = useSubmissions();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [pkg, setPkg] = useState<ParsedPackage | null>(null);
  const [studyId, setStudyId] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const handleFile = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setMessage(null);
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setMessage({ kind: 'error', text: 'Please provide the study package as a .zip file.' });
      return;
    }
    setParsing(true);
    try {
      const parsed = await parsePackage(file);
      setPkg(parsed);
      setStudyId(parsed.metadata?.study_id ?? '');
    } catch (e) {
      setMessage({ kind: 'error', text: `Could not read zip: ${e instanceof Error ? e.message : String(e)}` });
      setPkg(null);
    } finally {
      setParsing(false);
    }
  }, []);

  const submit = async () => {
    if (!pkg) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const md = pkg.metadata ?? {};
      const createRes = await apiFetch('/api/submissions', {
        method: 'POST',
        body: JSON.stringify({
          study_id: studyId.trim(),
          file_name: pkg.file.name,
          file_size: pkg.file.size,
          study_title: md.title,
          phase: md.phase,
          indication: md.indication,
          therapeutic_area: md.therapeutic_area,
          sponsor: md.sponsor,
          notes: notes.trim() || undefined,
          manifest: pkg.manifest,
        }),
      });
      if (!createRes.ok) throw new Error(await readError(createRes));
      const created = (await createRes.json()) as { submission_id: string; upload_path: string };

      const uploadRes = await fetch(`/api/files/files/upload?path=${encodeURIComponent(created.upload_path)}`, {
        method: 'POST',
        body: pkg.file,
      });
      if (!uploadRes.ok) throw new Error(`Upload failed: ${await readError(uploadRes)}`);

      const submitRes = await apiFetch(`/api/submissions/${created.submission_id}/submit`, { method: 'POST' });
      if (!submitRes.ok) throw new Error(await readError(submitRes));

      setMessage({ kind: 'ok', text: `${created.submission_id} submitted. An Admin must approve it before processing starts.` });
      setPkg(null);
      setNotes('');
      await refresh();
    } catch (e) {
      setMessage({ kind: 'error', text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const allChecksOk = pkg?.checks.every((c) => c.ok) ?? false;

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Study Startup"
        title="Onboard a new study"
        description="Upload the sponsor's study package (EDC exports, vendor lab files and protocol metadata as a single .zip). The package is validated here, then routed to an Admin for approval before it is processed into the clinical data hub."
      />

      {message && (
        <Alert variant={message.kind === 'error' ? 'destructive' : 'default'}>
          {message.kind === 'error' ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          <AlertTitle>{message.kind === 'error' ? 'Something went wrong' : 'Submitted for approval'}</AlertTitle>
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>1. Study package</CardTitle>
            <CardDescription>Drag a .zip here or browse. Contents are inspected in your browser before upload.</CardDescription>
          </CardHeader>
          <CardContent>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                void handleFile(e.dataTransfer.files?.[0]);
              }}
              className={`flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
                dragOver ? 'border-primary bg-accent' : 'border-border hover:bg-muted'
              }`}
            >
              {parsing ? <Loader2 className="h-8 w-8 animate-spin text-primary" /> : <UploadCloud className="h-8 w-8 text-primary" />}
              <span className="text-sm font-medium">{pkg ? pkg.file.name : 'Drop study package (.zip)'}</span>
              <span className="text-xs text-muted-foreground">
                {pkg ? `${formatBytes(pkg.file.size)} · ${pkg.manifest.length} files` : 'EDC CSVs, vendor Excel, study_metadata.json'}
              </span>
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(e) => {
                void handleFile(e.target.files?.[0]);
                e.target.value = '';
              }}
            />

            {pkg && (
              <div className="mt-4 space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Package checks</div>
                {pkg.checks.map((c) => (
                  <div key={c.label} className="flex items-center gap-2 text-sm">
                    {c.ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-destructive" />}
                    <span className={c.ok ? '' : 'text-destructive'}>{c.label}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>2. Review and submit</CardTitle>
            <CardDescription>Protocol details are read from study_metadata.json.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!pkg ? (
              <EmptyBlock title="No package selected" description="Select a study package to preview its protocol details and file manifest." icon={<FileArchive />} />
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="study-id">Study ID</Label>
                    <Input id="study-id" value={studyId} onChange={(e) => setStudyId(e.target.value)} placeholder="e.g. ONC-101" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Protocol</Label>
                    <div className="text-sm">
                      {pkg.metadata?.phase ?? '\u2014'} · {pkg.metadata?.therapeutic_area ?? '\u2014'}
                      {pkg.metadata?.nct_id && <Badge variant="outline" className="ml-2">{pkg.metadata.nct_id}</Badge>}
                    </div>
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label>Title</Label>
                    <div className="text-sm text-muted-foreground">{pkg.metadata?.title ?? 'Not provided'}</div>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Sponsor</Label>
                    <div className="text-sm text-muted-foreground">{pkg.metadata?.sponsor ?? '\u2014'}</div>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Planned enrollment / sites</Label>
                    <div className="text-sm text-muted-foreground">
                      {pkg.metadata?.planned_enrollment ?? '\u2014'} subjects · {pkg.metadata?.sites?.length ?? '\u2014'} sites
                    </div>
                  </div>
                </div>

                <div className="max-h-56 overflow-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>File</TableHead>
                        <TableHead>Domain</TableHead>
                        <TableHead className="text-right">Size</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {pkg.manifest.map((m) => (
                        <TableRow key={m.path}>
                          <TableCell className="font-mono text-xs">{m.path}</TableCell>
                          <TableCell>
                            {m.domain ? <Badge variant="secondary">{DOMAIN_LABEL[m.domain] ?? m.domain}</Badge> : <Badge variant="destructive">Unmapped</Badge>}
                          </TableCell>
                          <TableCell className="text-right text-xs tabular-nums">{formatBytes(m.size)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="notes">Notes for the approver (optional)</Label>
                  <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Data cut-off 02-Nov, includes new BMI field in DM" />
                </div>

                <div className="flex items-center justify-end gap-2">
                  <Button variant="ghost" onClick={() => setPkg(null)} disabled={submitting}>
                    Clear
                  </Button>
                  <Button onClick={() => void submit()} disabled={submitting || !allChecksOk || !studyId.trim()}>
                    {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Submit for approval
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent submissions</CardTitle>
          <CardDescription>Status refreshes automatically every few seconds.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingBlock />
          ) : error ? (
            <ErrorBlock message={error} />
          ) : submissions.length === 0 ? (
            <EmptyBlock title="No submissions yet" description="Uploaded study packages will appear here." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Submission</TableHead>
                  <TableHead>Study</TableHead>
                  <TableHead>Submitted</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Progress</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {submissions.slice(0, 10).map((s) => (
                  <TableRow key={s.submission_id}>
                    <TableCell className="font-mono text-xs">{s.submission_id}</TableCell>
                    <TableCell>
                      {s.status === 'PUBLISHED' ? (
                        <Link className="font-medium text-primary underline-offset-4 hover:underline" to={`/studies/${s.study_id}`}>
                          {s.study_id}
                        </Link>
                      ) : (
                        <span className="font-medium">{s.study_id}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(s.submitted_at)}
                      <div>{s.submitted_by}</div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={s.status} />
                    </TableCell>
                    <TableCell>
                      {s.status === 'PROCESSING' || s.status === 'PUBLISHED' || s.status === 'FAILED' ? (
                        <PipelineProgress tasks={s.run_tasks} status={s.status} />
                      ) : s.status === 'REJECTED' ? (
                        <span className="text-xs text-muted-foreground">{s.review_comment ?? 'Rejected by approver'}</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Awaiting Admin approval</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
