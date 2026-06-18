import type { Severity } from '../types/analysis';

const VIOLATION_NAME_MAP: Record<string, string> = {
  helmet_missing: 'Missing Helmet',
  missing_helmet: 'Missing Helmet',
  seatbelt_missing: 'Missing Seatbelt',
  missing_seatbelt: 'Missing Seatbelt',
  hands_off_wheel: 'Hands Off Wheel',
  phone_use: 'Phone Use',
};

export function formatViolationName(name: string): string {
  const normalized = name.trim().toLowerCase();

  if (VIOLATION_NAME_MAP[normalized]) {
    return VIOLATION_NAME_MAP[normalized];
  }

  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatQueryRelevance(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatSeverity(severity: Severity): string {
  return severity;
}

export function formatConfidenceRange(values: number[]): string {
  if (values.length === 0) {
    return 'N/A';
  }

  const percentages = values.map((value) => Math.round(value * 100));
  const min = Math.min(...percentages);
  const max = Math.max(...percentages);

  if (min === max) {
    return `${max}%`;
  }

  return `${min}-${max}%`;
}

export function formatAverageConfidence(values: number[]): string {
  if (values.length === 0) {
    return 'N/A';
  }

  const total = values.reduce((sum, value) => sum + value, 0);
  return formatConfidence(total / values.length);
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}
