interface ChatHeaderProps {
  onToggleDrawer: () => void;
  onClose: () => void;
}

export function ChatHeader({ onToggleDrawer, onClose }: ChatHeaderProps) {
  return (
    <div className="chat-panel__header">
      <button className="chat-panel__header-btn" onClick={onToggleDrawer} type="button" aria-label="会话列表">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <span className="chat-panel__header-title">智能助手</span>
      <button className="chat-panel__header-btn" onClick={onClose} type="button" aria-label="关闭">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}
