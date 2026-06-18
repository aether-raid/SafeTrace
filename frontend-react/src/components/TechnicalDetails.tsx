import { ChevronDown } from 'lucide-react';
import type { FrameResult } from '../types/analysis';

type TechnicalDetailsProps = {
  frame: FrameResult;
};

export function TechnicalDetails({ frame }: TechnicalDetailsProps) {
  const technicalPayload = {
    internalFilename: frame.internalFilename,
    queryRelevanceScore: frame.queryRelevanceScore,
    detections: frame.detections,
    violations: frame.violations.map((violation) => ({
      type: violation.type,
      confidence: violation.confidence,
      evidence: violation.evidence,
    })),
    technicalEvidence: frame.technicalEvidence,
  };

  return (
    <details className="group rounded-lg border border-slate-200 bg-white">
      <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-semibold text-slate-700">
        Technical evidence
        <ChevronDown className="h-4 w-4 transition group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="border-t border-slate-200 p-3">
        <dl className="grid gap-2 text-xs text-slate-600">
          <div>
            <dt className="font-semibold text-slate-800">Internal filename</dt>
            <dd className="mt-1 break-all">{frame.internalFilename}</dd>
          </div>
          <div>
            <dt className="font-semibold text-slate-800">Raw detection details</dt>
            <dd className="mt-2">
              <pre className="max-h-60 overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
                {JSON.stringify(technicalPayload, null, 2)}
              </pre>
            </dd>
          </div>
        </dl>
      </div>
    </details>
  );
}
