"""Markdown analysis used by the live-preview editor.

This module is UI-agnostic: it classifies lines into blocks and tokenises inline
syntax, reporting character offsets for both the visible content and the syntax
markers so a renderer can style the former and hide the latter.

Supported (GitHub-flavoured + Obsidian):
  headings (# .. ######), paragraphs, blockquotes (nested >), unordered and
  ordered lists (nested), task lists (- [ ] / - [x]), fenced code blocks
  (``` and ~~~), tables with column alignment, horizontal rules,
  **bold**, *italic*, ***bold italic***, ~~strike~~, ==highlight==, `code`,
  [[wiki links]] (with #heading and |alias), [links](url), ![images](url),
  bare https:// URLs and backslash escapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------- inline


@dataclass(frozen=True)
class InlineToken:
    kind: str                 # bold, italic, bolditalic, strike, highlight, code, wikilink, link, image, url, escape
    start: int                # absolute start of the whole token (markers included)
    end: int                  # absolute end of the whole token
    content_start: int        # visible content range
    content_end: int
    target: str = ""          # link/wikilink target
    children: tuple["InlineToken", ...] = ()

    @property
    def markers(self) -> list[tuple[int, int]]:
        """Ranges of syntax characters that a live preview should hide."""
        ranges = []
        if self.content_start > self.start:
            ranges.append((self.start, self.content_start))
        if self.end > self.content_end:
            ranges.append((self.content_end, self.end))
        return ranges


_EMPHASIS = {"bold", "italic", "bolditalic", "strike", "highlight"}

# Ordered by priority: when two patterns match at the same position the first wins.
_INLINE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("escape", re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~=>])")),
    ("code", re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")),
    ("wikilink", re.compile(r"\[\[([^\]|#\n]+)(#[^\]|\n]*)?(?:\|([^\]\n]+))?\]\]")),
    ("image", re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"\n]*\")?\)")),
    ("link", re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"\n]*\")?\)")),
    ("url", re.compile(r"https?://[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"*_~]")),
    ("bolditalic", re.compile(r"(\*\*\*|___)(?=\S)(.+?)(?<=\S)\1")),
    ("bold", re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")),
    ("strike", re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")),
    ("highlight", re.compile(r"==(?=\S)(.+?)(?<=\S)==")),
    ("italic", re.compile(r"(?<![*\\])\*(?=[^\s*])(.+?)(?<=[^\s*\\])\*(?!\*)")),
    ("italic_u", re.compile(r"(?<![\w\\])_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)")),
]


def _token_from_match(kind: str, match: re.Match, base: int) -> InlineToken:
    start, end = match.start() + base, match.end() + base
    if kind == "escape":
        return InlineToken("escape", start, end, start + 1, end)
    if kind == "code":
        ticks = len(match.group(1))
        return InlineToken("code", start, end, start + ticks, end - ticks)
    if kind == "wikilink":
        target = match.group(1).strip()
        if match.group(3):
            alias_start = match.start(3) + base
            return InlineToken("wikilink", start, end, alias_start, alias_start + len(match.group(3)), target)
        content_end = (match.end(2) if match.group(2) else match.end(1)) + base
        return InlineToken("wikilink", start, end, start + 2, content_end, target)
    if kind in {"image", "link"}:
        label_start = match.start(1) + base
        return InlineToken(kind, start, end, label_start, label_start + len(match.group(1)), match.group(2))
    if kind == "url":
        return InlineToken("url", start, end, start, end, match.group(0))
    marker = {"bolditalic": 3, "bold": 2, "strike": 2, "highlight": 2, "italic": 1, "italic_u": 1}[kind]
    return InlineToken("italic" if kind == "italic_u" else kind, start, end, start + marker, end - marker)


_INLINE_HINT = re.compile(r"[\\`*_\[\]!~=]|https?://")
_PATTERN_HINTS: dict[str, tuple[str, ...]] = {
    "escape": ("\\",),
    "code": ("`",),
    "wikilink": ("[[",),
    "image": ("![",),
    "link": ("](",),
    "url": ("http://", "https://"),
    "bolditalic": ("***", "___"),
    "bold": ("**", "__"),
    "strike": ("~~",),
    "highlight": ("==",),
    "italic": ("*",),
    "italic_u": ("_",),
}


def parse_inline(text: str, base: int = 0) -> list[InlineToken]:
    """Tokenise inline Markdown. Offsets are relative to ``base``."""
    if not text or not _INLINE_HINT.search(text):
        return []
    tokens: list[InlineToken] = []
    pos = 0
    length = len(text)
    active: list[list] = []
    for priority, (kind, pattern) in enumerate(_INLINE_PATTERNS):
        if any(hint in text for hint in _PATTERN_HINTS[kind]):
            match = pattern.search(text, 0)
            if match and match.end() > match.start():
                active.append([priority, kind, pattern, match])

    while pos < length and active:
        best: tuple[int, int, str, re.Match] | None = None
        idx = 0
        while idx < len(active):
            entry = active[idx]
            match = entry[3]
            if match.start() < pos:
                match = entry[2].search(text, pos)
                if match is None or match.end() <= match.start():
                    active.pop(idx)
                    continue
                entry[3] = match
            key = (match.start(), entry[0])
            if best is None or key < best[:2]:
                best = (match.start(), entry[0], entry[1], match)
            idx += 1
        if best is None:
            break
        token = _token_from_match(best[2], best[3], base)
        if token.kind in _EMPHASIS:
            inner_start, inner_end = token.content_start - base, token.content_end - base
            children = tuple(parse_inline(text[inner_start:inner_end], token.content_start))
            token = InlineToken(token.kind, token.start, token.end, token.content_start, token.content_end,
                                token.target, children)
        tokens.append(token)
        pos = best[3].end()
    return tokens


def plain_text(text: str) -> str:
    """Return ``text`` with inline syntax removed (used for table cell measurement)."""
    out, pos = [], 0
    for token in parse_inline(text):
        out.append(text[pos:token.start])
        inner = text[token.content_start:token.content_end]
        out.append(plain_text(inner) if token.children else inner)
        pos = token.end
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------- block

HEADING = re.compile(r"^(#{1,6})(\s+|$)")
QUOTE = re.compile(r"^(\s{0,3}>\s?)+")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(\s+)(\[( |x|X)\]\s)?")
HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


@dataclass
class LineInfo:
    kind: str                         # blank, paragraph, heading, quote, list, hr, fence, code, table_header,
                                      # table_separator, table_row
    block: int = -1                   # id shared by every line of a code block or table
    level: int = 0                    # heading level / list nesting / quote depth
    marker_end: int = 0               # end offset of the line's block marker (#, >, list bullet)
    ordered: bool = False
    marker: str = ""                  # list marker text, e.g. "-", "3."
    task: str | None = None           # None, " " or "x"
    task_range: tuple[int, int] = (0, 0)
    content_start: int = 0            # where inline content begins
    extra: dict = field(default_factory=dict)


def split_table_row(line: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of each cell's trimmed content."""
    cells, start, escaped = [], 0, False
    body_start = len(line) - len(line.lstrip())
    body_end = len(line.rstrip())
    if body_start < body_end and line[body_start] == "|":
        body_start += 1
    if body_end > body_start and line[body_end - 1] == "|" and (body_end < 2 or line[body_end - 2] != "\\"):
        body_end -= 1
    start = body_start
    for index in range(body_start, body_end + 1):
        char = line[index] if index < body_end else "|"
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            raw = line[start:index]
            left = start + (len(raw) - len(raw.lstrip()))
            right = start + len(raw.rstrip())
            cells.append((left, max(left, right)))
            start = index + 1
    return cells


