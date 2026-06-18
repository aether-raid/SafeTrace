import { LoaderCircle, Play, RotateCcw, Search } from 'lucide-react';
import type { FormEvent } from 'react';

type QueryPanelProps = {
  query: string;
  isLoading: boolean;
  hasResult: boolean;
  onQueryChange: (query: string) => void;
  onAnalyze: () => void;
  onReset: () => void;
};

export function QueryPanel({
  query,
  isLoading,
  hasResult,
  onQueryChange,
  onAnalyze,
  onReset,
}: QueryPanelProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onAnalyze();
  }

  return (
    <form className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft" onSubmit={handleSubmit}>
      <label className="block text-sm font-semibold text-slate-950" htmlFor="safety-query">
        Safety query
      </label>
      <div className="mt-3 flex flex-col gap-3 lg:flex-row">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            id="safety-query"
            className="focus-ring h-12 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-4 text-base text-slate-950 placeholder:text-slate-400"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Describe the safety condition to check"
          />
        </div>

        <div className="flex gap-2">
          <button
            className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-safety-blue px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            type="submit"
            disabled={isLoading}
          >
            {isLoading ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="h-4 w-4" aria-hidden="true" />
            )}
            {isLoading ? 'Analyzing...' : 'Analyze'}
          </button>

          <button
            className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
            type="button"
            disabled={isLoading || !hasResult}
            onClick={onReset}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Reset
          </button>
        </div>
      </div>
    </form>
  );
}
