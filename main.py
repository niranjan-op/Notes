import customtkinter as ctk
from app.UI.setup_view import SetupView
from app.UI.login_view import LoginView
from app.UI.welcome_view import WelcomeView
import app.core.config as cf

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Notes App")
        self.geometry("800x600")
        self.resizable(False, False)
        
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        
        # 1. Configure Grid Layout (Move this out so it applies to ALL views)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        self.frames = {}
        
        # 2. Initialize ALL views (Loop approach)
        # We load both now so you can seamlessly switch between them later
        # Note: We use login_view.LoginView because of your import style
        for F in (WelcomeView, SetupView, LoginView):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            
            # Stack them on top of each other
            frame.grid(row=0, column=0, sticky="nsew")

        # 3. Check Config and Select Startup Screen
        # Always show WelcomeView first as per new design
        self.show_frame("WelcomeView")
    
    def show_frame(self, page_name, context=None):
        frame = self.frames[page_name]
        
        # Refresh the view if it supports it
        if hasattr(frame, "update_view"):
            try:
                frame.update_view(context)
            except TypeError:
                # Handle cases where update_view doesn't accept arguments (like in old views)
                frame.update_view()
            
        frame.tkraise()

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = MainApp()
    app.mainloop()