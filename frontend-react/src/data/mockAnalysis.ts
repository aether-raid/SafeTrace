import type { AnalysisResult, FrameResult, MediaItem, Severity, Violation } from '../types/analysis';

export const sampleMedia: MediaItem = {
  id: 'media-2026-06-18-113842',
  filename: 'video_2026-06-18_11-38-42.mp4',
  type: 'video',
  sizeLabel: '4.25 MB',
  duration: '00:01:05',
  durationSeconds: 65,
  uploadedAt: '2026-06-18T11:38:42+08:00',
  status: 'ready',
  source: 'sample',
};

export const loadingBayMedia: MediaItem = {
  id: 'media-sample-loading-bay',
  filename: 'loading_bay_sample.mp4',
  type: 'video',
  sizeLabel: '7.80 MB',
  duration: '00:02:18',
  durationSeconds: 138,
  uploadedAt: '2026-06-17T16:25:08+08:00',
  status: 'completed',
  source: 'sample',
};

export const maintenanceMedia: MediaItem = {
  id: 'media-sample-maintenance',
  filename: 'maintenance_zone_reference.jpg',
  type: 'image',
  sizeLabel: '1.14 MB',
  uploadedAt: '2026-06-15T09:12:44+08:00',
  status: 'ready',
  source: 'sample',
};

function createViolation(
  frameIndex: number,
  type: string,
  name: string,
  severity: Severity,
  description: string,
  confidence: number,
  evidence: Record<string, unknown>,
): Violation {
  return {
    id: `frame-${frameIndex}-${type}`,
    type,
    name,
    severity,
    description,
    confidence,
    evidence,
  };
}

function createSafetyViolation(
  frameIndex: number,
  type: 'helmet_missing' | 'seatbelt_missing',
  confidence: number,
): Violation {
  const isHelmet = type === 'helmet_missing';
  return createViolation(
    frameIndex,
    type,
    isHelmet ? 'Missing Helmet' : 'Missing Seatbelt',
    'High',
    isHelmet
      ? 'Worker head detected without overlapping helmet.'
      : 'Person torso detected without an overlapping seatbelt.',
    confidence,
    {
      rule: type,
      threshold: 0.2,
      measuredOverlap: isHelmet ? 0.04 : 0.08,
      source: 'preview-rule-engine',
    },
  );
}

function createLoadingBayViolation(
  frameIndex: number,
  type: 'high_vis_missing' | 'restricted_zone_entry',
  confidence: number,
): Violation {
  const isVest = type === 'high_vis_missing';
  return createViolation(
    frameIndex,
    type,
    isVest ? 'Missing High-Visibility Vest' : 'Restricted Zone Entry',
    isVest ? 'Medium' : 'High',
    isVest
      ? 'Worker detected in loading area without a visible high-visibility vest.'
      : 'Person detected inside a marked forklift operating zone.',
    confidence,
    {
      rule: type,
      zoneOverlap: isVest ? 0.18 : 0.74,
      threshold: isVest ? 0.35 : 0.5,
      source: 'preview-rule-engine',
    },
  );
}

