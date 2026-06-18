import type { ReactNode } from 'react';

type AppShellProps = {
  sidebar: ReactNode;
  rightPanel: ReactNode;
  children: ReactNode;
};

export function AppShell({ sidebar, rightPanel, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[#f5f7fb] text-slate-950">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="border-b border-slate-200 bg-ink text-white lg:border-b-0 lg:border-r lg:border-slate-800">
          {sidebar}
        </aside>

        <main className="min-w-0">
          <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-7 lg:py-6">
            {children}
          </div>
        </main>

        <aside className="hidden border-l border-slate-200 bg-white xl:block">
          {rightPanel}
        </aside>
      </div>
    </div>
  );
}
