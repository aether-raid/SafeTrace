import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileJson,
  FileText,
  ListChecks,
  ShieldCheck,
  TrendingUp,
  Video,
} from 'lucide-react';
import type { ReactNode } from 'react';
import type { AnalysisResult, Severity } from '../types/analysis';
import type { CachedResultEntry } from '../services/resultCache';

type SafetyInsightsDashboardProps = {
  entries: CachedResultEntry[];
  currentResult: AnalysisResult | null;
  backendConnected: boolean;
  onOpenResult: (entry: CachedResultEntry) => void;
  onBackToAnalysis: () => void;
};

type DashboardRow = {
  id: string;
  entry: CachedResultEntry;
  mediaName: string;
  query: string;
  source: string;
  status: string;
  updatedAt: string;
  analyzed: boolean;
  violationCount: number;
  topViolation: string;
  topSeverity?: Severity;
  frameCount: number;
};

export type SafetyInsightsReportRow = {
  video: string;
  jobId: string;
  status: string;
  violationType: string;
  severity: string;
  frameNumber: string;
  timestamp: string;
  confidence: string;
  evidenceCount: number;
  topFinding: string;
  updatedAt: string;
  completedAt: string;
};

const SEVERITIES: Severity[] = ['High', 'Medium', 'Low'];

const REPORT_COLUMNS: Array<[keyof SafetyInsightsReportRow, string]> = [
  ['video', 'Video'],
  ['jobId', 'Job/result ID'],
  ['status', 'Status'],
  ['violationType', 'Violation type'],
  ['severity', 'Severity'],
  ['frameNumber', 'Frame'],
  ['timestamp', 'Timestamp'],
  ['confidence', 'Confidence'],
  ['evidenceCount', 'Evidence count'],
  ['topFinding', 'Top finding'],
  ['updatedAt', 'Updated'],
  ['completedAt', 'Completed'],
];

function normalizeSeverity(value?: string): Severity | undefined {
  const normalized = (value || '').toLowerCase();
  if (normalized === 'high') return 'High';
  if (normalized === 'medium') return 'Medium';
  if (normalized === 'low') return 'Low';
  return undefined;
}

function getViolationCounts(result?: AnalysisResult) {
  const byType = new Map<string, number>();
  const bySeverity: Record<Severity, number> = { High: 0, Medium: 0, Low: 0 };
  if (!result) return { total: 0, byType, bySeverity, topViolation: 'None', topSeverity: undefined };

  result.frames.forEach((frame) => {
    frame.violations.forEach((violation) => {
      byType.set(violation.name, (byType.get(violation.name) || 0) + 1);
      const severity = normalizeSeverity(violation.severity);
      if (severity) bySeverity[severity] += 1;
    });
  });

  let topViolation = 'None';
  let topCount = 0;
  byType.forEach((count, name) => {
    if (count > topCount) {
      topViolation = name;
      topCount = count;
    }
  });
  const topSeverity = SEVERITIES.find((severity) => bySeverity[severity] > 0);
  const total = Array.from(byType.values()).reduce((sum, count) => sum + count, 0);
  return { total, byType, bySeverity, topViolation, topSeverity };
}

function buildCurrentEntry(result: AnalysisResult): CachedResultEntry {
  const now = new Date().toISOString();
  const resultKey = result.jobId ?? result.id;
  return {
    cacheKey: `current:${resultKey}`,
    cacheVersion: 1,
    mediaId: result.media.id,
    mediaName: result.media.filename,
    query: result.query,
    source: 'backend',
    status: result.status ?? 'completed',
    savedAt: now,
    updatedAt: now,
    jobId: result.jobId,
    result,
  };
}

