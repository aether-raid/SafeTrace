import clsx from 'clsx';
import { useRef, useState, type DragEvent } from 'react';
import { UploadCloud } from 'lucide-react';
import type { MediaItem } from '../types/analysis';

type UploadPanelProps = {
  media: MediaItem | null;
  onFileSelected: (file: File) => void;
  disabled?: boolean;
};

export function UploadPanel({ media, onFileSelected, disabled = false }: UploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    if (disabled) return;
    const file = files?.[0];
    if (file) {
      onFileSelected(file);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    handleFiles(event.dataTransfer.files);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-950">Selected media</h2>
      </div>

      <div className="mx-auto w-full max-w-2xl">
        <div
          className={clsx(
            'flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed px-4 py-5 text-center transition',
            disabled
              ? 'cursor-not-allowed border-slate-200 bg-slate-50 opacity-70'
              : isDragging
                ? 'border-safety-blue bg-blue-50'
                : 'border-slate-300 bg-white hover:border-safety-blue hover:bg-slate-50',
          )}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!disabled) setIsDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
        >
          <UploadCloud className="h-6 w-6 text-slate-400" aria-hidden="true" />
          <p className="mt-2 text-sm font-semibold text-slate-800">Select local media</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {disabled ? 'Connect to the SafeTrace backend before selecting media.' : 'Drop a video or image, or browse from this device.'}
          </p>
          <button
            className="focus-ring mt-3 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
            type="button"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
          >
            Browse files
          </button>
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            accept="image/*,video/*"
            disabled={disabled}
            onChange={(event) => handleFiles(event.target.files)}
          />
        </div>
        {media ? (
          <p className="mt-3 truncate text-xs font-medium text-slate-500">Current selection: {media.filename}</p>
        ) : null}
      </div>


    </section>
  );
}
