interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function ChatBubble({ role, content, isStreaming }: ChatBubbleProps) {
  const showTypingDots = isStreaming && !content;

  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {content}
      {showTypingDots && (
        <span className="chat-typing-indicator">
          <span />
          <span />
          <span />
        </span>
      )}
    </div>
  );
}
