let currentComments = [];

document.addEventListener('DOMContentLoaded', () => {
    const searchBtn = document.getElementById('searchBtn');
    const videoUrl = document.getElementById('videoUrl');
    const extractMethod = document.getElementById('extractMethod');
    const sortMode = document.getElementById('sortMode');
    const numComments = document.getElementById('numComments');
    const selectionMode = document.getElementById('selectionMode');
    
    // UI Elements
    const errorMessage = document.getElementById('errorMessage');
    const resultsSection = document.getElementById('resultsSection');
    const commentsList = document.getElementById('commentsList');

    // Terminal Console Elements
    const consoleWindow = document.getElementById('consoleWindow');
    const consoleOutput = document.getElementById('consoleOutput');

    // Settings Modal Elements
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const apiStatusBox = document.getElementById('apiStatusBox');

    // Theme Toggle
    document.getElementById('themeToggle').addEventListener('click', (e) => {
        document.body.classList.toggle('theme-dark');
        e.target.textContent = document.body.classList.contains('theme-dark') ? 'Switch to light mode' : 'Switch to dark mode';
    });

    // Check statuses on load
    function updateStatuses() {
        fetch('/api/settings/cookies').then(r => r.json()).then(d => {
            const cs = document.getElementById('cookiesStatus');
            if (d.has_cookies) { cs.textContent = '✅ Cookies saved and active'; cs.style.color = 'green'; }
            else { cs.textContent = '❌ No cookies saved'; cs.style.color = 'red'; }
        });
        fetch('/api/auth/status').then(r => r.json()).then(d => {
            if (!d.configured) {
                apiStatusBox.innerHTML = '<p style="color:red;font-weight:bold;">❌ API Not Configured</p><p style="font-size:0.85em;">The server host must set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables to use this feature.</p>';
            } else if (d.logged_in) {
                apiStatusBox.innerHTML = '<p style="color:green;font-weight:bold;">✅ Signed in with Google</p><button id="googleLogoutBtn" class="btn btn-copy-json" style="margin-top:10px;width:100%">Sign Out</button>';
                document.getElementById('googleLogoutBtn').addEventListener('click', () => {
                    fetch('/api/auth/logout').then(() => updateStatuses());
                });
            } else {
                apiStatusBox.innerHTML = '<p style="color:orange;font-weight:bold;">⚠️ Not signed in</p><button id="googleLoginBtn" class="btn btn-download" style="margin-top:10px;width:100%">Sign in with Google</button>';
                document.getElementById('googleLoginBtn').addEventListener('click', () => {
                    window.location.href = '/api/auth/login';
                });
            }
        });
    }

    settingsBtn.addEventListener('click', () => {
        settingsModal.classList.add('active');
        updateStatuses();
    });
    document.getElementById('settingsModalClose').addEventListener('click', () => settingsModal.classList.remove('active'));

    document.getElementById('saveCookiesBtn').addEventListener('click', async () => {
        const cookies = document.getElementById('cookiesInput').value.trim();
        if (!cookies) return alert('Enter cookies first.');
        const res = await fetch('/api/settings/cookies', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({cookies}) });
        if (res.ok) { alert('Cookies saved!'); document.getElementById('cookiesInput').value = ''; updateStatuses(); }
        else alert('Error saving cookies');
    });

    document.getElementById('clearCookiesBtn').addEventListener('click', async () => {
        if (await fetch('/api/settings/cookies', { method: 'DELETE' }).then(r=>r.ok)) { alert('Cleared'); updateStatuses(); }
    });

    function appendLog(text) {
        const div = document.createElement('div');
        div.className = 'log-line';
        if (text.includes('[ERROR]')) div.classList.add('log-error');
        else if (text.includes('[SUCCESS]')) div.classList.add('log-success');
        else if (text.includes('[INFO]')) div.classList.add('log-info');
        else if (text.includes('[SYSTEM]')) div.classList.add('log-system');
        else if (text.includes('[NETWORK]')) div.classList.add('log-network');
        
        const timestamp = new Date().toLocaleTimeString();
        div.textContent = `[${timestamp}] ${text}`;
        consoleOutput.appendChild(div);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    // Extract Comments
    searchBtn.addEventListener('click', async () => {
        const url = videoUrl.value.trim();
        if (!url) return showError('Please enter a YouTube video URL');

        hideError();
        resultsSection.style.display = 'none';
        
        consoleOutput.innerHTML = '';
        consoleWindow.style.display = 'block';
        searchBtn.disabled = true;

        try {
            const response = await fetch('/api/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url,
                    method: extractMethod.value,
                    sort_mode: sortMode.value,
                    num_comments: numComments.value,
                    selection_mode: selectionMode.value
                })
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const {value, done} = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n').filter(l => l.trim());
                
                for (let line of lines) {
                    try {
                        const data = JSON.parse(line);
                        if (data.log) {
                            appendLog(data.log);
                        }
                        if (data.error) {
                            throw new Error(data.error);
                        }
                        if (data.success) {
                            currentComments = data.comments;
                            displayResults(data);
                        }
                    } catch (e) {
                        if (e.message !== "Unexpected end of JSON input" && !e.message.startsWith("Unexpected token")) {
                            throw e;
                        }
                    }
                }
            }
        } catch (error) { 
            appendLog(`[ERROR] ${error.message}`);
            showError(error.message); 
        } finally {
            searchBtn.disabled = false;
        }
    });

    function displayResults(data) {
        document.getElementById('commentCount').textContent = data.count;
        document.getElementById('selectionInfo').innerHTML = `Selected <strong>${data.count}</strong> comments out of a fetched pool of <strong>${data.pool_size_fetched}</strong>.<br>Mode: <strong>${data.selection_mode === 'random' ? 'Random Sample (Debiased)' : 'Ordered'}</strong>`;
        commentsList.innerHTML = '';
        data.comments.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${c.nickname||'Anonymous'}</td><td>${c.date||'Unknown'}</td><td><span class="comment-text" title="${c.comment}">${c.comment}</span></td>`;
            commentsList.appendChild(tr);
        });
        resultsSection.style.display = 'block';
    }

    // Downloads & Utilities
    document.getElementById('downloadCsvBtn').addEventListener('click', async () => {
        if (!currentComments.length) return;
        const response = await fetch('/api/download', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({comments: currentComments}) });
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = window.URL.createObjectURL(blob);
        a.download = `yt_comments_${Date.now()}.csv`;
        a.click();
    });

    document.getElementById('downloadJsonBtn').addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(currentComments, null, 2)], { type: 'application/json' }));
        a.download = `yt_comments_${Date.now()}.json`;
        a.click();
    });

    document.getElementById('viewJsonBtn').addEventListener('click', () => {
        document.getElementById('jsonContent').textContent = JSON.stringify(currentComments, null, 2);
        document.getElementById('jsonModal').classList.add('active');
    });

    ['jsonModalClose', 'jsonModalCloseBtn'].forEach(id => {
        document.getElementById(id).addEventListener('click', () => document.getElementById('jsonModal').classList.remove('active'));
    });

    function showError(m) {
        errorMessage.textContent = m;
        errorMessage.style.display = 'block';
        resultsSection.style.display = 'none';
    }
    function hideError() { errorMessage.style.display = 'none'; }
    updateStatuses();
});
