import { authFetch } from "./authApi";

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
  tool_calls?: Record<string, unknown>[] | null;
}

export interface ChatStreamEvent {
  event: "delta" | "tool_call" | "done" | "error";
  data: Record<string, unknown>;
}

const STREAM_EVENT_NAMES = new Set<string>(["delta", "tool_call", "done", "error"]);

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof payload?.detail === "string" ? payload.detail : "request failed";
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

interface SessionsListResponse {
  sessions: ChatSession[];
}

interface MessagesListResponse {
  messages: ChatMessage[];
}

export async function createChatSession(): Promise<ChatSession> {
  return authFetch("/api/chat/sessions", { method: "POST" }).then(readJson<ChatSession>);
}

export async function listChatSessions(limit?: number): Promise<ChatSession[]> {
  const url =
    limit !== undefined ? `/api/chat/sessions?limit=${encodeURIComponent(String(limit))}` : "/api/chat/sessions";
  const body = await authFetch(url).then(readJson<SessionsListResponse>);
  return body.sessions;
}

export async function getChatMessages(sessionId: string): Promise<ChatMessage[]> {
  const body = await authFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`).then(
    readJson<MessagesListResponse>,
  );
  return body.messages;
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await authFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof payload?.detail === "string" ? payload.detail : "request failed";
    throw new Error(message);
  }
}

function splitSseBlocks(buffer: string): { blocks: string[]; rest: string } {
  const blocks: string[] = [];
  let rest = buffer;

  while (rest.length > 0) {
    const lf = rest.indexOf("\n\n");
    const crlf = rest.indexOf("\r\n\r\n");
    let sep = -1;
    let sepLen = 2;

    if (lf === -1 && crlf === -1) {
      break;
    }
    if (lf === -1 || (crlf !== -1 && crlf < lf)) {
      sep = crlf;
      sepLen = 4;
    } else {
      sep = lf;
      sepLen = 2;
    }

    blocks.push(rest.slice(0, sep));
    rest = rest.slice(sep + sepLen);
  }

  return { blocks, rest };
}

function parseSseBlock(block: string): ChatStreamEvent | null {
  const lines = block.split(/\r?\n/);
  let eventName: string | undefined;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (!eventName || !STREAM_EVENT_NAMES.has(eventName)) {
    return null;
  }

  const dataRaw = dataLines.join("\n");
  let data: Record<string, unknown> = {};
  if (dataRaw.length > 0) {
    try {
      const parsed: unknown = JSON.parse(dataRaw);
      data = typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
    } catch {
      data = {};
    }
  }

  return { event: eventName as ChatStreamEvent["event"], data };
}

async function* readSseChatStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<ChatStreamEvent> {
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    const { blocks, rest } = splitSseBlocks(buffer);
    buffer = rest;

    for (const block of blocks) {
      if (!block.trim()) {
        continue;
      }
      const evt = parseSseBlock(block);
      if (evt) {
        yield evt;
      }
    }

    if (done) {
      buffer += decoder.decode();
      const tail = buffer.trim();
      if (tail) {
        const evt = parseSseBlock(buffer);
        if (evt) {
          yield evt;
        }
      }
      break;
    }
  }
}

export async function* sendChatMessage(
  sessionId: string,
  content: string,
): AsyncGenerator<ChatStreamEvent> {
  const response = await authFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    body: JSON.stringify({ content }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof payload?.detail === "string" ? payload.detail : "request failed";
    throw new Error(message);
  }

  const body = response.body;
  if (!body) {
    throw new Error("request failed");
  }

  yield* readSseChatStream(body.getReader());
}