const worksiteFrames: FrameResult[] = [
  {
    id: 'frame-001',
    frameIndex: 46,
    timestamp: '00:00:46',
    timestampSeconds: 46,
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00046.jpg',
    score: 0.059,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000046_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Visual evidence shows a worker in the active area with head and torso regions detected, but no matching helmet or seatbelt overlap.',
    violations: [createSafetyViolation(46, 'helmet_missing', 1), createSafetyViolation(46, 'seatbelt_missing', 1)],
    detections: [
      { id: 'd-46-person', label: 'person', confidence: 0.99, bbox: [34, 22, 31, 64], source: 'detector' },
      { id: 'd-46-head', label: 'head', confidence: 0.96, bbox: [43, 16, 12, 14], source: 'detector' },
      { id: 'd-46-torso', label: 'torso', confidence: 0.93, bbox: [39, 34, 22, 31], source: 'detector' },
    ],
  },
  {
    id: 'frame-002',
    frameIndex: 16,
    timestamp: '00:00:16',
    timestampSeconds: 16,
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00016.jpg',
    score: 0.056,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000016_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'The selected frame contains a relevant worker pose and repeated missing protective equipment indicators.',
    violations: [createSafetyViolation(16, 'helmet_missing', 0.93), createSafetyViolation(16, 'seatbelt_missing', 0.96)],
    detections: [
      { id: 'd-16-person', label: 'person', confidence: 0.97, bbox: [18, 19, 30, 66], source: 'detector' },
      { id: 'd-16-head', label: 'head', confidence: 0.91, bbox: [27, 14, 12, 15], source: 'detector' },
      { id: 'd-16-torso', label: 'torso', confidence: 0.89, bbox: [22, 34, 22, 33], source: 'detector' },
    ],
  },
  {
    id: 'frame-003',
    frameIndex: 19,
    timestamp: '00:00:19',
    timestampSeconds: 19,
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00019.jpg',
    score: 0.052,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000019_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Protective equipment evidence remains below the configured overlap thresholds for this worker.',
    violations: [createSafetyViolation(19, 'helmet_missing', 0.87), createSafetyViolation(19, 'seatbelt_missing', 0.92)],
    detections: [
      { id: 'd-19-person', label: 'person', confidence: 0.94, bbox: [52, 24, 27, 61], source: 'detector' },
      { id: 'd-19-head', label: 'head', confidence: 0.88, bbox: [60, 18, 11, 13], source: 'detector' },
      { id: 'd-19-torso', label: 'torso', confidence: 0.86, bbox: [56, 37, 19, 29], source: 'detector' },
    ],
  },
  {
    id: 'frame-004',
    frameIndex: 21,
    timestamp: '00:00:21',
    timestampSeconds: 21,
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00021.jpg',
    score: 0.041,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000021_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Helmet and seatbelt detections overlap the expected body regions, so this frame is clear for the current query.',
    violations: [],
    detections: [
      { id: 'd-21-person', label: 'person', confidence: 0.92, bbox: [38, 22, 27, 61], source: 'detector' },
      { id: 'd-21-helmet', label: 'helmet', confidence: 0.9, bbox: [45, 16, 11, 12], source: 'detector' },
      { id: 'd-21-seatbelt', label: 'seatbelt', confidence: 0.84, bbox: [42, 39, 17, 12], source: 'detector' },
    ],
  },
  {
    id: 'frame-005',
    frameIndex: 33,
    timestamp: '00:00:33',
    timestampSeconds: 33,
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00033.jpg',
    score: 0.048,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000033_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'The worker remains relevant to the query and both protective equipment rules are triggered.',
    violations: [createSafetyViolation(33, 'helmet_missing', 0.91), createSafetyViolation(33, 'seatbelt_missing', 0.94)],
    detections: [
      { id: 'd-33-person', label: 'person', confidence: 0.95, bbox: [25, 20, 32, 64], source: 'detector' },
      { id: 'd-33-head', label: 'head', confidence: 0.9, bbox: [34, 15, 12, 14], source: 'detector' },
      { id: 'd-33-torso', label: 'torso', confidence: 0.88, bbox: [29, 35, 23, 31], source: 'detector' },
    ],
  },
];

const loadingBayFrames: FrameResult[] = [
  {
    id: 'loading-frame-001',
    frameIndex: 12,
    timestamp: '00:00:12',
    timestampSeconds: 12,
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00012.jpg',
    score: 0.071,
    explanation: 'A worker is detected inside the loading path while the restricted zone boundary is active.',
    violations: [createLoadingBayViolation(12, 'restricted_zone_entry', 0.98)],
    detections: [
      { id: 'lb-12-person', label: 'person', confidence: 0.98, bbox: [45, 26, 22, 56], source: 'detector' },
      { id: 'lb-12-zone', label: 'restricted_zone', confidence: 0.91, bbox: [28, 18, 58, 70], source: 'detector' },
    ],
  },
  {
    id: 'loading-frame-002',
    frameIndex: 44,
    timestamp: '00:00:44',
    timestampSeconds: 44,
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00044.jpg',
    score: 0.064,
    explanation: 'The person is inside a monitored loading area and high-visibility vest evidence is weak.',
    violations: [
      createLoadingBayViolation(44, 'restricted_zone_entry', 0.94),
      createLoadingBayViolation(44, 'high_vis_missing', 0.86),
    ],
    detections: [
      { id: 'lb-44-person', label: 'person', confidence: 0.96, bbox: [22, 24, 26, 58], source: 'detector' },
      { id: 'lb-44-zone', label: 'restricted_zone', confidence: 0.88, bbox: [12, 18, 62, 68], source: 'detector' },
      { id: 'lb-44-vest', label: 'vest', confidence: 0.38, bbox: [27, 40, 17, 21], source: 'detector' },
    ],
  },
  {
    id: 'loading-frame-003',
    frameIndex: 63,
    timestamp: '00:01:03',
    timestampSeconds: 63,
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00103.jpg',
    score: 0.051,
    explanation: 'The area is visible and relevant, but the person is outside the restricted boundary.',
    violations: [],
    detections: [
      { id: 'lb-63-person', label: 'person', confidence: 0.9, bbox: [8, 28, 21, 55], source: 'detector' },
      { id: 'lb-63-zone', label: 'restricted_zone', confidence: 0.87, bbox: [42, 20, 48, 66], source: 'detector' },
      { id: 'lb-63-vest', label: 'vest', confidence: 0.81, bbox: [12, 43, 13, 20], source: 'detector' },
    ],
  },
  {
    id: 'loading-frame-004',
    frameIndex: 97,
    timestamp: '00:01:37',
    timestampSeconds: 97,
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00137.jpg',
    score: 0.047,
    explanation: 'The worker appears close to the active loading lane with insufficient vest evidence.',
    violations: [createLoadingBayViolation(97, 'high_vis_missing', 0.82)],
    detections: [
      { id: 'lb-97-person', label: 'person', confidence: 0.93, bbox: [62, 26, 20, 53], source: 'detector' },
      { id: 'lb-97-vest', label: 'vest', confidence: 0.35, bbox: [66, 43, 11, 19], source: 'detector' },
    ],
  },
];

