import type { FrameResult } from '../types/analysis';
import { FrameEvidenceCard } from './FrameEvidenceCard';

type EvidenceFramesProps = {
  frames: FrameResult[];
  showExplanations: boolean;
  highlightedFrameId?: string | null;
};

export function EvidenceFrames({ frames, showExplanations, highlightedFrameId }: EvidenceFramesProps) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="text-lg font-bold text-slate-950">Evidence Frames</h2>
        <p className="mt-1 text-sm text-slate-600">
          Review the frames that support each safety finding.
        </p>
      </div>

      <div className="grid gap-4">
        {frames.map((frame) => (
          <FrameEvidenceCard
            key={frame.id}
            frame={frame}
            showExplanation={showExplanations}
            isHighlighted={frame.id === highlightedFrameId}
          />
        ))}
      </div>
    </section>
  );
}
