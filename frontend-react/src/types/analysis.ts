export type Severity = 'High' | 'Medium' | 'Low';

export type MediaType = 'video' | 'image' | 'unknown';

export type MediaStatus = 'ready' | 'processing' | 'completed' | 'error';

export type DeviceMode = 'Auto' | 'CPU' | 'GPU';

export type BackendConnectionState = 'live' | 'connecting' | 'connected' | 'disconnected' | 'incompatible' | 'error';

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

export type RuntimeCheckStatus = 'ready' | 'available' | 'warning' | 'missing' | 'unavailable' | 'disabled' | 'loading';

export type RuntimeCheck = {
  status: RuntimeCheckStatus | string;
  message?: string | null;
  path?: string | null;
  actionHint?: string | null;
  details?: Record<string, unknown>;
};

export type SystemRuntimeStatus = {
  backend?: Record<string, unknown>;
  python?: {
    executable?: string;
    version?: string;
  };
  workingDirectory?: string;
  device?: {
    configured?: string;
    gpuAvailable?: boolean;
  };
  models?: Record<string, BackendModelStatus>;
  chat?: {
    enabled?: boolean;
    available?: boolean;
    state?: string;
    status?: string;
    provider?: string;
    model?: string | null;
    model_path?: string | null;
    model_exists?: boolean | null;
    runtime_available?: boolean | null;
    speed_profile?: string | null;
    warmup_on_open?: boolean | null;
    reason?: string | null;
    action_hint?: string | null;
    message?: string | null;
  };
  openmp?: {
    status?: string;
    kmpDuplicateLibOk?: boolean;
    rawKmpDuplicateLibOk?: string | null;
    ompNumThreads?: string | null;
    message?: string | null;
    actionHint?: string | null;
  };
  uploadLimits?: Record<string, unknown>;
  batchLimits?: Record<string, unknown>;
  jobStorePath?: string;
};

export type SystemPreflightStatus = {
  checks?: Record<string, RuntimeCheck>;
  summary?: {
    ready?: number;
    warnings?: number;
  };
};

export type SystemStatus = {
  app_version?: string | null;
  backend_version?: string | null;
  build_mode?: string | null;
  runtime_layout?: string | null;
  device: string;
  gpuAvailable: boolean;
  models: Record<string, BackendModelStatus>;
  limits?: Record<string, unknown>;
  queue?: Record<string, unknown>;
  runtime?: SystemRuntimeStatus;
  preflight?: SystemPreflightStatus;
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
