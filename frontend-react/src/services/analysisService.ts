import { mockAnalysisByMediaId, mockMediaLibrary, sampleMedia } from '../data/mockAnalysis';
import type {
  AnalysisJob,
  AnalysisRequest,
  AnalysisResult,
  AnalysisSettings,
  BackendHealth,
  Detection,
  DeviceMode,
  JobStatus,
  MediaItem,
  MediaType,
  Severity,
  SystemStatus,
  Violation,
} from '../types/analysis';

const MOCK_DELAY_MS = 150;
const DEFAULT_API_BASE = '/api';

export const SAFETRACE_API_BASE = normalizeApiBase(
  import.meta.env.VITE_SAFETRACE_API_BASE || DEFAULT_API_BASE,
);
export const SAFETRACE_REQUIRE_BACKEND = parseEnvBoolean(
  import.meta.env.VITE_SAFETRACE_REQUIRE_BACKEND,
  true,
);
export const SAFETRACE_ENABLE_PREVIEW_MODE = parseEnvBoolean(
  import.meta.env.VITE_SAFETRACE_ENABLE_PREVIEW_MODE,
  false,
);

type RunMockAnalysisInput = {
  query: string;
  media: MediaItem;
  settings: AnalysisSettings;
};

type BackendMedia = {
  id: string;
  name: string;
  type: MediaType;
  sizeBytes: number;
  durationSeconds?: number | null;
};

type BackendViolation = {
  id: string;
  name: string;
  severity: string;
  confidence: number;
  description: string;
};

type BackendGroupedViolation = {
  id: string;
  name: string;
  severity: string;
  description: string;
  affectedFrames: Array<{
    frameId: string;
    frameNumber: number;
    timestamp: string;
    confidence: number;
  }>;
  confidenceMin: number;
  confidenceMax: number;
};

type BackendFrameResult = {
  id: string;
  frameNumber: number;
  timestamp: string;
  queryRelevance: number;
  status: 'violations_detected' | 'no_violations';
  imageUrl?: string | null;
  imageMessage?: string | null;
  violations: BackendViolation[];
  technicalEvidence: Record<string, unknown>;
};

type BackendAnalysisResult = {
  jobId: string;
  status: 'completed';
  media: BackendMedia;
  query: string;
  summary: {
    framesAnalyzed: number;
    framesWithViolations: number;
    uniqueViolationTypes: number;
    highestSeverity?: string | null;
    summaryText: string;
  };
  violations: BackendGroupedViolation[];
  frames: BackendFrameResult[];
  technicalDetails?: Record<string, unknown> | null;
};

function parseEnvBoolean(value: string | boolean | undefined, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
}

function normalizeApiBase(value: string): string {
  return value.trim().replace(/\/+$/, '') || DEFAULT_API_BASE;
}

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');
const trimLeadingSlash = (value: string) => value.replace(/^\/+/, '');

function isAbsoluteHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

export function buildApiUrl(path: string): string {
  const base = trimTrailingSlash(SAFETRACE_API_BASE || DEFAULT_API_BASE);
  const cleanPath = trimLeadingSlash(path);
  return `${base}/${cleanPath}`;
}

