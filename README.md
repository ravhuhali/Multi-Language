# Multi-Language Speech Translator

A Flask web application that captures speech, transcribes it with a local AI model, translates with Google Translate, and plays back spoken results.

## Features

- **Voice Input**: Record speech via microphone
- **Local AI Transcription**: Uses `faster-whisper` to convert speech to text
- **Automatic Language Detection**: Detects spoken language from audio
- **Text Input**: Type text manually
- **Translation**: Uses Google Translate to translate to your selected language
- **Audio Playback**: Hear translations spoken aloud

## Requirements

- Python 3.8+
- FFmpeg (for audio processing)

## Installation

1. **Clone the repository**
   ```bash
   cd project
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\Scripts\activate     # On Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg** (required for audio processing)
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt install ffmpeg

   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

## Running the App

```bash
python proj.py
```

Then open http://localhost:5000 in your browser.

## Usage

1. Select your target language (Zulu, Xhosa, Sotho, or Afrikaans)
2. Either:
   - Click the microphone button and speak in English
   - Type English text in the input field
3. View the translation and click "Play Translation" to hear it

## Project Structure

```
project/
├── proj.py              # Flask backend
├── templates/
│   └── index.html       # Web interface
├── static/
│   ├── script.js        # Frontend JavaScript
│   └── style.css        # Styles
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

## Technologies

- **Flask** - Web framework
- **faster-whisper** - Local AI speech-to-text
- **googletrans** - Translation API
- **edge-tts** - Text-to-speech
- **pydub** - Audio format conversion
