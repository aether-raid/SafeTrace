import clsx from 'clsx';
import { CheckCircle2, ShieldAlert, Sparkles } from 'lucide-react';
import type { FrameResult } from '../types/analysis';
import { formatConfidence, formatQueryRelevance } from '../utils/formatters';
import { EvidenceFrameVisual } from './EvidenceFrameVisual';
import { SeverityBadge } from './SeverityBadge';
import { StatusBadge } from './StatusBadge';
import { TechnicalDetails } from './TechnicalDetails';

type FrameEvidenceCardProps = {
  frame: FrameResult;
  showExplanation: boolean;
  isHighlighted?: boolean;
};

export function FrameEvidenceCard({ frame, showExplanation, isHighlighted = false }: FrameEvidenceCardProps) {
  const hasViolations = frame.violations.length > 0;

  return (
    <article
      id={`frame-${frame.id}`}
      className={clsx(
        'scroll-mt-6 overflow-hidden rounded-lg border bg-white shadow-soft transition',
        isHighlighted ? 'border-safety-blue ring-4 ring-blue-100' : 'border-slate-200',
      )}
    >
      <div className="border-b border-slate-200 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-950">
              Frame {frame.frameNumber} - {frame.timestamp}
            </h3>
            <p className="mt-1 text-sm text-slate-500">Query relevance: {formatQueryRelevance(frame.queryRelevance)}</p>
          </div>
          <StatusBadge
            label={hasViolations ? 'Violations detected' : 'No violations detected'}
            tone={hasViolations ? 'danger' : 'success'}
          />
        </div>
      </div>

      <div className="grid gap-4 p-4 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <EvidenceFrameVisual frame={frame} />
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {hasViolations ? (
            <div>
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-950">
                <ShieldAlert className="h-4 w-4 text-red-600" aria-hidden="true" />
                Frame findings
              </div>
              <div className="flex flex-col gap-2">
                {frame.violations.map((violation) => (
                  <div
                    key={violation.id}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-950">{violation.name}</span>
                      <SeverityBadge severity={violation.severity} />
                    </div>
                    <p className="mt-1 text-xs font-medium text-slate-500">
                      Confidence: {formatConfidence(violation.confidence)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-800">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>No matching violations found in this frame.</span>
              </div>
            </div>
          )}

          {showExplanation && frame.explanation ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm leading-6 text-blue-900">
              <div className="mb-1 flex items-center gap-2 font-semibold">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                Visual explanation
              </div>
              {frame.explanation}
            </div>
          ) : null}
        </div>
      </div>

      <div className="border-t border-slate-200 p-4">
        <TechnicalDetails frame={frame} />
      </div>
    </article>
  );
}