export function getApiOrigin(): string {
  if (isAbsoluteHttpUrl(SAFETRACE_API_BASE)) {
    return new URL(SAFETRACE_API_BASE).origin;
  }
  return window.location.origin;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...options,
    headers: {
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    let message = `SafeTrace API returned ${response.status}`;
    try {
      const body = await response.json();
      message = body?.detail?.message || body?.message || message;
    } catch {
      const text = await response.text();
      message = text || message;
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

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

function toSeverity(value: string | undefined): Severity {
  const normalized = (value || '').toLowerCase();
  if (normalized === 'high' || normalized === 'critical') return 'High';
  if (normalized === 'medium') return 'Medium';
  return 'Low';
}

function toMediaType(value: string | undefined): MediaType {
  if (value === 'video' || value === 'image') return value;
  return 'unknown';
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return 'Unknown size';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function formatDuration(seconds?: number | null): string | undefined {
  if (!seconds || !Number.isFinite(seconds)) return undefined;
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function getDetectionBBox(value: unknown): [number, number, number, number] {
  if (Array.isArray(value) && value.length >= 4) {
    const [x, y, width, height] = value.map(Number);
    if ([x, y, width, height].every(Number.isFinite)) {
      return [x, y, width, height];
    }
  }
  return [0, 0, 0, 0];
}

function getDetectionValue(detection: unknown, key: string): unknown {
  if (typeof detection === 'object' && detection !== null && key in detection) {
    return (detection as Record<string, unknown>)[key];
  }
  return undefined;
}

function mapDetections(frame: BackendFrameResult): Detection[] {
  const rawDetections = frame.technicalEvidence?.detections;
  if (!Array.isArray(rawDetections)) return [];

  return rawDetections.map((detection, index) => {
    const label = String(getDetectionValue(detection, 'label') || getDetectionValue(detection, 'name') || 'detection');
    const confidence = Number(getDetectionValue(detection, 'confidence') || 0);

    return {
      id: `${frame.id}-detection-${index}`,
      label,
      confidence: Number.isFinite(confidence) ? confidence : 0,
      bbox: getDetectionBBox(getDetectionValue(detection, 'bbox')),
      source: 'detector',
    };
  });
}

function mapViolations(violations: BackendViolation[]): Violation[] {
  return violations.map((violation) => ({
    id: violation.id,
    type: violation.id,
    name: violation.name,
    severity: toSeverity(violation.severity),
    description: violation.description,
    confidence: violation.confidence,
  }));
}

function mapBackendResult(result: BackendAnalysisResult): AnalysisResult {
  const mediaName = result.media.name || result.media.id || 'Selected media';

  return {
    jobId: result.jobId,
    status: result.status,
    id: result.jobId,
    query: result.query,
    media: {
      id: result.media.id || `media-${result.jobId}`,
      filename: mediaName,
      type: toMediaType(result.media.type),
      sizeLabel: formatBytes(result.media.sizeBytes),
      duration: formatDuration(result.media.durationSeconds),
      uploadedAt: new Date().toISOString(),
      status: 'completed',
      source: 'local',
    },
    summary: result.summary,
    violations: result.violations,
    framesAnalyzed: result.summary.framesAnalyzed,
    generatedAt: new Date().toISOString(),
    summaryText: result.summary.summaryText,
    settings: undefined,
    frames: result.frames.map((frame) => ({
      id: frame.id,
      frameNumber: frame.frameNumber,
      timestamp: frame.timestamp,
      internalFilename: String(frame.technicalEvidence?.sourceFramePath || frame.id),
      queryRelevance: frame.queryRelevance,
      imageUrl: resolveBackendMediaUrl(frame.imageUrl ?? null) ?? undefined,
      imageMessage: frame.imageMessage ?? undefined,
      evidenceImageRequired: Boolean(frame.imageUrl || frame.imageMessage),
      explanation: typeof frame.technicalEvidence?.explanation === 'string' ? frame.technicalEvidence.explanation : undefined,
      violations: mapViolations(frame.violations),
      detections: mapDetections(frame),
      technicalEvidence: frame.technicalEvidence,
    })),
    technicalDetails: result.technicalDetails,
  };
}

function deviceToApiMode(device: DeviceMode): 'auto' | 'cpu' | 'cuda' {
  if (device === 'CPU') return 'cpu';
  if (device === 'GPU') return 'cuda';
  return 'auto';
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
      return { ...frame, imageUrl: media.previewUrl, evidenceImageRequired: false };
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

export async function checkBackendHealth(): Promise<BackendHealth> {
  return apiFetch<BackendHealth>('health');
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return apiFetch<SystemStatus>('system/status');
}

export async function runBackendAnalysis(request: AnalysisRequest): Promise<AnalysisJob> {
  const formData = new FormData();
  formData.append('file', request.file);
  formData.append('query', request.query);
  formData.append('fps', String(request.fps));
  formData.append('topK', String(request.topK));
  formData.append('enableVlm', String(request.enableVlm));
  formData.append('device', deviceToApiMode(request.device));

  return apiFetch<AnalysisJob>('analyze', {
    method: 'POST',
    body: formData,
  });
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`jobs/${encodeURIComponent(jobId)}`);
}

export async function getJobResult(jobId: string): Promise<AnalysisResult> {
  const result = await apiFetch<BackendAnalysisResult>(`jobs/${encodeURIComponent(jobId)}/result`);
  return mapBackendResult(result);
}

export async function getTechnicalReport(jobId: string): Promise<AnalysisResult> {
  const result = await apiFetch<BackendAnalysisResult>(`reports/${encodeURIComponent(jobId)}/technical-json`);
  return mapBackendResult(result);
}

export async function deleteJob(jobId: string): Promise<void> {
  await apiFetch(`jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
  });
}

export function resolveBackendMediaUrl(imageUrl: string | null): string | null {
  if (!imageUrl) return null;
  if (/^(https?:|blob:|data:)/i.test(imageUrl)) return imageUrl;

  const base = trimTrailingSlash(SAFETRACE_API_BASE || DEFAULT_API_BASE);
  const isAbsoluteApiBase = isAbsoluteHttpUrl(base);
  const origin = getApiOrigin();

  if (imageUrl.startsWith('/api/')) {
    return isAbsoluteApiBase ? `${origin}${imageUrl}` : imageUrl;
  }
  if (imageUrl.startsWith('/media/')) {
    return `${base}${imageUrl}`;
  }
  if (imageUrl.startsWith('/')) {
    return isAbsoluteApiBase ? `${origin}${imageUrl}` : imageUrl;
  }

  const cleanPath = trimLeadingSlash(imageUrl);
  if (cleanPath.startsWith('api/')) {
    return isAbsoluteApiBase ? `${origin}/${cleanPath}` : `/${cleanPath}`;
  }
  return `${base}/${cleanPath}`;
}
