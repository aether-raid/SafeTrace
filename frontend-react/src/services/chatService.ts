import { buildApiUrl } from './analysisService';
import type { ChatRequest, ChatResponse, ChatStatus } from '../types/chat';

async function readChatErrorMessage(response: Response): Promise<string> {
  const fallback = `SafeTrace Assistant returned ${response.status}`;
  const raw = await response.text();
  if (!raw) return response.statusText ? `${fallback}: ${response.statusText}` : fallback;

  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string') return parsed.detail;
    if (typeof parsed?.detail?.message === 'string') return parsed.detail.message;
    if (typeof parsed?.message === 'string') return parsed.message;
    if (typeof parsed?.error === 'string') return parsed.error;
  } catch {
    return raw;
  }

  return raw || fallback;
}

async function chatFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readChatErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

export async function getChatStatus(): Promise<ChatStatus> {
  return chatFetch<ChatStatus>('chat/status');
}

export async function warmupSafeTraceAssistant(): Promise<ChatStatus> {
  return chatFetch<ChatStatus>('chat/warmup', {
    method: 'POST',
  });
}

export async function askSafeTraceAssistant(request: ChatRequest): Promise<ChatResponse> {
  return chatFetch<ChatResponse>('chat', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
