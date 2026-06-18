import { ShieldCheck, List, Clock, BarChart2 } from 'lucide-react';
import { useState } from 'react';
import type { AnalysisResult, Severity } from '../types/analysis';
import { formatViolationName } from '../utils/formatters';
import { ViolationCard, type GroupedViolation } from './ViolationCard';

type ViolationSummaryProps = {
  result: AnalysisResult;
  onFrameSelect: (frameId: string) => void;
  // Pass your new visualization components into this component
  timelineComponent?: React.ReactNode;
  statisticsComponent?: React.ReactNode;
};

// We define the three tabs we want to show
type TabView = 'list' | 'timeline' | 'statistics';

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

export function ViolationSummary({ result, onFrameSelect, timelineComponent, statisticsComponent }: ViolationSummaryProps) {
  // State to track which tab is currently selected
  const [activeTab, setActiveTab] = useState<TabView>('list');
  const groupedViolations = groupViolations(result);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-soft">
      {/* Header and Tab Controls */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Analysis Results</h2>
          <p className="mt-1 text-sm text-slate-600">Review findings, timelines, and statistics.</p>
        </div>

        {/* Tab Toggle Switch (Similar to your image) */}
        <div className="flex inline-flex items-center rounded-lg bg-slate-100 p-1">
          <button
            onClick={() => setActiveTab('list')}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === 'list' ? 'bg-white text-slate-900 shadow' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <List className="h-4 w-4" />
            List
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === 'timeline' ? 'bg-white text-slate-900 shadow' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Clock className="h-4 w-4" />
            Timeline
          </button>
          <button
            onClick={() => setActiveTab('statistics')}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === 'statistics' ? 'bg-white text-slate-900 shadow' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <BarChart2 className="h-4 w-4" />
            Statistics
          </button>
        </div>
      </div>

      {/* Conditional Rendering: Show content based on the active tab */}
      
      {activeTab === 'list' && (
        groupedViolations.length > 0 ? (
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
        )
      )}

      {activeTab === 'timeline' && (
        <div className="mt-4">
          {timelineComponent || <p className="text-sm text-slate-500">Timeline view is not available.</p>}
        </div>
      )}

      {activeTab === 'statistics' && (
        <div className="mt-4">
          {statisticsComponent || <p className="text-sm text-slate-500">Statistics view is not available.</p>}
        </div>
      )}
    </section>
  );
}