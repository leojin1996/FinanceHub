import { useEffect, useRef } from "react";

import { useChatState } from "./chat-state";
import { ChatBubble } from "./ChatBubble";

export function ChatThread() {
  const { messages, isStreaming, streamingContent } = useChatState();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <div className="chat-panel__thread">
      {isEmpty && (
        <div className="chat-welcome">你好！我是你的智能理财助手。有什么可以帮你的？</div>
      )}
      {messages.map((msg) => (
        <ChatBubble key={msg.id} role={msg.role === "user" ? "user" : "assistant"} content={msg.content} />
      ))}
      {isStreaming && (
        <ChatBubble role="assistant" content={streamingContent} isStreaming />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
