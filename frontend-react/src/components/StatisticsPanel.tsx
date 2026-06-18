import { BarChart3, PieChart, TrendingUp, AlertTriangle } from 'lucide-react';
import type { AnalysisResult, Severity } from '../types/analysis';

type StatisticsPanelProps = {
  result: AnalysisResult;
};

function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'High': return 'bg-red-500';
    case 'Medium': return 'bg-amber-500';
    case 'Low': return 'bg-yellow-500';
    default: return 'bg-slate-400';
  }
}

export function StatisticsPanel({ result }: StatisticsPanelProps) {
  const violationCounts = new Map<string, { count: number; severity: Severity }>();
  const severityCounts: Record<string, number> = { High: 0, Medium: 0, Low: 0 };

  result.frames.forEach((frame) => {
    frame.violations.forEach((v) => {
      const current = violationCounts.get(v.type) || { count: 0, severity: v.severity };
      current.count++;
      if (v.severity) severityCounts[v.severity]++;
      violationCounts.set(v.type, current);
    });
  });

  const maxViolationCount = Math.max(...Array.from(violationCounts.values()).map((v) => v.count), 1);
  const totalViolations = Array.from(violationCounts.values()).reduce((s, v) => s + v.count, 0);
  const hasData = violationCounts.size > 0;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2">
        <BarChart3 className="h-5 w-5 text-safety-blue" />
        <h2 className="text-lg font-bold text-slate-950">Statistical Visualizations</h2>
      </div>

      {!hasData ? (
        <div className="flex items-center gap-3 rounded-lg border border-slate-100 bg-slate-50 p-4 text-sm text-slate-500">
          <TrendingUp className="h-5 w-5" />
          No violation data to visualize. Run an analysis to see statistics.
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <BarChart3 className="h-4 w-4 text-safety-blue" />
                Violation Frequency
              </h3>
              <span className="text-xs text-slate-500">{totalViolations} total</span>
            </div>
            <div className="space-y-2">
              {Array.from(violationCounts.entries()).map(([type, data]) => {
                const pct = (data.count / maxViolationCount) * 100;
                return (
                  <div key={type}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="font-medium text-slate-700">{type.replace(/_/g, ' ')}</span>
                      <span className="text-slate-500">{data.count} instance{data.count !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="h-5 w-full overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${getSeverityColor(data.severity)}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
              <PieChart className="h-4 w-4 text-safety-blue" />
              Severity Distribution
            </div>
            <div className="flex items-center gap-4">
              {['High', 'Medium', 'Low'].map((sev) => {
                const count = severityCounts[sev] || 0;
                const pct = totalViolations > 0 ? (count / totalViolations) * 100 : 0;
                return (
                  <div key={sev} className="flex flex-1 flex-col items-center gap-1">
                    <div className="relative flex h-20 w-full items-end justify-center">
                      <div
                        className={`w-full rounded-t ${getSeverityColor(sev)} transition-all duration-500`}
                        style={{ height: `${pct}%`, minHeight: count > 0 ? '4px' : '0' }}
                      />
                    </div>
                    <span className="text-[10px] font-semibold uppercase text-slate-500">{sev}</span>
                    <span className="text-xs font-bold text-slate-700">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-600">
              <AlertTriangle className="h-3.5 w-3.5" />
              Frames with violations: {result.frames.filter((f) => f.violations.length > 0).length} / {result.frames.length}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
