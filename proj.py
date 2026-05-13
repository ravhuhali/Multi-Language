"""
English Speech to Zulu Translator - Flask Web App
Speech-to-Speech: Listen in English, Respond in Zulu
"""

from flask import Flask, render_template, request, jsonify, send_file
from deep_translator import GoogleTranslator
from dotenv import load_dotenv
import edge_tts
import asyncio
import os
import tempfile
import io
import uuid
from datetime import datetime
import requests as http_requests
import subprocess
import shutil
import speech_recognition as sr
from openai import OpenAI

load_dotenv()  # loads OPENAI_API_KEY from .env


def _get_ffmpeg():
    """Return path to ffmpeg: system PATH first, then imageio_ffmpeg fallback."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            'ffmpeg not found. Install it (https://ffmpeg.org) or run: pip install imageio-ffmpeg'
        )

app = Flask(__name__)


# Store generated audio files temporarily
audio_cache = {}

# Store user input audio files temporarily
user_audio_cache = {}

RECORDS_FILE = os.path.join(os.path.dirname(__file__), 'records')

# BCP-47 language codes for Google Cloud STT (SA native languages only)
_SR_LANG = {
    'zu':  'zu-ZA',   # Zulu
    'xh':  'xh-ZA',   # Xhosa
    'st':  'st-ZA',   # Sotho
    'nso': 'nso-ZA',  # Sepedi
    'tn':  'tn-ZA',   # Tswana
    'ts':  'ts-ZA',   # Tsonga
    'en':  'en-ZA',   # English
}


# ElevenLabs: one natural voice – multilingual_v2 model speaks any language
# correctly when the translated text is in that language.
ELEVENLABS_VOICE_ID = 'EXAVITQu4vr4xnSDxMaL'  # Bella

# edge-tts: SA native languages only.
# Only Zulu has a native edge-tts voice; all others use Zulu as the closest
# phonetically similar SA voice available.
EDGE_TTS_VOICES = {
    'zu':  'zu-ZA-ThandoNeural',  # Zulu   – native voice
    'xh':  'zu-ZA-ThandoNeural',  # Xhosa  – no native voice, use Zulu
    'st':  'zu-ZA-ThandoNeural',  # Sotho  – no native voice, use Zulu
    'nso': 'zu-ZA-ThandoNeural',  # Sepedi – no native voice, use Zulu
    'tn':  'zu-ZA-ThandoNeural',  # Tswana – no native voice, use Zulu
    'ts':  'zu-ZA-ThandoNeural',  # Tsonga – no native voice, use Zulu
    'en':  'en-US-AriaNeural',      # English
}

# ── multilanguage OpenAI agent ────────────────────────────────────────────────
_LANG_NAMES = {
    'zu':  'isiZulu',
    'xh':  'isiXhosa',
    'st':  'Sesotho',
    'nso': 'Sepedi',
    'tn':  'Setswana',
    'ts':  'Xitsonga',
    'en':  'English',
}

_MULTILANGUAGE_SYSTEM = (
    "You are the 'multilanguage' South African language refinement agent. "
    "Your only job is to take a raw or roughly translated sentence and rewrite it "
    "as a single, fluent, natural-sounding sentence in the specified language. "
    "Rules:\n"
    "- Keep the meaning intact.\n"
    "- Fix grammar, word order, and phrasing so it sounds like a native speaker.\n"
    "- Do NOT translate to a different language — stay in the target language.\n"
    "- Return ONLY the refined sentence. No explanations, no labels."
)


def multilanguage_agent(text: str, language_code: str) -> str:
    """Refine *text* into a fluent sentence in *language_code* using OpenAI.

    Falls back to the original text if the API call fails or the key is missing.
    """
    api_key = os.getenv('OPENAI_API_KEY', '')
    if not api_key or api_key == 'your-openai-api-key-here':
        return text  # no key configured – return as-is

    lang_name = _LANG_NAMES.get(language_code, language_code)
    user_prompt = (
        f"Language: {lang_name}\n"
        f"Raw sentence: {text}\n\n"
        "Refined sentence:"
    )
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _MULTILANGUAGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=256,
            temperature=0.3,
        )
        refined = response.choices[0].message.content.strip()
        return refined if refined else text
    except Exception:
        return text
# ─────────────────────────────────────────────────────────────────────────────


def _generate_audio_elevenlabs(text, language):
    """Generate audio via ElevenLabs multilingual_v2.
    The model speaks in the correct language based on the text content."""
    api_key = os.getenv('ELEVENLABS_API_KEY', '')
    if not api_key:
        return None
    try:
        resp = http_requests.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}',
            headers={
                'xi-api-key': api_key,
                'Content-Type': 'application/json',
                'Accept': 'audio/mpeg',
            },
            json={
                'text': text,
                'model_id': 'eleven_multilingual_v2',
                'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8},
            },
            timeout=30,
        )
        if resp.ok and resp.content:
            return resp.content
    except Exception:
        pass
    return None


async def _generate_audio_edge_tts(text, language):
    """Generate audio via edge-tts (Microsoft Azure Neural TTS)."""
    voice = EDGE_TTS_VOICES.get(language, 'en-US-AriaNeural')
    try:
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            temp_file = fp.name
        await communicate.save(temp_file)
        with open(temp_file, 'rb') as f:
            audio_data = f.read()
        os.remove(temp_file)
        return audio_data
    except Exception:
        communicate = edge_tts.Communicate(text, 'en-US-AriaNeural')
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            temp_file = fp.name
        await communicate.save(temp_file)
        with open(temp_file, 'rb') as f:
            audio_data = f.read()
        os.remove(temp_file)
        return audio_data


def generate_audio(text, language):
    """Try ElevenLabs first (highest quality), fall back to edge-tts."""
    el_audio = _generate_audio_elevenlabs(text, language)
    if el_audio:
        return el_audio
    return asyncio.run(_generate_audio_edge_tts(text, language))


def _webm_to_wav(audio_bytes):
    """Convert webm bytes to a wav temp file. Returns the wav path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as fp:
        temp_webm = fp.name
        fp.write(audio_bytes)
    temp_wav = temp_webm.replace('.webm', '.wav')
    ffmpeg_exe = _get_ffmpeg()
    subprocess.run(
        [ffmpeg_exe, '-y', '-i', temp_webm, temp_wav],
        check=True, capture_output=True
    )
    os.remove(temp_webm)
    return temp_wav


