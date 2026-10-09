let currentComments = [];

document.addEventListener('DOMContentLoaded', () => {
    const searchBtn = document.getElementById('searchBtn');
    const videoUrl = document.getElementById('videoUrl');
    const extractMethod = document.getElementById('extractMethod');
    const sortMode = document.getElementById('sortMode');
    const numComments = document.getElementById('numComments');
    const selectionMode = document.getElementById('selectionMode');
    
    // UI Elements
    const loadingSpinner = document.getElementById('loadingSpinner');
    const loadingText = document.getElementById('loadingText');
    const errorMessage = document.getElementById('errorMessage');
    const resultsSection = document.getElementById('resultsSection');
    const commentsList = document.getElementById('commentsList');

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
        // Check Cookies
        fetch('/api/settings/cookies').then(r => r.json()).then(d => {
            const cs = document.getElementById('cookiesStatus');
            if (d.has_cookies) { cs.textContent = '✅ Cookies saved and active'; cs.style.color = 'green'; }
            else { cs.textContent = '❌ No cookies saved'; cs.style.color = 'red'; }
        });
        // Check API Auth
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

    // Extract Comments
    searchBtn.addEventListener('click', async () => {
        const url = videoUrl.value.trim();
        if (!url) return showError('Please enter a YouTube video URL');

        hideError();
        resultsSection.style.display = 'none';
        
        if (selectionMode.value === 'random') {
            loadingText.textContent = "Performing Deep Scan for true randomness... This may take up to 10 seconds.";
        } else {
            loadingText.textContent = "Extracting comments... This may take a moment.";
        }
        loadingSpinner.style.display = 'block';

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
            const data = await response.json();
            if (!response.ok) {
                if (response.status === 401 && extractMethod.value === 'api') {
                    throw new Error('You must Sign in with Google (in Settings) to use the API method.');
                }
                throw new Error(data.error || 'Failed to extract comments');
            }
            currentComments = data.comments;
            displayResults(data);
        } catch (error) { showError(error.message); } 
        finally { loadingSpinner.style.display = 'none'; }
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
