import { useState } from "react";

import { useChatState } from "./chat-state";
import { ChatHeader } from "./ChatHeader";
import { ChatInput } from "./ChatInput";
import { ChatSessionDrawer } from "./ChatSessionDrawer";
import { ChatThread } from "./ChatThread";

export function ChatPanel() {
  const { closePanel, error, clearError } = useChatState();
  const [showDrawer, setShowDrawer] = useState(false);

  return (
    <div className="chat-panel">
      {error ? (
        <div className="chat-panel__error" role="alert">
          <span className="chat-panel__error-text">{error}</span>
          <button className="chat-panel__error-dismiss" onClick={clearError} type="button">
            关闭
          </button>
        </div>
      ) : null}
      <ChatHeader
        onToggleDrawer={() => setShowDrawer((v) => !v)}
        onClose={closePanel}
      />
      <ChatThread />
      <ChatInput />
      <ChatSessionDrawer open={showDrawer} onClose={() => setShowDrawer(false)} />
    </div>
  );
}
