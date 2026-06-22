export type Severity = 'High' | 'Medium' | 'Low';

export type MediaType = 'video' | 'image' | 'unknown';

export type MediaStatus = 'ready' | 'processing' | 'completed' | 'error';

export type DeviceMode = 'Auto' | 'CPU' | 'GPU';

export type BackendConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

export type AnalysisSettings = {
  fps: number;
  topK: number;
  vlmExplanations: boolean;
  deviceMode: DeviceMode;
};

export type Violation = {
  id: string;
  type: string;
  name: string;
  severity: Severity;
  description: string;
  confidence: number;
  evidence?: Record<string, unknown>;
};

export type Detection = {
  id: string;
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  source: 'detector' | 'rule-engine' | 'mock';
};

export type FrameResult = {
  id: string;
  frameNumber: number;
  timestamp: string;
  internalFilename: string;
  queryRelevance: number;
  queryRelevanceScore?: number;
  score?: number;
  imageUrl?: string;
  imageMessage?: string;
  evidenceImageRequired?: boolean;
  visualVariant?: 'worksite' | 'loading-bay' | 'maintenance';
  explanation?: string;
  violations: Violation[];
  detections: Detection[];
  technicalEvidence: Record<string, unknown>;
};

export type Annotation = {
  id: string;
  mediaId: string;
  type: 'bbox' | 'note';
  label?: string;
  note?: string;
  bbox?: [number, number, number, number];
  color?: string;
  createdAt: string;
};

export type MediaItem = {
  id: string;
  filename: string;
  type: MediaType;
  sizeLabel: string;
  duration?: string;
  uploadedAt: string;
  status: MediaStatus;
  source?: 'sample' | 'local';
  previewUrl?: string;
};

export type BackendHealth = {
  status: 'ok';
  api: 'safetrace-local';
  version: string;
  offline: boolean;
};

export type BackendModelStatus = {
  status: 'ready' | 'missing' | 'unavailable';
  path?: string | null;
  message?: string | null;
};

export type SystemStatus = {
  device: string;
  gpuAvailable: boolean;
  models: Record<string, BackendModelStatus>;
  limits?: Record<string, unknown>;
  queue?: Record<string, unknown>;
};

export type AnalysisRequest = {
  file: File;
  query: string;
  fps: number;
  topK: number;
  enableVlm: boolean;
  device: DeviceMode;
};

export type BatchAnalysisRequest = {
  files: File[];
  query: string;
  fps: number;
  topK: number;
  enableVlm: boolean;
  device: DeviceMode;
};

export type AnalysisJob = {
  jobId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
};

export type JobStatus = AnalysisJob & {
  progress: number;
  currentStep: string;
  error?: string | null;
  metrics?: Record<string, unknown>;
};

export type BatchAcceptedFile = {
  originalFilename: string;
  filename: string;
  sizeBytes: number;
  mediaType: 'video';
  jobId: string;
  status: AnalysisJob['status'];
  error?: string | null;
};

export type BatchRejectedFile = {
  filename: string;
  reason: string;
};

export type BatchStatus = {
  batchId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'partial' | 'cancelled';
  sourceFilename: string;
  acceptedFiles: BatchAcceptedFile[];
  rejectedFiles: BatchRejectedFile[];
  jobIds: string[];
  statusCounts: Record<string, number>;
  createdAt: string;
  updatedAt: string;
};

export type ViolationEvent = {
  id: string;
  type: string;
  name: string;
  severity: Severity;
  description: string;
  startTimestamp: string;
  endTimestamp: string;
  representativeConfidence: number;
  confidenceMin: number;
  confidenceMax: number;
  supportingFrameCount: number;
  supportingFrames: Array<{
    frameId: string;
    frameNumber: number;
    timestamp: string;
    confidence: number;
    imageUrl?: string | null;
  }>;
};

export type AnalysisResult = {
  jobId?: string;
  status?: 'completed';
  id: string;
  query: string;
  media: MediaItem;
  summary?: {
    framesAnalyzed: number;
    framesWithViolations: number;
    uniqueViolationTypes: number;
    highestSeverity?: string | null;
    summaryText: string;
    potentialEventCount?: number;
    eventTypes?: string[];
    overallConfidence?: number;
    keyEvents?: unknown[];
  };
  violations?: Array<{
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
  }>;
  framesAnalyzed: number;
  generatedAt: string;
  summaryText?: string;
  settings?: AnalysisSettings;
  events?: ViolationEvent[];
  frames: FrameResult[];
  technicalDetails?: Record<string, unknown> | null;
};
