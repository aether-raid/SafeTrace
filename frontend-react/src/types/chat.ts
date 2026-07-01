export type ChatAvailabilityState = 'available' | 'disabled' | 'missing_model' | 'missing_runtime' | 'loading' | 'unavailable';

export type ChatStatus = {
  enabled: boolean;
  available: boolean;
  state: ChatAvailabilityState;
  status: ChatAvailabilityState;
  enabled_mode: string;
  provider: string;
  model?: string | null;
  model_path?: string | null;
  model_exists?: boolean | null;
  runtime_available?: boolean | null;
  speed_profile?: string | null;
  warmup_on_open?: boolean | null;
  fallback_available?: boolean | null;
  fallback_label?: string | null;
  runtime_diagnostics?: Record<string, unknown> | null;
  python_executable?: string | null;
  expected_venv_python?: string | null;
  running_in_expected_venv?: boolean | null;
  llama_cpp_import_status?: string | null;
  llama_cpp_spec_found?: boolean | null;
  llama_cpp_import_error_type?: string | null;
  llama_cpp_import_error_message?: string | null;
  setup_command?: string | null;
  restart_required?: string | null;
  reason?: string | null;
  action_hint?: string | null;
  message: string;
};

export type ChatRequest = {
  message: string;
  job_id?: string;
  batch_id?: string;
  include_current_result?: boolean;
};

export type ChatResponse = {
  answer: string;
  sources: string[];
  safeTraceOnly: boolean;
  modelProvider: string;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
};
