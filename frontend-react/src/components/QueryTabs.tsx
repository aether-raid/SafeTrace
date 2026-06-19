import { LoaderCircle, SendHorizontal, RotateCcw } from 'lucide-react';
import type { FormEvent } from 'react';

type QueryTabsProps = {
  query: string;
  isLoading: boolean;
  hasResult: boolean;
  canAnalyze: boolean;
  disabledReason?: string;
  previewMode?: boolean;
  onQueryChange: (query: string) => void;
  onAnalyze: () => void;
  onReset: () => void;
};

const QUERY_EXAMPLES = [
  'worker without helmet',
  'person near machinery',
  'someone falling',
  'damaged equipment',
];

export function QueryTabs({
  query,
  isLoading,
  hasResult,
  canAnalyze,
  disabledReason,
  previewMode = false,
  onQueryChange,
  onAnalyze,
  onReset,
}: QueryTabsProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onAnalyze();
  }

  return (
    <form className="rounded-2xl border border-slate-200 bg-white p-4 shadow-lg" onSubmit={handleSubmit}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="relative min-w-0 flex-1">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <label className="block text-sm font-semibold text-slate-950" htmlFor="tab-query">
                Enter Query
              </label>
              {previewMode ? (
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-700">
                  Preview Mode
                </span>
              ) : null}
            </div>
            <input
              id="tab-query"
              className="focus-ring h-12 w-full rounded-lg border border-slate-200 bg-slate-50 px-4 text-base text-slate-950 placeholder:text-slate-400 focus:bg-white"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Ask me to analyze the scene..."
            />
          </div>

          <div className="flex gap-2">
            <button
              className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-safety-blue px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
              type="submit"
              disabled={isLoading || !canAnalyze}
              title={!canAnalyze ? disabledReason : undefined}
            >
              {isLoading ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <SendHorizontal className="h-4 w-4" />
              )}
              {isLoading ? 'Thinking...' : 'Send'}
            </button>
            
            <button
              className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
              type="button"
              disabled={isLoading || !hasResult}
              onClick={onReset}
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
        </div>

        {!canAnalyze && disabledReason ? (
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
            {disabledReason}
          </p>
        ) : null}

        <div className="mt-3 flex flex-wrap gap-2">
          <span className="text-xs font-semibold text-slate-400 mt-1">Suggested:</span>
          {QUERY_EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => onQueryChange(example)}
              className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 transition hover:border-safety-blue hover:text-safety-blue"
            >
              {example}
            </button>
          ))}
        </div>
    </form>
  );
}
