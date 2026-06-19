import { AlertTriangle, ClipboardCheck, RefreshCcw, Server, UploadCloud } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AnalysisProgress } from './components/AnalysisProgress';
import { AnalysisSummary } from './components/AnalysisSummary';
import { AnnotationViewer } from './components/AnnotationViewer';
import { AppShell } from './components/AppShell';
import { EvidenceFrames } from './components/EvidenceFrames';
import { MediaLibraryPanel } from './components/MediaLibraryPanel';
import { QueryTabs } from './components/QueryTabs';
import { ReportActions } from './components/ReportActions';
import { Sidebar } from './components/Sidebar';
import { StatisticsPanel } from './components/StatisticsPanel';
import { TimelineVisualization } from './components/TimelineVisualization';
import { UploadPanel } from './components/UploadPanel';
import { VideoQueue } from './components/VideoQueue';
import { ViolationSummary } from './components/ViolationSummary';
import { sampleMedia } from './data/mockAnalysis';
import {
  SAFETRACE_API_BASE,
  SAFETRACE_ENABLE_PREVIEW_MODE,
  SAFETRACE_REQUIRE_BACKEND,
  checkBackendHealth,
  getJobResult,
  getJobStatus,
  getMockMediaLibrary,
  getSystemStatus,
  runBackendAnalysis,
  runMockAnalysis,
} from './services/analysisService';
import type {
  AnalysisResult,
  AnalysisSettings,
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

function App() {
  const previewMode = SAFETRACE_ENABLE_PREVIEW_MODE;
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [mediaLibrary, setMediaLibrary] = useState<MediaItem[]>(previewMode ? [sampleMedia] : []);
  const [selectedMedia, setSelectedMedia] = useState<MediaItem | null>(previewMode ? sampleMedia : null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
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
  const [backendState, setBackendState] = useState<BackendConnectionState>('connecting');
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [backendMessage, setBackendMessage] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [analysisMode, setAnalysisMode] = useState<'backend' | 'preview' | null>(null);
  const localFilesRef = useRef<Record<string, File>>({});

  const backendConnected = backendState === 'connected';
  const controlsLocked = SAFETRACE_REQUIRE_BACKEND && !backendConnected && !previewMode;
  const canUsePreview = previewMode && Boolean(selectedMedia);

  const refreshBackendConnection = useCallback(async () => {
    setBackendState('connecting');
    setBackendMessage(null);
    try {
      const [, status] = await Promise.all([checkBackendHealth(), getSystemStatus()]);
      setSystemStatus(status);
      setBackendState('connected');
      setBackendMessage(null);
    } catch (err) {
      setSystemStatus(null);
      setBackendState('disconnected');
      setBackendMessage(err instanceof Error ? err.message : 'SafeTrace backend is not reachable.');
      if (!previewMode) {
        setMediaLibrary([]);
        setSelectedMedia(null);
        setSelectedFile(null);
        setAnalysisResult(null);
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
    setSelectedFile(localFilesRef.current[media.id] ?? null);
    setAnalysisResult(null);
    setError(null);
    setJobStatus(null);
    setAnalysisMode(null);
    if (suggestedQuery && knownSampleQueries.includes(query)) {
      setQuery(suggestedQuery);
    }
  }

  function handleDeleteMedia(mediaId: string) {
    delete localFilesRef.current[mediaId];
    setMediaLibrary((prev) => prev.filter((m) => m.id !== mediaId));
    if (selectedMedia?.id === mediaId && mediaLibrary.length > 1) {
      const next = mediaLibrary.find((m) => m.id !== mediaId);
      if (next) {
        setSelectedMedia(next);
        setSelectedFile(localFilesRef.current[next.id] ?? null);
      }
    } else if (selectedMedia?.id === mediaId) {
      setSelectedMedia(null);
      setSelectedFile(null);
    }
  }

  function handleSettingsChange(nextSettings: AnalysisSettings) {
    setSettings(nextSettings);
  }

  function handleFileSelected(file: File) {
    if (controlsLocked) return;
    clearLocalPreview();
    const previewUrl = URL.createObjectURL(file);
    const media: MediaItem = {
      id: `local-${file.name}-${file.lastModified}`,
      filename: file.name,
      type: file.type.startsWith('image/') ? 'image' : 'video',
      sizeLabel: formatFileSize(file.size),
      uploadedAt: new Date().toISOString(),
      status: 'ready',
      source: 'local',
      previewUrl,
    };
    localFilesRef.current[media.id] = file;
    setLocalPreviewUrl(previewUrl);
    setSelectedFile(file);
    setSelectedMedia(media);
    setMediaLibrary((prev) => [media, ...prev.filter((item) => item.id !== media.id)]);
    setAnalysisResult(null);
    setError(null);
    setJobStatus(null);
    setAnalysisMode(null);
  }

  function progressToStep(progress: number) {
    if (progress >= 1) return ANALYSIS_STEPS.length;
    return Math.min(ANALYSIS_STEPS.length - 1, Math.max(0, Math.floor(progress * ANALYSIS_STEPS.length)));
  }

  async function pollBackendJob(jobId: string): Promise<JobStatus> {
    const startedAt = Date.now();
    const timeoutMs = 5 * 60 * 1000;

    while (Date.now() - startedAt < timeoutMs) {
      const status = await getJobStatus(jobId);
      setJobStatus(status);
      setActiveStep(progressToStep(status.progress));

      if (status.status === 'completed') return status;
      if (status.status === 'failed' || status.status === 'cancelled') {
        throw new Error(status.error || 'Analysis could not be completed.');
      }

      await wait(1200);
    }

    throw new Error('Analysis timed out while waiting for the backend job to finish.');
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

    try {
      if (backendConnected && selectedFile) {
        setAnalysisMode('backend');
        setActiveStep(0);
        setSelectedMedia((current) => current ? { ...current, status: 'processing' } : current);
        const job = await runBackendAnalysis({
          file: selectedFile,
          query: trimmedQuery,
          fps: settings.fps,
          topK: settings.topK,
          enableVlm: settings.vlmExplanations,
          device: settings.deviceMode,
        });
        setJobStatus({
          ...job,
          progress: 0,
          currentStep: 'Queued for analysis',
          error: null,
        });
        await pollBackendJob(job.jobId);
        const result = await getJobResult(job.jobId);
        result.settings = settings;
        setActiveStep(ANALYSIS_STEPS.length);
        setAnalysisResult(result);
        setSelectedMedia((current) => current ? { ...current, status: 'completed' } : current);
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
    setAnalysisMode(null);
  }

  function handleFrameSelect(frameId: string) {
    setHighlightedFrameId(frameId);
    window.requestAnimationFrame(() => {
      document.getElementById(`frame-${frameId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    window.setTimeout(() => setHighlightedFrameId(null), 2200);
  }

  const analyzeDisabledReason = !backendConnected && !previewMode
    ? 'Start the SafeTrace backend and retry the connection.'
    : !selectedFile && !canUsePreview
      ? 'Select a local image or video before analysis.'
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
          apiBase={SAFETRACE_API_BASE}
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
          apiBase={SAFETRACE_API_BASE}
          state={backendState}
          message={backendMessage}
          onRetry={refreshBackendConnection}
        />
      ) : null}

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
      {error ? <ErrorState message={error} details={jobStatus?.error || backendMessage} /> : null}

      {!analysisResult && !isLoading && !error && (backendConnected || previewMode) ? (
        <PreAnalysisState hasMedia={Boolean(selectedFile || canUsePreview)} previewMode={canUsePreview} />
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
         }} disabled={controlsLocked} />
      </div>
    </div>
  )}
    </AppShell>
  );
}

function BackendUnavailableState({
  apiBase,
  state,
  message,
  onRetry,
}: {
  apiBase: string;
  state: BackendConnectionState;
  message: string | null;
  onRetry: () => void;
}) {
  const isConnecting = state === 'connecting';

  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-amber-950 shadow-soft">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
            <Server className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-bold">
              {isConnecting ? 'Connecting to SafeTrace backend' : 'SafeTrace backend unavailable'}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6">
              SafeTrace requires the local FastAPI backend before upload and analysis are enabled. Start the backend,
              then retry the connection.
            </p>
            <dl className="mt-3 grid gap-1 text-xs">
              <div>
                <dt className="font-semibold uppercase text-amber-700">API base</dt>
                <dd className="break-all font-mono text-amber-900">{apiBase}</dd>
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
          Retry Connection
        </button>
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
                : 'Upload a local image or video, then describe what SafeTrace should inspect.'}
          </p>
        </div>
      </div>
    </section>
  );
}

export default App;
