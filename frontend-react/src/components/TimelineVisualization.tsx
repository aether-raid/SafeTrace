import { Clock, AlertTriangle, Info } from 'lucide-react';
import type { AnalysisResult, FrameResult } from '../types/analysis';

type TimelineVisualizationProps = {
  result: AnalysisResult;
  onFrameSelect: (frameId: string) => void;
  selectedFrameId?: string | null;
};

function getSeverityColor(frame: FrameResult): string {
  const severities = frame.violations.map((v) => v.severity);
  if (severities.includes('High')) return 'bg-red-500';
  if (severities.includes('Medium')) return 'bg-amber-500';
  if (severities.length > 0) return 'bg-yellow-500';
  return 'bg-emerald-500';
}

function getSeverityDotColor(frame: FrameResult): string {
  const severities = frame.violations.map((v) => v.severity);
  if (severities.includes('High')) return 'bg-red-500 ring-red-200';
  if (severities.includes('Medium')) return 'bg-amber-500 ring-amber-200';
  if (severities.length > 0) return 'bg-yellow-500 ring-yellow-200';
  return 'bg-emerald-500 ring-emerald-200';
}

export function TimelineVisualization({ result, onFrameSelect, selectedFrameId }: TimelineVisualizationProps) {
  const duration = result.totalDurationSeconds || result.media.durationSeconds || 65;
  if (duration <= 0 || result.frames.length === 0) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="h-5 w-5 text-safety-blue" />
          <h2 className="text-lg font-bold text-slate-950">Timeline Visualization</h2>
        </div>
        <span className="text-xs text-slate-500">
          {result.frames.length} violation track{result.frames.length !== 1 ? 's' : ''} across {result.media.duration || '0s'}
        </span>
      </div>

      <div className="relative">
        <div className="mb-1 flex justify-between text-xs text-slate-500">
          <span>00:00</span>
          <span>{result.media.duration || '00:00'}</span>
        </div>

        <div className="relative h-8 w-full rounded-full bg-slate-100">
          {result.frames.map((frame) => {
            const pct = duration > 0 ? (frame.timestampSeconds || 0) / duration * 100 : 0;
            const isSelected = frame.id === selectedFrameId;
            const hasViolations = frame.violations.length > 0;

            return (
              <div
                key={frame.id}
                className="absolute top-1/2 -translate-y-1/2"
                style={{ left: `${Math.min(pct, 100)}%` }}
              >
                <button
                  type="button"
                  onClick={() => onFrameSelect(frame.id)}
                  title={`Frame at ${frame.timestamp}${hasViolations ? ` - ${frame.violations.length} violation(s)` : ' - No violations'}`}
                  className={`relative flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-full ring-2 transition hover:scale-125 ${
                    hasViolations
                      ? getSeverityDotColor(frame)
                      : 'bg-slate-400 ring-slate-200'
                  } ${isSelected ? 'scale-125 ring-safety-blue' : ''}`}
                >
                  {hasViolations ? (
                    <AlertTriangle className="h-3 w-3 text-white" />
                  ) : (
                    <Info className="h-3 w-3 text-white" />
                  )}
                </button>
                <span className="absolute left-1/2 top-7 -translate-x-1/2 whitespace-nowrap text-[10px] font-medium text-slate-600">
                  {frame.timestamp}
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-8 flex flex-wrap gap-3">
          {result.frames.filter((f) => f.violations.length > 0).length > 0 && (
            <div className="flex items-center gap-4 text-xs text-slate-600">
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-full bg-red-500" /> Violation
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-full bg-amber-500" /> Warning
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded-full bg-emerald-500" /> Clear
              </span>
            </div>
          )}
        </div>
      </div>

      {result.frames.some((f) => f.imageUrl) && (
        <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
          {result.frames.map((frame) => {
            const pct = duration > 0 ? (frame.timestampSeconds || 0) / duration * 100 : 0;
            return (
              <button
                key={frame.id}
                type="button"
                onClick={() => onFrameSelect(frame.id)}
                className={`group relative overflow-hidden rounded-lg border-2 transition ${
                  frame.id === selectedFrameId ? 'border-safety-blue ring-2 ring-blue-100' : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                {frame.imageUrl ? (
                  <img src={frame.imageUrl} alt="" className="h-16 w-full object-cover" loading="lazy" />
                ) : (
                  <div className="flex h-16 items-center justify-center bg-slate-800 text-[10px] text-slate-400">
                    No preview
                  </div>
                )}
                <div className="flex items-center justify-between bg-slate-950/80 px-1.5 py-1">
                  <span className="text-[10px] text-white">{frame.timestamp}</span>
                  {frame.violations.length > 0 && (
                    <span className={`h-2 w-2 rounded-full ${getSeverityColor(frame)}`} />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
