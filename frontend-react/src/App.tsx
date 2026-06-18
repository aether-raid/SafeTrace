import { AlertTriangle, ClipboardCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
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
import { buildMockAnalysisResult, getMockMediaLibrary, runMockAnalysis } from './services/analysisService';
import type { AnalysisResult, AnalysisSettings, MediaItem, SaveStatus } from './types/analysis';
import { QueryTab } from './types/analysis';
import { formatFileSize } from './utils/formatters';

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
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [mediaLibrary, setMediaLibrary] = useState<MediaItem[]>([sampleMedia]);
  const [selectedMedia, setSelectedMedia] = useState<MediaItem>(sampleMedia);
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
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [showTimeline, setShowTimeline] = useState(true);
  const [showStatistics, setShowStatistics] = useState(true);
  const [showAnnotation, setShowAnnotation] = useState(false);
  const [showChatbot, setShowChatbot] = useState(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let isMounted = true;
    getMockMediaLibrary()
      .then((items) => {
        if (isMounted) setMediaLibrary(items);
      })
      .catch(() => {
        if (isMounted) setMediaLibrary([sampleMedia]);
      });
    return () => { isMounted = false; };
  }, []);

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
    setAnalysisResult(null);
    setError(null);
    if (suggestedQuery && knownSampleQueries.includes(query)) {
      setQuery(suggestedQuery);
    }
  }

  function handleDeleteMedia(mediaId: string) {
    setMediaLibrary((prev) => prev.filter((m) => m.id !== mediaId));
    if (selectedMedia.id === mediaId && mediaLibrary.length > 1) {
      const next = mediaLibrary.find((m) => m.id !== mediaId);
      if (next) setSelectedMedia(next);
    }
  }

  function handleSettingsChange(nextSettings: AnalysisSettings) {
    setSettings(nextSettings);
    if (analysisResult) {
      setAnalysisResult(
        buildMockAnalysisResult({ query: analysisResult.query, media: selectedMedia, settings: nextSettings }),
      );
    }
  }

  function handleFileSelected(file: File) {
    clearLocalPreview();
    const previewUrl = URL.createObjectURL(file);
    setLocalPreviewUrl(previewUrl);
    setSelectedMedia({
      id: `local-${file.name}-${file.lastModified}`,
      filename: file.name,
      type: file.type.startsWith('image/') ? 'image' : 'video',
      sizeLabel: formatFileSize(file.size),
      uploadedAt: new Date().toISOString(),
      status: 'ready',
      source: 'local',
      previewUrl,
    });
    setAnalysisResult(null);
    setError(null);
  }

  async function handleAnalyze() {
    setIsLoading(true);
    setError(null);
    setAnalysisResult(null);
    setHighlightedFrameId(null);

    try {
      for (let index = 0; index < ANALYSIS_STEPS.length; index += 1) {
        setActiveStep(index);
        await wait(330);
      }

      const result = await runMockAnalysis({ query, media: selectedMedia, settings });
      setActiveStep(ANALYSIS_STEPS.length);
      await wait(150);
      setAnalysisResult(result);
    } catch {
      setError('Analysis could not be completed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }

  function handleReset() {
    setAnalysisResult(null);
    setError(null);
    setQuery(DEFAULT_QUERY);
    setHighlightedFrameId(null);
  }

  function handleFrameSelect(frameId: string) {
    setHighlightedFrameId(frameId);
    window.requestAnimationFrame(() => {
      document.getElementById(`frame-${frameId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    window.setTimeout(() => setHighlightedFrameId(null), 2200);
  }

  // function handleFileUploadClick() {
  //   fileInputRef.current?.click();
  // }

  return (
    <AppShell
      sidebar={<Sidebar settings={settings} onSettingsChange={handleSettingsChange} />}
      rightPanel={
        <VideoQueue
          mediaLibrary={mediaLibrary}
          selectedMedia={selectedMedia}
          onSelectMedia={handleSelectMedia}
          onDeleteMedia={handleDeleteMedia}
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
          </div>
          <div className="flex items-center gap-2">
            {saveStatus === 'saving' && (
              <span className="flex items-center gap-1 text-xs text-blue-600">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                Saving changes...
              </span>
            )}
            {saveStatus === 'saved' && (
              <span className="flex items-center gap-1 text-xs text-emerald-600">
                <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                All changes saved locally
              </span>
            )}
          </div>
        </div>
      </header>

      <UploadPanel media={selectedMedia} onFileSelected={handleFileSelected} />

      <QueryTabs
        query={query}
        isLoading={isLoading}
        hasResult={Boolean(analysisResult)}
        onQueryChange={setQuery}
        onAnalyze={handleAnalyze}
        onReset={handleReset}
      />

      {isLoading ? <AnalysisProgress steps={ANALYSIS_STEPS} activeStep={activeStep} /> : null}
      {error ? <ErrorState message={error} /> : null}

      {!analysisResult && !isLoading && !error ? <PreAnalysisState /> : null}

      {analysisResult && !isLoading ? (
        <>
          <AnalysisSummary result={analysisResult} showExplanations={settings.vlmExplanations} />
          <ViolationSummary result={analysisResult} onFrameSelect={handleFrameSelect} />
          <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
            <span className="text-xs font-semibold text-slate-600">Toggle sections:</span>
            <label className="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" checked={showTimeline} onChange={(e) => setShowTimeline(e.target.checked)} className="rounded" />
              Timeline
            </label>
            <label className="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" checked={showStatistics} onChange={(e) => setShowStatistics(e.target.checked)} className="rounded" />
              Statistics
            </label>
            {/* todo: manual anotation tool */}
            {/* <label className="flex items-center gap-1.5 text-xs text-slate-600">
              <input type="checkbox" checked={showAnnotation} onChange={(e) => setShowAnnotation(e.target.checked)} className="rounded" />
              Annotation Tool
            </label> */}
          </div>
          {showStatistics && <StatisticsPanel result={analysisResult} />}
          {showTimeline && (
            <TimelineVisualization
              result={analysisResult}
              onFrameSelect={handleFrameSelect}
              selectedFrameId={highlightedFrameId}
            />
          )}
          <EvidenceFrames
            frames={analysisResult.frames}
            showExplanations={settings.vlmExplanations}
            highlightedFrameId={highlightedFrameId}
          />
          
          {showAnnotation && (
            <AnnotationViewer
              mediaUrl={analysisResult.frames[0]?.imageUrl}
              mediaId={analysisResult.media.id}
              mediaType={analysisResult.media.type}
            />
          )}
          <ReportActions result={analysisResult} />

        </>
      ) : null}
    </AppShell>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <section className="rounded-lg border border-red-200 bg-red-50 p-5 text-red-900">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5" aria-hidden="true" />
        <div>
          <h2 className="text-sm font-bold">{message}</h2>
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer font-semibold">Debug details</summary>
            <p className="mt-2 text-red-800">The local analysis preview did not complete.</p>
          </details>
        </div>
      </div>
    </section>
  );
}

function PreAnalysisState() {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 text-slate-700 shadow-soft">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-safety-teal text-white">
          <ClipboardCheck className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-950">Ready to run analysis</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6">
            The selected media and query are ready. Click Analyze to prepare a local evidence summary, grouped safety
            findings, affected frames, and technical evidence when needed.
          </p>
        </div>
      </div>
    </section>
  );
}

export default App;
