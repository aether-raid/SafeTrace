import { Cpu, Gauge, Layers3, ShieldCheck, SlidersHorizontal, Sparkles } from 'lucide-react';
import type { AnalysisSettings, BackendConnectionState, BackendModelStatus, DeviceMode, SystemStatus } from '../types/analysis';
import { StatusBadge } from './StatusBadge';

type SidebarProps = {
  settings: AnalysisSettings;
  onSettingsChange: (settings: AnalysisSettings) => void;
  backendState: BackendConnectionState;
  apiBase: string;
  systemStatus: SystemStatus | null;
  backendMessage?: string | null;
  previewMode?: boolean;
};

function getDeviceStatus(deviceMode: DeviceMode) {
  if (deviceMode === 'GPU') {
    return { label: 'GPU mode selected', tone: 'success' as const };
  }

  if (deviceMode === 'CPU') {
    return { label: 'CPU mode selected', tone: 'info' as const };
  }

  return { label: 'Auto device selection active', tone: 'info' as const };
}

function getModelTone(status?: BackendModelStatus) {
  if (!status) return 'neutral' as const;
  if (status.status === 'ready') return 'success' as const;
  if (status.status === 'missing') return 'danger' as const;
  return 'warning' as const;
}

function modelLabel(label: string, status?: BackendModelStatus) {
  if (!status) return `${label} unknown`;
  if (status.status === 'ready') return `${label} ready`;
  if (status.status === 'missing') return `${label} missing`;
  return `${label} unavailable`;
}

function backendTone(state: BackendConnectionState) {
  if (state === 'connected') return 'success' as const;
  if (state === 'connecting') return 'info' as const;
  return 'danger' as const;
}

