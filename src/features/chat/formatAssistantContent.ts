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

export type AssistantContentBlock =
  | {
      kind: "paragraph";
      text: string;
    }
  | {
      heading: string;
      items: string[];
      kind: "list";
      tone: "primary" | "secondary" | "neutral";
    };

const LIST_MARKER_PATTERN = /^\s*(?:[-*•]|\d+[.、)]|[一二三四五六七八九十]+[、.])\s*/;

function trimHeadingMarker(line: string): string {
  return line.replace(/[：:]\s*$/, "").trim();
}

function normalizeListItem(line: string): string {
  return line.replace(LIST_MARKER_PATTERN, "").trim();
}

function getListTone(heading: string): "primary" | "secondary" | "neutral" {
  if (/能力|帮助|可以为你提供|核心/.test(heading)) {
    return "primary";
  }
  if (/想看|告诉我|可以问|问题|例如/.test(heading)) {
    return "secondary";
  }
  return "neutral";
}

function isListSection(lines: string[]): boolean {
  if (lines.length < 2) {
    return false;
  }

  const [heading] = lines;
  return /[：:]$/.test(heading.trim());
}

export function formatAssistantContent(text: string): AssistantContentBlock[] {
  const cleaned = stripAssistantMarkdownMarkers(text).trim();
  if (!cleaned) {
    return [];
  }

  return cleaned
    .split(/\n\s*\n/)
    .map((part) =>
      part
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    )
    .filter((lines) => lines.length > 0)
    .map((lines): AssistantContentBlock => {
      if (isListSection(lines)) {
        const heading = trimHeadingMarker(lines[0]);
        return {
          heading,
          items: lines.slice(1).map(normalizeListItem).filter(Boolean),
          kind: "list",
          tone: getListTone(heading),
        };
      }

      return {
        kind: "paragraph",
        text: lines.join("\n"),
      };
    });
}