def table_alignments(separator: str) -> list[str]:
    aligns = []
    for left, right in split_table_row(separator):
        cell = separator[left:right]
        if cell.startswith(":") and cell.endswith(":"):
            aligns.append("center")
        elif cell.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


_BLANK_LINE = LineInfo("blank")
_PARAGRAPH_LINE = LineInfo("paragraph")


def analyze(text: str) -> list[LineInfo]:
    """Classify every line of ``text`` (split on \\n)."""
    return analyze_lines(text.split("\n"))


def analyze_lines(lines: list[str]) -> list[LineInfo]:
    """Classify a pre-split list of lines."""
    infos: list[LineInfo] = []
    block_id = 0
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")) and (len(line) - len(stripped) <= 3):
            fence = FENCE.match(line)
            if fence:
                fence_chars = fence.group(1)
                fc0 = fence_chars[0]
                fclen = len(fence_chars)
                block_id += 1
                infos.append(LineInfo("fence", block_id, extra={"lang": fence.group(2), "open": True}))
                index += 1
                code_info = LineInfo("code", block_id)
                while index < total:
                    cline = lines[index]
                    cstrip = cline.lstrip()
                    if cstrip.startswith(fc0 * fclen) and (len(cline) - len(cstrip) <= 3):
                        closing = FENCE.match(cline)
                        if closing and closing.group(1)[0] == fc0 and len(closing.group(1)) >= fclen \
                                and not cstrip[len(closing.group(1)):].strip():
                            infos.append(LineInfo("fence", block_id, extra={"open": False}))
                            index += 1
                            break
                    infos.append(code_info)
                    index += 1
                continue

        if "|" in line and index + 1 < total and ("|" in lines[index + 1] or stripped.startswith("|")) \
                and TABLE_SEPARATOR.match(lines[index + 1]):
            block_id += 1
            infos.append(LineInfo("table_header", block_id))
            infos.append(LineInfo("table_separator", block_id))
            index += 2
            row_info = LineInfo("table_row", block_id)
            while index < total and "|" in lines[index] and lines[index].strip():
                infos.append(row_info)
                index += 1
            continue

        infos.append(_classify(line))
        index += 1
    return infos


