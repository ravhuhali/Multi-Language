let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let currentAudioUrl = null;
let targetLanguage = 'en';
let transcriptHistory = [];
let lastSourceText = '';
let lastRecordedUserAudioId = null;

const languageNames = {
    en: 'English',
    zu: 'Zulu',
    st: 'Sotho',
    xh: 'Xhosa',
    af: 'Afrikaans',
    auto: 'Auto-detected'
};

function getLanguageName(code) {
    return languageNames[code] || code;
}

function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function updateLanguageUI() {
    const targetName = getLanguageName(targetLanguage);

    document.getElementById('langLabel').textContent = targetName;
    document.getElementById('sourceLabel').textContent = 'Detected input';
    document.getElementById('textInputTitle').textContent = 'Or type in any language';
    document.getElementById('textInput').placeholder = 'Type text here...';
}

function setTargetLanguage(langCode) {
    targetLanguage = langCode;
    updateLanguageUI();

    if (lastSourceText) {
        retranslateLastSource();
    }
}

// Tab switching
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    if (tabName === 'translate') {
        document.querySelector('.tab-btn:first-child').classList.add('active');
        document.getElementById('translateTab').classList.add('active');
    } else {
        document.querySelector('.tab-btn:last-child').classList.add('active');
        document.getElementById('transcriptTab').classList.add('active');
    }
}

function addToTranscript(sourceText, translation, languagePair, translatedAudioId, userAudioId) {
    const entry = {
        timestamp: new Date().toLocaleString(),
        source: sourceText,
        translation,
        language: languagePair,
        translatedAudioId: translatedAudioId || null,
        userAudioId: userAudioId || null
    };
    transcriptHistory.push(entry);
    updateTranscriptDisplay();
}

function updateTranscriptDisplay() {
    const listEl = document.getElementById('transcriptList');
    const query = (document.getElementById('transcriptSearch')?.value || '').toLowerCase().trim();

    if (transcriptHistory.length === 0) {
        listEl.innerHTML = '<p class="empty-message">No translations yet. Start translating to see your history!</p>';
        return;
    }

    const filtered = transcriptHistory.filter(entry => {
        if (!query) return true;
        return (
            entry.source.toLowerCase().includes(query) ||
            entry.translation.toLowerCase().includes(query) ||
            entry.language.toLowerCase().includes(query) ||
            entry.timestamp.toLowerCase().includes(query)
        );
    });

    if (filtered.length === 0) {
        listEl.innerHTML = '<p class="empty-message">No results match your search.</p>';
        return;
    }

    const rows = filtered.map((entry, i) => {
        const userAudio = entry.userAudioId
            ? `<audio controls preload="none" src="/listen/${encodeURIComponent(entry.userAudioId)}"></audio>
               <a class="audio-dl-link" href="/listen/${encodeURIComponent(entry.userAudioId)}" download="your_speech_${i + 1}.mp3" title="Download audio">⬇️</a>`
            : '<span class="no-audio">—</span>';
        const translatedAudio = entry.translatedAudioId
            ? `<audio controls preload="none" src="/speak/${encodeURIComponent(entry.translatedAudioId)}"></audio>
               <a class="audio-dl-link" href="/speak/${encodeURIComponent(entry.translatedAudioId)}" download="translation_${i + 1}.mp3" title="Download audio">⬇️</a>`
            : '<span class="no-audio">—</span>';

        return `
        <tr>
            <td class="col-num">${i + 1}</td>
            <td class="col-time">${escapeHtml(entry.timestamp)}</td>
            <td class="col-lang">${escapeHtml(entry.language)}</td>
            <td class="col-english">${escapeHtml(entry.source)}</td>
            <td class="col-translation">${escapeHtml(entry.translation)}</td>
            <td class="col-audio">${userAudio}</td>
            <td class="col-audio">${translatedAudio}</td>
        </tr>`;
    }).join('');

    listEl.innerHTML = `
    <div class="transcript-table-wrap">
        <table class="transcript-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Time</th>
                    <th>Language Pair</th>
                    <th>Source (You said)</th>
                    <th>Translation</th>
                    <th>Your Audio</th>
                    <th>Translation Audio</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    </div>`;
}

