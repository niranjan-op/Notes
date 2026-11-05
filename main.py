import ctypes
import sys

import customtkinter as ctk

import app.core.config as cf
from app.UI.brand import APP_NAME, APP_USER_MODEL_ID
from app.UI.components import set_window_icon
from app.UI.login_view import LoginView
from app.UI.main_view import MainView
from app.UI.setup_view import SetupView
from app.UI.styles import Colors, apply_color_theme
from app.UI.welcome_view import WelcomeView


def _register_windows_app_id() -> None:
    """Give the process its own taskbar identity so Windows shows our icon, not Python's."""
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            pass


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=Colors.bg)
        self.title(APP_NAME)
        # Calling iconbitmap also stops CustomTkinter replacing the icon with its own.
        set_window_icon(self)
        self._fit_to_screen()

        self.container = ctk.CTkFrame(self, fg_color=Colors.bg, corner_radius=0)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for view in (WelcomeView, SetupView, LoginView, MainView):
            frame = view(parent=self.container, controller=self)
            self.frames[view.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_frame("WelcomeView")

    def _fit_to_screen(self) -> None:
        """Open at a comfortable size for the current monitor and DPI scaling."""
        scaling = ctk.ScalingTracker.get_window_scaling(self)
        screen_w = self.winfo_screenwidth() / scaling
        screen_h = self.winfo_screenheight() / scaling
        width = int(min(1320, max(960, screen_w * 0.78)))
        height = int(min(840, max(600, screen_h * 0.8)))
        width, height = int(min(width, screen_w - 40)), int(min(height, screen_h - 80))
        x = int((screen_w - width) / 2 * scaling)
        y = int((screen_h - height) / 3 * scaling)
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.minsize(min(940, width), min(580, height))

    def show_frame(self, page_name, context=None):
        self._current_page = page_name
        frame = self.frames[page_name]
        if hasattr(frame, "update_view"):
            frame.update_view(context)
        if getattr(self, "_current_page", page_name) == page_name:
            frame.tkraise()

    def on_close(self) -> None:
        """Flush pending edits and close the vault before exiting."""
        self.frames["MainView"].lock(navigate=False)
        self.destroy()


def _initial_theme() -> str:
    theme = cf.get_preference("theme", "dark").lower()
    return theme if theme in {"dark", "light", "system"} else "dark"


if __name__ == "__main__":
    _register_windows_app_id()
    apply_color_theme(cf.get_preference("color_theme", "default"))
    ctk.set_appearance_mode(_initial_theme())
    app = MainApp()
    app.mainloop()
