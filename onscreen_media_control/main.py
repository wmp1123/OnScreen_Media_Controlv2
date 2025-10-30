from onscreen_media_control.ui import MediaController
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
import sys
import ctypes
import os


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OnScreenMediaControl.App")

        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

        window = MediaController()
        window.setWindowTitle("OnScreen Media Control")
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        print(f"[FATAL] {e}")
