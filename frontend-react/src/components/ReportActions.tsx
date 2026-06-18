import { Download, FileJson, FileText } from 'lucide-react';
import type { AnalysisResult } from '../types/analysis';
import { formatAverageConfidence, formatDateTime } from '../utils/formatters';

type ReportActionsProps = {
  result: AnalysisResult;
};

type SummaryFinding = {
  name: string;
  frames: string[];
  confidences: number[];
};

function downloadFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function getSummaryFindings(result: AnalysisResult): SummaryFinding[] {
  const findings = new Map<string, SummaryFinding>();

  result.frames.forEach((frame) => {
    frame.violations.forEach((violation) => {
      const current = findings.get(violation.type) ?? {
        name: violation.name,
        frames: [],
        confidences: [],
      };
      current.frames.push(`Frame ${frame.frameNumber} at ${frame.timestamp}`);
      current.confidences.push(violation.confidence);
      findings.set(violation.type, current);
    });
  });

  return Array.from(findings.values());
}

function buildSummaryReport(result: AnalysisResult) {
  const findings = getSummaryFindings(result);
  const lines = [
    'SafeTrace Summary Report',
    `Generated: ${formatDateTime(result.generatedAt)}`,
    `Media: ${result.media.filename}`,
    `Query: ${result.query}`,
    `Frames analyzed: ${result.framesAnalyzed}`,
    '',
    findings.length > 0 ? 'Findings:' : 'Findings: No matching safety violations were detected.',
  ];

  findings.forEach((finding) => {
    lines.push(
      `- ${finding.name}`,
      `  Evidence: ${finding.frames.join(', ')}`,
      `  Average confidence: ${formatAverageConfidence(finding.confidences)}`,
    );
  });

  return `${lines.join('\n')}\n`;
}

export function ReportActions({ result }: ReportActionsProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Download className="h-4 w-4 text-safety-blue" aria-hidden="true" />
            Technical Report / Export
          </div>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Export a review-ready summary or the full technical evidence package.
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-safety-blue px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
            type="button"
            onClick={() => downloadFile('safetrace-summary-report.txt', buildSummaryReport(result), 'text/plain')}
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            Download summary report
          </button>
          <button
            className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
            type="button"
            onClick={() =>
              downloadFile(
                'safetrace-technical-evidence.json',
                JSON.stringify(result, null, 2),
                'application/json',
              )
            }
          >
            <FileJson className="h-4 w-4" aria-hidden="true" />
            Download technical JSON
          </button>
        </div>
      </div>
    </section>
  );
}
