import { formatAssistantContent } from "./formatAssistantContent";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

export function ChatBubble({ role, content, isStreaming }: ChatBubbleProps) {
  const showTypingDots = isStreaming && !content;
  const assistantBlocks = role === "assistant" ? formatAssistantContent(content) : [];

  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {role === "assistant" ? (
        <div className="chat-bubble__content">
          {assistantBlocks.map((block, index) => {
            if (block.kind === "paragraph") {
              return (
                <p className="chat-bubble__paragraph" key={`${block.kind}-${index}`}>
                  {block.text}
                </p>
              );
            }

            return (
              <section
                className={`chat-bubble__section chat-bubble__section--${block.tone}`}
                key={`${block.kind}-${index}`}
              >
                <div className="chat-bubble__section-title">{block.heading}</div>
                <ul className="chat-bubble__list">
                  {block.items.map((item, itemIndex) => (
                    <li className="chat-bubble__list-item" key={`${item}-${itemIndex}`}>
                      {item}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      ) : (
        content
      )}
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
