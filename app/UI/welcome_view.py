import customtkinter as ctk
from .styles import Colors, Fonts
import app.core.config as cf
class WelcomeView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg)
        self.controller = controller
        self.setup_ui()

    def setup_ui(self):
        # --- Centered Card ---
        self.card = ctk.CTkFrame(
            self, 
            fg_color=Colors.card,
            corner_radius=15,
            border_width=1,
            border_color=Colors.border,
            width=400,
            height=400 # slightly smaller than setup/login since fewer fields
        )
        self.card.pack_propagate(False)
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # --- Content Container ---
        content = ctk.CTkFrame(self.card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=40, pady=40)

        # --- App Icon/Logo Placeholder (Optional) ---
        # ctk.CTkLabel(content, text="🔒", font=("Segoe UI", 48)).pack(pady=(10, 20))

        # --- Headers ---
        ctk.CTkLabel(
            content, 
            text="Secure Vault", 
            font=Fonts.header, 
            text_color=Colors.text
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            content, 
            text="Your personal secure notes manager.\nEncrypted and local.", 
            font=Fonts.body, 
            text_color=Colors.text_sub,
            justify="center"
        ).pack(pady=(0, 40))

        # --- Buttons ---
        
        # 1. Create New Vault
        self.create_btn = ctk.CTkButton(
            content, 
            text="Create New Vault", 
            height=45, 
            font=("Segoe UI", 13, "bold"),
            fg_color=Colors.primary, 
            hover_color=Colors.primary_hover,
            corner_radius=8,
            command=lambda: self.controller.show_frame("SetupView")
        )
        self.create_btn.pack(fill="x", pady=(0, 20))

        # --- Vault List Container ---
        self.vault_container = ctk.CTkFrame(content, fg_color="transparent")
        self.vault_container.pack(fill="x", pady=(0, 10))
        
        # Initial load
        self.refresh_vault_list()

        # --- Version/Footer (Moved here so it can access 'content') ---
        ctk.CTkLabel(
            content,
            text="v1.0.0",
            font=("Segoe UI", 10),
            text_color=Colors.text_sub
        ).pack(side="bottom", pady=(20, 0))

    def update_view(self, context=None):
        """Called by controller when switching to this view"""
        self.refresh_vault_list()
    
    def open_selected_vault(self):
        if hasattr(self, 'vault_select'):
            vault_name = self.vault_select.get()
            if vault_name:
                self.controller.show_frame("LoginView", context={"vault_name": vault_name})

    def refresh_vault_list(self):
        # Clear existing widgets in the container
        for widget in self.vault_container.winfo_children():
            widget.destroy()

        if cf.search_config():
            vaults, _ = cf.read_config()
            vault_values = list(vaults) if vaults else []
            if vault_values:
                ctk.CTkLabel(
                    self.vault_container,
                    text="Open Existing Vault",
                    font=Fonts.body_bold,
                    text_color=Colors.text,
                    anchor="w"
                ).pack(fill="x", pady=(0, 5))

                self.vault_select = ctk.CTkComboBox(
                    self.vault_container,
                    values=vault_values,
                    height=40,
                    font=Fonts.body,
                    dropdown_font=Fonts.body,
                    fg_color=Colors.input_bg,
                    border_color=Colors.border,
                    text_color=Colors.text,
                    button_color=Colors.primary,
                    button_hover_color=Colors.primary_hover
                )
                self.vault_select.set(vault_values[-1]) # Default to most recent
                self.vault_select.pack(fill="x", pady=(0, 10))

                self.open_btn = ctk.CTkButton(
                    self.vault_container, 
                    text="Open Selected", 
                    height=40, 
                    font=("Segoe UI", 13, "bold"),
                    fg_color="transparent", 
                    border_width=2,
                    border_color=Colors.primary,
                    text_color=Colors.primary, 
                    hover_color=Colors.input_bg, 
                    corner_radius=8,
                    command=self.open_selected_vault
                )
                self.open_btn.pack(fill="x")