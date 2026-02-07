import customtkinter as ctk
import os
from tkinter import filedialog, messagebox
from tkinter import filedialog
import config as cf
# try:
#     import secure_storage
# except ImportError:
#     print("secure_storage was not imported!")
#     secure_storage = None

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("800x600")
        self.folder_id = 0
        # self.config = self.load_config()
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        self.setup_fn()
        # # load config file
        # if self.config is None:
        #     self.setup_fn()
        # else:
        #     pass
        #     # self.login()

    def load_config(self):
        """Load configuration from file - returns None if not exists"""
        # TODO: Implement config loading from file
        return None

    def clear_frame(self):
        for widget in self.container.winfo_children():
            widget.destroy()
    
    
    def setup_fn(self):
        self.clear_frame()

        # Main setup frame with centered content
        setup_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        setup_frame.pack(fill="both", expand=True, padx=40, pady=40)

        # Center container for form
        center_frame = ctk.CTkFrame(setup_frame, fg_color="transparent")
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Welcome header
        title_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 30))

        ctk.CTkLabel(
            title_frame,
            text="Welcome to Notes",
            font=("Segoe UI", 32, "bold"),
            text_color=("#1f538d", "#4a9eff")
        ).pack()

        ctk.CTkLabel(
            title_frame,
            text="Let's get you set up in just a few steps",
            font=("Segoe UI", 14),
            text_color=("gray40", "gray60")
        ).pack(pady=(5, 0))

        # Decorative line
        separator = ctk.CTkFrame(center_frame, height=2, fg_color=("#d0d0d0", "#404040"))
        separator.pack(fill="x", pady=(0, 30))

        # Form fields container
        form_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        form_frame.pack(pady=10)

        # Database Location Section
        location_section = ctk.CTkFrame(form_frame, fg_color="transparent")
        location_section.pack(fill="x", pady=15)

        ctk.CTkLabel(
            location_section,
            text="Database Location",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(anchor="w", pady=(0, 8))

        location_row = ctk.CTkFrame(location_section, fg_color="transparent")
        location_row.pack(fill="x")

        self.location_entry = ctk.CTkEntry(
            location_row,
            width=400,
            height=40,
            placeholder_text="Select where to store your database...",
            font=("Segoe UI", 12),
            border_color=("#3b8ed0", "#1f6aa5"),
            border_width=2
        )
        self.location_entry.pack(side="left", padx=(0, 10))

        browse_btn = ctk.CTkButton(
            location_row,
            text="Browse",
            width=100,
            height=40,
            font=("Segoe UI", 12, "bold"),
            command=self.browse_location,
            fg_color=("#3b8ed0", "#1f6aa5"),
            hover_color=("#2f72a8", "#164a7a")
        )
        browse_btn.pack(side="left")

        # Password Section
        password_section = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_section.pack(fill="x", pady=15)

        ctk.CTkLabel(
            password_section,
            text="Master Password",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(anchor="w", pady=(0, 8))

        self.password_entry = ctk.CTkEntry(
            password_section,
            width=510,
            height=40,
            placeholder_text="Create a secure password...",
            font=("Segoe UI", 12),
            show="●",
            border_color=("#3b8ed0", "#1f6aa5"),
            border_width=2
        )
        self.password_entry.pack(fill="x")

        ctk.CTkLabel(
            password_section,
            text="This password will protect your notes",
            font=("Segoe UI", 10),
            text_color=("gray40", "gray60")
        ).pack(anchor="w", pady=(5, 0))

        # Confirm Password
        confirm_password_section = ctk.CTkFrame(form_frame, fg_color="transparent")
        confirm_password_section.pack(fill="x", pady=15)

        ctk.CTkLabel(
            confirm_password_section,
            text="Confirm Password",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(anchor="w", pady=(0, 8))

        self.confirm_password_entry = ctk.CTkEntry(
            confirm_password_section,
            width=510,
            height=40,
            placeholder_text="Re-enter your password...",
            font=("Segoe UI", 12),
            show="●",
            border_color=("#3b8ed0", "#1f6aa5"),
            border_width=2
        )
        self.confirm_password_entry.pack(fill="x")

        # Theme Selection Section
        theme_section = ctk.CTkFrame(form_frame, fg_color="transparent")
        theme_section.pack(fill="x", pady=15)

        ctk.CTkLabel(
            theme_section,
            text="Appearance Theme",
            font=("Segoe UI", 14, "bold"),
            anchor="w"
        ).pack(anchor="w", pady=(0, 12))

        theme_buttons_frame = ctk.CTkFrame(theme_section, fg_color="transparent")
        theme_buttons_frame.pack(fill="x")

        self.theme_var = ctk.StringVar(value="dark")

        # Light theme button
        light_frame = ctk.CTkFrame(
            theme_buttons_frame,
            width=240,
            height=80,
            corner_radius=10
        )
        light_frame.pack(side="left", padx=(0, 20))
        light_frame.pack_propagate(False)

        light_radio = ctk.CTkRadioButton(
            light_frame,
            text="",
            variable=self.theme_var,
            value="light",
            width=0
        )
        light_radio.place(x=10, y=10)

        ctk.CTkLabel(
            light_frame,
            text="☀️ Light Mode",
            font=("Segoe UI", 13, "bold")
        ).place(relx=0.5, rely=0.35, anchor="center")

        ctk.CTkLabel(
            light_frame,
            text="Bright & Clean",
            font=("Segoe UI", 10),
            text_color=("gray40", "gray60")
        ).place(relx=0.5, rely=0.65, anchor="center")

        # Dark theme button
        dark_frame = ctk.CTkFrame(
            theme_buttons_frame,
            width=240,
            height=80,
            corner_radius=10
        )
        dark_frame.pack(side="left")
        dark_frame.pack_propagate(False)

        dark_radio = ctk.CTkRadioButton(
            dark_frame,
            text="",
            variable=self.theme_var,
            value="dark",
            width=0
        )
        dark_radio.place(x=10, y=10)

        ctk.CTkLabel(
            dark_frame,
            text="🌙 Dark Mode",
            font=("Segoe UI", 13, "bold")
        ).place(relx=0.5, rely=0.35, anchor="center")

        ctk.CTkLabel(
            dark_frame,
            text="Easy on the Eyes",
            font=("Segoe UI", 10),
            text_color=("gray40", "gray60")
        ).place(relx=0.5, rely=0.65, anchor="center")

        # Action buttons
        buttons_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        buttons_frame.pack(pady=(40, 0))

        complete_btn = ctk.CTkButton(
            buttons_frame,
            text="Complete Setup",
            width=510,
            height=45,
            font=("Segoe UI", 14, "bold"),
            command=self.complete_setup,
            fg_color=("#2ecc71", "#27ae60"),
            hover_color=("#27ae60", "#1e8449"),
            corner_radius=8
        )
        complete_btn.pack()

        # Footer tip
        ctk.CTkLabel(
            center_frame,
            text="💡 Tip: Choose a strong password you won't forget!",
            font=("Segoe UI", 11),
            text_color=("gray50", "gray50")
        ).pack(pady=(20, 0))

    def browse_location(self):
        """Handle browse button click"""
        file_path = filedialog.askdirectory(
            title="Select a location to store your database",
            initialdir=os.getcwd()
        )
        if file_path:
            self.location_entry.delete(0, "end")
            self.location_entry.insert(0, file_path)

    def complete_setup(self):
        """Handle setup completion"""
        location = self.location_entry.get()
        password = self.password_entry.get()
        confirm_password = self.confirm_password_entry.get()
        theme = self.theme_var.get()

        # Validation
        if not location:
            messagebox.showerror("Error", "Please select a database location")
            return

        if not os.path.exists(location):
            messagebox.showerror("Error", "The selected location does not exist")
            return

        if not password:
            messagebox.showerror("Error", "Please enter a password")
            return

        if len(password) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters long")
            return

        if password != confirm_password:
            print("Password"+password+' '+ confirm_password)
            messagebox.showerror("Error", "Passwords do not match")
            return

        existing_config = cf.load_config()
        if existing_config is not None:
            print("Config file already exists")
        else:
            print("Config file doesn't exist, creating one...")
            success = cf.create_config(db_path=location, setup_complete=True, theme=theme, password=password)
            if not success:
                messagebox.showerror("Error", "Failed to create database. Please try again.")
                return

        # Apply the selected theme
        ctk.set_appearance_mode(theme)

        messagebox.showinfo(
            "Setup Complete",
            f"Setup completed successfully!\n\nLocation: {location}\nTheme: {theme.capitalize()}"
        )

        # TODO: Save config and proceed to main app
        
        

if __name__ == "__main__":
    app = App()
    app.mainloop()