export function Sidebar({
  settings,
  onSettingsChange,
  backendState,
  apiBase,
  systemStatus,
  backendMessage,
  previewMode = false,
}: SidebarProps) {
  const processingCost = settings.fps >= 3 ? 'High coverage' : settings.fps >= 1.5 ? 'Balanced coverage' : 'Fast preview';
  const systemStatuses = [
    {
      label: backendState === 'connected'
        ? 'Backend connected'
        : backendState === 'connecting'
          ? 'Backend connecting'
          : 'Backend disconnected',
      tone: backendTone(backendState),
    },
    {
      label: systemStatus?.gpuAvailable ? 'GPU available' : 'GPU unavailable',
      tone: systemStatus?.gpuAvailable ? 'success' as const : 'warning' as const,
    },
    {
      label: modelLabel('Embedding model', systemStatus?.models.embeddingModel),
      tone: getModelTone(systemStatus?.models.embeddingModel),
    },
    {
      label: modelLabel('Detector', systemStatus?.models.detector),
      tone: getModelTone(systemStatus?.models.detector),
    },
    {
      label: modelLabel('MobileSAM', systemStatus?.models.mobileSam),
      tone: getModelTone(systemStatus?.models.mobileSam),
    },
    {
      label: modelLabel('VLM', systemStatus?.models.vlm),
      tone: getModelTone(systemStatus?.models.vlm),
    },
  ];

  function updateSettings(nextSettings: Partial<AnalysisSettings>) {
    onSettingsChange({ ...settings, ...nextSettings });
  }

  return (
    <div className="flex h-full flex-col gap-6 px-5 py-6">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-safety-teal text-white shadow-insetLine">
          <ShieldCheck className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <p className="text-lg font-bold tracking-normal">SafeTrace</p>
          <p className="text-xs font-medium text-slate-300">
            {previewMode ? 'Developer preview enabled' : 'Backend-required offline intelligence'}
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Analysis controls
        </div>

        <div className="space-y-5">
          <label className="block">
            <span className="flex items-center justify-between text-sm font-semibold text-white">
              <span className="inline-flex items-center gap-2">
                <Gauge className="h-4 w-4 text-slate-300" aria-hidden="true" />
                Frame sampling FPS
              </span>
              <span>{settings.fps.toFixed(1)}</span>
            </span>
            <span className="mt-1 block text-xs leading-5 text-slate-300">
              Controls how many frames per second are sampled from the uploaded video. Higher values improve coverage but may take longer.
            </span>
            <input
              className="control-range mt-3"
              type="range"
              min="0.5"
              max="5"
              step="0.5"
              value={settings.fps}
              onInput={(event) => updateSettings({ fps: Number(event.currentTarget.value) })}
              onChange={(event) => updateSettings({ fps: Number(event.target.value) })}
            />
            <span className="mt-2 block text-xs font-medium text-slate-200">{processingCost}</span>
          </label>

          <label className="block">
            <span className="flex items-center justify-between text-sm font-semibold text-white">
              <span className="inline-flex items-center gap-2">
                <Layers3 className="h-4 w-4 text-slate-300" aria-hidden="true" />
                Top-K frames
              </span>
              <span>{settings.topK}</span>
            </span>
            <span className="mt-1 block text-xs leading-5 text-slate-300">
              Selects the most relevant frames for the query. Higher values show more evidence.
            </span>
            <input
              className="control-range mt-3"
              type="range"
              min="1"
              max="20"
              step="1"
              value={settings.topK}
              onInput={(event) => updateSettings({ topK: Number(event.currentTarget.value) })}
              onChange={(event) => updateSettings({ topK: Number(event.target.value) })}
            />
            <span className="mt-2 block text-xs font-medium text-slate-200">
              Showing up to {settings.topK} evidence frame{settings.topK === 1 ? '' : 's'}
            </span>
          </label>

          <div>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="inline-flex items-center gap-2 text-sm font-semibold text-white">
                  <Sparkles className="h-4 w-4 text-slate-300" aria-hidden="true" />
                  VLM explanations
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-300">
                  Adds natural-language explanations when an explanation model is available.
                </p>
              </div>
              <button
                className="focus-ring relative mt-1 h-6 w-11 rounded-full border border-white/20 bg-slate-700 transition data-[checked=true]:bg-safety-teal"
                type="button"
                role="switch"
                aria-checked={settings.vlmExplanations}
                data-checked={settings.vlmExplanations}
                onClick={() => updateSettings({ vlmExplanations: !settings.vlmExplanations })}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                    settings.vlmExplanations ? 'left-5' : 'left-0.5'
                  }`}
                />
              </button>
            </div>
          </div>

          <label className="block">
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-white">
              <Cpu className="h-4 w-4 text-slate-300" aria-hidden="true" />
              Device
            </span>
            <span className="mt-1 block text-xs leading-5 text-slate-300">
              Choose automatic, CPU, or GPU analysis mode.
            </span>
            <select
              className="focus-ring mt-3 w-full rounded-lg border border-white/15 bg-slate-900 px-3 py-2 text-sm text-white"
              value={settings.deviceMode}
              onChange={(event) => updateSettings({ deviceMode: event.target.value as DeviceMode })}
            >
              <option>Auto</option>
              <option>CPU</option>
              <option>GPU</option>
            </select>
          </label>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <p className="mb-3 text-sm font-semibold text-white">System status</p>
        <div className="flex flex-col gap-2">
          {systemStatuses.map((status) => (
            <StatusBadge key={status.label} label={status.label} tone={status.tone} className="justify-center" />
          ))}
        </div>
        <details className="mt-3 rounded-lg border border-white/10 bg-slate-950/50 p-3 text-xs text-slate-300">
          <summary className="cursor-pointer font-semibold text-white">Backend details</summary>
          <dl className="mt-3 grid gap-2">
            <div>
              <dt className="font-semibold text-slate-200">API base</dt>
              <dd className="break-all font-mono">{apiBase}</dd>
            </div>
            <div>
              <dt className="font-semibold text-slate-200">Selected device</dt>
              <dd>{getDeviceStatus(settings.deviceMode).label}</dd>
            </div>
            {backendMessage ? (
              <div>
                <dt className="font-semibold text-slate-200">Connection message</dt>
                <dd>{backendMessage}</dd>
              </div>
            ) : null}
          </dl>
        </details>
      </div>
    </div>
  );
}
