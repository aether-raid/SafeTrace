import { AlertTriangle, ClipboardCheck, Database, RefreshCcw, Server, Trash2, UploadCloud } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AnalysisProgress } from './components/AnalysisProgress';
import { AnalysisSummary } from './components/AnalysisSummary';
import { AnnotationViewer } from './components/AnnotationViewer';
import { AppShell } from './components/AppShell';
import { EvidenceFrames } from './components/EvidenceFrames';
import { MediaLibraryPanel } from './components/MediaLibraryPanel';
import { QueryTabs } from './components/QueryTabs';
import { ReportActions } from './components/ReportActions';
import { SafeTraceAssistant } from './components/SafeTraceAssistant';
import { Sidebar } from './components/Sidebar';
import { StatisticsPanel } from './components/StatisticsPanel';
import { TimelineVisualization } from './components/TimelineVisualization';
import { UploadPanel } from './components/UploadPanel';
import { VideoQueue } from './components/VideoQueue';
import { ViolationSummary } from './components/ViolationSummary';
import { sampleMedia } from './data/mockAnalysis';
import {
  SAFETRACE_API_BASE,
  SAFETRACE_API_BASE_CANDIDATES,
  SAFETRACE_ENABLE_PREVIEW_MODE,
  SAFETRACE_REQUIRE_BACKEND,
  BackendDiscoveryError,
  discoverBackendRuntime,
  getBatchStatus,
  getActiveApiBase,
  getJobResult,
  getJobStatus,
  getMockMediaLibrary,
  runBackendAnalysis,
  runBackendBatchAnalysis,
  runMockAnalysis,
} from './services/analysisService';
import {
  type CachedResultEntry,
  clearCachedResults,
  deleteCachedResult,
  isCacheEntryStale,
  jobCacheKey,
  loadCachedResults,
  mediaCacheKey,
  saveCachedResult,
} from './services/resultCache';
import type {
  AnalysisResult,
  AnalysisSettings,
  BatchStatus,
  BackendConnectionState,
  JobStatus,
  MediaItem,
  SystemStatus,
} from './types/analysis';
import { formatFileSize } from './utils/formatters';
import { SelectedMediaViewer } from './components/SelectedMediaViewer';

const DEFAULT_QUERY = 'worker without helmet';
const ANALYSIS_STEPS = [
  'Preparing selected media',
  'Sampling frames',
  'Matching query against visual evidence',
  'Grouping safety findings',
  'Preparing evidence report',
];
const SAMPLE_QUERY_BY_MEDIA_ID: Record<string, string> = {
  'media-2026-06-18-113842': 'worker without helmet',
  'media-sample-loading-bay': 'worker inside restricted loading bay',
  'media-sample-maintenance': 'worker without helmet',
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function isZipFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.zip') || file.type === 'application/zip';
}

function getMediaTypeForFiles(files: File[]): MediaItem['type'] {
  if (files.length !== 1) return 'unknown';
  const file = files[0];
  if (isZipFile(file)) return 'unknown';
  if (file.type.startsWith('image/')) return 'image';
  return 'video';
}

function getSelectionName(files: File[]): string {
  if (files.length === 1) return files[0].name;
  return `${files.length} selected videos`;
}

function getSelectionSize(files: File[]): string {
  const total = files.reduce((sum, file) => sum + file.size, 0);
  return formatFileSize(total);
}

