export function formatShortJobId(jobId?: string | null): string {
  if (!jobId) return 'Not assigned';
  const datedMatch = jobId.match(/^job_\d{8}_(.+)$/);
  if (datedMatch?.[1]) return datedMatch[1];
  if (jobId.length > 18) return `job_...${jobId.slice(-8)}`;
  return jobId;
}

export async function copyJobIdToClipboard(jobId?: string | null): Promise<void> {
  if (!jobId) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(jobId);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = jobId;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}
