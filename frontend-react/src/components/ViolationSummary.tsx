import { ShieldCheck, List, Clock, BarChart2 } from 'lucide-react';
import { useState } from 'react';
import type { AnalysisResult, Severity } from '../types/analysis';
import { formatConfidence, formatViolationName } from '../utils/formatters';
import { SeverityBadge } from './SeverityBadge';
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

type ViolationOverviewRow = {
  type: string;
  name: string;
  severity: Severity;
  eventCount: number;
  firstTimestamp: string;
  lastTimestamp: string;
  representativeConfidence: number;
  supportingFrameCount: number;
  firstFrameId?: string;
};

const severityRank: Record<Severity, number> = {
  High: 3,
  Medium: 2,
  Low: 1,
};

function groupViolations(result: AnalysisResult): GroupedViolation[] {
  if (result.events && result.events.length > 0) {
    return result.events.map((event) => ({
      type: event.type,
      name: event.name || formatViolationName(event.type),
      severity: event.severity,
      description: event.description,
      affectedFrames: event.supportingFrames.map((frame) => ({
        frameId: frame.frameId,
        frameNumber: frame.frameNumber,
        timestamp: frame.timestamp,
      })),
      confidences: event.supportingFrames.map((frame) => frame.confidence),
      startTimestamp: event.startTimestamp,
      endTimestamp: event.endTimestamp,
      representativeConfidence: event.representativeConfidence,
      supportingFrameCount: event.supportingFrameCount,
    }));
  }

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

function toSeverity(value: string | undefined): Severity {
  const normalized = (value || '').toLowerCase();
  if (normalized === 'high' || normalized === 'critical') return 'High';
  if (normalized === 'medium') return 'Medium';
  return 'Low';
}

function timestampValue(timestamp: string): number {
  const parts = timestamp.split(':').map(Number);
  if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return 0;
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function earlierTimestamp(current: string, next: string): string {
  return timestampValue(next) < timestampValue(current) ? next : current;
}

function laterTimestamp(current: string, next: string): string {
  return timestampValue(next) > timestampValue(current) ? next : current;
}

function buildOverviewRows(result: AnalysisResult): ViolationOverviewRow[] {
  const rows = new Map<string, ViolationOverviewRow>();

  function upsert(input: ViolationOverviewRow) {
    const existing = rows.get(input.type);
    if (!existing) {
      rows.set(input.type, input);
      return;
    }

    existing.eventCount += input.eventCount;
    existing.firstTimestamp = earlierTimestamp(existing.firstTimestamp, input.firstTimestamp);
    existing.lastTimestamp = laterTimestamp(existing.lastTimestamp, input.lastTimestamp);
    existing.representativeConfidence = Math.max(
      existing.representativeConfidence,
      input.representativeConfidence,
    );
    existing.supportingFrameCount += input.supportingFrameCount;
    if (severityRank[input.severity] > severityRank[existing.severity]) {
      existing.severity = input.severity;
    }
    existing.firstFrameId = existing.firstFrameId || input.firstFrameId;
  }

  if (result.events?.length) {
    result.events.forEach((event) => {
      upsert({
        type: event.type,
        name: event.name || formatViolationName(event.type),
        severity: event.severity,
        eventCount: 1,
        firstTimestamp: event.startTimestamp,
        lastTimestamp: event.endTimestamp,
        representativeConfidence: event.representativeConfidence,
        supportingFrameCount: event.supportingFrameCount,
        firstFrameId: event.supportingFrames[0]?.frameId,
      });
    });
  } else if (result.violations?.length) {
    result.violations.forEach((violation) => {
      const timestamps = violation.affectedFrames.map((frame) => frame.timestamp);
      upsert({
        type: violation.id,
        name: violation.name || formatViolationName(violation.id),
        severity: toSeverity(violation.severity),
        eventCount: 1,
        firstTimestamp: timestamps.reduce(earlierTimestamp, timestamps[0] || '00:00:00'),
        lastTimestamp: timestamps.reduce(laterTimestamp, timestamps[0] || '00:00:00'),
        representativeConfidence: violation.confidenceMax,
        supportingFrameCount: violation.affectedFrames.length,
        firstFrameId: violation.affectedFrames[0]?.frameId,
      });
    });
  } else {
    result.frames.forEach((frame) => {
      frame.violations.forEach((violation) => {
        upsert({
          type: violation.type,
          name: violation.name || formatViolationName(violation.type),
          severity: violation.severity,
          eventCount: 1,
          firstTimestamp: frame.timestamp,
          lastTimestamp: frame.timestamp,
          representativeConfidence: violation.confidence,
          supportingFrameCount: 1,
          firstFrameId: frame.id,
        });
      });
    });
  }

  return Array.from(rows.values()).sort((a, b) => severityRank[b.severity] - severityRank[a.severity]);
}

export function ViolationSummary({ result, onFrameSelect, timelineComponent, statisticsComponent }: ViolationSummaryProps) {
  // State to track which tab is currently selected
  const [activeTab, setActiveTab] = useState<TabView>('list');
  const groupedViolations = groupViolations(result);
  const overviewRows = buildOverviewRows(result);

  return (
    <section id="video-violation-overview" className="rounded-lg border border-slate-200 bg-white p-6 shadow-soft">
      {/* Header and Tab Controls */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Video Violation Overview</h2>
          <p className="mt-1 text-sm text-slate-600">Review grouped violation types, event spans, and supporting evidence.</p>
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

      <div className="mb-6 overflow-hidden rounded-lg border border-slate-200">
        {overviewRows.length > 0 ? (
          <>
            <div className="grid gap-3 bg-slate-50 px-4 py-3 text-xs font-bold uppercase text-slate-500 md:grid-cols-[1.5fr_0.8fr_0.9fr_0.9fr_0.8fr_0.9fr]">
              <span>Violation type</span>
              <span>Events</span>
              <span>First seen</span>
              <span>Last seen</span>
              <span>Confidence</span>
              <span>Support</span>
            </div>
            {overviewRows.map((row) => (
              <div
                key={row.type}
                className="grid gap-3 border-t border-slate-200 px-4 py-3 text-sm md:grid-cols-[1.5fr_0.8fr_0.9fr_0.9fr_0.8fr_0.9fr] md:items-center"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate font-semibold text-slate-950">{row.name}</p>
                    <SeverityBadge severity={row.severity} />
                  </div>
                </div>
                <span className="font-medium text-slate-700">{row.eventCount}</span>
                <span className="font-mono text-xs text-slate-600">{row.firstTimestamp}</span>
                <span className="font-mono text-xs text-slate-600">{row.lastTimestamp}</span>
                <span className="font-semibold text-slate-900">{formatConfidence(row.representativeConfidence)}</span>
                <div className="flex items-center gap-2">
                  <span className="text-slate-700">{row.supportingFrameCount} frame{row.supportingFrameCount === 1 ? '' : 's'}</span>
                  {row.firstFrameId ? (
                    <button
                      type="button"
                      onClick={() => onFrameSelect(row.firstFrameId as string)}
                      className="focus-ring rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 transition hover:border-safety-blue hover:text-safety-blue"
                    >
                      View
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </>
        ) : (
          <div className="flex items-start gap-3 bg-emerald-50 p-4 text-emerald-800">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p className="text-sm font-medium">
              No matching safety violations were detected in the selected frames for this query.
            </p>
          </div>
        )}
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
