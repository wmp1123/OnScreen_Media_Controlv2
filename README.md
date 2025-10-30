# OnScreen Media Control

A lightweight, floating media controller for Windows that allows you to:

- Control media playback (Play, Pause, Next, Previous)
- Adjust system volume with a slider
- Adjust window transparency with a slider
- Always-on-top toggle for quick access
- Draggable UI for convenient placement on your screen

## Features

- **Volume Slider**: Click or drag anywhere on the slider for precise control.  
- **Transparency Slider**: Adjust window transparency from 30% to 100%.  
- **Media Buttons**: Easily control media playback for the currently active application.  
- **Always-on-top**: Keep the controller visible over other windows.  

## Installation

### Prerequisites

- Python 3.10+  
- Windows OS  
- Install dependencies:

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/OnScreen-Media-Control.git
   ```

2. Navigate into the project directory:
    ```bash
    cd OnScreen-Media-Control
    ```

3. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Dependencies include:
- **pycaw** for audio control
- **comtypes**
- **asyncio**
- **tkinter** (usually comes with Python)

## Running the App
```bash
python -m onscreen_media_control.main
```

Or build an executable using PyInstaller (Require PyInstaller):
```bash
pyinstaller --name "OnScreen Media Control" --onefile -w onscreen_media_control/main.py
```

## Usage
- Launch the app.
- Drag the window from the top bar to reposition.
- Use sliders to adjust volume and transparency.
- Click buttons to control media playback.
- Toggle "Always on top" to keep it accessible while working with other apps