const maintenanceFrames: FrameResult[] = [
  {
    id: 'maintenance-frame-001',
    frameIndex: 1,
    timestamp: '00:00:00',
    timestampSeconds: 0,
    internalFilename: 'tmp_frames/maintenance_zone_reference.jpg',
    score: 0.044,
    explanation: 'The reference image shows controlled access equipment and no matching safety issue for the current query.',
    violations: [],
    detections: [
      { id: 'mz-1-person', label: 'technician', confidence: 0.89, bbox: [36, 26, 25, 56], source: 'detector' },
      { id: 'mz-1-helmet', label: 'helmet', confidence: 0.86, bbox: [43, 18, 12, 13], source: 'detector' },
      { id: 'mz-1-vest', label: 'vest', confidence: 0.82, bbox: [39, 41, 18, 24], source: 'detector' },
    ],
  },
  {
    id: 'maintenance-frame-002',
    frameIndex: 2,
    timestamp: '00:00:00',
    timestampSeconds: 0,
    internalFilename: 'tmp_frames/maintenance_zone_reference_detail.jpg',
    score: 0.038,
    explanation: 'Machine area and worker PPE are visible with no matching violation for this query.',
    violations: [],
    detections: [
      { id: 'mz-2-person', label: 'technician', confidence: 0.87, bbox: [58, 24, 22, 54], source: 'detector' },
      { id: 'mz-2-helmet', label: 'helmet', confidence: 0.84, bbox: [64, 17, 11, 13], source: 'detector' },
      { id: 'mz-2-guard', label: 'machine_guard', confidence: 0.79, bbox: [20, 31, 26, 31], source: 'detector' },
    ],
  },
  {
    id: 'maintenance-frame-003',
    frameIndex: 3,
    timestamp: '00:00:00',
    timestampSeconds: 0,
    internalFilename: 'tmp_frames/maintenance_zone_reference_wide.jpg',
    score: 0.032,
    explanation: 'The wider inspection view is relevant but does not show a matching safety violation.',
    violations: [],
    detections: [
      { id: 'mz-3-person', label: 'technician', confidence: 0.83, bbox: [17, 24, 20, 55], source: 'detector' },
      { id: 'mz-3-sign', label: 'safety_sign', confidence: 0.76, bbox: [68, 16, 15, 20], source: 'detector' },
    ],
  },
];

export const mockMediaLibrary: MediaItem[] = [sampleMedia, loadingBayMedia, maintenanceMedia];

export const mockAnalysisByMediaId: Record<string, AnalysisResult> = {
  [sampleMedia.id]: {
    id: 'analysis-worksite-001',
    query: 'worker without helmet',
    media: sampleMedia,
    framesAnalyzed: worksiteFrames.length,
    generatedAt: '2026-06-18T12:04:18+08:00',
    summaryText: 'SafeTrace found repeated missing helmet and missing seatbelt findings across the most relevant frames.',
    frames: worksiteFrames,
    totalDurationSeconds: 65,
  },
  [loadingBayMedia.id]: {
    id: 'analysis-loading-bay-001',
    query: 'worker inside restricted loading bay',
    media: loadingBayMedia,
    framesAnalyzed: loadingBayFrames.length,
    generatedAt: '2026-06-18T12:05:11+08:00',
    summaryText: 'SafeTrace found restricted-zone activity and a high-visibility vest issue in the selected loading bay footage.',
    frames: loadingBayFrames,
    totalDurationSeconds: 138,
  },
  [maintenanceMedia.id]: {
    id: 'analysis-maintenance-001',
    query: 'worker without helmet',
    media: maintenanceMedia,
    framesAnalyzed: maintenanceFrames.length,
    generatedAt: '2026-06-18T12:06:07+08:00',
    summaryText: 'No matching safety violations were detected in the selected maintenance reference image.',
    frames: maintenanceFrames,
    totalDurationSeconds: 0,
  },
};
