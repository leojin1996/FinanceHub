import { ChatWidget } from "../features/chat/ChatWidget";

import { AppRouter } from "./router";
import { AppStateProvider } from "./state/AppStateProvider";
import { MarketDataProvider } from "./state/MarketDataProvider";

export default function App() {
  return (
    <AppStateProvider>
      <MarketDataProvider>
        <AppRouter />
        <ChatWidget />
      </MarketDataProvider>
    </AppStateProvider>
  );
}