def transcribe_audio(audio_bytes, source_language='en'):
    """Transcribe uploaded audio bytes using Google Cloud STT."""
    recognizer = sr.Recognizer()
    temp_wav = _webm_to_wav(audio_bytes)
    try:
        with sr.AudioFile(temp_wav) as source:
            audio = recognizer.record(source)
        lang = _SR_LANG.get(source_language, 'en-US')
        text = recognizer.recognize_google(audio, language=lang)
        if not text:
            raise ValueError('Could not understand audio')
        return text
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def transcribe_audio_auto(audio_bytes):
    """Transcribe audio with Google Cloud STT. Tries multiple language hints
    so native SA languages (Zulu, Xhosa, Sotho, etc.) are picked up.
    Google Translate source='auto' then detects and translates correctly."""
    recognizer = sr.Recognizer()
    temp_wav = _webm_to_wav(audio_bytes)
    try:
        with sr.AudioFile(temp_wav) as source:
            audio = recognizer.record(source)

        # Try each SA native language hint in order; return first successful result.
        attempts = ['zu-ZA', 'xh-ZA', 'st-ZA', 'nso-ZA', 'tn-ZA', 'ts-ZA', 'en-ZA', 'en-US']
        last_err = None
        for lang in attempts:
            try:
                text = recognizer.recognize_google(audio, language=lang)
                if text:
                    return text, 'auto'
            except sr.UnknownValueError as e:
                last_err = e
            except sr.RequestError as e:
                raise RuntimeError(f'Speech recognition service error: {e}')

        raise ValueError('Could not understand audio — please speak clearly and try again')
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def translate_language(text, source_language, target_language):
    """Translate text between source and target languages."""
    return GoogleTranslator(source=source_language, target=target_language).translate(text)


SA_LANGUAGES = (
    "isiZulu (Zulu), isiXhosa (Xhosa), Sesotho (Sotho), Setswana (Tswana), "
    "Sepedi (Northern Sotho / Pedi), Xitsonga (Tsonga), Tshivenda (Venda), "
    "siSwati (Swati), isiNdebele (Ndebele), and Afrikaans"
)

