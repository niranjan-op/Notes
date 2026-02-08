import customtkinter as ctk
from app.UI.setup_view import SetupView
import app.core.config as cf

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Notes App")
        self.geometry("800x600")
        self.resizable(False, False)
        
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        
        self.frames = {}
        if cf.load_config():
            #login_view
            pass
        else:
        # Initialize SetupView
            frame = SetupView(parent=self.container, controller=self)
            self.frames["SetupView"] = frame
            frame.grid(row=0, column=0, sticky="nsew")
            
            self.container.grid_rowconfigure(0, weight=1)
            self.container.grid_columnconfigure(0, weight=1)
    
            self.show_frame("SetupView")
    
    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = MainApp()
    app.mainloop()