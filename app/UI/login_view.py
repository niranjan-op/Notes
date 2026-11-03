import customtkinter as ctk
from tkinter import messagebox
from .styles import Colors, Fonts

# Try/Except block to handle config import
try:
    from app.core import config as cf
except ImportError:
    # Mock config for UI testing purposes
    class cf:
        @staticmethod
        def verify_password(pwd): 
            # Mock validation: Returns True if password is 'password'
            return pwd == "password"

class LoginView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg)
        self.controller = controller
        
        # State
        self.password_visible = False
        self.vault_name = None
        
        # Build UI
        self.setup_ui()
    
    def update_view(self, context=None):
        if context and "vault_name" in context:
            self.vault_name = context["vault_name"]
            self.header_label.configure(text=f"Unlock {self.vault_name}")
        else:
            self.vault_name = None
            self.header_label.configure(text="Welcome Back")
            
        self.password_entry.delete(0, 'end')
        self.password_entry.focus()

    def setup_ui(self):
        # --- Centered Card ---
        self.card = ctk.CTkFrame(
            self, 
            fg_color=Colors.card,
            corner_radius=15,
            border_width=1,
            border_color=Colors.border,
            width=400,
            height=450
        )
        self.card.pack_propagate(False)
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # --- Content Container ---
        content = ctk.CTkFrame(self.card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=40, pady=40)

        # --- Back Button ---
        self.back_btn = ctk.CTkButton(
            content, 
            text="← Back", 
            width=50, 
            height=20,
            fg_color="transparent", 
            text_color=Colors.text_sub,
            hover_color=Colors.bg,
            font=("Segoe UI", 11),
            anchor="w",
            command=lambda: self.controller.show_frame("WelcomeView")
        )
        self.back_btn.pack(anchor="w", pady=(0, 5))

        # --- Headers ---
        self.header_label = ctk.CTkLabel(
            content, 
            text="Welcome Back", 
            font=Fonts.header, 
            text_color=Colors.text
        )
        self.header_label.pack(pady=(10, 5))

        ctk.CTkLabel(
            content, 
            text="Enter your master password to unlock", 
            font=Fonts.sub_header, 
            text_color=Colors.text_sub,
            wraplength=300
        ).pack(pady=(0, 25))

        # --- Warning Label ---
        self.warning_label = ctk.CTkLabel(
            content,
            text="",
            font=("Segoe UI", 11),
            text_color=Colors.error,
            height=15
        )
        self.warning_label.pack(pady=(0, 5))

        # --- Form: Password ---
        self.create_label(content, "Master Password")
        pwd_frame = self.create_input_frame(content)

        self.password_entry = ctk.CTkEntry(
            pwd_frame,
            border_width=0,
            fg_color="transparent",
            font=Fonts.body,
            placeholder_text="Enter password",
            show="●",
            height=40,
            text_color=Colors.text
        )
        self.password_entry.pack(side="left", fill="x", expand=True, padx=10)
        
        # Bind Enter key to login
        self.password_entry.bind("<Return>", lambda event: self.perform_login())

        self.pwd_toggle_btn = self.create_icon_button(pwd_frame, self.toggle_password)
        self.pwd_toggle_btn.pack(side="right", padx=5)

        # Bind security events (Prevent Copy/Paste)
        self.password_entry.bind("<Control-v>", lambda e, w=self.password_entry: self.prevent_paste(e, w))
        self.password_entry.bind("<Control-c>", self.prevent_copy)
        self.password_entry.bind("<Control-x>", self.prevent_copy)

        # --- Spacer ---
        ctk.CTkLabel(content, text="", height=20).pack()

        # --- Action Button ---
        self.login_btn = ctk.CTkButton(
            content, 
            text="Unlock Vault", 
            height=45, 
            font=("Segoe UI", 13, "bold"),
            fg_color=Colors.primary, 
            hover_color=Colors.primary_hover,
            corner_radius=8,
            command=self.perform_login
        )
        self.login_btn.pack(fill="x", pady=(10, 0))

        # --- Forgot Password Link (Visual Only) ---
        self.forgot_btn = ctk.CTkButton(
            content,
            text="Reset Vault?",
            font=("Segoe UI", 11),
            fg_color="transparent",
            text_color=Colors.text_sub,
            hover_color=Colors.bg,
            height=20,
            width=100,
            command=self.forgot_password_action
        )
        self.forgot_btn.pack(pady=(15, 0))

    # --- UI Helpers (Reused for consistency) ---
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
        # Clear warning after 3 seconds
        self.after(3000, lambda: self.warning_label.configure(text=""))
    
    def toggle_password(self):
        self.password_visible = not self.password_visible
        self.password_entry.configure(show="" if self.password_visible else "●")
        self.pwd_toggle_btn.configure(text="🔓" if self.password_visible else "🔒")

    def forgot_password_action(self):
        # Optional: Add logic to reset database or show hint
        messagebox.showinfo("Reset", "To reset the vault, manually delete the database file.")

    def perform_login(self):
        password = self.password_entry.get()

        if not password:
            self.show_warning("⚠ Please enter your password")
            return
            
        if not self.vault_name:
            self.show_warning("⚠ No vault selected")
            return

        # Attempt to verify with backend
        if cf.load_config(password, self.vault_name):
            print("Login successful. Transitioning...")
            self.controller.show_frame("MainView", context={"vault_name": self.vault_name, "password": password})
        else:
            self.show_warning("⚠ Wrong Password")
            self.password_entry.delete(0, 'end')
            self.password_entry.focus()