def _classify(line: str) -> LineInfo:
    stripped = line.lstrip()
    if not stripped:
        return _BLANK_LINE
    first = stripped[0]
    if first in "-*_":
        if HR.match(line):
            return LineInfo("hr", marker_end=len(line))
        if first != "_":
            item = LIST_ITEM.match(line)
            if item:
                indent = len(item.group(1).replace("\t", "    "))
                info = LineInfo("list", level=indent // 2, marker_end=item.end(3), ordered=False,
                                marker=item.group(2), content_start=item.end())
                if item.group(4):
                    info.task = item.group(5).lower()
                    info.task_range = (item.start(4), item.start(4) + 3)
                return info
        return _PARAGRAPH_LINE
    if first == "#":
        heading = HEADING.match(line)
        if heading:
            return LineInfo("heading", level=len(heading.group(1)), marker_end=heading.end(),
                            content_start=heading.end())
        return _PARAGRAPH_LINE
    if first == ">":
        quote = QUOTE.match(line)
        if quote:
            depth = quote.group(0).count(">")
            rest = _classify(line[quote.end():])
            info = LineInfo("quote", level=depth, marker_end=quote.end(), content_start=quote.end())
            info.extra["inner"] = rest
            return info
        return _PARAGRAPH_LINE
    if first == "+" or first.isdigit():
        item = LIST_ITEM.match(line)
        if item:
            indent = len(item.group(1).replace("\t", "    "))
            info = LineInfo("list", level=indent // 2, marker_end=item.end(3), ordered=first.isdigit(),
                            marker=item.group(2), content_start=item.end())
            if item.group(4):
                info.task = item.group(5).lower()
                info.task_range = (item.start(4), item.start(4) + 3)
            return info
        return _PARAGRAPH_LINE
    return _PARAGRAPH_LINE


def next_list_prefix(line: str) -> tuple[str, bool] | None:
    """For Enter-key list continuation: return (prefix for next line, current item is empty)."""
    item = LIST_ITEM.match(line)
    if item:
        indent, marker, spacing = item.group(1), item.group(2), item.group(3)
        empty = not line[item.end():].strip()
        if marker[0].isdigit():
            marker = f"{int(marker[:-1]) + 1}{marker[-1]}"
        task = "[ ] " if item.group(4) else ""
        return f"{indent}{marker}{spacing}{task}", empty
    quote = QUOTE.match(line)
    if quote:
        return quote.group(0), not line[quote.end():].strip()
    return None

