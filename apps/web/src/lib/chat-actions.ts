import type { Citation, Message, ProposedAction } from "@/lib/types";
import {
  displayAssistantBody,
  resolveAssistantCitations,
} from "@/lib/format-assistant-message";

export interface ChatMessage extends Message {
  citations?: Citation[];
  proposedActions?: ProposedAction[];
  /** Clean assistant text for rendering (no sources footer or action blocks). */
  displayContent?: string;
}

/** Merge action lists by id; later entries win (fresh API status overrides stale). */
export function mergeActionsById(
  ...groups: Array<ProposedAction[] | undefined>
): ProposedAction[] {
  const byId = new Map<string, ProposedAction>();
  for (const group of groups) {
    for (const action of group ?? []) {
      byId.set(action.id, action);
    }
  }
  return [...byId.values()];
}

/** API stores pending actions on the user message id; show them under the next assistant reply. */
export function attachActionsBelowAssistantReplies(
  messages: Message[],
  actions: ProposedAction[],
): ChatMessage[] {
  const byTrigger = actions.reduce<Record<string, ProposedAction[]>>((acc, action) => {
    const key = action.triggering_message_id;
    acc[key] = [...(acc[key] ?? []), action];
    return acc;
  }, {});

  const result: ChatMessage[] = messages.map((m) => enrichMessage({ ...m }));

  for (let i = 0; i < result.length; i += 1) {
    const msg = result[i];
    if (msg.role !== "user") continue;
    const attached = byTrigger[msg.id];
    if (!attached?.length) continue;

    for (let j = i + 1; j < result.length; j += 1) {
      if (result[j].role === "assistant") {
        result[j] = enrichMessage({
          ...result[j],
          proposedActions: mergeActionsById(result[j].proposedActions, attached),
        });
        break;
      }
    }
  }

  return result;
}

export function enrichMessage(message: ChatMessage): ChatMessage {
  if (message.role !== "assistant") {
    return message;
  }
  return {
    ...message,
    displayContent: displayAssistantBody(message.content),
    citations: resolveAssistantCitations(message.content, message.citations),
  };
}

export function isActionAwaitingApproval(status: string): boolean {
  return status === "pending" || status === "proposed";
}
