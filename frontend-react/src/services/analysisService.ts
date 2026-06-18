import { mockAnalysisByMediaId, mockMediaLibrary, sampleMedia } from '../data/mockAnalysis';
import type { AnalysisResult, AnalysisSettings, MediaItem } from '../types/analysis';

const MOCK_DELAY_MS = 150;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

type RunMockAnalysisInput = {
  query: string;
  media: MediaItem;
  settings: AnalysisSettings;
};

function cloneResult(result: AnalysisResult): AnalysisResult {
  return {
    ...result,
    media: { ...result.media },
    frames: result.frames.map((frame) => ({
      ...frame,
      violations: frame.violations.map((violation) => ({
        ...violation,
        evidence: violation.evidence ? { ...violation.evidence } : undefined,
      })),
      detections: frame.detections.map((detection) => ({ ...detection })),
      technicalEvidence: { ...frame.technicalEvidence },
    })),
  };
}

export function buildMockAnalysisResult({
  query,
  media,
  settings,
}: RunMockAnalysisInput): AnalysisResult {
  const template = mockAnalysisByMediaId[media.id] ?? mockAnalysisByMediaId[sampleMedia.id];
  const result = cloneResult(template);
  const limitedFrames = result.frames.slice(0, settings.topK).map((frame) => {
    if (media.source === 'local' && media.type === 'image' && media.previewUrl) {
      return {
        ...frame,
        imageUrl: media.previewUrl,
        visualVariant: 'maintenance' as const,
      };
    }

    return frame;
  });

  return {
    ...result,
    query: query.trim() || result.query,
    media: {
      ...media,
      status: 'completed',
    },
    framesAnalyzed: limitedFrames.length,
    frames: limitedFrames,
    generatedAt: new Date().toISOString(),
    settings,
  };
}

// Future integration point: replace or extend this with calls to a Python/FastAPI
// service that wraps the SafeTrace pipeline. Components should continue receiving
// typed AnalysisResult data through this service boundary.
export async function runMockAnalysis({
  query,
  media,
  settings,
}: RunMockAnalysisInput): Promise<AnalysisResult> {
  await delay(MOCK_DELAY_MS);
  return buildMockAnalysisResult({ query, media, settings });
}

// Future integration point: fetch available uploaded media from the backend once
// media storage and upload endpoints exist.
export async function getMockMediaLibrary(): Promise<MediaItem[]> {
  await delay(250);
  return mockMediaLibrary;
}