function App() {
  const previewMode = SAFETRACE_ENABLE_PREVIEW_MODE;
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [mediaLibrary, setMediaLibrary] = useState<MediaItem[]>(previewMode ? [sampleMedia] : []);
  const [selectedMedia, setSelectedMedia] = useState<MediaItem | null>(previewMode ? sampleMedia : null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [settings, setSettings] = useState<AnalysisSettings>({
    fps: 1,
    topK: 5,
    vlmExplanations: false,
    deviceMode: 'Auto',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [highlightedFrameId, setHighlightedFrameId] = useState<string | null>(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAnnotation, setShowAnnotation] = useState(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [hoveredFrameId, setHoveredFrameId] = useState<string | null>(null);
  const [backendState, setBackendState] = useState<BackendConnectionState>('live');
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [backendMessage, setBackendMessage] = useState<string | null>(null);
  const [activeApiBase, setActiveApiBase] = useState(SAFETRACE_API_BASE);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [selectedBatchJobId, setSelectedBatchJobId] = useState<string | null>(null);
  const [batchResultLoadingJobId, setBatchResultLoadingJobId] = useState<string | null>(null);
  const [analysisMode, setAnalysisMode] = useState<'backend' | 'preview' | null>(null);
  const [cachedEntries, setCachedEntries] = useState<Record<string, CachedResultEntry>>({});
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const localFilesRef = useRef<Record<string, File>>({});
  const localFileGroupsRef = useRef<Record<string, File[]>>({});
  const selectedMediaIdRef = useRef<string | null>(selectedMedia?.id ?? null);

  const backendConnected = backendState === 'connected';
  const controlsLocked = SAFETRACE_REQUIRE_BACKEND && !backendConnected && !previewMode;
  const canUsePreview = previewMode && Boolean(selectedMedia);
  const cachedEntryCount = Object.keys(cachedEntries).length;

  useEffect(() => {
    selectedMediaIdRef.current = selectedMedia?.id ?? null;
  }, [selectedMedia?.id]);

  useEffect(() => {
    let isMounted = true;
    loadCachedResults()
      .then((entries) => {
        if (!isMounted) return;
        const next = Object.fromEntries(entries.map((entry) => [entry.cacheKey, entry]));
        setCachedEntries(next);
      })
      .catch(() => {
        if (isMounted) {
          setCacheMessage('Local result cache could not be opened in this browser session.');
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  function rememberCachedEntry(entry: CachedResultEntry) {
    setCachedEntries((current) => ({ ...current, [entry.cacheKey]: entry }));
    void saveCachedResult(entry).then((result) => {
      if (!result.saved && result.reason) {
        setCacheMessage(result.reason);
      }
    }).catch(() => {
      setCacheMessage('Result is available in this tab, but could not be saved to the local browser cache.');
    });
  }

  function updateMediaStatus(mediaId: string, status: MediaItem['status']) {
    setMediaLibrary((current) => current.map((item) => (
      item.id === mediaId ? { ...item, status } : item
    )));
    setSelectedMedia((current) => (
      current?.id === mediaId ? { ...current, status } : current
    ));
  }

  function buildCacheEntry({
    media,
    result,
    jobStatus: nextJobStatus,
    batchStatus: nextBatchStatus,
    selectedJobId,
    source = 'backend',
    status,
  }: {
    media: MediaItem;
    result?: AnalysisResult;
    jobStatus?: JobStatus | null;
    batchStatus?: BatchStatus | null;
    selectedJobId?: string | null;
    source?: CachedResultEntry['source'];
    status?: string;
  }): CachedResultEntry {
    const existing = cachedEntries[mediaCacheKey(media.id)];
    return {
      cacheKey: mediaCacheKey(media.id),
      cacheVersion: 1,
      mediaId: media.id,
      mediaName: media.filename,
      query: result?.query ?? query,
      source,
      status: status ?? result?.status ?? nextBatchStatus?.status ?? nextJobStatus?.status ?? media.status,
      savedAt: existing?.savedAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      jobId: result?.jobId ?? nextJobStatus?.jobId ?? existing?.jobId,
      batchId: nextBatchStatus?.batchId ?? existing?.batchId,
      selectedJobId: selectedJobId ?? existing?.selectedJobId,
      result: result ?? existing?.result,
      jobStatus: nextJobStatus ?? existing?.jobStatus ?? null,
      batchStatus: nextBatchStatus ?? existing?.batchStatus ?? null,
    };
  }

  function restoreCachedMedia(media: MediaItem): boolean {
    const entry = cachedEntries[mediaCacheKey(media.id)];
    const childEntry = entry?.selectedJobId ? cachedEntries[jobCacheKey(entry.selectedJobId)] : undefined;
    const restoredResult = childEntry?.result ?? entry?.result;
    if (!entry && !childEntry) return false;

    setAnalysisResult(restoredResult ?? null);
    setJobStatus(childEntry?.jobStatus ?? entry?.jobStatus ?? null);
    setBatchStatus(entry?.batchStatus ?? null);
    setSelectedBatchJobId(entry?.selectedJobId ?? childEntry?.jobId ?? null);
    setAnalysisMode(restoredResult ? entry?.source ?? childEntry?.source ?? 'backend' : null);
    if (entry && isCacheEntryStale(entry)) {
      setCacheMessage('Showing an older cached result. Reconnect the local runtime to refresh it, or clear the cache.');
    }
    return true;
  }

  async function refreshCachedResultFromBackend(media: MediaItem) {
    const entry = cachedEntries[mediaCacheKey(media.id)];
    const jobId = entry?.selectedJobId ?? entry?.jobId;
    if (!backendConnected || !jobId) return;
    try {
      const status = await getJobStatus(jobId);
      const nextEntry = buildCacheEntry({ media, jobStatus: status, status: status.status });
      rememberCachedEntry(nextEntry);
      if (selectedMediaIdRef.current === media.id) setJobStatus(status);
      if (status.status !== 'completed') return;

      const result = await getJobResult(jobId);
      result.settings = settings;
      const jobEntry: CachedResultEntry = {
        cacheKey: jobCacheKey(jobId),
        cacheVersion: 1,
        mediaId: media.id,
        mediaName: media.filename,
        query: result.query,
        source: 'backend',
        status: 'completed',
        savedAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        jobId,
        batchId: entry?.batchId,
        result,
        jobStatus: status,
      };
      rememberCachedEntry(jobEntry);
      rememberCachedEntry(buildCacheEntry({ media, result, jobStatus: status, selectedJobId: jobId, status: 'completed' }));
      if (selectedMediaIdRef.current === media.id) {
        setAnalysisResult(result);
        setAnalysisMode('backend');
      }
    } catch {
      if (entry?.result) {
        setCacheMessage('Showing cached result; the local runtime could not refresh it right now.');
      }
    }
  }

  const refreshBackendConnection = useCallback(async () => {
    setBackendState('connecting');
    setBackendMessage(null);
    try {
      const runtime = await discoverBackendRuntime();
      setActiveApiBase(runtime.apiBase);
      setSystemStatus(runtime.systemStatus);
      setBackendState('connected');
      setBackendMessage(null);
    } catch (err) {
      setActiveApiBase(getActiveApiBase());
      setSystemStatus(null);
      setBackendState(err instanceof BackendDiscoveryError ? err.state : 'disconnected');
      setBackendMessage(
        err instanceof Error
          ? err.message
          : 'SafeTrace Local Runtime is not reachable from this browser.',
      );
      if (!previewMode) {
        setMediaLibrary([]);
        setSelectedMedia(null);
        setSelectedFile(null);
        setSelectedFiles([]);
        setAnalysisResult(null);
        setBatchStatus(null);
        setSelectedBatchJobId(null);
      }
    }
  }, [previewMode]);

  useEffect(() => {
    void refreshBackendConnection();
  }, [refreshBackendConnection]);

  useEffect(() => {
    if (!previewMode) return undefined;
    let isMounted = true;
    getMockMediaLibrary()
      .then((items) => {
        if (isMounted) setMediaLibrary(items);
      })
      .catch(() => {
        if (isMounted) setMediaLibrary([sampleMedia]);
      });
    return () => { isMounted = false; };
  }, [previewMode]);

  useEffect(() => {
    return () => {
      if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    };
  }, [localPreviewUrl]);

  function clearLocalPreview() {
    if (localPreviewUrl) {
      URL.revokeObjectURL(localPreviewUrl);
      setLocalPreviewUrl(null);
    }
  }

  function handleSelectMedia(media: MediaItem) {
    const knownSampleQueries = Object.values(SAMPLE_QUERY_BY_MEDIA_ID);
    const suggestedQuery = SAMPLE_QUERY_BY_MEDIA_ID[media.id];
    clearLocalPreview();
    setSelectedMedia(media);
    const fileGroup = localFileGroupsRef.current[media.id] ?? (
      localFilesRef.current[media.id] ? [localFilesRef.current[media.id]] : []
    );
    setSelectedFiles(fileGroup);
    setSelectedFile(fileGroup.length === 1 ? fileGroup[0] : null);
    setError(null);
    setCacheMessage(null);
    const restored = restoreCachedMedia(media);
    if (!restored) {
      setAnalysisResult(null);
      setJobStatus(null);
      setBatchStatus(null);
      setSelectedBatchJobId(null);
      setAnalysisMode(null);
    }
    void refreshCachedResultFromBackend(media);
    if (suggestedQuery && knownSampleQueries.includes(query)) {
      setQuery(suggestedQuery);
    }
  }

  function handleDeleteMedia(mediaId: string) {
    const entry = cachedEntries[mediaCacheKey(mediaId)];
    delete localFilesRef.current[mediaId];
    delete localFileGroupsRef.current[mediaId];
    setCachedEntries((current) => {
      const next = { ...current };
      delete next[mediaCacheKey(mediaId)];
      if (entry?.selectedJobId) delete next[jobCacheKey(entry.selectedJobId)];
      return next;
    });
    void deleteCachedResult(mediaCacheKey(mediaId));
    if (entry?.selectedJobId) void deleteCachedResult(jobCacheKey(entry.selectedJobId));
    setMediaLibrary((prev) => prev.filter((m) => m.id !== mediaId));
    if (selectedMedia?.id === mediaId && mediaLibrary.length > 1) {
      const next = mediaLibrary.find((m) => m.id !== mediaId);
      if (next) {
        setSelectedMedia(next);
        const nextFiles = localFileGroupsRef.current[next.id] ?? (
          localFilesRef.current[next.id] ? [localFilesRef.current[next.id]] : []
        );
        setSelectedFiles(nextFiles);
        setSelectedFile(nextFiles.length === 1 ? nextFiles[0] : null);
      }
    } else if (selectedMedia?.id === mediaId) {
      setSelectedMedia(null);
      setSelectedFile(null);
      setSelectedFiles([]);
    }
  }

  function handleSettingsChange(nextSettings: AnalysisSettings) {
    setSettings(nextSettings);
  }

  function handleFilesSelected(files: File[]) {
    if (controlsLocked) return;
    const selected = files.filter(Boolean);
    if (!selected.length) return;
    clearLocalPreview();
    const isSinglePreviewableFile = selected.length === 1 && !isZipFile(selected[0]);
    const previewUrl = isSinglePreviewableFile ? URL.createObjectURL(selected[0]) : undefined;
    const id = selected.length === 1
      ? `local-${selected[0].name}-${selected[0].lastModified}`
      : `local-batch-${Date.now()}`;
    const media: MediaItem = {
      id,
      filename: getSelectionName(selected),
      type: getMediaTypeForFiles(selected),
      sizeLabel: getSelectionSize(selected),
      uploadedAt: new Date().toISOString(),
      status: 'ready',
      source: 'local',
      previewUrl,
    };
    if (selected.length === 1) {
      localFilesRef.current[media.id] = selected[0];
    }
    localFileGroupsRef.current[media.id] = selected;
    setLocalPreviewUrl(previewUrl ?? null);
    setSelectedFile(selected.length === 1 ? selected[0] : null);
    setSelectedFiles(selected);
    setSelectedMedia(media);
    setMediaLibrary((prev) => [media, ...prev.filter((item) => item.id !== media.id)]);
    setAnalysisResult(null);
    setError(null);
    setJobStatus(null);
    setBatchStatus(null);
    setSelectedBatchJobId(null);
    setAnalysisMode(null);
  }

  function handleFileSelected(file: File) {
    handleFilesSelected([file]);
  }

  function progressToStep(progress: number) {
    if (progress >= 1) return ANALYSIS_STEPS.length;
    return Math.min(ANALYSIS_STEPS.length - 1, Math.max(0, Math.floor(progress * ANALYSIS_STEPS.length)));
  }

  function isBatchSelection(files: File[]) {
    return files.length > 1 || (files.length === 1 && isZipFile(files[0]));
  }

  async function pollBackendJob(jobId: string, media?: MediaItem): Promise<JobStatus> {
    const startedAt = Date.now();
    const timeoutMs = 5 * 60 * 1000;

    while (Date.now() - startedAt < timeoutMs) {
      const status = await getJobStatus(jobId);
      if (!media || selectedMediaIdRef.current === media.id) {
        setJobStatus(status);
        setActiveStep(progressToStep(status.progress));
      }
      if (media) {
        rememberCachedEntry(buildCacheEntry({ media, jobStatus: status, status: status.status }));
      }

      if (status.status === 'completed') return status;
      if (status.status === 'failed' || status.status === 'cancelled') {
        throw new Error(status.error || 'Analysis could not be completed.');
      }

      await wait(1200);
    }

    throw new Error('Analysis timed out while waiting for the backend job to finish.');
  }

  async function pollBackendBatch(batchId: string, media?: MediaItem): Promise<BatchStatus> {
    const startedAt = Date.now();
    const timeoutMs = 10 * 60 * 1000;

    while (Date.now() - startedAt < timeoutMs) {
      const status = await getBatchStatus(batchId);
      if (!media || selectedMediaIdRef.current === media.id) {
        setBatchStatus(status);
      }
      const totalJobs = Math.max(status.acceptedFiles.length, 1);
      const completedJobs = status.acceptedFiles.filter((file) => (
        file.status === 'completed' || file.status === 'failed' || file.status === 'cancelled'
      )).length;
      const progressStatus: JobStatus = {
        jobId: batchId,
        status: status.status === 'running' ? 'running' : status.status === 'queued' ? 'queued' : 'completed',
        progress: completedJobs / totalJobs,
        currentStep: `Batch analysis ${status.status}`,
        error: status.status === 'failed' ? 'No videos completed successfully.' : null,
      };
      if (!media || selectedMediaIdRef.current === media.id) {
        setActiveStep(progressToStep(completedJobs / totalJobs));
        setJobStatus(progressStatus);
      }
      if (media) {
        rememberCachedEntry(buildCacheEntry({
          media,
          jobStatus: progressStatus,
          batchStatus: status,
          status: status.status,
        }));
      }

      if (status.status === 'completed' || status.status === 'partial') return status;
      if (status.status === 'failed' || status.status === 'cancelled') {
        throw new Error('Batch analysis could not be completed.');
      }

      await wait(1500);
    }

    throw new Error('Batch analysis timed out while waiting for the backend jobs to finish.');
  }

  async function handleAnalyze() {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setError('Enter a query before starting analysis.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);
    setHighlightedFrameId(null);
    setJobStatus(null);
    setBatchStatus(null);
    setSelectedBatchJobId(null);

    try {
      const activeMedia = selectedMedia;
      const backendFiles = selectedFiles.length ? selectedFiles : selectedFile ? [selectedFile] : [];

      if (backendConnected && backendFiles.length) {
        setAnalysisMode('backend');
        setActiveStep(0);
        if (activeMedia) updateMediaStatus(activeMedia.id, 'processing');
        if (isBatchSelection(backendFiles)) {
          const batch = await runBackendBatchAnalysis({
            files: backendFiles,
            query: trimmedQuery,
            fps: settings.fps,
            topK: settings.topK,
            enableVlm: settings.vlmExplanations,
            device: settings.deviceMode,
          });
          setBatchStatus(batch);
          if (activeMedia) {
            rememberCachedEntry(buildCacheEntry({
              media: activeMedia,
              batchStatus: batch,
              status: batch.status,
            }));
          }
          const finalBatch = await pollBackendBatch(batch.batchId, activeMedia ?? undefined);
          const completedFile = finalBatch.acceptedFiles.find((file) => file.status === 'completed');
          if (!completedFile) {
            throw new Error('Batch analysis finished without a completed video result.');
          }
          const result = await getJobResult(completedFile.jobId);
          result.settings = settings;
          if (activeMedia) {
            const jobEntry: CachedResultEntry = {
              cacheKey: jobCacheKey(completedFile.jobId),
              cacheVersion: 1,
              mediaId: activeMedia.id,
              mediaName: completedFile.filename,
              query: result.query,
              source: 'backend',
              status: 'completed',
              savedAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
              jobId: completedFile.jobId,
              batchId: finalBatch.batchId,
              result,
              batchStatus: finalBatch,
            };
            rememberCachedEntry(jobEntry);
            rememberCachedEntry(buildCacheEntry({
              media: activeMedia,
              result,
              batchStatus: finalBatch,
              selectedJobId: completedFile.jobId,
              status: finalBatch.status,
            }));
            updateMediaStatus(activeMedia.id, 'completed');
          }
          if (!activeMedia || selectedMediaIdRef.current === activeMedia.id) {
            setSelectedBatchJobId(completedFile.jobId);
            setActiveStep(ANALYSIS_STEPS.length);
            setAnalysisResult(result);
          }
          return;
        }

        const job = await runBackendAnalysis({
          file: backendFiles[0],
          query: trimmedQuery,
          fps: settings.fps,
          topK: settings.topK,
          enableVlm: settings.vlmExplanations,
          device: settings.deviceMode,
        });
        const queuedStatus: JobStatus = {
          ...job,
          progress: 0,
          currentStep: 'Queued for analysis',
          error: null,
        };
        setJobStatus(queuedStatus);
        if (activeMedia) {
          rememberCachedEntry(buildCacheEntry({
            media: activeMedia,
            jobStatus: queuedStatus,
            status: queuedStatus.status,
          }));
        }
        const completedStatus = await pollBackendJob(job.jobId, activeMedia ?? undefined);
        const result = await getJobResult(job.jobId);
        result.settings = settings;
        if (activeMedia) {
          rememberCachedEntry(buildCacheEntry({
            media: activeMedia,
            result,
            jobStatus: completedStatus,
            status: 'completed',
          }));
          updateMediaStatus(activeMedia.id, 'completed');
        }
        if (!activeMedia || selectedMediaIdRef.current === activeMedia.id) {
          setActiveStep(ANALYSIS_STEPS.length);
          setAnalysisResult(result);
        }
        return;
      }

      if (canUsePreview && selectedMedia) {
        setAnalysisMode('preview');
        for (let index = 0; index < ANALYSIS_STEPS.length; index += 1) {
          setActiveStep(index);
          await wait(330);
        }
        const result = await runMockAnalysis({ query: trimmedQuery, media: selectedMedia, settings });
        setActiveStep(ANALYSIS_STEPS.length);
        setAnalysisResult(result);
        rememberCachedEntry(buildCacheEntry({
          media: selectedMedia,
          result,
          source: 'preview',
          status: 'completed',
        }));
        return;
      }

      if (backendConnected) {
        throw new Error('Select a local image or video before running backend analysis.');
      }

      throw new Error('SafeTrace backend is not running or not reachable.');
    } catch (err) {
      setAnalysisMode(null);
      setSelectedMedia((current) => current?.status === 'processing' ? { ...current, status: 'error' } : current);
      setError(err instanceof Error ? err.message : 'Analysis could not be completed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }

  function handleReset() {
    setAnalysisResult(null);
    setError(null);
    setQuery(DEFAULT_QUERY);
    setHighlightedFrameId(null);
    setJobStatus(null);
    setBatchStatus(null);
    setSelectedBatchJobId(null);
    setAnalysisMode(null);
  }

  async function handleSelectBatchResult(jobId: string) {
    if (batchResultLoadingJobId === jobId) return;
    setBatchResultLoadingJobId(jobId);
    setError(null);
    const cached = cachedEntries[jobCacheKey(jobId)];
    if (cached?.result) {
      setSelectedBatchJobId(jobId);
      setAnalysisResult(cached.result);
      setAnalysisMode(cached.source);
      if (isCacheEntryStale(cached)) {
        setCacheMessage('Showing an older cached batch result while SafeTrace refreshes from the local runtime.');
      }
    }
    try {
      const result = await getJobResult(jobId);
      result.settings = settings;
      setSelectedBatchJobId(jobId);
      setAnalysisResult(result);
      setActiveStep(ANALYSIS_STEPS.length);
      if (selectedMedia) {
        rememberCachedEntry({
          cacheKey: jobCacheKey(jobId),
          cacheVersion: 1,
          mediaId: selectedMedia.id,
          mediaName: selectedMedia.filename,
          query: result.query,
          source: 'backend',
          status: 'completed',
          savedAt: cached?.savedAt ?? new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          jobId,
          batchId: batchStatus?.batchId,
          result,
          batchStatus,
        });
        rememberCachedEntry(buildCacheEntry({
          media: selectedMedia,
          result,
          batchStatus,
          selectedJobId: jobId,
          status: batchStatus?.status ?? 'completed',
        }));
      }
    } catch (err) {
      if (!cached?.result) {
        setError(err instanceof Error ? err.message : 'Could not load this batch result.');
      } else {
        setCacheMessage('Showing cached batch result; the local runtime could not refresh it right now.');
      }
    } finally {
      setBatchResultLoadingJobId(null);
    }
  }

  async function handleClearResultCache() {
    await clearCachedResults();
    setCachedEntries({});
    setCacheMessage('Local result cache cleared. Uploaded media files were not stored in the browser cache.');
  }

  async function handleClearSelectedResultCache() {
    if (!selectedMedia) return;
    const entry = cachedEntries[mediaCacheKey(selectedMedia.id)];
    const next = { ...cachedEntries };
    delete next[mediaCacheKey(selectedMedia.id)];
    await deleteCachedResult(mediaCacheKey(selectedMedia.id));
    if (entry?.selectedJobId) {
      delete next[jobCacheKey(entry.selectedJobId)];
      await deleteCachedResult(jobCacheKey(entry.selectedJobId));
    }
    setCachedEntries(next);
    setAnalysisResult(null);
    setJobStatus(null);
    setBatchStatus(null);
    setSelectedBatchJobId(null);
    setCacheMessage(`Cleared cached result for ${selectedMedia.filename}.`);
  }

  function handleFrameSelect(frameId: string) {
    setHighlightedFrameId(frameId);
    window.requestAnimationFrame(() => {
      document.getElementById(`frame-${frameId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    window.setTimeout(() => setHighlightedFrameId(null), 2200);
  }

  const analyzeDisabledReason = !backendConnected && !previewMode
    ? 'Start SafeTrace Local Runtime, then reconnect before analysis.'
    : !selectedFiles.length && !selectedFile && !canUsePreview
      ? 'Select a local image, video, ZIP archive, or video batch before analysis.'
      : !query.trim()
        ? 'Enter a query before analysis.'
        : undefined;
  const canAnalyze = !isLoading && !analyzeDisabledReason;

  return (
    <AppShell
      sidebar={
        <Sidebar
          settings={settings}
          onSettingsChange={handleSettingsChange}
          backendState={backendState}
          apiBase={activeApiBase}
          systemStatus={systemStatus}
          backendMessage={backendMessage}
          previewMode={previewMode}
        />
      }
      rightPanel={
        <VideoQueue
          mediaLibrary={mediaLibrary}
          selectedMedia={selectedMedia}
          onSelectMedia={handleSelectMedia}
          onDeleteMedia={handleDeleteMedia}
          onUploadClick={() => setIsUploadModalOpen(true)}
          uploadDisabled={controlsLocked}
        />
      }
    >
      <header className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold text-safety-teal">SafeTrace dashboard</p>
            <h1 className="mt-1 text-3xl font-bold tracking-normal text-slate-950">
              Safety Violation Detection
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Upload safety footage, describe what to check for, and review evidence-backed violation findings.
            </p>
            {previewMode ? (
              <p className="mt-3 inline-flex rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold uppercase text-amber-700">
                Developer Preview Mode
              </p>
            ) : null}
          </div>
        </div>
      </header>

      {!backendConnected && !previewMode ? (
        <BackendUnavailableState
          apiBase={activeApiBase}
          apiBaseCandidates={SAFETRACE_API_BASE_CANDIDATES}
          state={backendState}
          message={backendMessage}
          onRetry={refreshBackendConnection}
        />
      ) : null}

      <ResultCachePanel
        entryCount={cachedEntryCount}
        message={cacheMessage}
        hasSelectedCachedResult={Boolean(selectedMedia && cachedEntries[mediaCacheKey(selectedMedia.id)])}
        selectedMediaName={selectedMedia?.filename}
        onClearAll={() => void handleClearResultCache()}
        onClearSelected={() => void handleClearSelectedResultCache()}
      />

      <SelectedMediaViewer
        media={selectedMedia}
        disabled={controlsLocked}
        backendConnected={backendConnected}
        previewMode={previewMode}
        onUploadClick={() => setIsUploadModalOpen(true)}
      />

      <QueryTabs
        query={query}
        isLoading={isLoading}
        hasResult={Boolean(analysisResult)}
        onQueryChange={setQuery}
        onAnalyze={handleAnalyze}
        onReset={handleReset}
        canAnalyze={canAnalyze}
        disabledReason={analyzeDisabledReason}
        previewMode={previewMode && !backendConnected}
      />

      {isLoading ? (
        <AnalysisProgress
          steps={ANALYSIS_STEPS}
          activeStep={activeStep}
          currentStep={jobStatus?.currentStep}
          progress={jobStatus?.progress}
          mode={analysisMode}
        />
      ) : null}
      {batchStatus ? (
        <BatchStatusPanel
          batch={batchStatus}
          selectedJobId={selectedBatchJobId}
          loadingJobId={batchResultLoadingJobId}
          onSelectJob={handleSelectBatchResult}
        />
      ) : null}
      {error ? <ErrorState message={error} details={jobStatus?.error || backendMessage} /> : null}

      {!analysisResult && !isLoading && !error && (backendConnected || previewMode) ? (
        <PreAnalysisState hasMedia={Boolean(selectedFiles.length || selectedFile || canUsePreview)} previewMode={canUsePreview} />
      ) : null}

      {analysisResult && !isLoading ? (
        <>
          <AnalysisSummary result={analysisResult} showExplanations={settings.vlmExplanations} />
          
          <ViolationSummary 
            result={analysisResult} 
            onFrameSelect={handleFrameSelect} 
            timelineComponent={
              <TimelineVisualization 
                result={analysisResult} 
                onFrameSelect={handleFrameSelect}
                selectedFrameId={highlightedFrameId}
                hoveredFrameId={hoveredFrameId}
                onHover={setHoveredFrameId}
              />
            } 
            statisticsComponent={<StatisticsPanel result={analysisResult} />} 
          />
          
          <EvidenceFrames
            frames={analysisResult.frames}
            showExplanations={settings.vlmExplanations}
            highlightedFrameId={highlightedFrameId}
          />
          
          {showAnnotation && (
            <AnnotationViewer
              mediaUrl={analysisResult.frames[0]?.imageUrl}
              mediaId={analysisResult.media.id}
              mediaType={analysisResult.media.type === 'video' ? 'video' : 'image'}
            />
          )}
          
          <ReportActions result={analysisResult} />
        </>
      ) : null}

      {isUploadModalOpen && (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl relative">
         <button 
           onClick={() => setIsUploadModalOpen(false)}
           className="absolute right-4 top-4 text-slate-400 hover:text-slate-600"
         >
           Close
         </button>
         <h2 className="text-lg font-bold mb-4">Upload More Videos</h2>
         {/* Insert your UploadPanel component here instead of the main view */}
         <UploadPanel media={selectedMedia} onFileSelected={(file) => {
            handleFileSelected(file);
            setIsUploadModalOpen(false); // Close modal after upload
         }} onFilesSelected={(files) => {
            handleFilesSelected(files);
            setIsUploadModalOpen(false); // Close modal after upload
         }} disabled={controlsLocked} />
      </div>
    </div>
  )}

      <SafeTraceAssistant
        backendConnected={backendConnected}
        result={analysisResult}
        batch={batchStatus}
        selectedJobId={selectedBatchJobId}
      />
    </AppShell>
  );
}

function BackendUnavailableState({
  apiBase,
  apiBaseCandidates,
  state,
  message,
  onRetry,
}: {
  apiBase: string;
  apiBaseCandidates: string[];
  state: BackendConnectionState;
  message: string | null;
  onRetry: () => void;
}) {
  const isConnecting = state === 'connecting' || state === 'live';
  const title = state === 'incompatible'
    ? 'SafeTrace Local Runtime incompatible'
    : state === 'connecting'
      ? 'Connecting to SafeTrace Local Runtime'
      : 'SafeTrace Local Runtime not connected';

  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-amber-950 shadow-soft">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
            <Server className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-amber-700">Live website loaded</p>
            <h2 className="mt-1 text-base font-bold">{title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6">
              To use analysis, run SafeTrace.exe on this computer, keep the local runtime window open, then return here
              and click Reconnect.
            </p>
            <p className="mt-2 max-w-3xl text-sm leading-6">
              During development, run <span className="font-mono">scripts\start_safetrace_windows.bat</span> instead.
            </p>
            <dl className="mt-3 grid gap-1 text-xs">
              <div>
                <dt className="font-semibold uppercase text-amber-700">Active API base</dt>
                <dd className="break-all font-mono text-amber-900">{apiBase}</dd>
              </div>
              <div>
                <dt className="font-semibold uppercase text-amber-700">Discovery candidates</dt>
                <dd className="break-all font-mono text-amber-900">{apiBaseCandidates.join(', ')}</dd>
              </div>
              {message ? (
                <div>
                  <dt className="font-semibold uppercase text-amber-700">Status</dt>
                  <dd>{message}</dd>
                </div>
              ) : null}
            </dl>
          </div>
        </div>
        <button
          type="button"
          onClick={onRetry}
          disabled={isConnecting}
          className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-800 disabled:opacity-60"
        >
          <RefreshCcw className={`h-4 w-4 ${isConnecting ? 'animate-spin' : ''}`} aria-hidden="true" />
          Reconnect to Local Runtime
        </button>
      </div>
    </section>
  );
}

function BatchStatusPanel({
  batch,
  selectedJobId,
  loadingJobId,
  onSelectJob,
}: {
  batch: BatchStatus;
  selectedJobId: string | null;
  loadingJobId: string | null;
  onSelectJob: (jobId: string) => void;
}) {
  const completed = batch.acceptedFiles.filter((file) => file.status === 'completed').length;
  const total = batch.acceptedFiles.length;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase text-safety-blue">Batch analysis</p>
          <h2 className="mt-1 text-base font-bold text-slate-950">{batch.sourceFilename}</h2>
          <p className="mt-1 text-sm text-slate-600">
            {completed} of {total} accepted video{total === 1 ? '' : 's'} completed.
          </p>
        </div>
        <span className="inline-flex w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold uppercase text-slate-700">
          {batch.status}
        </span>
      </div>

      {batch.acceptedFiles.length ? (
        <div className="mt-4 grid gap-2">
          {batch.acceptedFiles.map((file) => {
            const isSelected = selectedJobId === file.jobId;
            const isLoading = loadingJobId === file.jobId;

            return (
              <div
                key={file.jobId}
                className={`flex flex-col gap-2 rounded-lg border px-3 py-2 sm:flex-row sm:items-center sm:justify-between ${
                  isSelected ? 'border-safety-blue bg-blue-50' : 'border-slate-100 bg-slate-50'
                }`}
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">{file.filename}</p>
                  <p className="text-xs text-slate-500">{formatFileSize(file.sizeBytes)}</p>
                  {file.status === 'failed' ? (
                    <p className="mt-1 text-xs font-medium text-red-700">
                      {file.error || 'Analysis failed for this video.'}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs font-bold uppercase text-slate-600">{file.status}</span>
                  {file.status === 'completed' ? (
                    <button
                      type="button"
                      onClick={() => onSelectJob(file.jobId)}
                      disabled={isLoading}
                      className={`focus-ring rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                        isSelected
                          ? 'border-safety-blue bg-white text-safety-blue'
                          : 'border-slate-300 bg-white text-slate-700 hover:border-safety-blue hover:text-safety-blue'
                      } disabled:opacity-60`}
                    >
                      {isLoading ? 'Loading' : isSelected ? 'Viewing' : 'Open evidence'}
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {batch.rejectedFiles.length ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-bold uppercase text-amber-800">Rejected files</p>
          <ul className="mt-2 space-y-1 text-sm text-amber-950">
            {batch.rejectedFiles.map((file) => (
              <li key={`${file.filename}-${file.reason}`}>
                <span className="font-semibold">{file.filename}</span>: {file.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function ResultCachePanel({
  entryCount,
  message,
  hasSelectedCachedResult,
  selectedMediaName,
  onClearAll,
  onClearSelected,
}: {
  entryCount: number;
  message: string | null;
  hasSelectedCachedResult: boolean;
  selectedMediaName?: string;
  onClearAll: () => void;
  onClearSelected: () => void;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700 shadow-soft">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-safety-blue">
            <Database className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="font-bold text-slate-950">Local result cache</p>
            <p className="mt-1 leading-6">
              Cached results stay on this computer/browser only. They are not uploaded to cloud storage.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Stored: job and batch IDs, result JSON, evidence metadata, backend media/report URLs, and timestamps.
              Not stored: raw uploaded videos, copied evidence image bytes, model files, credentials, or secrets.
            </p>
            {message ? <p className="mt-2 text-xs font-semibold text-safety-blue">{message}</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <span className="inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold uppercase text-slate-600">
            {entryCount} cached item{entryCount === 1 ? '' : 's'}
          </span>
          {hasSelectedCachedResult ? (
            <button
              type="button"
              onClick={onClearSelected}
              className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-red-300 hover:text-red-700"
              title={selectedMediaName ? `Clear cached result for ${selectedMediaName}` : 'Clear selected cached result'}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Clear selected
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClearAll}
            disabled={entryCount === 0}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Clear local result cache
          </button>
        </div>
      </div>
    </section>
  );
}

function ErrorState({ message, details }: { message: string; details?: string | null }) {
  return (
    <section className="rounded-lg border border-red-200 bg-red-50 p-5 text-red-900">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5" aria-hidden="true" />
        <div>
          <h2 className="text-sm font-bold">{message}</h2>
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer font-semibold">Debug details</summary>
            <p className="mt-2 text-red-800">{details || 'The local analysis did not complete.'}</p>
          </details>
        </div>
      </div>
    </section>
  );
}

function PreAnalysisState({ hasMedia, previewMode }: { hasMedia: boolean; previewMode: boolean }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 text-slate-700 shadow-soft">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-safety-teal text-white">
          {hasMedia ? <ClipboardCheck className="h-6 w-6" aria-hidden="true" /> : <UploadCloud className="h-6 w-6" aria-hidden="true" />}
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-950">
            {hasMedia ? 'Ready to run analysis' : 'Select local media to begin'}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6">
            {previewMode
              ? 'Developer Preview Mode is enabled. Sample media can generate preview findings without the backend.'
              : hasMedia
                ? 'The selected media and query are ready. Click Analyze to submit the file to the local SafeTrace backend.'
                : 'Upload a local image, video, ZIP archive, or batch of videos, then describe what SafeTrace should inspect.'}
          </p>
        </div>
      </div>
    </section>
  );
}

export default App;
