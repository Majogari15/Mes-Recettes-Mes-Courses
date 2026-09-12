# Lanceur Windows sans console. Le code applicatif reste dans main.py.
from main import App, enable_windows_dpi_awareness

if __name__ == "__main__":
    enable_windows_dpi_awareness()
    app = App()
    app.mainloop()
