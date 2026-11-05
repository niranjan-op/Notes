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

import base64
import binascii
import ctypes
import hashlib
import io
import re
import sys
import tkinter as tk
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageGrab, ImageOps, ImageSequence, ImageTk, UnidentifiedImageError

from app.core.markdown import (
    InlineToken,
    LineInfo,
    analyze_lines,
    next_list_prefix,
    parse_inline,
    split_table_row,
    table_alignments,
)
from app.core.vault import IMAGE_EXTENSIONS
from .styles import MONO_FAMILY, Colors, Fonts, Metrics, resolve

VIEWPORT_FULL_DOC_LIMIT = 400
VIEWPORT_BUFFER_LINES = 80
VIEWPORT_CONTEXT_LINES = 60
MAX_EMBEDDED_TABLE_CELLS = 120
MAX_IMAGE_WIDTH = 560
MAX_IMAGE_HEIGHT = 420
MAX_TABLE_IMAGE_WIDTH = 220
MAX_TABLE_IMAGE_HEIGHT = 160
MAX_GIF_FRAMES = 120
MAX_MEDIA_CACHE = 48
_WIDTH_HINT_RE = re.compile(r"^(?:(.*?)\|)?(\d{2,4})(?:x(\d{2,4}))?$")
_HTML_DATA_GIF_RE = re.compile(r'src=["\'](data:image/gif;base64,([A-Za-z0-9+/=%]+))["\']', re.IGNORECASE)
_HTML_FILE_GIF_RE = re.compile(r'src=["\'](file:///[^"\']+?\.gif)["\']', re.IGNORECASE)
_STATIC_TAGS = (
    "md-hide", "md-syntax",
    "md-h1", "md-h2", "md-h3", "md-h4", "md-h5", "md-h6",
    "md-bold", "md-italic", "md-bolditalic", "md-strike", "md-highlight",
    "md-code", "md-wikilink", "md-link", "md-url", "md-image",
    "md-quote", "md-codeblock", "md-fence", "md-hr-line",
    "md-task-done", "md-task-checked", "md-task-unchecked", "md-table-raw",
    *(f"md-list-{i}" for i in range(6)),
)


@dataclass
class _DecodedMedia:
    frames: list[ImageTk.PhotoImage]
    durations: list[int]
    width: int
    height: int
    is_gif: bool = False
    current_frame: int = 0
    raw_frames: list[Image.Image] = field(default_factory=list, repr=False)


def _validate_image_bytes(raw: bytes) -> str | None:
    """Verify ``raw`` is a readable image and return its normalized extension (e.g. '.gif', '.png')."""
    if not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            fmt = (im.format or "").upper()
            im.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return None
    ext_map = {
        "GIF": ".gif",
        "PNG": ".png",
        "JPEG": ".jpg",
        "JPG": ".jpg",
        "WEBP": ".webp",
        "BMP": ".bmp",
        "DIB": ".png",
    }
    return ext_map.get(fmt, ".png")


def serialize_pil_image(img: Image.Image) -> tuple[bytes, str, str]:
    """Encode a PIL Image (including multi-frame GIFs) into raw bytes."""
    buf = io.BytesIO()
    is_anim = bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)
    fmt = (getattr(img, "format", "") or "").upper()
    if is_anim or fmt == "GIF":
        frames: list[Image.Image] = []
        durations: list[int] = []
        for frame in ImageSequence.Iterator(img):
            frames.append(frame.copy())
            durations.append(max(25, int(frame.info.get("duration", 80) or 80)))
        if len(frames) > 1:
            frames[0].save(
                buf,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=int(img.info.get("loop", 0) or 0),
                disposal=2,
            )
        else:
            img.save(buf, format="GIF")
        return buf.getvalue(), ".gif", "pasted-gif"
    out = img.convert("RGBA") if img.mode not in {"RGB", "RGBA", "L"} else img
    out.save(buf, format="PNG")
    return buf.getvalue(), ".png", "pasted-image"


def load_image_file(path: str | Path) -> tuple[bytes, str, str]:
    """Read and validate an image or GIF file from disk without stripping animation frames."""
    source = Path(path)
    if not source.is_file():
        raise ValueError("Image file does not exist.")
    raw = source.read_bytes()
    detected_ext = _validate_image_bytes(raw)
    if detected_ext is None:
        raise ValueError("Unsupported or corrupted image file.")
    ext = source.suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in IMAGE_EXTENSIONS or detected_ext == ".gif":
        ext = detected_ext
    return raw, ext, source.stem or ("pasted-gif" if ext == ".gif" else "pasted-image")


