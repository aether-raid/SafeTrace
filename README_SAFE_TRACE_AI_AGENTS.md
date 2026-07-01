# SafeTrace AI Agent Workflow

This folder contains starter Markdown files for a simple AI-agent development workflow.

## Files

- `AGENTS.md`
  - Repo-level rules for Codex.
  - Place this in the repository root.

- `PLANNER_AGENT_PROMPT.md`
  - Prompt for generating implementation specs.
  - Place this in `codex_prompts/`.

- `CODER_AGENT_PROMPT.md`
  - Prompt for implementation.
  - Place this in `codex_prompts/`.

- `TESTER_AGENT_PROMPT.md`
  - Prompt for test generation and test execution.
  - Place this in `codex_prompts/`.

- `REVIEWER_AGENT_PROMPT.md`
  - Read-only review prompt.
  - Place this in `codex_prompts/`.

- `FEATURE_REQUEST_TEMPLATE.md`
  - Template for `.ai-pipeline/000_intake/FEATURE_REQUEST.md`.

- `PLANNER_AGENT_PROCEDURE.md`
  - Step-by-step procedure for using ChatGPT first as the planner before Codex verifies the plan.

## Recommended repository placement

```text
SafeTrace/
  AGENTS.md

  codex_prompts/
    PLANNER_AGENT_PROMPT.md
    CODER_AGENT_PROMPT.md
    TESTER_AGENT_PROMPT.md
    REVIEWER_AGENT_PROMPT.md

  .ai-pipeline/
    000_intake/
      FEATURE_REQUEST.md
    001_planner/
    002_coder/
    003_tester/
    004_reviewer/
```

## Recommended sequence

1. Write the vague request into `.ai-pipeline/000_intake/FEATURE_REQUEST.md`.
2. Use ChatGPT to generate planner files.
3. Save planner files into `.ai-pipeline/001_planner/`.
4. Ask Codex Planner Agent to verify the planner files against the real repo.
5. Ask Codex Coder Agent to implement.
6. Ask Codex Tester Agent to test.
7. Ask Codex Reviewer Agent to review the diff.
8. Shane decides whether to merge.
