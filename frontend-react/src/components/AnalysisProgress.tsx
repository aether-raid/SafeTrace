import { CheckCircle2, LoaderCircle } from 'lucide-react';

type AnalysisProgressProps = {
  steps: string[];
  activeStep: number;
};

export function AnalysisProgress({ steps, activeStep }: AnalysisProgressProps) {
  return (
    <section className="rounded-lg border border-blue-200 bg-blue-50 p-5 text-blue-950 shadow-soft">
      <div className="flex items-start gap-3">
        <LoaderCircle className="mt-0.5 h-5 w-5 shrink-0 animate-spin" aria-hidden="true" />
        <div>
          <h2 className="text-sm font-bold">Analyzing selected footage...</h2>
          <p className="mt-1 text-sm leading-6">Sampling frames and preparing an evidence-backed report.</p>
        </div>
      </div>

      <ol className="mt-5 grid gap-3 md:grid-cols-5">
        {steps.map((step, index) => {
          const isComplete = index < activeStep;
          const isActive = index === activeStep;

          return (
            <li
              key={step}
              className={`rounded-lg border p-3 text-sm ${
                isComplete
                  ? 'border-emerald-200 bg-white text-emerald-800'
                  : isActive
                    ? 'border-blue-300 bg-white text-blue-900'
                    : 'border-blue-100 bg-blue-100/60 text-blue-700'
              }`}
            >
              <div className="mb-2 flex items-center gap-2">
                {isComplete ? (
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${isActive ? 'animate-pulse bg-blue-600' : 'bg-blue-300'}`}
                  />
                )}
                <span className="text-xs font-semibold uppercase">Step {index + 1}</span>
              </div>
              <p className="font-semibold leading-5">{step}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
