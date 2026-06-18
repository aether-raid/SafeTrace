import { ShieldCheck } from 'lucide-react';
import type { AnalysisResult, Severity } from '../types/analysis';
import { formatViolationName } from '../utils/formatters';
import { ViolationCard, type GroupedViolation } from './ViolationCard';

type ViolationSummaryProps = {
  result: AnalysisResult;
  onFrameSelect: (frameId: string) => void;
};

const severityRank: Record<Severity, number> = {
  High: 3,
  Medium: 2,
  Low: 1,
};

function groupViolations(result: AnalysisResult): GroupedViolation[] {
  const groups = new Map<string, GroupedViolation>();

  result.frames.forEach((frame) => {
    frame.violations.forEach((violation) => {
      const existing = groups.get(violation.type);
      const affectedFrame = {
        frameId: frame.id,
        frameNumber: frame.frameNumber,
        timestamp: frame.timestamp,
      };

      if (!existing) {
        groups.set(violation.type, {
          type: violation.type,
          name: violation.name || formatViolationName(violation.type),
          severity: violation.severity,
          description: violation.description,
          affectedFrames: [affectedFrame],
          confidences: [violation.confidence],
        });
        return;
      }

      existing.affectedFrames.push(affectedFrame);
      existing.confidences.push(violation.confidence);

      if (severityRank[violation.severity] > severityRank[existing.severity]) {
        existing.severity = violation.severity;
      }
    });
  });

  return Array.from(groups.values()).sort((a, b) => severityRank[b.severity] - severityRank[a.severity]);
}

export function ViolationSummary({ result, onFrameSelect }: ViolationSummaryProps) {
  const groupedViolations = groupViolations(result);

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Violation Summary</h2>
          <p className="mt-1 text-sm text-slate-600">Repeated findings are grouped by unique violation type.</p>
        </div>
      </div>

      {groupedViolations.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {groupedViolations.map((violation) => (
            <ViolationCard key={violation.type} violation={violation} onFrameSelect={onFrameSelect} />
          ))}
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p className="text-sm font-medium">
            No matching safety violations were detected in the selected frames for this query.
          </p>
        </div>
      )}
    </section>
  );
}
