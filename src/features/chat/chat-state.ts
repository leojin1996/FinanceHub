import { createContext, useContext } from "react";

import type { ChatMessage, ChatSession } from "../../services/chatApi";

export type { ChatMessage, ChatSession };

export interface ChatStateValue {
  // Panel state
  isOpen: boolean;
  openPanel: () => void;
  closePanel: () => void;

  // Session management
  sessions: ChatSession[];
  activeSessionId: string | null;
  switchSession: (sessionId: string) => void;
  createSession: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;

  // Messages
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  sendMessage: (content: string) => Promise<void>;

  // Loading states
  isLoadingSessions: boolean;
  isLoadingMessages: boolean;
  error: string | null;
  clearError: () => void;
}

export const ChatStateContext = createContext<ChatStateValue | null>(null);

export function useChatState(): ChatStateValue {
  const context = useContext(ChatStateContext);
  if (!context) {
    throw new Error("useChatState must be used within ChatStateProvider");
  }
  return context;
}