function downloadTableCSV() {
    if (transcriptHistory.length === 0) {
        alert('No transcript to download!');
        return;
    }

    const headers = ['#', 'Time', 'Language Pair', 'Source (You said)', 'Translation', 'Your Audio URL', 'Translation Audio URL'];
    const rows = transcriptHistory.map((entry, i) => [
        i + 1,
        entry.timestamp,
        entry.language,
        entry.source,
        entry.translation,
        entry.userAudioId ? `${window.location.origin}/listen/${entry.userAudioId}` : '',
        entry.translatedAudioId ? `${window.location.origin}/speak/${entry.translatedAudioId}` : ''
    ]);

    const escape = val => `"${String(val).replace(/"/g, '""')}"`;
    const csvContent = [headers, ...rows].map(row => row.map(escape).join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transcript_' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function downloadTranscript() {
    if (transcriptHistory.length === 0) {
        alert('No transcript to download!');
        return;
    }

    let content = '=== TRANSLATION TRANSCRIPT ===\n';
    content += 'Generated: ' + new Date().toLocaleString() + '\n\n';

    transcriptHistory.forEach((entry, index) => {
        content += `--- Entry ${index + 1} ---\n`;
        content += `Time: ${entry.timestamp}\n`;
        content += `Language Pair: ${entry.language}\n`;
        content += `Source: ${entry.source}\n`;
        content += `Translation: ${entry.translation}\n\n`;
        if (entry.userAudioId) {
            content += `What You Said Audio URL: ${window.location.origin}/listen/${entry.userAudioId}\n`;
        }
        if (entry.translatedAudioId) {
            content += `Translation Audio URL: ${window.location.origin}/speak/${entry.translatedAudioId}\n`;
        }
        content += '\n';
    });

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transcript_' + new Date().toISOString().slice(0, 10) + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function clearTranscript() {
    if (transcriptHistory.length === 0) return;
    if (confirm('Are you sure you want to clear the transcript?')) {
        transcriptHistory = [];
        updateTranscriptDisplay();
    }
}

async function retranslateLastSource() {
    document.getElementById('loader').classList.add('show');
    document.getElementById('status').textContent = `Retranslating to ${getLanguageName(targetLanguage)}...`;

    try {
        const response = await fetch('/translate_text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: lastSourceText,
                target_language: targetLanguage
            })
        });

        const data = await response.json();
        document.getElementById('loader').classList.remove('show');

        if (data.success) {
            showResult(lastSourceText, data.translation, data.audio_id, lastRecordedUserAudioId);
            currentAudioUrl = '/speak/' + data.audio_id;
        } else {
            document.getElementById('status').textContent = data.error || 'Translation failed';
        }
    } catch (err) {
        document.getElementById('loader').classList.remove('show');
        document.getElementById('status').textContent = 'Error: Could not connect to server';
    }
}

async function toggleRecording() {
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            await sendAudioForTranslation(audioBlob);
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        document.getElementById('recordBtn').classList.add('recording');
        document.getElementById('recordBtn').textContent = '⏹️';
        document.getElementById('status').textContent = 'Recording... Click to stop';
    } catch (err) {
        console.error('Error accessing microphone:', err);
        document.getElementById('status').textContent = 'Error: Could not access microphone';
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        document.getElementById('recordBtn').classList.remove('recording');
        document.getElementById('recordBtn').textContent = '🎙️';
        document.getElementById('status').textContent = 'Processing...';
        document.getElementById('loader').classList.add('show');
    }
}

async function sendAudioForTranslation(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.wav');
    formData.append('target_language', targetLanguage);

    try {
        const response = await fetch('/translate_audio', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        document.getElementById('loader').classList.remove('show');

        if (data.success) {
            const sourceText = data.source_text || data.english || '';
            const rawText = data.raw_text || sourceText;
            const detectedLanguage = data.detected_language || 'auto';
            showResult(rawText, sourceText, data.translation, data.audio_id, data.user_audio_id, detectedLanguage);
            currentAudioUrl = '/speak/' + data.audio_id;
            lastSourceText = sourceText;
            lastRecordedUserAudioId = data.user_audio_id || null;
        } else {
            document.getElementById('status').textContent = data.error || 'Translation failed';
        }
    } catch (err) {
        document.getElementById('loader').classList.remove('show');
        document.getElementById('status').textContent = 'Error: Could not connect to server';
    }
}

async function translateText() {
    const text = document.getElementById('textInput').value.trim();
    if (!text) return;

    document.getElementById('loader').classList.add('show');
    document.getElementById('status').textContent = 'Translating...';

    try {
        const response = await fetch('/translate_text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                target_language: targetLanguage
            })
        });

        const data = await response.json();
        document.getElementById('loader').classList.remove('show');

        if (data.success) {
            const sourceText = data.source_text || data.english || text;
            showResult(text, sourceText, data.translation, data.audio_id, null, 'auto');
            currentAudioUrl = '/speak/' + data.audio_id;
            lastSourceText = sourceText;
            lastRecordedUserAudioId = null;
        } else {
            document.getElementById('status').textContent = data.error || 'Translation failed';
        }
    } catch (err) {
        document.getElementById('loader').classList.remove('show');
        document.getElementById('status').textContent = 'Error: Could not connect to server';
    }
}

function showResult(rawText, sourceText, translatedText, translatedAudioId, userAudioId, sourceLanguageCode = 'auto') {
    document.getElementById('rawResult').textContent = rawText;
    document.getElementById('englishResult').textContent = sourceText;
    document.getElementById('zuluResult').textContent = translatedText;
    document.getElementById('resultBox').classList.add('show');
    document.getElementById('playBtn').classList.add('show');
    document.getElementById('status').textContent = 'Click to start recording';
    document.getElementById('sourceLabel').textContent =
        sourceLanguageCode && sourceLanguageCode !== 'auto'
            ? `Detected: ${getLanguageName(sourceLanguageCode)}`
            : 'Detected input';

    const spokenLang = sourceLanguageCode !== 'auto' ? getLanguageName(sourceLanguageCode) : 'Auto-detected';
    const languagePair = `${spokenLang} → ${getLanguageName(targetLanguage)}`;
    addToTranscript(sourceText, translatedText, languagePair, translatedAudioId, userAudioId);
}

async function playAudio() {
    if (currentAudioUrl) {
        const audio = document.getElementById('audioPlayer');
        audio.src = currentAudioUrl;
        audio.play();
    }
}

document.getElementById('textInput').addEventListener('keypress', e => {
    if (e.key === 'Enter') translateText();
});

updateLanguageUI();
