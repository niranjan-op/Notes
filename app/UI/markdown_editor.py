"""Live-preview Markdown renderer for a Tkinter / CustomTkinter text widget.

Gives an Obsidian-like hybrid experience:
- Off the active block/line, Markdown syntax markers (``#``, ``**``, ``*``,
  ``~~``, ``==``, `` ` ``, ``[[...]]``, ``[label](url)``, ``>``, ``---``,
  ``[ ]``/``[x]`` and ``` fences) are hidden with Tk's ``elide`` tag option,
  leaving only the formatted text.
- On the active line (or active code/table block), markers stay visible and
  quietly tinted so the user can edit raw Markdown directly; moving the caret
  to another line immediately collapses the markers into formatted output.
- Off-cursor GFM tables are rendered with a live embedded table widget (header
  shading, cell borders, column alignment, inline formatting, clickable links
  and checkboxes); clicking a table switches it to raw editing on that block.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Callable

import customtkinter as ctk

from app.core.markdown import (
    InlineToken,
    LineInfo,
    analyze,
    next_list_prefix,
    parse_inline,
    split_table_row,
    table_alignments,
)
from .styles import MONO_FAMILY, Colors, Fonts, Metrics, resolve


class MarkdownEditorController:
    """Attaches live-preview Markdown rendering and editing helpers to a CTkTextbox."""

    def __init__(
        self,
        textbox: ctk.CTkTextbox,
        on_open_wikilink: Callable[[str], None],
        on_modified: Callable[[], None],
        font_family: str = "Segoe UI",
    ):
        self.textbox = textbox
        self.widget: tk.Text = textbox._textbox
        self.on_open_wikilink = on_open_wikilink
        self.on_modified = on_modified
        self.font_family = font_family
        self.live_preview = True  # when False (Source mode), syntax markers are never elided
        self._embedded_widgets: list[tk.Widget] = []
        self._dynamic_tags: set[str] = set()
        self._render_job: str | None = None
        self._configure_tags()
        self._bind_events()

    # --------------------------------------------------------------- setup
    def set_font_family(self, family: str) -> None:
        self.font_family = family
        self._configure_tags()
        self.render()

    def set_live_preview(self, enabled: bool) -> None:
        self.live_preview = enabled
        self.render()

    def apply_theme(self) -> None:
        self._configure_tags()
        self.render()

    def _configure_tags(self) -> None:
        w = self.widget
        family = self.font_family
        fg = resolve(Colors.text)
        sub = resolve(Colors.text_sub)
        faint = resolve(Colors.text_faint)
        primary = resolve(Colors.primary)
        code_fg = resolve(Colors.code)
        code_bg = resolve(Colors.code_bg)
        quote_bg = resolve(Colors.quote_bg)
        hi_bg = resolve(Colors.highlight)

        w.configure(
            selectbackground=resolve(Colors.selection),
            selectforeground=fg,
            inactiveselectbackground=resolve(Colors.active),
            insertbackground=fg,
        )

        # Hidden syntax markers (live preview) vs faint visible syntax (active line / source mode)
        w.tag_configure("md-hide", elide=True)
        w.tag_configure("md-syntax", foreground=faint)

        # Headings H1..H6
        heading_specs = {
            1: (26, 12, 6),
            2: (22, 10, 5),
            3: (18, 8, 4),
            4: (16, 6, 3),
            5: (15, 4, 2),
            6: (14, 4, 2),
        }
        for level, (size, sp1, sp3) in heading_specs.items():
            color = sub if level == 6 else fg
            w.tag_configure(
                f"md-h{level}",
                font=(family, size, "bold"),
                foreground=color,
                spacing1=sp1,
                spacing3=sp3,
            )

        # Inline styles
        w.tag_configure("md-bold", font=(family, 15, "bold"))
        w.tag_configure("md-italic", font=(family, 15, "italic"))
        w.tag_configure("md-bolditalic", font=(family, 15, "bold italic"))
        w.tag_configure("md-strike", overstrike=True, foreground=sub)
        w.tag_configure("md-highlight", background=hi_bg, foreground=fg)
        w.tag_configure("md-code", font=(MONO_FAMILY, 13), foreground=code_fg, background=code_bg)
        w.tag_configure("md-wikilink", foreground=primary, underline=True)
        w.tag_configure("md-link", foreground=primary, underline=True)
        w.tag_configure("md-url", foreground=primary, underline=True)
        w.tag_configure("md-image", foreground=code_fg, underline=True)

        # Blocks
        w.tag_configure(
            "md-quote",
            foreground=sub,
            background=quote_bg,
            lmargin1=18,
            lmargin2=18,
            spacing1=3,
            spacing3=3,
        )
        w.tag_configure(
            "md-codeblock",
            font=(MONO_FAMILY, 13),
            foreground=code_fg,
            background=code_bg,
            lmargin1=14,
            lmargin2=14,
            rmargin=14,
            spacing1=2,
            spacing3=2,
        )
        w.tag_configure("md-fence", font=(MONO_FAMILY, 11), foreground=faint, background=code_bg)
        w.tag_configure("md-hr-line", foreground=resolve(Colors.border), overstrike=True, spacing1=8, spacing3=8)
        w.tag_configure("md-task-done", overstrike=True, foreground=sub)
        w.tag_configure(
            "md-table-raw",
            font=(MONO_FAMILY, 13),
            background=code_bg,
            lmargin1=8,
            lmargin2=8,
        )

        for level in range(6):
            indent = 16 + level * 20
            w.tag_configure(f"md-list-{level}", lmargin1=indent, lmargin2=indent + 14, spacing1=2, spacing3=2)

    def _bind_events(self) -> None:
        w = self.widget
        for seq in ("<KeyRelease>", "<ButtonRelease-1>", "<FocusIn>", "<FocusOut>"):
            w.bind(seq, self.queue_render, add="+")
        w.bind("<Return>", self._on_return)

        for tag in ("md-wikilink", "md-link", "md-url"):
            w.tag_bind(tag, "<Enter>", lambda _e: w.configure(cursor="hand2"))
            w.tag_bind(tag, "<Leave>", lambda _e: w.configure(cursor="xterm"))
        w.tag_bind("md-wikilink", "<Button-1>", self._click_wikilink)
        w.tag_bind("md-link", "<Button-1>", self._click_external_link)
        w.tag_bind("md-url", "<Button-1>", self._click_external_link)

    # --------------------------------------------------------- smart editing
    def _on_return(self, event) -> str | None:
        """Continue lists/blockquotes/tasks on Enter, or exit an empty item."""
        if event.state & 0x4:  # Control held
            return None
        w = self.widget
        index = w.index("insert")
        line_no = int(index.split(".")[0])
        line = w.get(f"{line_no}.0", f"{line_no}.end")
        cont = next_list_prefix(line)
        if cont is None:
            self.queue_render()
            return None
        prefix, is_empty = cont
        if is_empty:
            w.delete(f"{line_no}.0", f"{line_no}.end")
        else:
            w.insert("insert", "\n" + prefix)
        self.on_modified()
        self.queue_render()
        return "break"

    def _toggle_task(self, line_no: int, start_col: int, end_col: int) -> None:
        w = self.widget
        current = w.get(f"{line_no}.{start_col}", f"{line_no}.{end_col}")
        replacement = "[ ]" if "x" in current.lower() else "[x]"
        w.replace(f"{line_no}.{start_col}", f"{line_no}.{end_col}", replacement)
        self.on_modified()
        self.render()

    def _focus_line(self, line_no: int, col: int = 0) -> None:
        self.widget.mark_set("insert", f"{line_no}.{col}")
        self.widget.focus_set()
        self.render()

    # ----------------------------------------------------------- link clicks
    def _token_at_event(self, event, wanted_kinds: set[str]) -> InlineToken | None:
        w = self.widget
        idx = w.index(f"@{event.x},{event.y}")
        line_no, col = map(int, idx.split("."))
        line = w.get(f"{line_no}.0", f"{line_no}.end")

        def search(tokens: list[InlineToken]) -> InlineToken | None:
            for tok in tokens:
                if tok.start <= col < tok.end:
                    if tok.children:
                        inner = search(list(tok.children))
                        if inner:
                            return inner
                    if tok.kind in wanted_kinds:
                        return tok
            return None

        return search(parse_inline(line))

    def _click_wikilink(self, event) -> str | None:
        tok = self._token_at_event(event, {"wikilink"})
        if tok and tok.target:
            self.on_open_wikilink(tok.target)
            return "break"
        return None

    def _click_external_link(self, event) -> str | None:
        tok = self._token_at_event(event, {"link", "url"})
        if tok and tok.target:
            if tok.target.startswith(("http://", "https://", "mailto:")):
                webbrowser.open(tok.target)
            else:
                self.on_open_wikilink(tok.target.removesuffix(".md"))
            return "break"
        return None

    # ------------------------------------------------------------- rendering
    def queue_render(self, _event=None) -> None:
        if self._render_job:
            self.widget.after_cancel(self._render_job)
        self._render_job = self.widget.after(15, self.render)

    def _clear_render_state(self) -> None:
        w = self.widget
        for child in self._embedded_widgets:
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._embedded_widgets.clear()

        static_tags = (
            "md-hide", "md-syntax",
            "md-h1", "md-h2", "md-h3", "md-h4", "md-h5", "md-h6",
            "md-bold", "md-italic", "md-bolditalic", "md-strike", "md-highlight",
            "md-code", "md-wikilink", "md-link", "md-url", "md-image",
            "md-quote", "md-codeblock", "md-fence", "md-hr-line", "md-task-done", "md-table-raw",
            *(f"md-list-{i}" for i in range(6)),
        )
        for tag in static_tags:
            w.tag_remove(tag, "1.0", "end")
        for tag in list(self._dynamic_tags):
            w.tag_delete(tag)
        self._dynamic_tags.clear()

    def render(self, _event=None) -> None:
        if self._render_job:
            self.widget.after_cancel(self._render_job)
            self._render_job = None
        w = self.widget
        self._clear_render_state()

        raw = w.get("1.0", "end-1c")
        if not raw:
            return
        lines = raw.split("\n")
        infos = analyze(raw)

        has_focus = w.focus_displayof() is w
        active_line = int(w.index("insert").split(".")[0]) if has_focus else -1
        # If there is an active text selection, keep all selected lines un-elided for clean copy/edit.
        sel_lines: set[int] = set()
        if w.tag_ranges("sel"):
            s_line = int(w.index("sel.first").split(".")[0])
            e_line = int(w.index("sel.last").split(".")[0])
            sel_lines = set(range(s_line, e_line + 1))

        active_block = -1
        if 1 <= active_line <= len(infos):
            active_block = infos[active_line - 1].block

        # Group contiguous table blocks
        tables: dict[int, list[int]] = {}
        for idx, info in enumerate(infos, 1):
            if info.kind in {"table_header", "table_separator", "table_row"}:
                tables.setdefault(info.block, []).append(idx)

        rendered_tables: set[int] = set()

        for line_no, (line, info) in enumerate(zip(lines, infos), 1):
            is_active = (not self.live_preview) or (line_no == active_line) or (line_no in sel_lines) or (
                info.block != -1 and info.block == active_block
            )

            # 1. Fenced code block
            if info.kind == "fence":
                w.tag_add("md-fence", f"{line_no}.0", f"{line_no}.end")
                if not is_active:
                    w.tag_add("md-hide", f"{line_no}.0", f"{line_no}.end")
                continue
            if info.kind == "code":
                w.tag_add("md-codeblock", f"{line_no}.0", f"{line_no}.end")
                continue

            # 2. GFM Table
            if info.kind in {"table_header", "table_separator", "table_row"}:
                if is_active:
                    w.tag_add("md-table-raw", f"{line_no}.0", f"{line_no}.end")
                    if info.kind != "table_separator":
                        self._render_inline(line_no, line, 0, is_active=True)
                else:
                    if info.block not in rendered_tables:
                        rendered_tables.add(info.block)
                        self._render_table_block(tables[info.block], lines)
                continue

            # 3. Horizontal rule
            if info.kind == "hr":
                if is_active:
                    w.tag_add("md-syntax", f"{line_no}.0", f"{line_no}.end")
                else:
                    w.tag_add("md-hr-line", f"{line_no}.0", f"{line_no}.end")
                continue

            # 4. Blockquote (supports nested headings/lists inside the quote)
            if info.kind == "quote":
                w.tag_add("md-quote", f"{line_no}.0", f"{line_no}.end")
                self._mark_or_hide(line_no, 0, info.marker_end, is_active)
                inner: LineInfo | None = info.extra.get("inner")
                content_start = info.content_start
                if inner and inner.kind == "heading":
                    w.tag_add(f"md-h{inner.level}", f"{line_no}.0", f"{line_no}.end")
                    self._mark_or_hide(line_no, content_start, content_start + inner.marker_end, is_active)
                    content_start += inner.content_start
                self._render_inline(line_no, line, content_start, is_active)
                continue

            # 5. Heading (# .. ######)
            if info.kind == "heading":
                w.tag_add(f"md-h{info.level}", f"{line_no}.0", f"{line_no}.end")
                self._mark_or_hide(line_no, 0, info.marker_end, is_active)
                self._render_inline(line_no, line, info.content_start, is_active)
                continue

            # 6. Lists & Task lists
            if info.kind == "list":
                level = min(info.level, 5)
                w.tag_add(f"md-list-{level}", f"{line_no}.0", f"{line_no}.end")
                w.tag_add("md-syntax", f"{line_no}.0", f"{line_no}.{info.marker_end}")
                if info.task is not None:
                    t_start, t_end = info.task_range
                    self._render_task_checkbox(line_no, t_start, t_end, info.task == "x", is_active)
                    if info.task == "x":
                        w.tag_add("md-task-done", f"{line_no}.{info.content_start}", f"{line_no}.end")
                self._render_inline(line_no, line, info.content_start, is_active)
                continue

            # 7. Paragraph
            if info.kind == "paragraph":
                self._render_inline(line_no, line, 0, is_active)

    def _mark_or_hide(self, line_no: int, start: int, end: int, is_active: bool) -> None:
        if end <= start:
            return
        tag = "md-syntax" if is_active else "md-hide"
        self.widget.tag_add(tag, f"{line_no}.{start}", f"{line_no}.{end}")

    def _render_task_checkbox(self, line_no: int, start: int, end: int, checked: bool, is_active: bool) -> None:
        w = self.widget
        tag = f"md-task-{line_no}"
        self._dynamic_tags.add(tag)
        w.tag_configure(
            tag,
            foreground=resolve(Colors.primary) if checked else resolve(Colors.text_sub),
            font=(self.font_family, 13, "bold"),
        )
        w.tag_bind(tag, "<Enter>", lambda _e: w.configure(cursor="hand2"))
        w.tag_bind(tag, "<Leave>", lambda _e: w.configure(cursor="xterm"))
        w.tag_bind(
            tag,
            "<Button-1>",
            lambda _e, ln=line_no, s=start, e=end: (self._toggle_task(ln, s, e), "break")[1],
        )
        w.tag_add(tag, f"{line_no}.{start}", f"{line_no}.{end}")
        if not is_active:
            # Hide the outer brackets [ and ] so only the check state stands out cleanly.
            w.tag_add("md-hide", f"{line_no}.{start}", f"{line_no}.{start + 1}")
            w.tag_add("md-hide", f"{line_no}.{end - 1}", f"{line_no}.{end}")

    def _render_inline(self, line_no: int, line: str, start_offset: int, is_active: bool) -> None:
        tokens = parse_inline(line[start_offset:], base=start_offset)
        self._apply_tokens(line_no, tokens, is_active)

    def _apply_tokens(self, line_no: int, tokens: list[InlineToken], is_active: bool) -> None:
        w = self.widget
        tag_map = {
            "bold": "md-bold",
            "italic": "md-italic",
            "bolditalic": "md-bolditalic",
            "strike": "md-strike",
            "highlight": "md-highlight",
            "code": "md-code",
            "wikilink": "md-wikilink",
            "link": "md-link",
            "url": "md-url",
            "image": "md-image",
        }
        for tok in tokens:
            for m_start, m_end in tok.markers:
                self._mark_or_hide(line_no, m_start, m_end, is_active)
            style_tag = tag_map.get(tok.kind)
            if style_tag and tok.content_end > tok.content_start:
                w.tag_add(style_tag, f"{line_no}.{tok.content_start}", f"{line_no}.{tok.content_end}")
            if tok.children:
                self._apply_tokens(line_no, list(tok.children), is_active)

    # --------------------------------------------------------- table widgets
    def _render_table_block(self, line_numbers: list[int], all_lines: list[str]) -> None:
        """Render a GFM table as a styled grid widget and elide the raw pipe lines."""
        if len(line_numbers) < 2:
            return
        w = self.widget
        first_line = line_numbers[0]
        last_line = line_numbers[-1]
        header_line = all_lines[first_line - 1]
        sep_line = all_lines[first_line]
        body_lines = [all_lines[ln - 1] for ln in line_numbers[2:]]

        aligns = table_alignments(sep_line)
        header_ranges = split_table_row(header_line)
        col_count = max(len(aligns), len(header_ranges), 1)
        while len(aligns) < col_count:
            aligns.append("left")

        def extract_cells(raw_line: str) -> list[str]:
            cells = [raw_line[s:e] for s, e in split_table_row(raw_line)]
            while len(cells) < col_count:
                cells.append("")
            return cells[:col_count]

        rows_data = [extract_cells(header_line)] + [extract_cells(bl) for bl in body_lines]

        # Hide the raw Markdown lines; keep the final newline of the last line so vertical flow stays intact.
        for ln in line_numbers[:-1]:
            w.tag_add("md-hide", f"{ln}.0", f"{ln + 1}.0")
        w.tag_add("md-hide", f"{last_line}.0", f"{last_line}.end")

        outer = tk.Frame(
            w,
            bg=resolve(Colors.border),
            bd=0,
            highlightthickness=1,
            highlightbackground=resolve(Colors.border),
        )
        for col_idx in range(col_count):
            outer.grid_columnconfigure(col_idx, weight=1)

        anchor_map = {"left": "w", "center": "center", "right": "e"}
        justify_map = {"left": "left", "center": "center", "right": "right"}

        for row_idx, cells in enumerate(rows_data):
            is_header = row_idx == 0
            source_line = first_line if is_header else line_numbers[row_idx + 1]
            bg = resolve(Colors.table_header_bg if is_header else (Colors.bg if row_idx % 2 == 1 else Colors.table_row_bg))
            for col_idx, cell_text in enumerate(cells):
                align = aligns[col_idx]
                cell_frame = tk.Frame(outer, bg=bg, padx=12, pady=6)
                cell_frame.grid(
                    row=row_idx,
                    column=col_idx,
                    sticky="nsew",
                    padx=(0, 1 if col_idx < col_count - 1 else 0),
                    pady=(0, 1 if row_idx < len(rows_data) - 1 else 0),
                )
                self._populate_table_cell(
                    cell_frame,
                    cell_text,
                    bg=bg,
                    is_header=is_header,
                    anchor=anchor_map[align],
                    justify=justify_map[align],
                    source_line=source_line,
                )

        try:
            w.window_create(f"{last_line}.end", window=outer, padx=4, pady=6)
            self._embedded_widgets.append(outer)
        except tk.TclError:
            outer.destroy()

    def _populate_table_cell(
        self,
        parent: tk.Frame,
        raw_cell: str,
        bg: str,
        is_header: bool,
        anchor: str,
        justify: str,
        source_line: int,
    ) -> None:
        tokens = parse_inline(raw_cell)
        base_weight = "bold" if is_header else "normal"
        fg = resolve(Colors.text)

        # Fast path for plain cells or single-token cells
        if not tokens:
            lbl = tk.Label(
                parent,
                text=raw_cell,
                bg=bg,
                fg=fg,
                font=(self.font_family, 13, base_weight),
                anchor=anchor,
                justify=justify,
            )
            lbl.pack(fill="x", expand=True)
            for widget in (parent, lbl):
                widget.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))
            return

        row = tk.Frame(parent, bg=bg)
        row.pack(anchor=anchor)
        parent.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))
        row.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))

        pos = 0
        for tok in tokens:
            if tok.start > pos:
                seg = tk.Label(
                    row,
                    text=raw_cell[pos:tok.start],
                    bg=bg,
                    fg=fg,
                    font=(self.font_family, 13, base_weight),
                )
                seg.pack(side="left")
                seg.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))

            visible = raw_cell[tok.content_start:tok.content_end]
            font_style = base_weight
            seg_fg = fg
            seg_bg = bg
            font_name = self.font_family
            underline = False
            overstrike = False

            if tok.kind in {"bold", "bolditalic"}:
                font_style = "bold italic" if tok.kind == "bolditalic" else "bold"
            elif tok.kind == "italic":
                font_style = "bold italic" if is_header else "italic"
            elif tok.kind == "code":
                font_name = MONO_FAMILY
                seg_fg = resolve(Colors.code)
                seg_bg = resolve(Colors.code_bg)
            elif tok.kind == "highlight":
                seg_bg = resolve(Colors.highlight)
            elif tok.kind == "strike":
                overstrike = True
                seg_fg = resolve(Colors.text_sub)
            elif tok.kind in {"wikilink", "link", "url"}:
                seg_fg = resolve(Colors.primary)
                underline = True

            font_tuple: tuple = (font_name, 12 if font_name == MONO_FAMILY else 13, font_style)
            if underline:
                font_tuple = (*font_tuple, "underline")
            if overstrike:
                font_tuple = (*font_tuple, "overstrike")

            seg = tk.Label(row, text=visible, bg=seg_bg, fg=seg_fg, font=font_tuple, padx=2 if tok.kind == "code" else 0)
            seg.pack(side="left")
            if tok.kind == "wikilink" and tok.target:
                seg.configure(cursor="hand2")
                seg.bind("<Button-1>", lambda _e, t=tok.target: self.on_open_wikilink(t))
            elif tok.kind in {"link", "url"} and tok.target:
                seg.configure(cursor="hand2")
                seg.bind(
                    "<Button-1>",
                    lambda _e, t=tok.target: webbrowser.open(t)
                    if t.startswith(("http://", "https://", "mailto:"))
                    else self.on_open_wikilink(t.removesuffix(".md")),
                )
            else:
                seg.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))
            pos = tok.end

        if pos < len(raw_cell):
            tail = tk.Label(
                row,
                text=raw_cell[pos:],
                bg=bg,
                fg=fg,
                font=(self.font_family, 13, base_weight),
            )
            tail.pack(side="left")
            tail.bind("<Button-1>", lambda _e, ln=source_line: self._focus_line(ln))

