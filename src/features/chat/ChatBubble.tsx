import { stripAssistantMarkdownMarkers } from "./formatAssistantContent";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function ChatBubble({ role, content, isStreaming }: ChatBubbleProps) {
  const showTypingDots = isStreaming && !content;
  const displayContent =
    role === "assistant" ? stripAssistantMarkdownMarkers(content) : content;

  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {displayContent}
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
