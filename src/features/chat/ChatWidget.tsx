import { useAppState } from "../../app/state/app-state";

import { useChatState } from "./chat-state";
import { ChatFAB } from "./ChatFAB";
import { ChatPanel } from "./ChatPanel";
import { ChatStateProvider } from "./ChatStateProvider";

function ChatWidgetInner() {
  const { session } = useAppState();
  const { isOpen, openPanel, closePanel } = useChatState();

  if (!session) return null;

  return (
    <>
      <ChatFAB onClick={isOpen ? closePanel : openPanel} active={isOpen} />
      {isOpen && <ChatPanel />}
    </>
  );
}

export function ChatWidget() {
  return (
    <ChatStateProvider>
      <ChatWidgetInner />
    </ChatStateProvider>
  );
}
