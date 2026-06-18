import type { AnalysisResult, FrameResult, MediaItem, Severity, Violation } from '../types/analysis';

export const sampleMedia: MediaItem = {
  id: 'media-2026-06-18-113842',
  filename: 'video_2026-06-18_11-38-42.mp4',
  type: 'video',
  sizeLabel: '4.25 MB',
  duration: '00:01:05',
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
  frameNumber: number,
  type: string,
  name: string,
  severity: Severity,
  description: string,
  confidence: number,
  evidence: Record<string, unknown>,
): Violation {
  return {
    id: `frame-${frameNumber}-${type}`,
    type,
    name,
    severity,
    description,
    confidence,
    evidence,
  };
}

function createSafetyViolation(
  frameNumber: number,
  type: 'helmet_missing' | 'seatbelt_missing',
  confidence: number,
): Violation {
  const isHelmet = type === 'helmet_missing';

  return createViolation(
    frameNumber,
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
  frameNumber: number,
  type: 'high_vis_missing' | 'restricted_zone_entry',
  confidence: number,
): Violation {
  const isVest = type === 'high_vis_missing';

  return createViolation(
    frameNumber,
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
    frameNumber: 1,
    timestamp: '00:00:46',
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00046.jpg',
    queryRelevanceScore: 0.059,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000046_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Visual evidence shows a worker in the active area with head and torso regions detected, but no matching helmet or seatbelt overlap.',
    violations: [createSafetyViolation(1, 'helmet_missing', 1), createSafetyViolation(1, 'seatbelt_missing', 1)],
    detections: [
      { id: 'd-1-person', label: 'person', confidence: 0.99, bbox: [34, 22, 31, 64], source: 'detector' },
      { id: 'd-1-head', label: 'head', confidence: 0.96, bbox: [43, 16, 12, 14], source: 'detector' },
      { id: 'd-1-torso', label: 'torso', confidence: 0.93, bbox: [39, 34, 22, 31], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['helmet_missing', 'seatbelt_missing'],
      iou: { headHelmet: 0.04, torsoSeatbelt: 0.08 },
      thresholds: { headHelmetMinimum: 0.2, torsoSeatbeltMinimum: 0.2 },
      backendLabels: ['person', 'head', 'torso'],
    },
  },
  {
    id: 'frame-002',
    frameNumber: 2,
    timestamp: '00:00:16',
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00016.jpg',
    queryRelevanceScore: 0.056,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000016_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'The selected frame contains a relevant worker pose and repeated missing protective equipment indicators.',
    violations: [createSafetyViolation(2, 'helmet_missing', 0.93), createSafetyViolation(2, 'seatbelt_missing', 0.96)],
    detections: [
      { id: 'd-2-person', label: 'person', confidence: 0.97, bbox: [18, 19, 30, 66], source: 'detector' },
      { id: 'd-2-head', label: 'head', confidence: 0.91, bbox: [27, 14, 12, 15], source: 'detector' },
      { id: 'd-2-torso', label: 'torso', confidence: 0.89, bbox: [22, 34, 22, 33], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['helmet_missing', 'seatbelt_missing'],
      iou: { headHelmet: 0.11, torsoSeatbelt: 0.05 },
      thresholds: { headHelmetMinimum: 0.2, torsoSeatbeltMinimum: 0.2 },
      backendLabels: ['person', 'head', 'torso'],
    },
  },
  {
    id: 'frame-003',
    frameNumber: 3,
    timestamp: '00:00:19',
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00019.jpg',
    queryRelevanceScore: 0.052,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000019_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Protective equipment evidence remains below the configured overlap thresholds for this worker.',
    violations: [createSafetyViolation(3, 'helmet_missing', 0.87), createSafetyViolation(3, 'seatbelt_missing', 0.92)],
    detections: [
      { id: 'd-3-person', label: 'person', confidence: 0.94, bbox: [52, 24, 27, 61], source: 'detector' },
      { id: 'd-3-head', label: 'head', confidence: 0.88, bbox: [60, 18, 11, 13], source: 'detector' },
      { id: 'd-3-torso', label: 'torso', confidence: 0.86, bbox: [56, 37, 19, 29], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['helmet_missing', 'seatbelt_missing'],
      iou: { headHelmet: 0.17, torsoSeatbelt: 0.13 },
      thresholds: { headHelmetMinimum: 0.2, torsoSeatbeltMinimum: 0.2 },
      backendLabels: ['person', 'head', 'torso'],
    },
  },
  {
    id: 'frame-004',
    frameNumber: 4,
    timestamp: '00:00:21',
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00021.jpg',
    queryRelevanceScore: 0.041,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000021_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'Helmet and seatbelt detections overlap the expected body regions, so this frame is clear for the current query.',
    violations: [],
    detections: [
      { id: 'd-4-person', label: 'person', confidence: 0.92, bbox: [38, 22, 27, 61], source: 'detector' },
      { id: 'd-4-helmet', label: 'helmet', confidence: 0.9, bbox: [45, 16, 11, 12], source: 'detector' },
      { id: 'd-4-seatbelt', label: 'seatbelt', confidence: 0.84, bbox: [42, 39, 17, 12], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: [],
      iou: { headHelmet: 0.39, torsoSeatbelt: 0.31 },
      thresholds: { headHelmetMinimum: 0.2, torsoSeatbeltMinimum: 0.2 },
      backendLabels: ['person', 'helmet', 'seatbelt'],
    },
  },
  {
    id: 'frame-005',
    frameNumber: 5,
    timestamp: '00:00:33',
    internalFilename: 'tmp_frames/video_2026-06-18_11-38-42_frame_00033.jpg',
    queryRelevanceScore: 0.048,
    imageUrl: '/sample-evidence/video_2026-06-18_11-38-42_000033_annotated.jpg',
    evidenceImageRequired: true,
    visualVariant: 'worksite',
    explanation: 'The worker remains relevant to the query and both protective equipment rules are triggered.',
    violations: [createSafetyViolation(5, 'helmet_missing', 0.91), createSafetyViolation(5, 'seatbelt_missing', 0.94)],
    detections: [
      { id: 'd-5-person', label: 'person', confidence: 0.95, bbox: [25, 20, 32, 64], source: 'detector' },
      { id: 'd-5-head', label: 'head', confidence: 0.9, bbox: [34, 15, 12, 14], source: 'detector' },
      { id: 'd-5-torso', label: 'torso', confidence: 0.88, bbox: [29, 35, 23, 31], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['helmet_missing', 'seatbelt_missing'],
      iou: { headHelmet: 0.09, torsoSeatbelt: 0.1 },
      thresholds: { headHelmetMinimum: 0.2, torsoSeatbeltMinimum: 0.2 },
      backendLabels: ['person', 'head', 'torso'],
    },
  },
];

const loadingBayFrames: FrameResult[] = [
  {
    id: 'loading-frame-001',
    frameNumber: 1,
    timestamp: '00:00:12',
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00012.jpg',
    queryRelevanceScore: 0.071,
    visualVariant: 'loading-bay',
    explanation: 'A worker is detected inside the loading path while the restricted zone boundary is active.',
    violations: [createLoadingBayViolation(1, 'restricted_zone_entry', 0.98)],
    detections: [
      { id: 'lb-1-person', label: 'person', confidence: 0.98, bbox: [45, 26, 22, 56], source: 'detector' },
      { id: 'lb-1-zone', label: 'restricted_zone', confidence: 0.91, bbox: [28, 18, 58, 70], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['restricted_zone_entry'],
      zoneOverlap: 0.74,
      thresholds: { restrictedZoneOverlapMinimum: 0.5 },
      backendLabels: ['person', 'restricted_zone'],
    },
  },
  {
    id: 'loading-frame-002',
    frameNumber: 2,
    timestamp: '00:00:44',
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00044.jpg',
    queryRelevanceScore: 0.064,
    visualVariant: 'loading-bay',
    explanation: 'The person is inside a monitored loading area and high-visibility vest evidence is weak.',
    violations: [
      createLoadingBayViolation(2, 'restricted_zone_entry', 0.94),
      createLoadingBayViolation(2, 'high_vis_missing', 0.86),
    ],
    detections: [
      { id: 'lb-2-person', label: 'person', confidence: 0.96, bbox: [22, 24, 26, 58], source: 'detector' },
      { id: 'lb-2-zone', label: 'restricted_zone', confidence: 0.88, bbox: [12, 18, 62, 68], source: 'detector' },
      { id: 'lb-2-vest', label: 'vest', confidence: 0.38, bbox: [27, 40, 17, 21], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['restricted_zone_entry', 'high_vis_missing'],
      zoneOverlap: 0.68,
      vestCoverage: 0.18,
      thresholds: { restrictedZoneOverlapMinimum: 0.5, vestCoverageMinimum: 0.35 },
      backendLabels: ['person', 'restricted_zone', 'vest'],
    },
  },
  {
    id: 'loading-frame-003',
    frameNumber: 3,
    timestamp: '00:01:03',
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00103.jpg',
    queryRelevanceScore: 0.051,
    visualVariant: 'loading-bay',
    explanation: 'The area is visible and relevant, but the person is outside the restricted boundary.',
    violations: [],
    detections: [
      { id: 'lb-3-person', label: 'person', confidence: 0.9, bbox: [8, 28, 21, 55], source: 'detector' },
      { id: 'lb-3-zone', label: 'restricted_zone', confidence: 0.87, bbox: [42, 20, 48, 66], source: 'detector' },
      { id: 'lb-3-vest', label: 'vest', confidence: 0.81, bbox: [12, 43, 13, 20], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: [],
      zoneOverlap: 0.12,
      vestCoverage: 0.46,
      thresholds: { restrictedZoneOverlapMinimum: 0.5, vestCoverageMinimum: 0.35 },
      backendLabels: ['person', 'restricted_zone', 'vest'],
    },
  },
  {
    id: 'loading-frame-004',
    frameNumber: 4,
    timestamp: '00:01:37',
    internalFilename: 'tmp_frames/loading_bay_sample_frame_00137.jpg',
    queryRelevanceScore: 0.047,
    visualVariant: 'loading-bay',
    explanation: 'The worker appears close to the active loading lane with insufficient vest evidence.',
    violations: [createLoadingBayViolation(4, 'high_vis_missing', 0.82)],
    detections: [
      { id: 'lb-4-person', label: 'person', confidence: 0.93, bbox: [62, 26, 20, 53], source: 'detector' },
      { id: 'lb-4-vest', label: 'vest', confidence: 0.35, bbox: [66, 43, 11, 19], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: ['high_vis_missing'],
      vestCoverage: 0.22,
      thresholds: { vestCoverageMinimum: 0.35 },
      backendLabels: ['person', 'vest'],
    },
  },
];

const maintenanceFrames: FrameResult[] = [
  {
    id: 'maintenance-frame-001',
    frameNumber: 1,
    timestamp: '00:00:00',
    internalFilename: 'tmp_frames/maintenance_zone_reference.jpg',
    queryRelevanceScore: 0.044,
    visualVariant: 'maintenance',
    explanation: 'The reference image shows controlled access equipment and no matching safety issue for the current query.',
    violations: [],
    detections: [
      { id: 'mz-1-person', label: 'technician', confidence: 0.89, bbox: [36, 26, 25, 56], source: 'detector' },
      { id: 'mz-1-helmet', label: 'helmet', confidence: 0.86, bbox: [43, 18, 12, 13], source: 'detector' },
      { id: 'mz-1-vest', label: 'vest', confidence: 0.82, bbox: [39, 41, 18, 24], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: [],
      ppeCoverage: { helmet: 0.41, vest: 0.52 },
      thresholds: { helmetCoverageMinimum: 0.2, vestCoverageMinimum: 0.35 },
      backendLabels: ['technician', 'helmet', 'vest'],
    },
  },
  {
    id: 'maintenance-frame-002',
    frameNumber: 2,
    timestamp: '00:00:00',
    internalFilename: 'tmp_frames/maintenance_zone_reference_detail.jpg',
    queryRelevanceScore: 0.038,
    visualVariant: 'maintenance',
    explanation: 'Machine area and worker PPE are visible with no matching violation for this query.',
    violations: [],
    detections: [
      { id: 'mz-2-person', label: 'technician', confidence: 0.87, bbox: [58, 24, 22, 54], source: 'detector' },
      { id: 'mz-2-helmet', label: 'helmet', confidence: 0.84, bbox: [64, 17, 11, 13], source: 'detector' },
      { id: 'mz-2-guard', label: 'machine_guard', confidence: 0.79, bbox: [20, 31, 26, 31], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: [],
      ppeCoverage: { helmet: 0.36, vest: 0.4 },
      thresholds: { helmetCoverageMinimum: 0.2, machineGuardVisible: true },
      backendLabels: ['technician', 'helmet', 'machine_guard'],
    },
  },
  {
    id: 'maintenance-frame-003',
    frameNumber: 3,
    timestamp: '00:00:00',
    internalFilename: 'tmp_frames/maintenance_zone_reference_wide.jpg',
    queryRelevanceScore: 0.032,
    visualVariant: 'maintenance',
    explanation: 'The wider inspection view is relevant but does not show a matching safety violation.',
    violations: [],
    detections: [
      { id: 'mz-3-person', label: 'technician', confidence: 0.83, bbox: [17, 24, 20, 55], source: 'detector' },
      { id: 'mz-3-sign', label: 'safety_sign', confidence: 0.76, bbox: [68, 16, 15, 20], source: 'detector' },
    ],
    technicalEvidence: {
      rawViolationTypes: [],
      safetySignVisible: true,
      backendLabels: ['technician', 'safety_sign'],
    },
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
  },
  [loadingBayMedia.id]: {
    id: 'analysis-loading-bay-001',
    query: 'worker inside restricted loading bay',
    media: loadingBayMedia,
    framesAnalyzed: loadingBayFrames.length,
    generatedAt: '2026-06-18T12:05:11+08:00',
    summaryText: 'SafeTrace found restricted-zone activity and a high-visibility vest issue in the selected loading bay footage.',
    frames: loadingBayFrames,
  },
  [maintenanceMedia.id]: {
    id: 'analysis-maintenance-001',
    query: 'worker without helmet',
    media: maintenanceMedia,
    framesAnalyzed: maintenanceFrames.length,
    generatedAt: '2026-06-18T12:06:07+08:00',
    summaryText: 'No matching safety violations were detected in the selected maintenance reference image.',
    frames: maintenanceFrames,
  },
};