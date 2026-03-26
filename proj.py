"""
English Speech to Zulu Translator - Flask Web App
Speech-to-Speech: Listen in English, Respond in Zulu
"""

from flask import Flask, render_template, request, jsonify, send_file
import speech_recognition as sr
from googletrans import Translator
import edge_tts
import asyncio
import os
import tempfile
import io
import uuid
from pydub import AudioSegment

app = Flask(__name__)

# HTML, CSS, and JavaScript files are in templates/ and static/ directories

# Store generated audio files temporarily
audio_cache = {}


def generate_audio(text, language):
    """Convert text to speech in the specified language and return audio bytes"""
    # Map language codes to edge_tts voice names
    voice_map = {
        'zu': 'zu-ZA-ThandoNeural',   # Zulu
        'en': 'en-US-AriaNeural',      # English
        'st': 'zu-ZA-ThandoNeural',    # Sotho (use Afrikaans - most reliable)
        'xh': 'zu-ZA-ThandoNeural',    # Xhosa
        'af': 'af-ZA-WillemNeural'     # Afrikaans
    }
    
    voice = voice_map.get(language, 'zu-ZA-ThandoNeural')
    
    async def _generate():
        try:
            communicate = edge_tts.Communicate(text, voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_file = fp.name
            await communicate.save(temp_file)
            
            with open(temp_file, 'rb') as f:
                audio_data = f.read()
            
            os.remove(temp_file)
            return audio_data
        except Exception as e:
            # Fallback to English if voice fails
            try:
                communicate = edge_tts.Communicate(text, 'en-US-AriaNeural')
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                    temp_file = fp.name
                await communicate.save(temp_file)
                
                with open(temp_file, 'rb') as f:
                    audio_data = f.read()
                
                os.remove(temp_file)
                return audio_data
            except Exception:
                raise Exception(f"Could not generate audio for language {language}")
    
    return asyncio.run(_generate())


def transcribe_audio(audio_file):
    """Transcribe audio file to English text"""
    recognizer = sr.Recognizer()
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as fp:
        temp_webm = fp.name
        audio_file.save(temp_webm)
    
    # Convert webm to wav using pydub
    temp_wav = temp_webm.replace('.webm', '.wav')
    try:
        audio_segment = AudioSegment.from_file(temp_webm)
        audio_segment.export(temp_wav, format='wav')
        
        with sr.AudioFile(temp_wav) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="en-US")
            return text
    finally:
        if os.path.exists(temp_webm):
            os.remove(temp_webm)
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def translate_language(english_text, target_language):
    """Translate English text to the target language"""
    translator = Translator()
    translation = translator.translate(english_text, src='en', dest=target_language)
    return translation.text


@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/translate_audio', methods=['POST'])
def translate_audio():
    """Handle audio upload, transcribe, translate, and generate speech"""
    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'})
        
        audio_file = request.files['audio']
        language = request.form.get('language', 'zu')
        
        # Transcribe audio to English text
        english_text = transcribe_audio(audio_file)
        
        # Translate to target language
        translated_text = translate_language(english_text, language)
        
        # Generate audio
        audio_data = generate_audio(translated_text, language)
        audio_id = str(uuid.uuid4())
        audio_cache[audio_id] = audio_data
        
        return jsonify({
            'success': True,
            'english': english_text,
            'translation': translated_text,
            'audio_id': audio_id
        })
        
    except sr.UnknownValueError:
        return jsonify({'success': False, 'error': 'Could not understand audio'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/translate_text', methods=['POST'])
def translate_text_route():
    """Handle text translation"""
    try:
        data = request.get_json()
        english_text = data.get('text', '').strip()
        language = data.get('language', 'zu')
        
        if not english_text:
            return jsonify({'success': False, 'error': 'No text provided'})
        
        # Translate to target language
        translated_text = translate_language(english_text, language)
        
        # Generate audio
        audio_data = generate_audio(translated_text, language)
        audio_id = str(uuid.uuid4())
        audio_cache[audio_id] = audio_data
        
        return jsonify({
            'success': True,
            'english': english_text,
            'translation': translated_text,
            'audio_id': audio_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/speak/<audio_id>')
def speak(audio_id):
    """Serve generated audio file"""
    if audio_id in audio_cache:
        audio_data = audio_cache[audio_id]
        return send_file(
            io.BytesIO(audio_data),
            mimetype='audio/mpeg',
            as_attachment=False
        )
    return jsonify({'error': 'Audio not found'}), 404


if __name__ == "__main__":
    print("=" * 50)
    print("  English to Zulu Speech Translator")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 50)
    app.run(debug=True, port=5000)