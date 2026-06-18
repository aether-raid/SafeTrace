import { Search, LoaderCircle, Play, RotateCcw } from 'lucide-react';
import type { FormEvent } from 'react';

// We removed activeTab and onTabChange from the props
type QueryTabsProps = {
  query: string;
  isLoading: boolean;
  hasResult: boolean;
  onQueryChange: (query: string) => void;
  onAnalyze: () => void;
  onReset: () => void;
};

// Combined a few examples into one simple list
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
  onQueryChange,
  onAnalyze,
  onReset,
}: QueryTabsProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onAnalyze();
  }

  return (
    <form className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft" onSubmit={handleSubmit}>
      <div>
        <label className="block text-sm font-semibold text-slate-950" htmlFor="tab-query">
          Search Video
        </label>
        <div className="mt-2 flex flex-col gap-3 lg:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              id="tab-query"
              className="focus-ring h-12 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-4 text-base text-slate-950 placeholder:text-slate-400"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Describe a scene, person, or object to search for..."
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

        <div className="mt-3 flex flex-wrap gap-2">
          <span className="text-xs font-semibold text-slate-500 mt-1">Try:</span>
          {QUERY_EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => onQueryChange(example)}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 transition hover:border-safety-blue hover:text-safety-blue"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}