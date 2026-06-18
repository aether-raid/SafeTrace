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
  frameIndex: number;
  timestamp: string;
  timestampSeconds?: number;
  internalFilename: string;
  score: number;
  imageUrl?: string;
  annotatedUrl?: string;
  explanation?: string;
  violations: Violation[];
  detections: Detection[];
};

export type MediaItem = {
  id: string;
  filename: string;
  type: MediaType;
  sizeLabel: string;
  duration?: string;
  durationSeconds?: number;
  uploadedAt: string;
  status: MediaStatus;
  source?: 'sample' | 'local';
  previewUrl?: string;
  fps?: number;
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
  totalDurationSeconds?: number;
};

export type Annotation = {
  id: string;
  mediaId: string;
  type: 'bbox' | 'note';
  label?: string;
  bbox?: [number, number, number, number];
  note?: string;
  color?: string;
  createdAt: string;
};

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export enum QueryTab {
  SearchVideo = 'search-video',
  SearchEvent = 'search-event',
  SearchPerson = 'search-person',
  SearchObject = 'search-object',
}
