import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage, ChatSession } from "../../services/chatApi";
import {
  createChatSession,
  deleteChatSession,
  getChatMessages,
  listChatSessions,
  sendChatMessage,
} from "../../services/chatApi";

import { ChatStateContext } from "./chat-state";

interface ChatStateProviderProps {
  children: ReactNode;
}

function toUserFriendlyError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

function streamErrorMessage(data: Record<string, unknown>): string {
  const message = data["message"];
  if (typeof message === "string" && message.trim()) {
    return message;
  }
  return "The assistant could not complete this message. Please try again.";
}

export function ChatStateProvider({ children }: ChatStateProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const sessionsRef = useRef<ChatSession[]>([]);
  sessionsRef.current = sessions;
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initialOpenLoadCompletedRef = useRef(false);
  const initialOpenLoadInFlightRef = useRef(false);
  const isStreamingRef = useRef(false);
  isStreamingRef.current = isStreaming;

  const closePanel = useCallback(() => {
    setIsOpen(false);
  }, []);

  const openPanel = useCallback(() => {
    setIsOpen(true);

    if (initialOpenLoadCompletedRef.current || initialOpenLoadInFlightRef.current) {
      return;
    }

    initialOpenLoadInFlightRef.current = true;
    void (async () => {
      setIsLoadingSessions(true);
      setError(null);
      try {
        let list = await listChatSessions();
        if (list.length === 0) {
          const created = await createChatSession();
          list = [created];
        }
        setSessions(list);
        setActiveSessionId((current) => current ?? list[0]?.id ?? null);
        initialOpenLoadCompletedRef.current = true;
      } catch (err) {
        setError(toUserFriendlyError(err));
      } finally {
        initialOpenLoadInFlightRef.current = false;
        setIsLoadingSessions(false);
      }
    })();
  }, []);

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  const createSession = useCallback(async (): Promise<ChatSession | null> => {
    setError(null);
    try {
      const session = await createChatSession();
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
      initialOpenLoadCompletedRef.current = true;
      return session;
    } catch (err) {
      setError(toUserFriendlyError(err));
      return null;
    }
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    setError(null);
    try {
      await deleteChatSession(sessionId);
      const next = sessionsRef.current.filter((s) => s.id !== sessionId);
      setSessions(next);
      setActiveSessionId((active) => (active === sessionId ? next[0]?.id ?? null : active));
    } catch (err) {
      setError(toUserFriendlyError(err));
    }
  }, []);

  useEffect(() => {
    setIsStreaming(false);
    setStreamingContent("");
  }, [activeSessionId]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    setIsLoadingMessages(true);

    void (async () => {
      try {
        const loaded = await getChatMessages(activeSessionId);
        // Avoid overwriting optimistic / streaming messages while a reply is in flight.
        if (!cancelled && !isStreamingRef.current) {
          setMessages(loaded);
        }
      } catch (err) {
        if (!cancelled) {
          setError(toUserFriendlyError(err));
        }
      } finally {
        if (!cancelled) {
          setIsLoadingMessages(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }

      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await createSession();
        if (!session) {
          return;
        }
        sessionId = session.id;
      }

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
      };

      setStreamingContent("");
      setError(null);
      setIsStreaming(true);
      setMessages((prev) => [...prev, userMessage]);

      let accumulated = "";

      try {
        for await (const evt of sendChatMessage(sessionId, trimmed)) {
          if (evt.event === "delta") {
            const piece = evt.data["content"];
            if (typeof piece === "string") {
              accumulated += piece;
              setStreamingContent(accumulated);
            }
          } else if (evt.event === "done") {
            const assistantMessage: ChatMessage = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: accumulated,
              created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
            setStreamingContent("");
            setIsStreaming(false);
            return;
          } else if (evt.event === "error") {
            setError(streamErrorMessage(evt.data));
            setStreamingContent("");
            setIsStreaming(false);
            return;
          }
        }

        if (accumulated.length > 0) {
          const assistantMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: accumulated,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, assistantMessage]);
        }
        setStreamingContent("");
        setIsStreaming(false);
      } catch (err) {
        setError(toUserFriendlyError(err));
        setStreamingContent("");
        setIsStreaming(false);
      }
    },
    [activeSessionId, createSession],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value = useMemo(
    () => ({
      isOpen,
      openPanel,
      closePanel,
      sessions,
      activeSessionId,
      switchSession,
      createSession,
      deleteSession,
      messages,
      isStreaming,
      streamingContent,
      sendMessage,
      isLoadingSessions,
      isLoadingMessages,
      error,
      clearError,
    }),
    [
      activeSessionId,
      closePanel,
      createSession,
      deleteSession,
      error,
      isLoadingMessages,
      isLoadingSessions,
      isOpen,
      isStreaming,
      messages,
      openPanel,
      sendMessage,
      sessions,
      streamingContent,
      switchSession,
      clearError,
    ],
  );

  return <ChatStateContext.Provider value={value}>{children}</ChatStateContext.Provider>;
}
