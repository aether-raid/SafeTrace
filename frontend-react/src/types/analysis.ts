export type Severity = 'High' | 'Medium' | 'Low';

export type MediaType = 'video' | 'image';

export type MediaStatus = 'ready' | 'processing' | 'completed' | 'error';

export type DeviceMode = 'Auto' | 'CPU' | 'GPU';

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
  queryRelevanceScore: number;
  imageUrl?: string;
  evidenceImageRequired?: boolean;
  visualVariant?: 'worksite' | 'loading-bay' | 'maintenance';
  explanation?: string;
  violations: Violation[];
  detections: Detection[];
  technicalEvidence: Record<string, unknown>;
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

export type AnalysisResult = {
  id: string;
  query: string;
  media: MediaItem;
  framesAnalyzed: number;
  generatedAt: string;
  summaryText?: string;
  settings?: AnalysisSettings;
  frames: FrameResult[];
};
