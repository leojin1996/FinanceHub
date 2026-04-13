import { type ChangeEvent, type KeyboardEvent, useCallback, useRef, useState } from "react";

import { useChatState } from "./chat-state";

export function ChatInput() {
  const { sendMessage, isStreaming, activeSessionId, isLoadingSessions } = useChatState();
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Allow typing while the first session list is loading; only lock when we know there is no session (load finished empty/failed).
  const inputLocked = isStreaming || (!activeSessionId && !isLoadingSessions);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    }
  }, []);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    adjustHeight();
  };

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || inputLocked || !activeSessionId) return;
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    void sendMessage(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel__input">
      <textarea
        ref={textareaRef}
        className="chat-panel__input-field"
        rows={1}
        placeholder="输入消息..."
        value={text}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={inputLocked}
      />
      <button
        className="chat-panel__send-btn"
        onClick={handleSend}
        disabled={isStreaming || !activeSessionId || !text.trim()}
        type="button"
        aria-label="发送"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}
