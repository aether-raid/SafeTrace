import { Cpu, Gauge, HelpCircle, Layers3, ShieldCheck, SlidersHorizontal, Sparkles } from 'lucide-react';
import type {
  AnalysisSettings,
  BackendConnectionState,
  BackendModelStatus,
  DeviceMode,
  RuntimeCheck,
  SystemStatus,
  SystemVlmStatus,
  VlmExplanationProfileId,
  VlmProfileStatus,
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

type ResolvedVlmProfile = {
  id: VlmExplanationProfileId;
  label: string;
  installed: boolean;
  available: boolean;
  requiresActivation: boolean;
  path?: string | null;
  message?: string | null;
};

const VLM_PROFILE_LABELS: Record<VlmExplanationProfileId, string> = {
  rule_based: 'Rule-based',
  lightweight_256m: 'Lightweight VLM (256M)',
  enhanced_2b: 'Enhanced VLM (2B)',
};

const VLM_PROFILE_ORDER: VlmExplanationProfileId[] = ['rule_based', 'lightweight_256m', 'enhanced_2b'];

const VLM_HELP_LINES = [
  'Rule-based: Fastest and lowest-resource option. Uses SafeTrace detection results and does not load a VLM. This deterministic fallback is the default.',
  'Lightweight VLM (256M): Optional compact VLM for lower-spec devices. Uses the local SmolVLM profile for image-aware explanations when generation succeeds; falls back to rule-based explanations if unavailable.',
  'Enhanced VLM (2B): Optional higher-quality VLM. Uses the larger local SmolVLM profile for richer explanations with more RAM/VRAM; falls back to rule-based explanations if unavailable.',
];

declare const __SAFETRACE_BUILD_TIME__: string;

const FRONTEND_RELEASE_LABEL = 'SafeTrace RC SafeMode frontend';
const FRONTEND_BUILD_TIME = __SAFETRACE_BUILD_TIME__;

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
  if (status.status === 'ready' || status.status === 'available') return 'success' as const;
  if (status.status === 'missing') return 'danger' as const;
  return 'warning' as const;
}

