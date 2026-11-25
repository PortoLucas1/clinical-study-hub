import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  GenieChatInput,
  GenieChatMessageList,
  useGenieChat,
  type GenieMessageItem,
} from '@databricks/appkit-ui/react';
import { Sparkles } from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';
import { ErrorBlock } from './common';

const SUGGESTED = [
  'What is the SAE rate by treatment arm?',
  'Which adverse events are more frequent in the investigational arm?',
  'Show the ALT trend by visit for each arm',
  'Which sites have the highest discontinuation rate?',
  'List subjects with grade 3 or higher adverse events',
  'Summarize open data quality issues by rule',
];

const contextPrefix = (studyId: string) => `[Study: ${studyId}] `;

export function StudyGenie({ studyId, email }: { studyId: string; email: string | null }) {
  const { messages, status, error, sendMessage, reset, hasPreviousPage, fetchPreviousPage } = useGenieChat({
    alias: 'default',
    persistInUrl: false,
  });
  const lastStudy = useRef(studyId);

  useEffect(() => {
    if (lastStudy.current !== studyId) {
      lastStudy.current = studyId;
      reset();
    }
  }, [studyId, reset]);

  const prefix = contextPrefix(studyId);
  const displayMessages = useMemo<GenieMessageItem[]>(
    () =>
      messages.map((m) =>
        m.role === 'user' && m.content.startsWith('[Study: ') ? { ...m, content: m.content.replace(/^\[Study: [^\]]+\]\s*/, '') } : m,
      ),
    [messages],
  );

  const lastSql = useMemo(() => {
    for (const m of [...messages].reverse()) for (const a of m.attachments ?? []) if (a.query?.query) return a.query;
    return null;
  }, [messages]);

  const ask = (q: string) => sendMessage(`${prefix}${q}`);
  const busy = status === 'streaming' || status === 'loading-history';

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="flex h-[640px] flex-col overflow-hidden lg:col-span-2 py-0 gap-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">Ask about {studyId}</span>
            <Badge variant="secondary">Genie</Badge>
          </div>
          {messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={reset} className="text-xs text-muted-foreground">
              New conversation
            </Button>
          )}
        </div>
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
            <div>
              <div className="text-base font-semibold">What would you like to know about {studyId}?</div>
              <p className="mt-1 text-sm text-muted-foreground">
                Questions are answered from the curated gold tables for this study.
              </p>
            </div>
            <div className="flex max-w-xl flex-wrap justify-center gap-2">
              {SUGGESTED.map((q) => (
                <Button key={q} variant="outline" size="sm" className="h-auto whitespace-normal py-1.5 text-left text-xs" onClick={() => ask(q)}>
                  {q}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <GenieChatMessageList
            messages={displayMessages}
            status={status}
            hasPreviousPage={hasPreviousPage}
            onFetchPreviousPage={fetchPreviousPage}
          />
        )}
        {status === 'streaming' && <p className="px-4 pb-1 text-xs text-muted-foreground">Analyzing study data…</p>}
        {error && (
          <div className="px-4 pb-2">
            <ErrorBlock title="Genie could not answer" message={error} />
          </div>
        )}
        <GenieChatInput onSend={ask} disabled={busy} placeholder={`Ask a question about ${studyId}\u2026`} />
        <p className="border-t px-4 py-2 text-[11px] text-muted-foreground">
          AI-generated from study data via Genie — review the generated SQL before acting on results.
        </p>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Generated SQL</CardTitle>
            <CardDescription>{lastSql?.title ?? 'How the latest answer was computed'}</CardDescription>
          </CardHeader>
          <CardContent>
            {lastSql?.query ? (
              <pre className="max-h-72 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-relaxed">{lastSql.query}</pre>
            ) : (
              <p className="text-xs text-muted-foreground">Ask a question to see the SQL Genie generates.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Governance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-muted-foreground">
            <div>
              Signed in as <Badge variant="outline">{email ?? 'local developer'}</Badge>
            </div>
            <p>
              Gold-table charts run as the Study Hub app service principal. Genie questions run as you, scoped to{' '}
              <strong>{studyId}</strong>, against the curated Study Insights space.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
