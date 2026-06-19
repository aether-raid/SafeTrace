import { mockAnalysisByMediaId, mockMediaLibrary, sampleMedia } from '../data/mockAnalysis';
import type { AnalysisResult, AnalysisSettings, MediaItem } from '../types/analysis';

const MOCK_DELAY_MS = 150;
const API_BASE = '/api';

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
      violations: frame.violations.map((v) => ({
        ...v,
        evidence: v.evidence ? { ...v.evidence } : undefined,
      })),
      detections: frame.detections.map((d) => ({ ...d })),
    })),
  };
}

export function buildMockAnalysisResult({
  query,
  media,
  settings,
}: RunMockAnalysisInput): AnalysisResult {
  const template = mockAnalysisByMediaId[media.id] ?? mockAnalysisByMediaId[sampleMedia.id];
  if (!template) {
    return {
      id: 'analysis-empty',
      query,
      media,
      framesAnalyzed: 0,
      generatedAt: new Date().toISOString(),
      summaryText: 'No matching safety violations were detected.',
      frames: [],
      settings,
    };
  }
  const result = cloneResult(template);
  const limitedFrames = result.frames.slice(0, settings.topK).map((frame) => {
    if (media.source === 'local' && media.type === 'image' && media.previewUrl) {
      return { ...frame, imageUrl: media.previewUrl };
    }
    return frame;
  });

  return {
    ...result,
    query: query.trim() || result.query,
    media: { ...media, status: 'completed' },
    framesAnalyzed: limitedFrames.length,
    frames: limitedFrames,
    generatedAt: new Date().toISOString(),
    settings,
  };
}

export async function runMockAnalysis(input: RunMockAnalysisInput): Promise<AnalysisResult> {
  await delay(MOCK_DELAY_MS);
  return buildMockAnalysisResult(input);
}

export async function getMockMediaLibrary(): Promise<MediaItem[]> {
  await delay(250);
  return mockMediaLibrary;
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export type ApiAnalysisInput = {
  query: string;
  files: File[];
  fps: number;
  topK: number;
  onSaveStatus?: (status: SaveStatus) => void;
};

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export async function runApiAnalysis({
  query,
  files,
  fps,
  topK,
  onSaveStatus,
}: ApiAnalysisInput): Promise<AnalysisResult> {
  onSaveStatus?.('saving');

  try {
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }
    formData.append('fps', String(fps));

    onSaveStatus?.('saving');
    const ingestRes = await apiFetch<{ uploadId: string; media: MediaItem[]; fps: number }>('/ingest', {
      method: 'POST',
      body: formData,
    });
    onSaveStatus?.('saved');

    onSaveStatus?.('saving');
    const analyzeForm = new FormData();
    analyzeForm.append('query', query);
    analyzeForm.append('k', String(topK));
    analyzeForm.append('upload_id', ingestRes.uploadId);

    const analyzeRes = await apiFetch<{ resultId: string; result: AnalysisResult }>('/analyze', {
      method: 'POST',
      body: analyzeForm,
    });
    onSaveStatus?.('saved');

    const result = analyzeRes.result;
    result.settings = { fps, topK, vlmExplanations: false, deviceMode: 'Auto' };
    result.generatedAt = new Date().toISOString();
    result.media.uploadedAt = new Date().toISOString();

    return result;
  } catch (err) {
    onSaveStatus?.('error');
    throw err;
  }
}

export async function getApiMediaLibrary(): Promise<MediaItem[]> {
  const data = await apiFetch<{ media: MediaItem[] }>('/media');
  return data.media;
}