function modelLabel(label: string, status?: BackendModelStatus) {
  if (!status) return `${label} unknown`;
  if (status.status === 'ready') return `${label} ready`;
  if (status.status === 'available') return `${label} available`;
  if (status.status === 'missing') return `${label} missing`;
  if (status.status === 'missing_checkpoint') return `${label} missing checkpoint`;
  if (status.status === 'missing_runtime') return `${label} missing runtime`;
  if (status.status === 'disabled') return `${label} disabled`;
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
  if (
    status === 'warning'
    || status === 'disabled'
    || status === 'missing_checkpoint'
    || status === 'missing_runtime'
    || status === 'unavailable'
  ) return 'warning' as const;
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

function checkAvailable(check?: RuntimeCheck) {
  const status = String(check?.status || '').toLowerCase();
  return status === 'ready' || status === 'available';
}

function modelAvailable(status?: BackendModelStatus) {
  return status?.status === 'ready' || status?.status === 'available';
}

function isVlmProfileId(value: string | undefined): value is VlmExplanationProfileId {
  return Boolean(value && VLM_PROFILE_ORDER.includes(value as VlmExplanationProfileId));
}

function resolveProfileStatus(profile: VlmProfileStatus | undefined, fallback: ResolvedVlmProfile): ResolvedVlmProfile {
  if (!profile) return fallback;
  return {
    ...fallback,
    label: fallback.label,
    installed: Boolean(profile.installed ?? profile.available ?? fallback.installed),
    available: Boolean(profile.available ?? profile.installed ?? fallback.available),
    requiresActivation: Boolean(profile.requiresActivation ?? fallback.requiresActivation),
    path: profile.path ?? fallback.path,
    message: profile.message ?? fallback.message,
  };
}

function resolveVlmProfiles(systemStatus: SystemStatus | null, legacyVlmAvailable: boolean): ResolvedVlmProfile[] {
  const backendProfiles = systemStatus?.vlm?.profiles ?? [];
  const byId = new Map<string, VlmProfileStatus>(backendProfiles.map((profile) => [profile.id, profile]));

  return VLM_PROFILE_ORDER.map((id) => {
    const fallback: ResolvedVlmProfile = {
      id,
      label: VLM_PROFILE_LABELS[id],
      installed: id === 'rule_based' || (id === 'enhanced_2b' && !backendProfiles.length && legacyVlmAvailable),
      available: id === 'rule_based' || (id === 'enhanced_2b' && !backendProfiles.length && legacyVlmAvailable),
      requiresActivation: id !== 'rule_based',
    };

    return resolveProfileStatus(byId.get(id), fallback);
  });
}

function vlmStatusMessage({
  selectedProfile,
  selectedProfileStatus,
  vlmEnabled,
  backendConnected,
  vlmGloballyDisabled,
  backendVlmStatus,
  lightweightVlmWorkerEnabled,
}: {
  selectedProfile: VlmExplanationProfileId;
  selectedProfileStatus: ResolvedVlmProfile;
  vlmEnabled: boolean;
  backendConnected: boolean;
  vlmGloballyDisabled: boolean;
  backendVlmStatus?: SystemVlmStatus | null;
  lightweightVlmWorkerEnabled: boolean;
}) {
  if (selectedProfile === 'rule_based') return 'Rule-based explanations active.';
  if (vlmGloballyDisabled) return 'VLM is disabled by configuration. Rule-based explanations remain active.';
  if (!backendConnected) return 'Connect to local runtime to activate VLM. Rule-based explanations remain available.';

  const available = selectedProfileStatus.available;
  const installed = selectedProfileStatus.installed;
  const backendActualMode = String(backendVlmStatus?.actualExplanationMode || '').toLowerCase();
  const fallbackReason = backendVlmStatus?.fallbackReason || selectedProfileStatus.message;
  const label = selectedProfile === 'lightweight_256m' ? 'Lightweight VLM' : 'Enhanced VLM';
  const evidenceLabel = selectedProfile === 'lightweight_256m'
    ? 'Lightweight VLM explanation'
    : 'Enhanced VLM explanation';
  if (selectedProfile === 'lightweight_256m') {
    if (!installed) return 'Lightweight VLM not installed. Rule-based explanations remain active.';
    if (!available) return `Lightweight VLM unavailable. ${fallbackReason || 'Rule-based explanations remain active.'}`;
    if (lightweightVlmWorkerEnabled && vlmEnabled && backendActualMode === selectedProfile) {
      return 'Experimental Lightweight VLM worker selected for the next analysis. Evidence cards show "Lightweight VLM explanation" only when the worker succeeds; rule-based fallback remains active.';
    }
    if (vlmEnabled && backendActualMode === selectedProfile) {
      return `${label} selected for the next analysis. Evidence cards show "${evidenceLabel}" only when generation succeeds; otherwise they show rule-based fallback.`;
    }
    if (vlmEnabled && backendActualMode === 'rule_based') {
      return `${label} requested, but backend is using rule-based fallback. ${fallbackReason || 'Check local VLM runtime and assets.'}`;
    }
    return 'Lightweight VLM available but inactive.';
  }

  if (!installed) return 'Enhanced VLM not installed. Rule-based explanations remain active.';
  if (!available) return `Enhanced VLM unavailable. ${fallbackReason || 'Rule-based explanations remain active.'}`;
  if (vlmEnabled && backendActualMode === selectedProfile) {
    return `${label} selected for the next analysis. Evidence cards show "${evidenceLabel}" only when generation succeeds; otherwise they show rule-based fallback.`;
  }
  if (vlmEnabled && backendActualMode === 'rule_based') {
    return `${label} requested, but backend is using rule-based fallback. ${fallbackReason || 'Check local VLM runtime and assets.'}`;
  }
  return 'Enhanced VLM available but inactive.';
}

function vlmStatusTone(message: string) {
  if (message.includes('using rule-based fallback') || message.includes('unavailable')) return 'warning' as const;
  if (message.includes('inactive.')) return 'info' as const;
  if (message.includes('selected for the next analysis')) return 'success' as const;
  if (message.includes('worker selected')) return 'success' as const;
  if (message.includes('not installed') || message.includes('Connect to local runtime')) return 'warning' as const;
  return 'neutral' as const;
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
  const safeModeActive = Boolean(
    systemStatus?.safeMode
    || runtime?.analysis?.safeMode
    || systemStatus?.vlm?.vlmSuppressedReason === 'safe_mode',
  );
  const vlmCheck = preflightChecks?.vlm;
  const visualExplanationCheck = preflightChecks?.visualExplanations ?? runtime?.visual_explanations;
  const mobileSamCheck = preflightChecks?.mobileSam;
  const mobileSamDetails = systemStatus?.models.mobileSam?.details;
  const safeModeMobileSamAllowed = Boolean(
    runtime?.analysis?.safeModeMobileSamAllowed
    || mobileSamDetails?.safeModeMobileSamAllowed,
  );
  const mobileSamWorkerEnabled = Boolean(
    runtime?.analysis?.mobileSamWorkerEnabled
    || mobileSamDetails?.mobileSamWorkerEnabled,
  );
  const lightweightVlmWorkerEnabled = Boolean(
    runtime?.analysis?.lightweightVlmWorkerEnabled
    || systemStatus?.vlm?.lightweightVlmWorkerEnabled
    || systemStatus?.models.vlm?.details?.lightweightVlmWorkerEnabled,
  );
  const combinedWorkerExperiment = Boolean(mobileSamWorkerEnabled && lightweightVlmWorkerEnabled);
  const showVisualExplanations = settings.visualExplanations ?? settings.vlmExplanations ?? true;
  const legacyVlmAvailable = Boolean((vlmCheck && checkAvailable(vlmCheck)) || modelAvailable(systemStatus?.models.vlm));
  const vlmProfiles = resolveVlmProfiles(systemStatus, legacyVlmAvailable);
  const selectedProfile = isVlmProfileId(settings.vlmProfile) ? settings.vlmProfile : 'rule_based';
  const selectedProfileStatus = vlmProfiles.find((profile) => profile.id === selectedProfile) ?? vlmProfiles[0];
  const backendConnected = backendState === 'connected';
  const vlmGloballyDisabled = systemStatus?.models.vlm?.status === 'disabled'
    || String(systemStatus?.vlm?.message || '').includes('disabled by configuration')
    || (safeModeActive && !lightweightVlmWorkerEnabled);
  const selectedProfileAvailable = selectedProfileStatus.available;
  const vlmActivationEnabled = selectedProfile !== 'rule_based' && Boolean(settings.vlmEnabled);
  const vlmActivationActive = backendConnected
    && selectedProfileAvailable
    && vlmActivationEnabled
    && !vlmGloballyDisabled
    && Boolean(systemStatus?.vlm?.active)
    && systemStatus?.vlm?.selectedProfile === selectedProfile;
  const activationToggleDisabled = selectedProfile === 'rule_based' || !backendConnected || !selectedProfileAvailable || vlmGloballyDisabled;
  const vlmMessage = vlmStatusMessage({
    selectedProfile,
    selectedProfileStatus,
    vlmEnabled: vlmActivationActive,
    backendConnected,
    vlmGloballyDisabled,
    backendVlmStatus: systemStatus?.vlm,
    lightweightVlmWorkerEnabled,
  });
  const diagnosticChecks = [
    ['Assistant', preflightChecks?.assistant],
    ['Assistant model', preflightChecks?.assistantModel],
    ['Assistant runtime', preflightChecks?.assistantRuntime],
    ['OpenMP workaround', preflightChecks?.openmp],
    ['Visual explanations', visualExplanationCheck],
    ['MobileSAM', preflightChecks?.mobileSam],
    ['VLM provider', preflightChecks?.vlm],
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
      label: safeModeActive ? 'Safe local mode active' : 'Standard analysis mode',
      tone: safeModeActive ? 'warning' as const : 'info' as const,
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
      label: showVisualExplanations ? 'Visual explanations: enabled' : 'Visual explanations: hidden',
      tone: showVisualExplanations ? 'success' as const : 'neutral' as const,
    },
    {
      label: `VLM explanation mode: ${VLM_PROFILE_LABELS[selectedProfile]}`,
      tone: vlmStatusTone(vlmMessage),
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
          <p className="mt-1 text-[11px] leading-4 text-slate-400">
            {FRONTEND_RELEASE_LABEL} · Build {FRONTEND_BUILD_TIME}
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Analysis controls
        </div>

        <div className="space-y-5">
          {safeModeActive ? (
            <div className="rounded-lg border border-amber-300/40 bg-amber-400/10 p-3 text-xs leading-5 text-amber-100">
              <p className="font-semibold text-amber-50">
                {combinedWorkerExperiment
                  ? 'Experimental: MobileSAM worker + Lightweight VLM worker'
                  : mobileSamWorkerEnabled
                  ? 'Safe local mode with MobileSAM worker'
                  : safeModeMobileSamAllowed
                    ? 'Safe local mode with experimental MobileSAM'
                    : 'Safe local mode active'}
              </p>
              <p className="mt-1">
                {combinedWorkerExperiment ? 'Rule-based fallback active.' : 'Rule-based explanations only.'}
              </p>
              <p>
                {combinedWorkerExperiment
                  ? 'MobileSAM worker refinement and Lightweight VLM worker explanations may run on selected evidence frames. Rule-based fallback active.'
                  : mobileSamWorkerEnabled
                  ? 'MobileSAM worker refinement enabled. Detector-box fallback used if the worker fails. VLM disabled.'
                  : safeModeMobileSamAllowed
                  ? 'Experimental MobileSAM refinement may run on selected evidence frames. Rule-based fallback active; VLM disabled.'
                  : 'VLM/MobileSAM disabled for stability.'}
              </p>
            </div>
          ) : null}

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
                  Visual explanations
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-300">
                  {showVisualExplanations
                    ? 'Visual explanations are on. Choose rule-based or an activated local VLM mode.'
                    : 'Visual explanations are hidden. Turn on to choose rule-based or VLM explanations.'}
                </p>
              </div>
              <button
                className="focus-ring relative h-6 w-11 shrink-0 rounded-full border border-white/20 bg-slate-700 transition data-[checked=true]:bg-safety-teal"
                type="button"
                role="switch"
                aria-checked={showVisualExplanations}
                aria-label="Toggle visual explanations"
                data-checked={showVisualExplanations}
                onClick={() => updateSettings({ visualExplanations: !showVisualExplanations })}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                    showVisualExplanations ? 'left-5' : 'left-0.5'
                  }`}
                />
              </button>
            </div>

            {showVisualExplanations ? (
              <div className="mt-4 space-y-3">
                <label className="block">
                  <span className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-slate-200">Mode</span>
                  <span className="sr-only">VLM explanation mode</span>
                  <select
                    className="focus-ring w-full rounded-lg border border-white/15 bg-slate-900 px-3 py-2 text-sm text-white"
                    value={selectedProfile}
                    onChange={(event) => {
                      const nextProfile = event.target.value as VlmExplanationProfileId;
                      updateSettings({
                        vlmProfile: nextProfile,
                        vlmEnabled: nextProfile === 'rule_based' ? false : selectedProfile === 'rule_based' ? false : settings.vlmEnabled,
                      });
                    }}
                  >
                    {vlmProfiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {profile.label}
                      </option>
                    ))}
                  </select>
                  <details className="mt-2 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs leading-5 text-slate-200">
                    <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-1.5 rounded-md text-xs font-semibold text-slate-100">
                      <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
                      VLM explanation mode help
                    </summary>
                    <div className="mt-2 space-y-2 text-slate-300">
                      {VLM_HELP_LINES.map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                    </div>
                  </details>
                </label>

                {selectedProfile !== 'rule_based' ? (
                  <div className="space-y-2">
                    <p className="rounded-lg border border-amber-300/40 bg-amber-400/10 px-2 py-1.5 text-xs leading-5 text-amber-100">
                      Local VLM explanations are experimental and can be slower. Use Rule-based for the fastest local analysis.
                    </p>
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase text-slate-200">Activate VLM</p>
                        <p className="mt-0.5 text-xs leading-5 text-slate-300">
                          Turn on only when you want local VLM explanations.
                        </p>
                      </div>
                      <button
                        className="focus-ring relative h-6 w-11 shrink-0 rounded-full border border-white/20 bg-slate-700 transition data-[checked=true]:bg-safety-teal disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        role="switch"
                        aria-checked={vlmActivationEnabled}
                        aria-label="Activate selected VLM explanation mode"
                        data-checked={vlmActivationEnabled}
                        disabled={activationToggleDisabled}
                        onClick={() => updateSettings({ vlmEnabled: !settings.vlmEnabled })}
                      >
                        <span
                          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                            vlmActivationEnabled ? 'left-5' : 'left-0.5'
                          }`}
                        />
                      </button>
                    </div>
                  </div>
                ) : null}

                <p className={`rounded-lg border px-2 py-1.5 text-xs leading-5 ${
                  vlmStatusTone(vlmMessage) === 'success'
                    ? 'border-emerald-300/40 bg-emerald-400/10 text-emerald-100'
                    : vlmStatusTone(vlmMessage) === 'warning'
                      ? 'border-amber-300/40 bg-amber-400/10 text-amber-100'
                      : 'border-white/10 bg-white/5 text-slate-200'
                }`}
                >
                  {vlmMessage}
                </p>
                {visualExplanationCheck?.message ? (
                  <p className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs leading-5 text-slate-200">
                    {visualExplanationCheck.message}
                  </p>
                ) : null}
                {systemStatus?.vlm?.message ? (
                  <p className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs leading-5 text-slate-200">
                    {systemStatus.vlm.message}
                  </p>
                ) : null}
                {vlmCheck?.message ? (
                  <p className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs leading-5 text-slate-200">
                    {vlmCheck.message}
                    {vlmCheck.actionHint ? <span> {vlmCheck.actionHint}</span> : null}
                  </p>
                ) : null}
              </div>
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
