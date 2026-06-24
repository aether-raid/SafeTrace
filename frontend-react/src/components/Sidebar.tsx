import { Cpu, Gauge, Layers3, ShieldCheck, SlidersHorizontal, Sparkles } from 'lucide-react';
import type {
  AnalysisSettings,
  BackendConnectionState,
  BackendModelStatus,
  DeviceMode,
  RuntimeCheck,
  SystemStatus,
} from '../types/analysis';
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
  if (state === 'connecting' || state === 'live') return 'info' as const;
  if (state === 'incompatible') return 'warning' as const;
  return 'danger' as const;
}

function backendLabel(state: BackendConnectionState) {
  if (state === 'connected') return 'Local runtime connected';
  if (state === 'connecting') return 'Local runtime connecting';
  if (state === 'live') return 'Live website loaded';
  if (state === 'incompatible') return 'Local runtime incompatible';
  return 'Local runtime disconnected';
}

function checkTone(check?: RuntimeCheck) {
  const status = String(check?.status || '').toLowerCase();
  if (status === 'ready' || status === 'available') return 'success' as const;
  if (status === 'missing') return 'danger' as const;
  if (status === 'loading') return 'info' as const;
  if (status === 'warning' || status === 'disabled' || status === 'unavailable') return 'warning' as const;
  return 'neutral' as const;
}

function checkLabel(label: string, check?: RuntimeCheck) {
  if (!check) return `${label}: unknown`;
  const status = String(check.status || 'unknown').toLowerCase();
  if (label === 'Assistant model' && status === 'ready') return `${label}: found`;
  if (label === 'Assistant runtime' && status === 'ready') return `${label}: installed`;
  if (label === 'OpenMP workaround' && status === 'ready') return `${label}: enabled`;
  return `${label}: ${status}`;
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
  const preflightChecks = systemStatus?.preflight?.checks;
  const runtime = systemStatus?.runtime;
  const vlmCheck = preflightChecks?.vlm;
  const mobileSamCheck = preflightChecks?.mobileSam;
  const vlmUnavailable = Boolean(vlmCheck && String(vlmCheck.status).toLowerCase() !== 'ready');
  const diagnosticChecks = [
    ['Assistant', preflightChecks?.assistant],
    ['Assistant model', preflightChecks?.assistantModel],
    ['Assistant runtime', preflightChecks?.assistantRuntime],
    ['OpenMP workaround', preflightChecks?.openmp],
    ['MobileSAM', preflightChecks?.mobileSam],
    ['VLM', preflightChecks?.vlm],
  ].filter((item): item is [string, RuntimeCheck] => Boolean(item[1]));
  const systemStatuses = [
    {
      label: backendLabel(backendState),
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
      label: checkLabel('Assistant', preflightChecks?.assistant),
      tone: checkTone(preflightChecks?.assistant),
    },
    {
      label: checkLabel('Assistant model', preflightChecks?.assistantModel),
      tone: checkTone(preflightChecks?.assistantModel),
    },
    {
      label: checkLabel('Assistant runtime', preflightChecks?.assistantRuntime),
      tone: checkTone(preflightChecks?.assistantRuntime),
    },
    {
      label: checkLabel('OpenMP workaround', preflightChecks?.openmp),
      tone: checkTone(preflightChecks?.openmp),
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

          <div className="rounded-lg border border-white/10 bg-slate-950/30 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="inline-flex items-center gap-2 text-sm font-semibold text-white">
                  <Sparkles className="h-4 w-4 text-slate-300" aria-hidden="true" />
                  VLM explanations
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-300">
                  {vlmUnavailable
                    ? 'Optional VLM explanations are unavailable; SafeTrace will use rule-based explanations.'
                    : 'Adds natural-language explanations when an explanation model is available.'}
                </p>
              </div>
              <button
                className="focus-ring relative h-6 w-11 shrink-0 rounded-full border border-white/20 bg-slate-700 transition data-[checked=true]:bg-safety-teal disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
                role="switch"
                aria-checked={settings.vlmExplanations}
                aria-label="Toggle VLM explanations"
                data-checked={settings.vlmExplanations}
                disabled={vlmUnavailable}
                onClick={() => updateSettings({ vlmExplanations: !settings.vlmExplanations })}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                    settings.vlmExplanations ? 'left-5' : 'left-0.5'
                  }`}
                />
              </button>
            </div>
            {vlmCheck?.message ? (
              <p className="mt-2 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs leading-5 text-slate-200">
                {vlmCheck.message}
              </p>
            ) : null}
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
            {systemStatus?.build_mode || systemStatus?.runtime_layout ? (
              <div>
                <dt className="font-semibold text-slate-200">Runtime layout</dt>
                <dd>
                  {systemStatus.build_mode || 'unknown'} / {systemStatus.runtime_layout || 'unknown'}
                </dd>
              </div>
            ) : null}
            {backendMessage ? (
              <div>
                <dt className="font-semibold text-slate-200">Connection message</dt>
                <dd>{backendMessage}</dd>
              </div>
            ) : null}
            {runtime?.python?.executable ? (
              <div>
                <dt className="font-semibold text-slate-200">Python</dt>
                <dd className="break-all font-mono">
                  {runtime.python.version} - {runtime.python.executable}
                </dd>
              </div>
            ) : null}
            {runtime?.workingDirectory ? (
              <div>
                <dt className="font-semibold text-slate-200">Working directory</dt>
                <dd className="break-all font-mono">{runtime.workingDirectory}</dd>
              </div>
            ) : null}
            {runtime?.jobStorePath ? (
              <div>
                <dt className="font-semibold text-slate-200">Job store</dt>
                <dd className="break-all font-mono">{runtime.jobStorePath}</dd>
              </div>
            ) : null}
            {runtime?.chat ? (
              <div>
                <dt className="font-semibold text-slate-200">Assistant provider</dt>
                <dd>
                  {runtime.chat.provider || 'unknown'} / {runtime.chat.state || runtime.chat.status || 'unknown'}
                </dd>
              </div>
            ) : null}
            {runtime?.chat?.model_path ? (
              <div>
                <dt className="font-semibold text-slate-200">Assistant model path</dt>
                <dd className="break-all font-mono">{runtime.chat.model_path}</dd>
              </div>
            ) : null}
            {runtime?.openmp ? (
              <div>
                <dt className="font-semibold text-slate-200">OpenMP environment</dt>
                <dd>
                  KMP_DUPLICATE_LIB_OK={runtime.openmp.rawKmpDuplicateLibOk || 'unset'},
                  {' '}OMP_NUM_THREADS={runtime.openmp.ompNumThreads || 'unset'}
                </dd>
              </div>
            ) : null}
            {diagnosticChecks.length ? (
              <div>
                <dt className="font-semibold text-slate-200">Actionable diagnostics</dt>
                <dd>
                  <ul className="mt-1 space-y-1">
                    {diagnosticChecks.map(([label, check]) => (
                      <li key={label}>
                        <span className="font-semibold">{label}:</span> {check.message}
                        {check.actionHint ? <span> {check.actionHint}</span> : null}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ) : null}
            {mobileSamCheck?.message ? (
              <div>
                <dt className="font-semibold text-slate-200">MobileSAM note</dt>
                <dd>{mobileSamCheck.message}</dd>
              </div>
            ) : null}
            {vlmCheck?.message ? (
              <div>
                <dt className="font-semibold text-slate-200">VLM note</dt>
                <dd>{vlmCheck.message}</dd>
              </div>
            ) : null}
          </dl>
        </details>
      </div>
    </div>
  );
}