function buildRows(entries: CachedResultEntry[], currentResult: AnalysisResult | null): DashboardRow[] {
  const byKey = new Map<string, CachedResultEntry>();
  const rowKey = (entry: CachedResultEntry) => {
    const jobKey = entry.result?.jobId ?? entry.selectedJobId ?? entry.jobId;
    return jobKey ? `job:${jobKey}` : `media:${entry.mediaId}`;
  };
  entries.forEach((entry) => {
    const key = rowKey(entry);
    const existing = byKey.get(key);
    if (!existing || (!existing.result && entry.result)) {
      byKey.set(key, entry);
      return;
    }
    const existingUpdated = Date.parse(existing.updatedAt || existing.savedAt);
    const nextUpdated = Date.parse(entry.updatedAt || entry.savedAt);
    if (Number.isFinite(nextUpdated) && (!Number.isFinite(existingUpdated) || nextUpdated > existingUpdated)) {
      byKey.set(key, entry);
    }
  });
  if (currentResult) {
    const currentKey = currentResult.jobId ? `job:${currentResult.jobId}` : `media:${currentResult.media.id}`;
    if (!byKey.has(currentKey)) {
      byKey.set(`current:${currentResult.jobId}`, buildCurrentEntry(currentResult));
    }
  }

  return Array.from(byKey.values())
    .map((entry) => {
      const counts = getViolationCounts(entry.result);
      return {
        id: entry.cacheKey,
        entry,
        mediaName: entry.mediaName,
        query: entry.query,
        source: entry.source,
        status: entry.status,
        updatedAt: entry.updatedAt || entry.savedAt,
        analyzed: Boolean(entry.result),
        violationCount: counts.total,
        topViolation: counts.topViolation,
        topSeverity: counts.topSeverity,
        frameCount: entry.result?.frames.length ?? 0,
      };
    })
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

function formatDate(value: string) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return 'Not recorded';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function severityClass(severity?: Severity) {
  if (severity === 'High') return 'bg-red-500';
  if (severity === 'Medium') return 'bg-amber-500';
  if (severity === 'Low') return 'bg-yellow-500';
  return 'bg-slate-300';
}

function confidenceLabel(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Not reported';
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function csvEscape(value: unknown) {
  const text = String(value ?? '');
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function markdownEscape(value: unknown) {
  return String(value ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function completedAtFor(entry: CachedResultEntry) {
  const finishedAt = entry.jobStatus?.finishedAt;
  if (finishedAt) return finishedAt;
  return entry.result?.generatedAt ?? entry.updatedAt ?? entry.savedAt;
}

function reportRowsForDashboardRow(row: DashboardRow): SafetyInsightsReportRow[] {
  const result = row.entry.result;
  const jobId = result?.jobId ?? row.entry.selectedJobId ?? row.entry.jobId ?? row.entry.mediaId;
  const updatedAt = row.updatedAt || row.entry.updatedAt || row.entry.savedAt;
  const completedAt = completedAtFor(row.entry);

  if (!result) {
    return [{
      video: row.mediaName,
      jobId,
      status: row.status,
      violationType: 'Not analyzed',
      severity: 'Not reported',
      frameNumber: 'Not reported',
      timestamp: 'Not reported',
      confidence: 'Not reported',
      evidenceCount: 0,
      topFinding: row.topViolation,
      updatedAt,
      completedAt,
    }];
  }

  const eventRows = (result.events || []).flatMap((event) => (
    event.supportingFrames.length
      ? event.supportingFrames.map((frame) => ({
        video: row.mediaName,
        jobId,
        status: row.status,
        violationType: event.name,
        severity: event.severity,
        frameNumber: String(frame.frameNumber),
        timestamp: frame.timestamp,
        confidence: confidenceLabel(frame.confidence || event.representativeConfidence),
        evidenceCount: event.supportingFrameCount,
        topFinding: row.topViolation,
        updatedAt,
        completedAt,
      }))
      : [{
        video: row.mediaName,
        jobId,
        status: row.status,
        violationType: event.name,
        severity: event.severity,
        frameNumber: 'Not reported',
        timestamp: `${event.startTimestamp} to ${event.endTimestamp}`,
        confidence: confidenceLabel(event.representativeConfidence),
        evidenceCount: event.supportingFrameCount,
        topFinding: row.topViolation,
        updatedAt,
        completedAt,
      }]
  ));
  if (eventRows.length) return eventRows;

  const frameRows = result.frames.flatMap((frame) => frame.violations.map((violation) => ({
    video: row.mediaName,
    jobId,
    status: row.status,
    violationType: violation.name,
    severity: violation.severity,
    frameNumber: String(frame.frameNumber),
    timestamp: frame.timestamp,
    confidence: confidenceLabel(violation.confidence),
    evidenceCount: result.frames.filter((item) => item.violations.length > 0).length,
    topFinding: row.topViolation,
    updatedAt,
    completedAt,
  })));
  if (frameRows.length) return frameRows;

  return [{
    video: row.mediaName,
    jobId,
    status: row.status,
    violationType: 'No violation detected',
    severity: 'None',
    frameNumber: 'Not reported',
    timestamp: 'Not reported',
    confidence: 'Not reported',
    evidenceCount: 0,
    topFinding: row.topViolation,
    updatedAt,
    completedAt,
  }];
}

export function buildSafetyInsightsReportRows(
  entries: CachedResultEntry[],
  currentResult: AnalysisResult | null,
): SafetyInsightsReportRow[] {
  return buildRows(entries, currentResult).flatMap(reportRowsForDashboardRow);
}

export function buildSafetyInsightsCsv(rows: SafetyInsightsReportRow[]): string {
  return [
    REPORT_COLUMNS.map(([, label]) => csvEscape(label)).join(','),
    ...rows.map((row) => REPORT_COLUMNS.map(([key]) => csvEscape(row[key])).join(',')),
  ].join('\n');
}

export function buildSafetyInsightsMarkdown(rows: SafetyInsightsReportRow[]): string {
  const header = `| ${REPORT_COLUMNS.map(([, label]) => markdownEscape(label)).join(' | ')} |`;
  const divider = `| ${REPORT_COLUMNS.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${REPORT_COLUMNS.map(([key]) => markdownEscape(row[key])).join(' | ')} |`);
  return [
    '# SafeTrace Safety Insights Report',
    '',
    `Generated: ${new Date().toISOString()}`,
    '',
    header,
    divider,
    ...body,
    '',
    'Note: this report is generated from local browser-cached result metadata and does not include raw uploaded videos or copied evidence image bytes.',
  ].join('\n');
}

export function buildSafetyInsightsJson(rows: SafetyInsightsReportRow[]): string {
  return JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      storage: 'local browser cache metadata only',
      rows,
    },
    null,
    2,
  );
}

function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SafetyInsightsDashboard({
  entries,
  currentResult,
  backendConnected,
  onOpenResult,
  onBackToAnalysis,
}: SafetyInsightsDashboardProps) {
  const rows = buildRows(entries, currentResult);
  const totals = rows.reduce(
    (acc, row) => {
      acc.total += 1;
      if (row.analyzed && row.violationCount > 0) acc.withViolations += 1;
      if (row.analyzed && row.violationCount === 0) acc.withoutViolations += 1;
      if (!row.analyzed) acc.pending += 1;
      acc.violations += row.violationCount;
      if (row.analyzed) acc.analyzed += 1;
      return acc;
    },
    { total: 0, analyzed: 0, withViolations: 0, withoutViolations: 0, pending: 0, violations: 0 },
  );

  const typeCounts = new Map<string, number>();
  const severityCounts: Record<Severity, number> = { High: 0, Medium: 0, Low: 0 };
  rows.forEach((row) => {
    const counts = getViolationCounts(row.entry.result);
    counts.byType.forEach((count, name) => typeCounts.set(name, (typeCounts.get(name) || 0) + count));
    SEVERITIES.forEach((severity) => {
      severityCounts[severity] += counts.bySeverity[severity];
    });
  });
  const maxTypeCount = Math.max(1, ...Array.from(typeCounts.values()));
  const typeEntries = Array.from(typeCounts.entries()).sort((a, b) => b[1] - a[1]);
  const rankedRows = [...rows].sort((a, b) => b.violationCount - a.violationCount).slice(0, 5);
  const recentRows = rows.slice(0, 5);
  const reportRows = buildSafetyInsightsReportRows(entries, currentResult);
  const hasReportRows = reportRows.length > 0;

  function handleDownloadCsv() {
    downloadTextFile('safetrace-safety-insights.csv', buildSafetyInsightsCsv(reportRows), 'text/csv;charset=utf-8');
  }

  function handleDownloadMarkdown() {
    downloadTextFile('safetrace-safety-insights.md', buildSafetyInsightsMarkdown(reportRows), 'text/markdown;charset=utf-8');
  }

  function handleDownloadJson() {
    downloadTextFile('safetrace-safety-insights.json', buildSafetyInsightsJson(reportRows), 'application/json;charset=utf-8');
  }

  return (
    <section className="space-y-5">
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-safety-teal">Safety insights</p>
            <h2 className="mt-1 text-2xl font-bold text-slate-950">Cached analysis overview</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Summarizes current and locally cached SafeTrace results. Raw uploaded videos and copied evidence images are not stored in the browser cache.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <button
              type="button"
              onClick={handleDownloadCsv}
              disabled={!hasReportRows}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              CSV
            </button>
            <button
              type="button"
              onClick={handleDownloadMarkdown}
              disabled={!hasReportRows}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue disabled:cursor-not-allowed disabled:opacity-50"
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              Markdown
            </button>
            <button
              type="button"
              onClick={handleDownloadJson}
              disabled={!hasReportRows}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue disabled:cursor-not-allowed disabled:opacity-50"
            >
              <FileJson className="h-4 w-4" aria-hidden="true" />
              JSON
            </button>
            <button
              type="button"
              onClick={onBackToAnalysis}
              className="focus-ring inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue"
            >
              Back to analysis
            </button>
          </div>
        </div>
        {!backendConnected ? (
          <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <Clock3 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            Showing local cached metadata while the SafeTrace Local Runtime is disconnected.
          </div>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard icon={<Video />} label="Uploaded or cached" value={totals.total} />
        <MetricCard icon={<CheckCircle2 />} label="Analyzed" value={totals.analyzed} />
        <MetricCard icon={<AlertTriangle />} label="With violations" value={totals.withViolations} tone="warning" />
        <MetricCard icon={<ShieldCheck />} label="Without violations" value={totals.withoutViolations} tone="success" />
        <MetricCard icon={<BarChart3 />} label="Violation instances" value={totals.violations} />
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
          <Database className="mx-auto mb-3 h-8 w-8 text-slate-400" aria-hidden="true" />
          No cached analysis results yet. Run an analysis to populate Safety Insights.
        </div>
      ) : (
        <>
          <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-safety-blue" aria-hidden="true" />
                <h3 className="text-sm font-bold uppercase text-slate-600">Operational hotspots</h3>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {typeEntries.slice(0, 3).length ? (
                  typeEntries.slice(0, 3).map(([name, count], index) => (
                    <div key={name} className="rounded-lg border border-slate-100 bg-slate-50 p-4">
                      <p className="text-xs font-bold uppercase text-slate-500">Rank {index + 1}</p>
                      <p className="mt-2 text-sm font-semibold text-slate-950">{name}</p>
                      <p className="mt-1 text-2xl font-bold text-safety-blue">{count}</p>
                      <p className="text-xs text-slate-500">evidence instance{count === 1 ? '' : 's'}</p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-lg border border-slate-100 bg-slate-50 p-4 text-sm text-slate-500 md:col-span-3">
                    No violation hotspots have been recorded in cached results.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
              <div className="flex items-center gap-2">
                <ListChecks className="h-4 w-4 text-safety-blue" aria-hidden="true" />
                <h3 className="text-sm font-bold uppercase text-slate-600">Review queue</h3>
              </div>
              <div className="mt-4 space-y-3">
                {rankedRows.map((row) => (
                  <div key={row.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-950">{row.mediaName}</p>
                      <p className="truncate text-xs text-slate-500">{row.topViolation}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700">
                      {row.violationCount}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
              <h3 className="text-sm font-bold uppercase text-slate-600">Violation counts by type</h3>
              <div className="mt-4 space-y-3">
                {typeEntries.length ? (
                  typeEntries.map(([name, count]) => (
                    <div key={name}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-semibold text-slate-700">{name}</span>
                        <span className="text-slate-500">{count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-safety-blue" style={{ width: `${(count / maxTypeCount) * 100}%` }} />
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No violations recorded in cached results.</p>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
              <h3 className="text-sm font-bold uppercase text-slate-600">Severity distribution</h3>
              <div className="mt-4 grid grid-cols-3 gap-3">
                {SEVERITIES.map((severity) => (
                  <div key={severity} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                    <div className={`mb-3 h-2 rounded-full ${severityClass(severity)}`} />
                    <p className="text-xs font-semibold uppercase text-slate-500">{severity}</p>
                    <p className="mt-1 text-2xl font-bold text-slate-950">{severityCounts[severity]}</p>
                  </div>
                ))}
              </div>
              {totals.pending ? (
                <p className="mt-4 text-xs text-slate-500">{totals.pending} cached item{totals.pending === 1 ? '' : 's'} are pending or do not include result JSON.</p>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-sm font-bold uppercase text-slate-600">Recent analyses</h3>
              <p className="text-xs text-slate-500">Newest local cache entries first</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {recentRows.map((row) => (
                <div key={`recent-${row.id}`} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p className="truncate text-sm font-semibold text-slate-950">{row.mediaName}</p>
                  <p className="mt-1 text-xs text-slate-500">{formatDate(row.updatedAt)}</p>
                  <p className="mt-2 text-xs font-bold uppercase text-slate-600">{row.status}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {row.violationCount} finding{row.violationCount === 1 ? '' : 's'}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-soft">
            <div className="border-b border-slate-200 p-4">
              <h3 className="text-sm font-bold uppercase text-slate-600">Per-video results</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-xs font-bold uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Media</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Violations</th>
                    <th className="px-4 py-3">Top finding</th>
                    <th className="px-4 py-3">Updated</th>
                    <th className="px-4 py-3">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((row) => (
                    <tr key={row.id} className="align-top">
                      <td className="px-4 py-3">
                        <p className="font-semibold text-slate-900">{row.mediaName}</p>
                        <p className="mt-1 text-xs text-slate-500">{row.query}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold uppercase text-slate-600">
                          {row.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900">{row.violationCount}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`h-2.5 w-2.5 rounded-full ${severityClass(row.topSeverity)}`} />
                          <span>{row.topViolation}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">{row.frameCount} evidence frame{row.frameCount === 1 ? '' : 's'}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatDate(row.updatedAt)}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          disabled={!row.entry.result}
                          onClick={() => onOpenResult(row.entry)}
                          className="focus-ring rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Open result
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: ReactNode;
  label: string;
  value: number;
  tone?: 'default' | 'success' | 'warning';
}) {
  const color = tone === 'success' ? 'text-emerald-700' : tone === 'warning' ? 'text-amber-700' : 'text-safety-blue';
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
      <div className={`mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 ${color}`}>
        {icon}
      </div>
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-950">{value}</p>
    </div>
  );
}
