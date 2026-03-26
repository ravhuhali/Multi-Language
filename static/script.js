let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let currentAudioUrl = null;
let selectedLanguage = 'zu';
let languageName = 'Zulu';
let transcriptHistory = [];

// Tab switching
function switchTab(tabName) {
    // Update tab buttons
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

// Add to transcript history
function addToTranscript(english, translation, language) {
    const entry = {
        timestamp: new Date().toLocaleString(),
        english: english,
        translation: translation,
        language: language
    };
    transcriptHistory.push(entry);
    updateTranscriptDisplay();
}

// Update transcript display
function updateTranscriptDisplay() {
    const listEl = document.getElementById('transcriptList');
    
    if (transcriptHistory.length === 0) {
        listEl.innerHTML = '<p class="empty-message">No translations yet. Start translating to see your history!</p>';
        return;
    }
    
    listEl.innerHTML = transcriptHistory.map((entry, index) => `
        <div class="transcript-entry">
            <div class="transcript-time">${entry.timestamp} - ${entry.language}</div>
            <div class="transcript-original"><strong>Original:</strong> ${entry.english}</div>
            <div class="transcript-translated"><strong>Translation:</strong> ${entry.translation}</div>
        </div>
    `).join('');
}

// Download transcript as text file
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
        content += `Target Language: ${entry.language}\n`;
        content += `Original (English): ${entry.english}\n`;
        content += `Translation: ${entry.translation}\n\n`;
    });
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transcript_' + new Date().toISOString().slice(0,10) + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Clear transcript
function clearTranscript() {
    if (transcriptHistory.length === 0) return;
    if (confirm('Are you sure you want to clear the transcript?')) {
        transcriptHistory = [];
        updateTranscriptDisplay();
    }
}

function setLanguage(lang, name) {
    selectedLanguage = lang;
    languageName = name;
    document.getElementById('langLabel').textContent = name;
    
    // Update active button
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
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
        
        mediaRecorder.ondataavailable = (event) => {
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
    formData.append('language', selectedLanguage);
    
    try {
        const response = await fetch('/translate_audio', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        document.getElementById('loader').classList.remove('show');
        
        if (data.success) {
            showResult(data.english, data.translation);
            currentAudioUrl = '/speak/' + data.audio_id;
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
            body: JSON.stringify({ text: text, language: selectedLanguage })
        });
        
        const data = await response.json();
        document.getElementById('loader').classList.remove('show');
        
        if (data.success) {
            showResult(data.english, data.translation);
            currentAudioUrl = '/speak/' + data.audio_id;
        } else {
            document.getElementById('status').textContent = data.error || 'Translation failed';
        }
    } catch (err) {
        document.getElementById('loader').classList.remove('show');
        document.getElementById('status').textContent = 'Error: Could not connect to server';
    }
}

function showResult(english, zulu) {
    document.getElementById('englishResult').textContent = english;
    document.getElementById('zuluResult').textContent = zulu;
    document.getElementById('resultBox').classList.add('show');
    document.getElementById('playBtn').classList.add('show');
    document.getElementById('status').textContent = 'Click to start recording';
    
    // Add to transcript
    addToTranscript(english, zulu, languageName);
}

async function playAudio() {
    if (currentAudioUrl) {
        const audio = document.getElementById('audioPlayer');
        audio.src = currentAudioUrl;
        audio.play();
    }
}

// Allow Enter key to translate
document.getElementById('textInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') translateText();
});
