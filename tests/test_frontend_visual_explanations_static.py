from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend-react" / "src" / path).read_text(encoding="utf-8")


def read_all_frontend_sources() -> str:
    src_root = ROOT / "frontend-react" / "src"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in src_root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )


def test_local_runtime_docs_use_venv_python_and_openmp_defaults():
    docs = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "docs/safetrace_local_validation.md",
            "docs/safetrace_assistant.md",
            "docs/safetrace_performance_troubleshooting.md",
            "docs/react_fastapi_backend_integration.md",
        )
    )

    assert ".venv\\Scripts\\python.exe -m uvicorn src.api.server:app" in docs
    assert "set KMP_DUPLICATE_LIB_OK=TRUE" in docs
    assert "set OMP_NUM_THREADS=1" in docs
    assert ".venv\\Scripts\\python.exe -c \"import sys; print(sys.executable); import llama_cpp; print('llama_cpp ok')\"" in docs
    assert "Safe local validation mode" in docs
    assert "set SAFETRACE_ANALYSIS_SAFE_MODE=true" in docs
    assert "set SAFETRACE_DEVICE=cpu" in docs
    assert "set SAFETRACE_MOBILESAM_ENABLED=false" in docs
    assert "set SAFETRACE_VLM_ENABLED=false" in docs
    assert "embeddingRequested=false" in docs
    assert "object/rule-based frame ranking" in docs
    assert "driver without seatbelt" in docs
    assert "MobileSAM can improve mask and evidence quality" in docs
    assert "SafeTrace_RC_MobileSAM_RuleBased" in docs
    assert "SafeTrace_RC_MobileSAM_LightweightVLM_Experimental" in docs
    assert "python -m uvicorn src.api.server:app" not in docs


def test_sidebar_uses_explicit_vlm_mode_selector():
    source = read_frontend("components/Sidebar.tsx")

    vite_config = (ROOT / "frontend-react" / "vite.config.ts").read_text(encoding="utf-8")

    assert "SafeTrace RC SafeMode frontend" in source
    assert "Build {FRONTEND_BUILD_TIME}" in source
    assert "__SAFETRACE_BUILD_TIME__" in source
    assert "__SAFETRACE_BUILD_TIME__" in vite_config
    assert "new Date().toISOString()" in vite_config
    assert "Visual explanations" in source
    assert "VLM explanation mode" in source
    assert "Rule-based" in source
    assert "Lightweight VLM (256M)" in source
    assert "Enhanced VLM (2B)" in source
    assert "Activate VLM" in source
    assert "Rule-based explanations active." in source
    assert "Rule-based explanations remain active." in source
    assert "Visual explanations are hidden. Turn on to choose rule-based or VLM explanations." in source
    assert "Lightweight VLM not installed. Rule-based explanations remain active." in source
    assert "Lightweight VLM unavailable." in source
    assert "Enhanced VLM not installed. Rule-based explanations remain active." in source
    assert "selected for the next analysis" in source
    assert "Evidence cards show" in source
    assert "using rule-based fallback" in source
    assert "Connect to local runtime to activate VLM. Rule-based explanations remain available." in source
    assert "VLM is disabled by configuration. Rule-based explanations remain active." in source
    assert "safeModeActive" in source
    assert "Safe local mode active" in source
    assert "Safe local mode with experimental MobileSAM" in source
    assert "Safe local mode with MobileSAM worker" in source
    assert "Experimental: MobileSAM worker + Lightweight VLM worker" in source
    assert "Experimental Lightweight VLM worker selected for the next analysis." in source
    assert "Rule-based fallback active." in source
    assert "Rule-based explanations only." in source
    assert "MobileSAM worker refinement enabled. Detector-box fallback used if the worker fails. VLM disabled." in source
    assert "MobileSAM worker refinement and Lightweight VLM worker explanations may run on selected evidence frames." in source
    assert "Experimental MobileSAM refinement may run on selected evidence frames. Rule-based fallback active; VLM disabled." in source
    assert "VLM/MobileSAM disabled for stability." in source
    assert "systemStatus?.vlm?.vlmSuppressedReason === 'safe_mode'" in source
    assert "showVisualExplanations ? (" in source
    assert "selectedProfile !== 'rule_based' ? (" in source
    assert "vlmGloballyDisabled" in source
    assert "|| vlmGloballyDisabled" in source
    assert "Rule-based: Fastest and lowest-resource option. Uses SafeTrace detection results and does not load a VLM." in source
    assert "Lightweight VLM (256M): Optional compact VLM for lower-spec devices." in source
    assert "Enhanced VLM (2B): Optional higher-quality VLM." in source
    assert "VLM explanation mode help" in source
    assert "Local VLM explanations are experimental and can be slower." in source
    assert "Use Rule-based for the fastest local analysis." in source
    assert "absolute left-1/2 top-7" not in source
    assert "w-72 -translate-x-1/2" not in source
    assert "disabled={vlmUnavailable}" not in source
    assert "onClick={() => updateSettings({ visualExplanations: !showVisualExplanations })}" in source
    assert "aria-label=\"Activate selected VLM explanation mode\"" in source


