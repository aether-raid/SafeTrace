import clsx from 'clsx';

type StatusBadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

type StatusBadgeProps = {
  label: string;
  tone?: StatusBadgeTone;
  className?: string;
};

const toneClasses: Record<StatusBadgeTone, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  danger: 'border-red-200 bg-red-50 text-red-700',
  info: 'border-blue-200 bg-blue-50 text-blue-700',
  neutral: 'border-slate-200 bg-slate-50 text-slate-700',
};

export function StatusBadge({ label, tone = 'neutral', className }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold',
        toneClasses[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
