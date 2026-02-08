import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
from .styles import Colors, Fonts

# Try/Except block to handle config import
try:
    # FIXED: Use full package path 'app.core' so main.py can resolve it
    from app.core import config as cf
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import backend. {e}")
    # Mock config for UI testing purposes
    class cf:
        @staticmethod
        def load_config(): return None
        @staticmethod
        def create_config(**kwargs): 
            print("WARNING: Using MOCK backend. No DB file will be created.") 
            return True

class SetupView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg)
        self.controller = controller
        
        # State
        self.password_visible = False
        self.confirm_password_visible = False
        
        # Build UI
        self.setup_ui()

    def setup_ui(self):
        # --- Centered Card ---
        self.card = ctk.CTkFrame(
            self, 
            fg_color=Colors.card,
            corner_radius=15,
            border_width=1,
            border_color=Colors.border,
            width=420,
            height=560 # Slightly taller to fit everything comfortably
        )
        self.card.pack_propagate(False)
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # --- Content Container ---
        content = ctk.CTkFrame(self.card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=40, pady=35)

        # --- Headers ---
        ctk.CTkLabel(
            content, 
            text="Setup Vault", 
            font=Fonts.header, 
            text_color=Colors.text
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            content, 
            text="Configure your secure storage", 
            font=Fonts.sub_header, 
            text_color=Colors.text_sub
        ).pack(pady=(0, 15))

        # --- Warning Label ---
        self.warning_label = ctk.CTkLabel(
            content,
            text="",
            font=("Segoe UI", 11),
            text_color=Colors.error,
            height=15
        )
        self.warning_label.pack(pady=(0, 5))

        # --- Form: Location ---
        self.create_label(content, "Database Location")
        loc_frame = self.create_input_frame(content)
        
        self.location_entry = ctk.CTkEntry(
            loc_frame, 
            border_width=0, 
            fg_color="transparent", 
            font=Fonts.body,
            height=40,
            placeholder_text="Select folder...",
            text_color=Colors.text
        )
        self.location_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.location_entry.configure(state="readonly")

        ctk.CTkButton(
            loc_frame, 
            text="Browse", 
            width=60, 
            height=32, 
            font=Fonts.body_bold,
            fg_color=Colors.bg, 
            text_color=Colors.text, 
            hover_color=Colors.border, 
            command=self.browse_location
        ).pack(side="right", padx=5)

        # --- Form: Password ---
        self.create_label(content, "Master Password")
        pwd_frame = self.create_input_frame(content)

        self.password_entry = ctk.CTkEntry(
            pwd_frame,
            border_width=0,
            fg_color="transparent",
            font=Fonts.body,
            placeholder_text="Min 6 characters",
            show="●",
            height=40,
            text_color=Colors.text
        )
        self.password_entry.pack(side="left", fill="x", expand=True, padx=10)
        
        self.pwd_toggle_btn = self.create_icon_button(pwd_frame, self.toggle_password)
        self.pwd_toggle_btn.pack(side="right", padx=5)

        # --- Form: Confirm Password ---
        self.create_label(content, "Confirm Password")
        conf_frame = self.create_input_frame(content)

        self.confirm_password_entry = ctk.CTkEntry(
            conf_frame,
            border_width=0,
            fg_color="transparent",
            font=Fonts.body,
            placeholder_text="Repeat password",
            show="●",
            height=40,
            text_color=Colors.text
        )
        self.confirm_password_entry.pack(side="left", fill="x", expand=True, padx=10)

        self.confirm_pwd_toggle_btn = self.create_icon_button(conf_frame, self.toggle_confirm_password)
        self.confirm_pwd_toggle_btn.pack(side="right", padx=5)

        # Bind security events
        for entry in [self.password_entry, self.confirm_password_entry]:
            entry.bind("<Control-v>", lambda e, w=entry: self.prevent_paste(e, w))
            entry.bind("<Control-c>", self.prevent_copy)
            entry.bind("<Control-x>", self.prevent_copy)

        # --- Theme Switch ---
        theme_frame = ctk.CTkFrame(content, fg_color="transparent")
        theme_frame.pack(fill="x", pady=(20, 20))
        
        ctk.CTkLabel(theme_frame, text="Dark Mode", font=Fonts.body_bold, text_color=Colors.text).pack(side="left")
        
        self.theme_switch = ctk.CTkSwitch(
            theme_frame,
            text="",
            width=40, 
            height=20,
            command=self.toggle_theme,
            onvalue="dark",
            offvalue="light",
            progress_color=Colors.primary,
            button_color=Colors.text
        )
        self.theme_switch.pack(side="right")
        self.theme_switch.select() # Default to dark

        # --- Action Button ---
        self.start_btn = ctk.CTkButton(
            content, 
            text="Initialize Vault", 
            height=45, 
            font=("Segoe UI", 13, "bold"),
            fg_color=Colors.primary, 
            hover_color=Colors.primary_hover,
            corner_radius=8,
            command=self.complete_setup
        )
        self.start_btn.pack(fill="x", pady=(5, 0))

    # --- UI Helpers ---
    def create_label(self, parent, text):
        ctk.CTkLabel(
            parent, 
            text=text, 
            font=Fonts.body_bold, 
            text_color=Colors.text, 
            anchor="w"
        ).pack(fill="x", pady=(10, 2))

    def create_input_frame(self, parent):
        frame = ctk.CTkFrame(
            parent, 
            fg_color=Colors.input_bg, 
            border_width=1, 
            border_color=Colors.border, 
            corner_radius=8, 
            height=42
        )
        frame.pack(fill="x")
        frame.pack_propagate(False)
        return frame

    def create_icon_button(self, parent, command):
        return ctk.CTkButton(
            parent,
            text="🔒",
            width=30,
            height=30,
            fg_color="transparent",
            text_color=Colors.text_sub,
            hover_color=Colors.bg,
            font=Fonts.icon,
            command=command
        )

    # --- Logic ---
    def prevent_paste(self, event, entry_widget):
        self.show_warning("For security, please type manually.")
        return "break"
    
    def prevent_copy(self, event):
        return "break"
    
    def show_warning(self, message):
        self.warning_label.configure(text=message)
        self.after(3000, lambda: self.warning_label.configure(text=""))
    
    def toggle_password(self):
        self.password_visible = not self.password_visible
        self.password_entry.configure(show="" if self.password_visible else "●")
        self.pwd_toggle_btn.configure(text="🔓" if self.password_visible else "🔒")
    
    def toggle_confirm_password(self):
        self.confirm_password_visible = not self.confirm_password_visible
        self.confirm_password_entry.configure(show="" if self.confirm_password_visible else "●")
        self.confirm_pwd_toggle_btn.configure(text="🔓" if self.confirm_password_visible else "🔒")

    def toggle_theme(self):
        ctk.set_appearance_mode(self.theme_switch.get())

    def browse_location(self):
        file_path = filedialog.askdirectory(initialdir=os.getcwd())
        if file_path:
            self.location_entry.configure(state="normal")
            self.location_entry.delete(0, "end")
            self.location_entry.insert(0, file_path)
            self.location_entry.configure(state="readonly")

    def complete_setup(self):
        # STRIP WHITESPACE to prevent path errors
        location = self.location_entry.get().strip()
        password = self.password_entry.get()
        confirm = self.confirm_password_entry.get()
        theme = self.theme_switch.get()

        if not location:
            self.show_warning("⚠ Please select a storage location")
            return
        if not password or len(password) < 6:
            self.show_warning("⚠ Password must be at least 6 characters")
            return
        if password != confirm:
            self.show_warning("⚠ Passwords do not match")
            return

        print(f"Creating DB at: {location}")
        
        # Call your config backend
        success = cf.create_config(
            db_path=location, 
            theme=theme, 
            password=password
        )

        if success:
            messagebox.showinfo("Success", "Vault initialized!")
            # Logic to switch screens
            # self.controller.show_frame("LoginView") 
            print("Transitioning to next screen...")
        else:
            self.show_warning("⚠ Failed to create database")