def _grab_win32_clipboard_gif() -> list[tuple[bytes, str, str]]:
    """Inspect Windows clipboard for native GIF bytes or HTML-embedded GIFs before DIB fallback."""
    if sys.platform != "win32":
        return []
    try:
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.OpenClipboard.restype = wintypes.BOOL
        u32.CloseClipboard.argtypes = []
        u32.CloseClipboard.restype = wintypes.BOOL
        u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        u32.RegisterClipboardFormatW.restype = wintypes.UINT
        u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        u32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        u32.GetClipboardData.argtypes = [wintypes.UINT]
        u32.GetClipboardData.restype = wintypes.HANDLE
        k32.GlobalLock.argtypes = [wintypes.HANDLE]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalUnlock.argtypes = [wintypes.HANDLE]
        k32.GlobalUnlock.restype = wintypes.BOOL
        k32.GlobalSize.argtypes = [wintypes.HANDLE]
        k32.GlobalSize.restype = ctypes.c_size_t

        def read_format(name: str) -> bytes | None:
            fmt_id = u32.RegisterClipboardFormatW(name)
            if not fmt_id or not u32.IsClipboardFormatAvailable(fmt_id):
                return None
            handle = u32.GetClipboardData(fmt_id)
            if not handle:
                return None
            size = k32.GlobalSize(handle)
            if not size:
                return None
            ptr = k32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.string_at(ptr, size)
            finally:
                k32.GlobalUnlock(handle)

        if not u32.OpenClipboard(None):
            return []
        try:
            for fmt_name in ("image/gif", "GIF"):
                raw = read_format(fmt_name)
                if raw and _validate_image_bytes(raw) == ".gif":
                    return [(raw, ".gif", "pasted-gif")]

            html_bytes = read_format("HTML Format")
            if html_bytes:
                html_text = html_bytes.decode("utf-8", errors="ignore")
                m_data = _HTML_DATA_GIF_RE.search(html_text)
                if m_data:
                    b64_str = urllib.parse.unquote(m_data.group(2))
                    raw = base64.b64decode(b64_str, validate=False)
                    if _validate_image_bytes(raw) == ".gif":
                        return [(raw, ".gif", "pasted-gif")]
                m_file = _HTML_FILE_GIF_RE.search(html_text)
                if m_file:
                    parsed = urllib.parse.urlparse(m_file.group(1))
                    local_path = Path(urllib.parse.unquote(parsed.path.lstrip("/")))
                    if local_path.is_file():
                        return [load_image_file(local_path)]
        finally:
            u32.CloseClipboard()
    except (OSError, ValueError, binascii.Error):
        return []
    return []


def grab_clipboard_images() -> list[tuple[bytes, str, str]]:
    """Return a list of ``(raw_bytes, ext, name_hint)`` from the OS clipboard, or ``[]``."""
    win_gifs = _grab_win32_clipboard_gif()
    if win_gifs:
        return win_gifs

    try:
        grabbed = ImageGrab.grabclipboard()
    except (OSError, ValueError, NotImplementedError, ChildProcessError):
        return []

    if isinstance(grabbed, list):
        items: list[tuple[bytes, str, str]] = []
        for entry in grabbed:
            try:
                p = Path(entry)
                if p.suffix.lower() in IMAGE_EXTENSIONS and p.is_file():
                    items.append(load_image_file(p))
            except (OSError, ValueError):
                continue
        return items

    if isinstance(grabbed, Image.Image):
        try:
            return [serialize_pil_image(grabbed)]
        except (OSError, ValueError):
            return []

    return []