LLM_PROMPT_TEMPLATE = (
    "You are a multilingual South African speech-to-text correction assistant.\n"
    "IMPORTANT CONTEXT: The raw text below was produced by a speech-to-text model "
    "that was listening to someone speaking in a South African native language "
    "(or a mix of English and a native language). "
    "The model may have rendered native words as garbled or phonetic English-looking text "
    "because it struggled with the language.\n"
    "South African languages in use: " + SA_LANGUAGES + ".\n\n"
    "Your job:\n"
    "1. Assume most or all of the words may be from a native SA language, "
    "NOT English — even if they look like broken English.\n"
    "2. Translate everything into clean, natural English.\n"
    "3. If a word looks like a phonetic rendering of a Zulu/Xhosa/Sotho/Afrikaans word, "
    "identify what native word it likely represents and translate it.\n"
    "4. Correct grammar, remove fillers (um, uh, like), and produce "
    "one fluent English sentence or phrase.\n"
    "5. Return ONLY the final English text — no explanations, no labels.\n\n"
    "Raw transcription: {raw_text}\n\nEnglish translation:"
)


def clean_to_english(raw_text):
    """Send raw text to a local LLM to resolve SA languages and fix grammar.
    Returns (cleaned_text, src_lang) where src_lang is 'en' if LLM succeeded,
    or 'auto' so Google Translate can detect the language itself as a fallback."""
    model_name = os.getenv('OLLAMA_MODEL', 'llama3')
    prompt = LLM_PROMPT_TEMPLATE.format(raw_text=raw_text)
    try:
        resp = http_requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model_name, 'prompt': prompt, 'stream': False},
            timeout=30
        )
        if resp.ok:
            cleaned = resp.json().get('response', '').strip()
            if cleaned:
                return cleaned, 'en'
    except Exception:
        pass
    return raw_text, 'auto'


def save_spoken_record(raw_text, detected_language, target_language, translated_text):
    """Append spoken input and translation details to the records file."""
    timestamp = datetime.now().isoformat(timespec='seconds')
    line = (
        f"{timestamp} | detected={detected_language} | target={target_language} | "
        f"said={raw_text} | translation={translated_text}\n"
    )
    with open(RECORDS_FILE, 'a', encoding='utf-8') as records_file:
        records_file.write(line)


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
        target_language = request.form.get('target_language', 'zu')

        # Read and keep a copy of the user's original recording
        uploaded_audio = audio_file.read()
        if not uploaded_audio:
            return jsonify({'success': False, 'error': 'Empty audio file provided'})
        user_audio_id = str(uuid.uuid4())
        user_audio_cache[user_audio_id] = {
            'data': uploaded_audio,
            'mimetype': audio_file.mimetype or 'audio/webm'
        }
        
        native_text, detected_language = transcribe_audio_auto(uploaded_audio)
        translated_text = translate_language(native_text, 'auto', target_language)
        # Refine the translation into a fluent native-language sentence
        translated_text = multilanguage_agent(translated_text, target_language)
        save_spoken_record(native_text, detected_language, target_language, translated_text)
        output_voice_language = target_language

        # Generate output audio
        audio_data = generate_audio(translated_text, output_voice_language)
        audio_id = str(uuid.uuid4())
        audio_cache[audio_id] = audio_data

        return jsonify({
            'success': True,
            'raw_text': native_text,
            'source_text': native_text,
            'detected_language': detected_language,
            'translation': translated_text,
            'audio_id': audio_id,
            'user_audio_id': user_audio_id
        })

    except ValueError:
        return jsonify({'success': False, 'error': 'Could not understand audio'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/translate_text', methods=['POST'])
def translate_text_route():
    """Handle text translation"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        target_language = data.get('target_language', 'zu')
        
        if not text:
            return jsonify({'success': False, 'error': 'No text provided'})

        translated_text = translate_language(text, 'auto', target_language)
        # Refine the translation into a fluent native-language sentence
        translated_text = multilanguage_agent(translated_text, target_language)
        output_voice_language = target_language

        # Generate output audio
        audio_data = generate_audio(translated_text, output_voice_language)
        audio_id = str(uuid.uuid4())
        audio_cache[audio_id] = audio_data

        return jsonify({
            'success': True,
            'raw_text': text,
            'source_text': text,
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


@app.route('/listen/<audio_id>')
def listen(audio_id):
    """Serve user's original recorded audio"""
    if audio_id in user_audio_cache:
        audio_obj = user_audio_cache[audio_id]
        return send_file(
            io.BytesIO(audio_obj['data']),
            mimetype=audio_obj['mimetype'],
            as_attachment=False
        )
    return jsonify({'error': 'Audio not found'}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5010))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)