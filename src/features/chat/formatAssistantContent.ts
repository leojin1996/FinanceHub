/**
 * Assistant replies may include Markdown-style `**bold**` while the UI renders
 * plain text. Unwrap paired markers and drop stray `**` so nothing shows up
 * as literal asterisks.
 */
export function stripAssistantMarkdownMarkers(text: string): string {
  let out = text.replace(/\*\*([^*]+)\*\*/g, "$1");
  out = out.replace(/\*\*/g, "");
  return out;
}