class MarkdownEditorController:
    """Attaches live-preview Markdown rendering and editing helpers to a CTkTextbox."""

    def __init__(
        self,
        textbox: ctk.CTkTextbox,
        on_open_wikilink: Callable[[str], None],
        on_modified: Callable[[], None],
        font_family: str = "Segoe UI",
        resolve_image: Callable[[str], bytes | None] | None = None,
        on_paste_image: Callable[[bytes, str, str], str | None] | None = None,
    ):
        self.textbox = textbox
        self.widget: tk.Text = textbox._textbox
        self.on_open_wikilink = on_open_wikilink
        self.on_modified = on_modified
        self.font_family = font_family
        self.resolve_image = resolve_image
        self.on_paste_image = on_paste_image
        self.live_preview = True  # when False (Source mode), syntax markers are never elided
        self.reading_mode = False  # when True, editing is disabled and all Markdown is rendered
        self._embedded_widgets: list[tk.Widget] = []
        self._gif_jobs: dict[tk.Widget, str] = {}
        self._media_cache: dict[tuple[str, int, int], _DecodedMedia] = {}
        self._line_cache: dict[int, tuple] = {}
        self._line_tags: dict[int, set[str]] = {}
        self._last_total_lines: int = 0
        self._render_job: str | None = None
        self._rendered_range: tuple[int, int] | None = None
        self._last_scroll_top: int = 1
        self._is_rendering = False
        self._configure_tags()
        self._bind_events()

    # --------------------------------------------------------------- setup
    def clear_media_cache(self) -> None:
        """Drop all cached PhotoImage frames and cancel active GIF timers."""
        self._cancel_gif_jobs()
        self._media_cache.clear()

    def _cancel_gif_jobs(self) -> None:
        for job in list(self._gif_jobs.values()):
            try:
                self.widget.after_cancel(job)
            except tk.TclError:
                pass
        self._gif_jobs.clear()

    def _invalidate_render_cache(self, clear_widgets: bool = False) -> None:
        self._line_cache.clear()
        if clear_widgets and self._embedded_widgets:
            for child in list(self._embedded_widgets):
                self._destroy_embedded_widget(child)
            self._embedded_widgets.clear()

    def set_font_family(self, family: str) -> None:
        self.font_family = family
        self._configure_tags()
        self._invalidate_render_cache(clear_widgets=True)
        self.render()

    def set_live_preview(self, enabled: bool) -> None:
        if self.live_preview == enabled:
            return
        self.live_preview = enabled
        self._invalidate_render_cache(clear_widgets=False)
        self.render()

    def set_reading_mode(self, enabled: bool) -> None:
        self.reading_mode = enabled
        self._invalidate_render_cache(clear_widgets=True)
        self.render()
        self.widget.configure(
            state="disabled" if enabled else "normal",
            insertwidth=0 if enabled else 2,
        )

    def apply_theme(self) -> None:
        self._configure_tags()
        self._invalidate_render_cache(clear_widgets=True)
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
        w.tag_configure("md-task-checked", foreground=primary, font=(family, 13, "bold"))
        w.tag_configure("md-task-unchecked", foreground=sub, font=(family, 13, "bold"))
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
        w.bind("<KeyRelease>", self._on_key_release, add="+")
        for seq in ("<ButtonRelease-1>", "<FocusIn>", "<FocusOut>"):
            w.bind(seq, self.queue_render, add="+")
        w.bind("<MouseWheel>", self._on_mousewheel, add="+")
        w.bind("<Return>", self._on_return)
        w.bind("<<Paste>>", self._on_paste)

        orig_yscroll = w.cget("yscrollcommand")
        if orig_yscroll:
            def _on_yscroll(*args):
                self.widget.tk.call(orig_yscroll, *args)
                if not self._is_rendering:
                    try:
                        top_line = int(w.index("@0,0").split(".")[0])
                        if abs(top_line - self._last_scroll_top) >= 20:
                            self.queue_render()
                    except tk.TclError:
                        pass
            w.configure(yscrollcommand=_on_yscroll)

        for tag in ("md-wikilink", "md-link", "md-url", "md-task-checked", "md-task-unchecked"):
            w.tag_bind(tag, "<Enter>", lambda _e: w.configure(cursor="hand2"))
            w.tag_bind(tag, "<Leave>", lambda _e: w.configure(cursor="xterm"))
        w.tag_bind("md-wikilink", "<Button-1>", self._click_wikilink)
        w.tag_bind("md-link", "<Button-1>", self._click_external_link)
        w.tag_bind("md-url", "<Button-1>", self._click_external_link)
        w.tag_bind("md-task-checked", "<Button-1>", self._click_task_checkbox)
        w.tag_bind("md-task-unchecked", "<Button-1>", self._click_task_checkbox)

    def _on_key_release(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in {
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Caps_Lock", "Super_L", "Super_R",
        }:
            return
        self.queue_render()

    def _on_mousewheel(self, _event=None) -> None:
        try:
            total_lines = int(self.widget.index("end-1c").split(".")[0])
            if total_lines > VIEWPORT_FULL_DOC_LIMIT:
                top_line = int(self.widget.index("@0,0").split(".")[0])
                if abs(top_line - self._last_scroll_top) >= 20:
                    self.queue_render()
        except tk.TclError:
            pass

    # --------------------------------------------------------- smart editing
    def _on_paste(self, _event=None) -> str | None:
        if self.reading_mode:
            return "break"
        if self.paste_from_clipboard():
            return "break"
        self.widget.after_idle(self._after_text_paste)
        return None

    def _after_text_paste(self) -> None:
        self.on_modified()
        self.queue_render()

    def paste_from_clipboard(self) -> bool:
        """If the clipboard holds one or more images/GIFs, store and insert them. Returns True if handled."""
        if self.reading_mode or self.on_paste_image is None:
            return False
        items = grab_clipboard_images()
        if not items:
            return False
        inserted = False
        for raw_bytes, ext, name_hint in items:
            if self.insert_image_bytes(raw_bytes, ext, name_hint, render_now=False):
                inserted = True
        if inserted:
            self.on_modified()
            self.render()
        return inserted

    def insert_image_bytes(
        self,
        raw_bytes: bytes,
        ext: str = ".png",
        name_hint: str = "pasted-image",
        render_now: bool = True,
    ) -> bool:
        """Persist ``raw_bytes`` via ``on_paste_image`` and insert Markdown image syntax at the caret."""
        if self.reading_mode or self.on_paste_image is None or not raw_bytes:
            return False
        target = self.on_paste_image(raw_bytes, ext, name_hint)
        if not target:
            return False
        w = self.widget
        if w.tag_ranges("sel"):
            w.delete("sel.first", "sel.last")
        alt = Path(name_hint).stem or ("gif" if ext.lower() == ".gif" else "image")
        alt = alt.replace("[", "").replace("]", "").strip() or "image"
        insert_idx = w.index("insert")
        line_no, col = map(int, insert_idx.split("."))
        line_text = w.get(f"{line_no}.0", f"{line_no}.end")
        prefix = "\n" if col > 0 and line_text[:col].strip() else ""
        snippet = f"{prefix}![{alt}]({target})\n"
        w.insert("insert", snippet)
        w.see("insert")
        if render_now:
            self.on_modified()
            self.render()
        return True
    def _on_return(self, event) -> str | None:
        """Continue lists/blockquotes/tasks on Enter, or exit an empty item."""
        if self.reading_mode:
            return "break"
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
        if self.reading_mode:
            return
        w = self.widget
        current = w.get(f"{line_no}.{start_col}", f"{line_no}.{end_col}")
        replacement = "[ ]" if "x" in current.lower() else "[x]"
        w.replace(f"{line_no}.{start_col}", f"{line_no}.{end_col}", replacement)
        self.on_modified()
        self.render()

    def _focus_line(self, line_no: int, col: int = 0) -> None:
        if self.reading_mode:
            return
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

    def _click_task_checkbox(self, event) -> str | None:
        w = self.widget
        idx = w.index(f"@{event.x},{event.y}")
        line_no = int(idx.split(".")[0])
        line = w.get(f"{line_no}.0", f"{line_no}.end")
        info = analyze_lines([line])[0]
        if info.kind == "list" and info.task is not None:
            t_start, t_end = info.task_range
            self._toggle_task(line_no, t_start, t_end)
            return "break"
        return None

    # ------------------------------------------------------------- rendering
    def reset(self) -> None:
        """Clear all rendered widgets and tags across the entire document."""
        if self._render_job:
            self.widget.after_cancel(self._render_job)
            self._render_job = None
        was_disabled = str(self.widget.cget("state")) == "disabled"
        if was_disabled:
            self.widget.configure(state="normal")
        try:
            self._clear_render_state(1, None)
            self._rendered_range = None
            self._line_cache.clear()
            self._line_tags.clear()
            self._last_total_lines = 0
        finally:
            if was_disabled or self.reading_mode:
                self.widget.configure(state="disabled", insertwidth=0)

    def queue_render(self, _event=None) -> None:
        if self._render_job:
            self.widget.after_cancel(self._render_job)
        self._render_job = self.widget.after(18, self.render)

    def _destroy_embedded_widget(self, child: tk.Widget) -> None:
        w = self.widget
        job = self._gif_jobs.pop(child, None)
        if job is not None:
            try:
                w.after_cancel(job)
            except tk.TclError:
                pass
        for sub in list(self._gif_jobs.keys()):
            try:
                if str(sub).startswith(str(child) + "."):
                    sub_job = self._gif_jobs.pop(sub, None)
                    if sub_job is not None:
                        w.after_cancel(sub_job)
            except tk.TclError:
                pass
        was_undo = bool(w.cget("undo"))
        if was_undo:
            w.configure(undo=False)
        try:
            try:
                w.delete(child)
            except tk.TclError:
                pass
            try:
                child.destroy()
            except tk.TclError:
                pass
        finally:
            if was_undo:
                w.configure(undo=True)

    def _clear_render_state(self, start_line: int = 1, end_line: int | None = None) -> None:
        w = self.widget
        self._cancel_gif_jobs()
        if self._embedded_widgets:
            for child in list(self._embedded_widgets):
                self._destroy_embedded_widget(child)
            self._embedded_widgets.clear()

        start_idx = f"{max(1, start_line)}.0"
        end_idx = f"{end_line}.end" if end_line is not None else "end"
        for tag in _STATIC_TAGS:
            w.tag_remove(tag, start_idx, end_idx)

    @staticmethod
    def _add_span(desired: dict[str, list[tuple[int, int]]], tag: str, start: int, end: int) -> None:
        if end > start:
            desired.setdefault(tag, []).append((start, end))

    @staticmethod
    def _merge_spans(spans: list[tuple[int, int]], line_len: int) -> list[tuple[int, int]]:
        cleaned = [
            (max(0, s), min(line_len, e))
            for s, e in spans
            if min(line_len, e) > max(0, s)
        ]
        if not cleaned:
            return []
        cleaned.sort()
        merged: list[tuple[int, int]] = [cleaned[0]]
        for s, e in cleaned[1:]:
            prev_s, prev_e = merged[-1]
            if s <= prev_e:
                merged[-1] = (prev_s, max(prev_e, e))
            else:
                merged.append((s, e))
        return merged

    def _sync_line_tags(
        self,
        line_no: int,
        line_len: int,
        desired: dict[str, list[tuple[int, int]]],
        hide_newline: bool,
        full_clean: bool = False,
    ) -> None:
        w = self.widget
        old_tags = set(_STATIC_TAGS) if full_clean else self._line_tags.get(line_no, set())
        new_tags: set[str] = set()

        for tag, raw_spans in desired.items():
            spans = self._merge_spans(raw_spans, line_len)
            if not spans:
                continue
            new_tags.add(tag)
            cursor = 0
            for s, e in spans:
                if s > cursor:
                    w.tag_remove(tag, f"{line_no}.{cursor}", f"{line_no}.{s}")
                w.tag_add(tag, f"{line_no}.{s}", f"{line_no}.{e}")
                cursor = e
            if cursor < line_len:
                w.tag_remove(tag, f"{line_no}.{cursor}", f"{line_no}.{line_len}")

        for tag in old_tags - new_tags:
            w.tag_remove(tag, f"{line_no}.0", f"{line_no}.{line_len}")

        if hide_newline:
            w.tag_add("md-hide", f"{line_no}.{line_len}", f"{line_no + 1}.0")
        else:
            w.tag_remove("md-hide", f"{line_no}.{line_len}", f"{line_no + 1}.0")

        self._line_tags[line_no] = new_tags

    def render(self, _event=None) -> None:
        if self._render_job:
            self.widget.after_cancel(self._render_job)
            self._render_job = None
        if self._is_rendering:
            return
        self._is_rendering = True
        if self.reading_mode:
            self.widget.configure(state="normal")
        try:
            self._render_viewport()
        finally:
            if self.reading_mode:
                self.widget.configure(state="disabled", insertwidth=0)
            self._is_rendering = False

    def _render_viewport(self) -> None:
        w = self.widget
        if w.compare("end-1c", "==", "1.0"):
            if self._rendered_range is not None or self._embedded_widgets:
                self._clear_render_state(1, None)
                self._rendered_range = None
                self._line_cache.clear()
                self._line_tags.clear()
                self._last_total_lines = 0
            return

        total_lines = int(w.index("end-1c").split(".")[0])
        lines_shifted = total_lines != self._last_total_lines
        if lines_shifted:
            self._line_cache.clear()
            self._line_tags.clear()
            self._last_total_lines = total_lines

        if total_lines <= VIEWPORT_FULL_DOC_LIMIT:
            win_start = ctx_start = 1
            win_end = ctx_end = total_lines
            self._last_scroll_top = 1
        else:
            first_vis = int(w.index("@0,0").split(".")[0])
            height = max(w.winfo_height(), 1)
            last_vis = int(w.index(f"@0,{height}").split(".")[0])
            if last_vis < first_vis:
                last_vis = min(total_lines, first_vis + 50)
            self._last_scroll_top = first_vis
            win_start = max(1, first_vis - VIEWPORT_BUFFER_LINES)
            win_end = min(total_lines, max(last_vis + VIEWPORT_BUFFER_LINES, win_start + 160))
            ctx_start = max(1, win_start - VIEWPORT_CONTEXT_LINES)
            ctx_end = min(total_lines, win_end + VIEWPORT_CONTEXT_LINES)

        if self._rendered_range is not None:
            prev_start, prev_end = self._rendered_range
            if prev_start < win_start:
                for tag in _STATIC_TAGS:
                    w.tag_remove(tag, f"{prev_start}.0", f"{win_start}.0")
                for ln in range(prev_start, win_start):
                    self._line_cache.pop(ln, None)
                    self._line_tags.pop(ln, None)
            if prev_end > win_end:
                for tag in _STATIC_TAGS:
                    w.tag_remove(tag, f"{win_end + 1}.0", f"{prev_end}.end")
                for ln in range(win_end + 1, prev_end + 1):
                    self._line_cache.pop(ln, None)
                    self._line_tags.pop(ln, None)
        self._rendered_range = (ctx_start, ctx_end)

        raw = w.get(f"{ctx_start}.0", f"{ctx_end}.end")
        if not raw:
            return
        lines = raw.split("\n")
        infos = analyze_lines(lines)

        has_focus = w.focus_displayof() is w
        active_line = int(w.index("insert").split(".")[0]) if has_focus else -1
        sel_range: tuple[int, int] | None = None
        if w.tag_ranges("sel"):
            s_line = int(w.index("sel.first").split(".")[0])
            e_line = int(w.index("sel.last").split(".")[0])
            sel_range = (s_line, e_line)

        active_block = -1
        if ctx_start <= active_line <= ctx_start + len(infos) - 1:
            active_block = infos[active_line - ctx_start].block

        existing_by_key: dict[tuple, list[tk.Widget]] = {}
        alive_widgets: list[tuple[int, tk.Widget]] = []
        for child in self._embedded_widgets:
            try:
                idx = w.index(child)
                cur_line = int(idx.split(".")[0])
                spec = getattr(child, "_md_spec", None)
                if spec is not None and win_start <= cur_line <= win_end:
                    existing_by_key.setdefault((cur_line, spec), []).append(child)
                    alive_widgets.append((cur_line, child))
                    continue
            except tk.TclError:
                pass
            self._destroy_embedded_widget(child)

        # Group contiguous table blocks inside the context slice
        tables: dict[int, list[int]] = {}
        for offset, info in enumerate(infos):
            if info.kind in {"table_header", "table_separator", "table_row"}:
                tables.setdefault(info.block, []).append(ctx_start + offset)

        processed_tables: set[int] = set()
        line_plans: list[tuple[int, int, dict[str, list[tuple[int, int]]], bool, tuple]] = []
        reused_lines: set[int] = set()
        kept_widgets: list[tk.Widget] = []
        kept_set: set[tk.Widget] = set()
        to_create_images: list[tuple[int, InlineToken, _DecodedMedia, tuple]] = []
        to_create_tables: list[tuple[list[int], list[str], list[list[str]], tuple]] = []

        for offset, (line, info) in enumerate(zip(lines, infos)):
            line_no = ctx_start + offset
            if line_no < win_start or line_no > win_end:
                continue
            if self.reading_mode:
                is_active = False
            else:
                in_sel = sel_range is not None and sel_range[0] <= line_no <= sel_range[1]
                is_active = (not self.live_preview) or (line_no == active_line) or in_sel or (
                    info.block != -1 and info.block == active_block
                )

            desired: dict[str, list[tuple[int, int]]] = {}
            hide_newline = False
            pending_embeds: list[tuple[InlineToken, _DecodedMedia]] = []
            line_len = len(line)

            # 1. Fenced code block
            if info.kind == "fence":
                self._add_span(desired, "md-fence", 0, line_len)
                if not is_active:
                    self._add_span(desired, "md-hide", 0, line_len)
            elif info.kind == "code":
                self._add_span(desired, "md-codeblock", 0, line_len)

            # 2. GFM Table
            elif info.kind in {"table_header", "table_separator", "table_row"}:
                if is_active:
                    self._add_span(desired, "md-table-raw", 0, line_len)
                    if info.kind != "table_separator":
                        self._collect_inline(desired, line, 0, is_active=True, pending_embeds=pending_embeds)
                else:
                    t_lines = tables.get(info.block, [line_no])
                    t_plan = self._plan_table_block(t_lines, lines, ctx_start)
                    if t_plan is None:
                        self._add_span(desired, "md-table-raw", 0, line_len)
                    else:
                        aligns, rows_data, table_spec = t_plan
                        self._add_span(desired, "md-hide", 0, line_len)
                        hide_newline = line_no != t_lines[-1]
                        if info.block not in processed_tables:
                            processed_tables.add(info.block)
                            last_ln = t_lines[-1]
                            bucket = existing_by_key.get((last_ln, table_spec))
                            if bucket:
                                outer = bucket.pop(0)
                                kept_widgets.append(outer)
                                kept_set.add(outer)
                                reused_lines.update(t_lines)
                            else:
                                to_create_tables.append((t_lines, aligns, rows_data, table_spec))

            # 3. Horizontal rule
            elif info.kind == "hr":
                self._add_span(desired, "md-syntax" if is_active else "md-hr-line", 0, line_len)

            # 4. Blockquote (supports nested headings/lists inside the quote)
            elif info.kind == "quote":
                self._add_span(desired, "md-quote", 0, line_len)
                self._collect_mark_or_hide(desired, 0, info.marker_end, is_active)
                inner: LineInfo | None = info.extra.get("inner")
                content_start = info.content_start
                if inner and inner.kind == "heading":
                    self._add_span(desired, f"md-h{inner.level}", 0, line_len)
                    self._collect_mark_or_hide(desired, content_start, content_start + inner.marker_end, is_active)
                    content_start += inner.content_start
                self._collect_inline(desired, line, content_start, is_active, pending_embeds)

            # 5. Heading (# .. ######)
            elif info.kind == "heading":
                self._add_span(desired, f"md-h{info.level}", 0, line_len)
                self._collect_mark_or_hide(desired, 0, info.marker_end, is_active)
                self._collect_inline(desired, line, info.content_start, is_active, pending_embeds)

            # 6. Lists & Task lists
            elif info.kind == "list":
                level = min(info.level, 5)
                self._add_span(desired, f"md-list-{level}", 0, line_len)
                self._add_span(desired, "md-syntax", 0, info.marker_end)
                if info.task is not None:
                    t_start, t_end = info.task_range
                    self._collect_task_checkbox(desired, t_start, t_end, info.task == "x", is_active)
                    if info.task == "x":
                        self._add_span(desired, "md-task-done", info.content_start, line_len)
                self._collect_inline(desired, line, info.content_start, is_active, pending_embeds)

            # 7. Paragraph
            elif info.kind == "paragraph":
                self._collect_inline(desired, line, 0, is_active, pending_embeds)

            for tok, media in reversed(pending_embeds):
                img_spec = ("image", tok.start, tok.end, tok.target, media.width, media.height, self.reading_mode)
                bucket = existing_by_key.get((line_no, img_spec))
                if bucket:
                    lbl = bucket.pop(0)
                    lbl.bind("<Button-1>", lambda _e, ln=line_no, c=tok.start: self._focus_line(ln, c))
                    if len(media.frames) > 1 and lbl not in self._gif_jobs:
                        self._schedule_gif_frame(lbl, media)
                    kept_widgets.append(lbl)
                    kept_set.add(lbl)
                    reused_lines.add(line_no)
                else:
                    to_create_images.append((line_no, tok, media, img_spec))

            sig = (
                line,
                info.kind,
                info.block,
                info.level,
                is_active,
                hide_newline,
                tuple((k, tuple(v)) for k, v in sorted(desired.items())),
            )
            line_plans.append((line_no, line_len, desired, hide_newline, sig))

        for cur_line, child in alive_widgets:
            if child not in kept_set:
                self._destroy_embedded_widget(child)
                self._line_cache.pop(cur_line, None)

        for line_no, line_len, desired, hide_newline, sig in line_plans:
            if self._line_cache.get(line_no) != sig:
                if line_no not in reused_lines:
                    self._sync_line_tags(line_no, line_len, desired, hide_newline, full_clean=lines_shifted)
                else:
                    self._line_tags[line_no] = set(desired.keys())
                self._line_cache[line_no] = sig

        for line_no, tok, media, img_spec in to_create_images:
            lbl = self._embed_image_token(line_no, tok, media, img_spec)
            if lbl is not None:
                kept_widgets.append(lbl)

        for t_lines, aligns, rows_data, table_spec in to_create_tables:
            outer = self._create_table_widget(t_lines, aligns, rows_data, table_spec)
            if outer is not None:
                kept_widgets.append(outer)

        self._embedded_widgets = kept_widgets

    def _collect_mark_or_hide(
        self,
        desired: dict[str, list[tuple[int, int]]],
        start: int,
        end: int,
        is_active: bool,
    ) -> None:
        if end <= start:
            return
        tag = "md-syntax" if is_active else "md-hide"
        self._add_span(desired, tag, start, end)

    def _collect_task_checkbox(
        self,
        desired: dict[str, list[tuple[int, int]]],
        start: int,
        end: int,
        checked: bool,
        is_active: bool,
    ) -> None:
        tag = "md-task-checked" if checked else "md-task-unchecked"
        self._add_span(desired, tag, start, end)
        if not is_active:
            self._add_span(desired, "md-hide", start, start + 1)
            self._add_span(desired, "md-hide", end - 1, end)

    def _collect_inline(
        self,
        desired: dict[str, list[tuple[int, int]]],
        line: str,
        start_offset: int,
        is_active: bool,
        pending_embeds: list[tuple[InlineToken, _DecodedMedia]],
    ) -> None:
        tokens = parse_inline(line[start_offset:], base=start_offset)
        self._collect_tokens(desired, line, tokens, is_active, pending_embeds)

    def _collect_tokens(
        self,
        desired: dict[str, list[tuple[int, int]]],
        line: str,
        tokens: list[InlineToken],
        is_active: bool,
        pending_embeds: list[tuple[InlineToken, _DecodedMedia]],
    ) -> None:
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
            if tok.kind == "image" and not is_active and self.resolve_image is not None:
                alt_raw = line[tok.content_start:tok.content_end]
                max_w, max_h = self._parse_image_dimensions(alt_raw, MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT)
                media = self._resolve_and_decode_media(tok.target, max_w, max_h)
                if media is not None:
                    self._add_span(desired, "md-hide", tok.start, tok.end)
                    pending_embeds.append((tok, media))
                    continue

            for m_start, m_end in tok.markers:
                self._collect_mark_or_hide(desired, m_start, m_end, is_active)
            style_tag = tag_map.get(tok.kind)
            if style_tag and tok.content_end > tok.content_start:
                self._add_span(desired, style_tag, tok.content_start, tok.content_end)
            if tok.children:
                self._collect_tokens(desired, line, list(tok.children), is_active, pending_embeds)

    @staticmethod
    def _parse_image_dimensions(alt_text: str, default_w: int, default_h: int) -> tuple[int, int]:
        m = _WIDTH_HINT_RE.match(alt_text.strip())
        if not m:
            return default_w, default_h
        w = max(32, min(int(m.group(2)), 900))
        h = max(32, min(int(m.group(3)), 900)) if m.group(3) else default_h
        return w, h

    def _resolve_and_decode_media(self, target: str, max_w: int, max_h: int) -> _DecodedMedia | None:
        if not target or self.resolve_image is None:
            return None
        raw = self.resolve_image(target)
        if not raw:
            return None
        digest = hashlib.sha256(raw).hexdigest()[:16]
        cache_key = (digest, max_w, max_h)
        cached = self._media_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            with Image.open(io.BytesIO(raw)) as img:
                is_anim = bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)
                fmt = (getattr(img, "format", "") or "").upper()
                if is_anim:
                    orig_w, orig_h = img.size
                    if orig_w <= 0 or orig_h <= 0:
                        return None
                    scale = min(1.0, max_w / orig_w, max_h / orig_h)
                    disp_w = max(1, round(orig_w * scale))
                    disp_h = max(1, round(orig_h * scale))
                    n_frames = int(getattr(img, "n_frames", 1))
                    step = max(1, (n_frames + MAX_GIF_FRAMES - 1) // MAX_GIF_FRAMES)
                    photo_frames: list[ImageTk.PhotoImage] = []
                    raw_frames: list[Image.Image] = []
                    durations: list[int] = []
                    for frame_idx in range(0, n_frames, step):
                        img.seek(frame_idx)
                        rgba = img.convert("RGBA")
                        if (disp_w, disp_h) != (orig_w, orig_h):
                            rgba = rgba.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
                        raw_frames.append(rgba)
                        photo_frames.append(ImageTk.PhotoImage(rgba, master=self.widget))
                        raw_dur = int(img.info.get("duration", 80) or 80)
                        durations.append(max(25, min(raw_dur * step, 5000)))
                    if not photo_frames:
                        return None
                    media = _DecodedMedia(
                        frames=photo_frames,
                        durations=durations,
                        width=disp_w,
                        height=disp_h,
                        is_gif=True,
                        raw_frames=raw_frames,
                    )
                else:
                    transposed = ImageOps.exif_transpose(img)
                    orig_w, orig_h = transposed.size
                    if orig_w <= 0 or orig_h <= 0:
                        return None
                    scale = min(1.0, max_w / orig_w, max_h / orig_h)
                    disp_w = max(1, round(orig_w * scale))
                    disp_h = max(1, round(orig_h * scale))
                    rgba = transposed.convert("RGBA")
                    if (disp_w, disp_h) != (orig_w, orig_h):
                        rgba = rgba.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(rgba, master=self.widget)
                    media = _DecodedMedia(
                        frames=[photo],
                        durations=[0],
                        width=disp_w,
                        height=disp_h,
                        is_gif=(fmt == "GIF"),
                        raw_frames=[rgba],
                    )
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, tk.TclError):
            return None

        if len(self._media_cache) >= MAX_MEDIA_CACHE:
            oldest_key = next(iter(self._media_cache))
            self._media_cache.pop(oldest_key, None)
        self._media_cache[cache_key] = media
        return media

    def _create_media_label(
        self,
        parent: tk.Widget,
        media: _DecodedMedia,
        bg: str,
        source_line: int,
        source_col: int = 0,
    ) -> tk.Label:
        idx = media.current_frame % len(media.frames)
        lbl = tk.Label(
            parent,
            image=media.frames[idx],
            bg=bg,
            bd=0,
            highlightthickness=1,
            highlightbackground=resolve(Colors.border),
            cursor="arrow" if self.reading_mode else "hand2",
        )
        lbl.bind("<Button-1>", lambda _e, ln=source_line, c=source_col: self._focus_line(ln, c))
        if len(media.frames) > 1:
            self._schedule_gif_frame(lbl, media)
        return lbl

    def _schedule_gif_frame(self, label: tk.Label, media: _DecodedMedia) -> None:
        if len(media.frames) <= 1:
            return
        delay = media.durations[media.current_frame % len(media.durations)]

        def _advance() -> None:
            self._gif_jobs.pop(label, None)
            try:
                if not label.winfo_exists():
                    return
                media.current_frame = (media.current_frame + 1) % len(media.frames)
                label.configure(image=media.frames[media.current_frame])
            except tk.TclError:
                return
            next_delay = media.durations[media.current_frame % len(media.durations)]
            self._gif_jobs[label] = self.widget.after(next_delay, _advance)

        self._gif_jobs[label] = self.widget.after(delay, _advance)

    def _embed_image_token(
        self,
        line_no: int,
        tok: InlineToken,
        media: _DecodedMedia,
        spec: tuple,
    ) -> tk.Label | None:
        w = self.widget
        bg = resolve(Colors.bg)
        lbl = self._create_media_label(w, media, bg, line_no, tok.start)
        setattr(lbl, "_md_spec", spec)
        was_undo = bool(w.cget("undo"))
        if was_undo:
            w.configure(undo=False)
        try:
            w.window_create(f"{line_no}.{tok.end}", window=lbl, padx=2, pady=4)
            w.tag_remove("md-hide", lbl)
            return lbl
        except tk.TclError:
            lbl.destroy()
            return None
        finally:
            if was_undo:
                w.configure(undo=True)

    # --------------------------------------------------------- table widgets
    def _plan_table_block(
        self,
        line_numbers: list[int],
        ctx_lines: list[str],
        ctx_start: int = 1,
    ) -> tuple[list[str], list[list[str]], tuple] | None:
        if len(line_numbers) < 2:
            return None
        first_line = line_numbers[0]
        header_line = ctx_lines[first_line - ctx_start]
        sep_line = ctx_lines[first_line - ctx_start + 1]
        body_lines = [ctx_lines[ln - ctx_start] for ln in line_numbers[2:]]

        aligns = table_alignments(sep_line)
        header_ranges = split_table_row(header_line)
        col_count = max(len(aligns), len(header_ranges), 1)
        if (len(body_lines) + 1) * col_count > MAX_EMBEDDED_TABLE_CELLS:
            return None
        while len(aligns) < col_count:
            aligns.append("left")

        def extract_cells(raw_line: str) -> list[str]:
            cells = [raw_line[s:e] for s, e in split_table_row(raw_line)]
            while len(cells) < col_count:
                cells.append("")
            return cells[:col_count]

        rows_data = [extract_cells(header_line)] + [extract_cells(bl) for bl in body_lines]
        spec = (
            "table",
            tuple(aligns),
            tuple(tuple(r) for r in rows_data),
            self.font_family,
            self.reading_mode,
        )
        return aligns, rows_data, spec

    def _create_table_widget(
        self,
        line_numbers: list[int],
        aligns: list[str],
        rows_data: list[list[str]],
        spec: tuple,
    ) -> tk.Frame | None:
        """Create and embed a GFM table grid widget at the end of the table block."""
        w = self.widget
        first_line = line_numbers[0]
        last_line = line_numbers[-1]
        col_count = len(aligns)

        outer = tk.Frame(
            w,
            bg=resolve(Colors.border),
            bd=0,
            highlightthickness=1,
            highlightbackground=resolve(Colors.border),
        )
        setattr(outer, "_md_spec", spec)
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

        was_undo = bool(w.cget("undo"))
        if was_undo:
            w.configure(undo=False)
        try:
            w.window_create(f"{last_line}.end", window=outer, padx=4, pady=6)
            w.tag_remove("md-hide", outer)
            return outer
        except tk.TclError:
            outer.destroy()
            return None
        finally:
            if was_undo:
                w.configure(undo=True)

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
            if tok.kind == "image" and self.resolve_image is not None:
                max_w, max_h = self._parse_image_dimensions(visible, MAX_TABLE_IMAGE_WIDTH, MAX_TABLE_IMAGE_HEIGHT)
                media = self._resolve_and_decode_media(tok.target, max_w, max_h)
                if media is not None:
                    img_lbl = self._create_media_label(row, media, bg, source_line, tok.start)
                    img_lbl.pack(side="left", padx=2, pady=2)
                    pos = tok.end
                    continue

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

