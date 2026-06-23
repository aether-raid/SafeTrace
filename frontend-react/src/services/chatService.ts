import { buildApiUrl } from './analysisService';
import type { ChatRequest, ChatResponse, ChatStatus } from '../types/chat';

async function chatFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    let message = `SafeTrace Assistant returned ${response.status}`;
    try {
      const body = await response.json();
      message = body?.detail?.message || body?.message || message;
    } catch {
      const text = await response.text();
      message = text || message;
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export async function getChatStatus(): Promise<ChatStatus> {
  return chatFetch<ChatStatus>('chat/status');
}

export async function askSafeTraceAssistant(request: ChatRequest): Promise<ChatResponse> {
  return chatFetch<ChatResponse>('chat', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