def test_app_uses_visual_toggle_for_display_and_vlm_profile_for_backend_vlm():
    source = read_frontend("App.tsx")

    assert "visualExplanations: true" in source
    assert "vlmProfile: vlmSettings.vlmProfile" in source
    assert "vlmEnabled: vlmSettings.vlmEnabled" in source
    assert "safetrace:vlm:selectedProfile" in source
    assert "safetrace:vlm:enabled" in source
    assert "enableVlm: shouldRequestVlm(settings)" in source
    assert "FRESH_BACKEND_HEARTBEAT_MS" in source
    assert "isBackendHeartbeatFresh(status)" in source
    assert "Analysis timed out because the backend heartbeat became stale" in source
    assert "Batch analysis timed out because the backend status stopped updating" in source
    assert "selectedProfile: settings.vlmProfile" in source
    assert "const backendProfile = systemStatus?.vlm?.selectedProfile" in source
    assert "persistVlmSettings(nextSettings)" in source
    assert "setSettings(nextSettings)" in source
    assert "showExplanations={settings.visualExplanations}" in source
    assert "BackendJobFailureError" in source
    assert "metricString(status.metrics, 'errorType')" in source
    assert "jobFailureDebugDetails(status)" in source
    assert "Analysis failed." in source
    assert "checkBackendHealth" in source
    assert "Job status could not be refreshed while the backend was still healthy." in source
    assert "status error" not in source.lower()


def test_analysis_service_supports_optional_vlm_settings_endpoint():
    source = read_frontend("services/analysisService.ts")

    assert "system/vlm/settings" in source
    assert "vlmProfile" in source
    assert "vlmEnabled" in source
    assert "VLM_ARTIFACT_PATTERN" in source
    assert "VLM_ROLE_LABEL_PATTERN" in source
    assert "VLM_PROMPT_ECHO_PATTERN" in source
    assert "async function readErrorMessage(response: Response)" in source
    assert "const raw = await response.text()" in source
    assert "JSON.parse(raw)" in source
    assert "const body = await response.json()" not in source


def test_safety_insights_dashboard_is_standalone_view():
    app_source = read_frontend("App.tsx")
    dashboard_source = read_frontend("components/SafetyInsightsDashboard.tsx")

    assert "SafetyInsightsDashboard" in app_source
    assert "activeView === 'insights'" in app_source
    assert "Safety Insights" in app_source
    assert "Cached analysis overview" in dashboard_source
    assert "Operational hotspots" in dashboard_source
    assert "Review queue" in dashboard_source
    assert "Recent analyses" in dashboard_source
    assert "Violation counts by type" in dashboard_source
    assert "Per-video results" in dashboard_source
    assert "buildSafetyInsightsCsv" in dashboard_source
    assert "buildSafetyInsightsMarkdown" in dashboard_source
    assert "buildSafetyInsightsJson" in dashboard_source
    assert "safetrace-safety-insights.csv" in dashboard_source
    assert "safetrace-safety-insights.md" in dashboard_source
    assert "safetrace-safety-insights.json" in dashboard_source
    assert "Raw uploaded videos and copied evidence images are not stored" in dashboard_source


