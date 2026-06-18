import { FileImage, FileVideo, HardDrive, UploadCloud } from 'lucide-react';
import clsx from 'clsx';
import { useRef, useState, type DragEvent } from 'react';
import type { MediaItem } from '../types/analysis';
import { StatusBadge } from './StatusBadge';

type UploadPanelProps = {
  media: MediaItem;
  onFileSelected: (file: File) => void;
};

function getMediaTypeLabel(media: MediaItem) {
  return media.type === 'video' ? 'Video' : 'Image';
}

export function UploadPanel({ media, onFileSelected }: UploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const Icon = media.type === 'video' ? FileVideo : FileImage;

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) {
      onFileSelected(file);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-950">Selected media</h2>
          <p className="mt-1 text-sm text-slate-500">Choose sample media or select a local file for analysis preview.</p>
        </div>
        <StatusBadge label={media.source === 'local' ? 'Local file selected' : 'Ready for analysis'} tone="success" />
      </div>

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-safety-blue text-white">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p className="break-words text-sm font-semibold text-slate-950">{media.filename}</p>
              <div className="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-3">
                <span>Type: {getMediaTypeLabel(media)}</span>
                <span>Size: {media.sizeLabel}</span>
                <span>{media.duration ? `Duration: ${media.duration}` : 'Single frame'}</span>
              </div>
              {media.previewUrl ? (
                <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white">
                  {media.type === 'video' ? (
                    <video className="h-40 w-full bg-slate-950 object-cover" src={media.previewUrl} controls muted />
                  ) : (
                    <img className="h-40 w-full object-cover" src={media.previewUrl} alt="" />
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div
          className={clsx(
            'flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed px-4 py-5 text-center transition',
            isDragging ? 'border-safety-blue bg-blue-50' : 'border-slate-300 bg-white hover:border-safety-blue hover:bg-slate-50',
          )}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
        >
          <UploadCloud className="h-6 w-6 text-slate-400" aria-hidden="true" />
          <p className="mt-2 text-sm font-semibold text-slate-800">Select local media</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">Drop a video or image, or browse from this device.</p>
          <button
            className="focus-ring mt-3 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            Browse files
          </button>
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            accept="image/*,video/*"
            onChange={(event) => handleFiles(event.target.files)}
          />
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
        <HardDrive className="h-4 w-4" aria-hidden="true" />
        Selected media is ready for local analysis preview.
      </div>
    </section>
  );
}
