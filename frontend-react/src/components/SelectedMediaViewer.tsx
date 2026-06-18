import { FileImage, FileVideo, HardDrive, Clock } from 'lucide-react';
import type { MediaItem } from '../types/analysis';
import { StatusBadge } from './StatusBadge'; // Make sure this is imported

type SelectedMediaViewerProps = {
  media: MediaItem;
};

export function SelectedMediaViewer({ media }: SelectedMediaViewerProps) {
  const Icon = media.type === 'video' ? FileVideo : FileImage;

  return (
    <div className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-soft">
      <div className="flex flex-col lg:flex-row relative">
        
        <div className="flex aspect-video w-full shrink-0 items-center justify-center bg-slate-900 lg:w-1/3 xl:w-1/4">
          {media.previewUrl ? (
             media.type === 'video' ? (
               <video src={media.previewUrl} className="h-full w-full object-cover" controls muted />
             ) : (
               <img src={media.previewUrl} alt={media.filename} className="h-full w-full object-cover" />
             )
          ) : (
             <Icon className="h-12 w-12 text-slate-600" />
          )}
        </div>

        <div className="flex flex-1 flex-col justify-center border-b border-slate-100 p-5 lg:border-b-0 lg:border-r border-slate-100 relative">
          
          <div className="absolute right-5 top-5">
             <StatusBadge label={media.source === 'local' ? 'Local file selected' : 'Ready for analysis'} tone="success" />
          </div>

          <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-safety-blue">
            Selected for Analysis
          </div>
          <h2 className="text-lg font-bold text-slate-950 truncate pr-32">{media.filename}</h2>
          
          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-slate-600">
            <div className="flex items-center gap-1.5">
              <HardDrive className="h-4 w-4" /> {media.sizeLabel}
            </div>
            {media.duration && (
              <div className="flex items-center gap-1.5">
                <Clock className="h-4 w-4" /> {media.duration}
              </div>
            )}
            <div className="flex items-center gap-1.5 capitalize">
              <span className={`flex h-2 w-2 rounded-full ${media.status === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`}></span>
              Status: {media.status}
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
            <HardDrive className="h-4 w-4" aria-hidden="true" />
            Selected media is ready for local analysis preview.
          </div>
        </div>

      </div>
    </div>
  );
}