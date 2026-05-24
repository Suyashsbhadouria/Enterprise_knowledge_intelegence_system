"use client";

import * as React from "react";

const CONVERSATION_KEY = "ekcip_conversation_id";

interface ConversationContextValue {
  conversationId: string | null;
  setConversationId: (id: string | null) => void;
}

const ConversationContext = React.createContext<ConversationContextValue>({
  conversationId: null,
  setConversationId: () => {},
});

export function ConversationProvider({ children }: { children: React.ReactNode }) {
  const [conversationId, setConversationIdState] = React.useState<string | null>(null);

  React.useEffect(() => {
    setConversationIdState(localStorage.getItem(CONVERSATION_KEY));
  }, []);

  const setConversationId = React.useCallback((id: string | null) => {
    if (id) localStorage.setItem(CONVERSATION_KEY, id);
    else localStorage.removeItem(CONVERSATION_KEY);
    setConversationIdState(id);
  }, []);

  return (
    <ConversationContext.Provider value={{ conversationId, setConversationId }}>
      {children}
    </ConversationContext.Provider>
  );
}

export function useConversation() {
  return React.useContext(ConversationContext);
}
