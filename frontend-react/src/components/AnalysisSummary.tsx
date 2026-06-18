import { Clock3, FileVideo, Layers3, ShieldAlert, type LucideIcon } from 'lucide-react';
import type { AnalysisResult, Severity } from '../types/analysis';
import { formatDateTime, pluralize } from '../utils/formatters';
import { SeverityBadge } from './SeverityBadge';
import { StatusBadge } from './StatusBadge';

type AnalysisSummaryProps = {
  result: AnalysisResult;
  showExplanations: boolean;
};

const severityRank: Record<Severity, number> = {
  High: 3,
  Medium: 2,
  Low: 1,
};

function getSummaryStats(result: AnalysisResult) {
  const framesWithViolations = result.frames.filter((frame) => frame.violations.length > 0).length;
  const uniqueViolations = new Map<string, Severity>();
  const uniqueViolationNames = new Map<string, string>();

  result.frames.forEach((frame) => {
    frame.violations.forEach((violation) => {
      const existingSeverity = uniqueViolations.get(violation.type);
      uniqueViolationNames.set(violation.type, violation.name);
      if (!existingSeverity || severityRank[violation.severity] > severityRank[existingSeverity]) {
        uniqueViolations.set(violation.type, violation.severity);
      }
    });
  });

  const highestSeverity = Array.from(uniqueViolations.values()).sort(
    (a, b) => severityRank[b] - severityRank[a],
  )[0];

  return {
    framesWithViolations,
    uniqueViolationCount: uniqueViolations.size,
    uniqueViolationNames: Array.from(uniqueViolationNames.values()),
    highestSeverity,
  };
}

export function AnalysisSummary({ result, showExplanations }: AnalysisSummaryProps) {
  const stats = getSummaryStats(result);
  const hasViolations = stats.uniqueViolationCount > 0;
  const severityLabel = stats.highestSeverity ? stats.highestSeverity.toLowerCase() : 'clear';
  const repeatedFindings = stats.uniqueViolationNames.join(' and ');

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-safety-blue">Analysis summary</p>
          <h2 className="mt-1 text-2xl font-bold tracking-normal text-slate-950">
            {hasViolations ? 'Violation findings detected' : 'No matching violations detected'}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            {hasViolations
              ? `SafeTrace found ${stats.uniqueViolationCount} ${severityLabel}-risk violation type${stats.uniqueViolationCount === 1 ? '' : 's'} across ${stats.framesWithViolations} of ${result.framesAnalyzed} relevant frames. Repeated findings include ${repeatedFindings}.`
              : 'No matching safety violations were detected in the selected frames for this query.'}
          </p>
          {showExplanations && result.summaryText ? (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm leading-6 text-blue-900">
              Explanation generated from available visual evidence. {result.summaryText}
            </div>
          ) : null}
        </div>

        {stats.highestSeverity ? (
          <SeverityBadge severity={stats.highestSeverity} />
        ) : (
          <StatusBadge label="Clear" tone="success" />
        )}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric icon={FileVideo} label="Media analyzed" value={result.media.filename} />
        <SummaryMetric icon={Layers3} label="Frames analyzed" value={String(result.framesAnalyzed)} />
        <SummaryMetric
          icon={ShieldAlert}
          label="Frames with violations"
          value={`${stats.framesWithViolations} of ${result.framesAnalyzed}`}
        />
        <SummaryMetric icon={Clock3} label="Generated" value={formatDateTime(result.generatedAt)} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <StatusBadge label={`Query: ${result.query}`} tone="info" />
        {result.settings ? (
          <>
            <StatusBadge label={`Top-K ${result.settings.topK}`} tone="neutral" />
            <StatusBadge label={`${result.settings.fps.toFixed(1)} FPS`} tone="neutral" />
            <StatusBadge label={`${result.settings.deviceMode} device`} tone="neutral" />
          </>
        ) : null}
        <StatusBadge label={pluralize(stats.uniqueViolationCount, 'violation type')} tone={hasViolations ? 'danger' : 'success'} />
        <StatusBadge label="Evidence-backed findings" tone="neutral" />
      </div>
    </section>
  );
}

type SummaryMetricProps = {
  icon: LucideIcon;
  label: string;
  value: string;
};

function SummaryMetric({ icon: Icon, label, value }: SummaryMetricProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-white text-safety-blue shadow-insetLine">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold leading-5 text-slate-950">{value}</p>
    </div>
  );
}
