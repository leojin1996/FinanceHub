interface ChatFABProps {
  onClick: () => void;
  active?: boolean;
}

function SpeechBubbleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function ChatFAB({ onClick, active }: ChatFABProps) {
  return (
    <button className="chat-fab" onClick={onClick} type="button" aria-label={active ? "关闭对话" : "打开对话"}>
      {active ? <CloseIcon /> : <SpeechBubbleIcon />}
    </button>
  );
}
