import clsx from 'clsx';
import type { Severity } from '../types/analysis';
import { formatSeverity } from '../utils/formatters';

type SeverityBadgeProps = {
  severity: Severity;
  className?: string;
};

const severityClasses: Record<Severity, string> = {
  High: 'border-red-200 bg-red-50 text-red-700',
  Medium: 'border-amber-200 bg-amber-50 text-amber-700',
  Low: 'border-emerald-200 bg-emerald-50 text-emerald-700',
};

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold',
        severityClasses[severity],
        className,
      )}
    >
      {formatSeverity(severity)}
    </span>
  );
}