def test_frontend_error_handling_reads_response_body_once():
    analysis_source = read_frontend("services/analysisService.ts")
    chat_source = read_frontend("services/chatService.ts")

    assert "throw new Error(await readErrorMessage(response))" in analysis_source
    assert "async function readChatErrorMessage(response: Response)" in chat_source
    assert "throw new Error(await readChatErrorMessage(response))" in chat_source
    assert "const raw = await response.text()" in chat_source
    assert "JSON.parse(raw)" in chat_source
    assert "const body = await response.json()" not in chat_source


def test_evidence_cards_use_two_explanation_source_labels():
    source = read_frontend("components/FrameEvidenceCard.tsx")
    service_source = read_frontend("services/analysisService.ts")
    details_source = read_frontend("components/TechnicalDetails.tsx")

    assert "'VLM explanation'" in source
    assert "'Lightweight VLM explanation'" in source
    assert "'Enhanced VLM explanation'" in source
    assert "'Rule-based explanation'" in source
    assert "Selected because" in source
    assert "Detector-box fallback used" in source
    assert "VLM fallback:" in source
    assert "lightweightVlmFallbackReason" in source
    assert "mobileSamRefinement" in source
    assert "mobileSamRefinement" in details_source
    assert "lightweightVlmExplanation" in source
    assert "lightweightVlmExplanation" in details_source
    assert "selectionReason" in source
    assert "rankingReason" in service_source
    assert "selectedFor" in service_source
    assert "VLM explanation: local provider" not in source
    assert "VLM explanation: Ollama" not in source


def test_assistant_has_limited_runtime_fallback_and_in_car_prompts():
    source = read_frontend("components/SafeTraceAssistant.tsx")

    assert "Was the driver wearing a seatbelt?" in source
    assert "Is the driver using a phone while driving?" in source
    assert "isLimitedFallbackAvailable" in source
    assert "Limited SafeTrace help is available without llama.cpp" in source
    assert "Runtime diagnostics" in source
    assert "Backend Python" in source
    assert "Expected .venv Python" in source
    assert "llama_cpp import" in source
    assert "<textarea" in source
    assert "Shift+Enter for a new line" in source
    assert "event.key === 'Enter' && !event.shiftKey" in source
    assert "flex-[1_1_65%]" in source
    assert "overflow-y-auto overflow-x-hidden" in source
    assert "[overflow-wrap:anywhere]" in source
    assert "canSubmit" in source
    assert "Selected job" in source
    assert "Copy selected job ID" in source


def test_frontend_surfaces_copyable_job_identifiers():
    summary_source = read_frontend("components/AnalysisSummary.tsx")
    media_source = read_frontend("components/SelectedMediaViewer.tsx")
    queue_source = read_frontend("components/VideoQueue.tsx")
    details_source = read_frontend("components/TechnicalDetails.tsx")
    app_source = read_frontend("App.tsx")
    helper_source = read_frontend("utils/jobIds.ts")

    assert "Result job" in summary_source
    assert "Copy job ID" in summary_source
    assert "formatShortJobId(jobId)" in summary_source
    assert "Copy selected media job ID" in media_source
    assert "Copy queue job ID" in queue_source
    assert "Copy batch job ID" in app_source
    assert "jobId={analysisResult.jobId}" in app_source
    assert "jobId={analysisResult?.jobId ?? selectedBatchJobId ?? jobStatus?.jobId}" in app_source
    assert "Job ID" in details_source
    assert "copyJobIdToClipboard" in helper_source
    assert "job_..." in helper_source


def test_progress_card_shows_elapsed_and_heartbeat_copy():
    source = read_frontend("components/AnalysisProgress.tsx")

    assert "Elapsed" in source
    assert "Backend heartbeat" in source
    assert "Still working locally" in source
    assert "startedAt" in source
    assert "heartbeatAt" in source


def test_frontend_source_does_not_display_raw_vlm_artifacts():
    source = read_all_frontend_sources()

    assert "User:" not in source
    assert "Assistant:" not in source
    assert "<global-img>" not in source
    assert "<row_" not in source
    assert "body stream already read" not in source
