import { useChatState } from "./chat-state";

interface ChatSessionDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function ChatSessionDrawer({ open, onClose }: ChatSessionDrawerProps) {
  const { sessions, activeSessionId, switchSession, createSession, deleteSession } = useChatState();

  if (!open) return null;

  const handleSelect = (sessionId: string) => {
    switchSession(sessionId);
    onClose();
  };

  const handleCreate = () => {
    void createSession();
  };

  const handleDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    void deleteSession(sessionId);
  };

  return (
    <div className="chat-session-drawer">
      <div className="chat-session-drawer__header">
        <button className="chat-panel__header-btn" onClick={onClose} type="button" aria-label="关闭列表">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <span className="chat-panel__header-title">会话列表</span>
      </div>
      <div className="chat-session-drawer__list">
        <button className="chat-session-drawer__new-btn" onClick={handleCreate} type="button">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新对话
        </button>
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`chat-session-drawer__item${session.id === activeSessionId ? " is-active" : ""}`}
            onClick={() => handleSelect(session.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter") handleSelect(session.id); }}
          >
            <span className="chat-session-drawer__item-title">{session.title || "未命名对话"}</span>
            <button
              className="chat-session-drawer__item-delete"
              onClick={(e) => handleDelete(e, session.id)}
              type="button"
              aria-label="删除会话"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
