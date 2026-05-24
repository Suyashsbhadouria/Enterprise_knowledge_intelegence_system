import type { Citation } from "@/lib/types";

const EKCIP_ACTIONS_BLOCK = /```ekcip_actions\s*\n[\s\S]*?\n```/gi;
const SOURCES_HEADER = /\n\n\*\*Sources:\*\*\s*\n/i;

/** Strip action blocks and embedded source footers from stored assistant content. */
export function stripAssistantContent(raw: string): string {
  let text = raw.replace(EKCIP_ACTIONS_BLOCK, "").trim();
  const sourcesIndex = text.search(SOURCES_HEADER);
  if (sourcesIndex >= 0) {
    text = text.slice(0, sourcesIndex).trim();
  }
  return text;
}

/** Parse legacy **Sources:** footers from older assistant replies. */
export function parseSourcesFooter(raw: string): Citation[] {
  const match = raw.match(SOURCES_HEADER);
  if (!match || match.index === undefined) return [];

  const footer = raw.slice(match.index + match[0].length);
  const lines = footer.split("\n").map((line) => line.trim()).filter(Boolean);
  const citations: Citation[] = [];

  for (const line of lines) {
    const parsed = line.match(/^-\s*\[([^\]]+)\]\s*(.+?)(?:\s+\((https?:\/\/[^)]+)\))?\s*$/);
    if (!parsed) continue;
    const [, sourceId, title, url] = parsed;
    citations.push({
      source: sourceId.split("-")[0]?.toLowerCase() ?? "source",
      source_id: sourceId,
      title: title.trim(),
      url: url ?? null,
      excerpt: "",
      score: 0,
    });
  }

  return citations;
}

export function resolveAssistantCitations(
  raw: string,
  citations?: Citation[],
): Citation[] {
  if (citations && citations.length > 0) return citations;
  return parseSourcesFooter(raw);
}

export function displayAssistantBody(raw: string): string {
  return stripAssistantContent(raw);
}
