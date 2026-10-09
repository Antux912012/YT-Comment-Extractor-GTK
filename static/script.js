let currentComments = [];

document.addEventListener('DOMContentLoaded', () => {
    const searchBtn = document.getElementById('searchBtn');
    const videoUrl = document.getElementById('videoUrl');
    const numComments = document.getElementById('numComments');
    const selectionMode = document.getElementById('selectionMode');
    const downloadCsvBtn = document.getElementById('downloadCsvBtn');
    const downloadJsonBtn = document.getElementById('downloadJsonBtn');
    const copyBtn = document.getElementById('copyBtn');
    const viewJsonBtn = document.getElementById('viewJsonBtn');
    const themeToggleBtn = document.getElementById('themeToggle');
    const settingsBtn = document.getElementById('settingsBtn');
    
    // UI Elements
    const loadingSpinner = document.getElementById('loadingSpinner');
    const errorMessage = document.getElementById('errorMessage');
    const resultsSection = document.getElementById('resultsSection');
    const commentCount = document.getElementById('commentCount');
    const totalCount = document.getElementById('totalCount');
    const selectionInfo = document.getElementById('selectionInfo');
    const commentsList = document.getElementById('commentsList');

    // JSON Modal Elements
    const jsonModal = document.getElementById('jsonModal');
    const jsonModalClose = document.getElementById('jsonModalClose');
    const jsonModalCloseBtn = document.getElementById('jsonModalCloseBtn');
    const jsonContent = document.getElementById('jsonContent');
    const copyJsonBtn = document.getElementById('copyJsonBtn');

    // Settings Modal Elements
    const settingsModal = document.getElementById('settingsModal');
    const settingsModalClose = document.getElementById('settingsModalClose');
    const settingsModalCloseBtn = document.getElementById('settingsModalCloseBtn');
    const saveCookiesBtn = document.getElementById('saveCookiesBtn');
    const clearCookiesBtn = document.getElementById('clearCookiesBtn');
    const cookiesInput = document.getElementById('cookiesInput');
    const cookiesStatus = document.getElementById('cookiesStatus');

    // Theme Toggle
    themeToggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('theme-dark');
        const isDark = document.body.classList.contains('theme-dark');
        themeToggleBtn.textContent = isDark ? 'Switch to light mode' : 'Switch to dark mode';
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });

    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('theme-dark');
        themeToggleBtn.textContent = 'Switch to light mode';
    }

    // Check cookies status on load
    checkCookiesStatus();

    function checkCookiesStatus() {
        fetch('/api/settings/cookies')
            .then(res => res.json())
            .then(data => {
                if (data.has_cookies) {
                    cookiesStatus.textContent = 'Status: Cookies are currently saved and active.';
                    cookiesStatus.style.color = '#10b981';
                } else {
                    cookiesStatus.textContent = 'Status: No cookies saved.';
                    cookiesStatus.style.color = '#ef4444';
                }
            });
    }

    // Settings Modal functionality
    settingsBtn.addEventListener('click', () => {
        settingsModal.classList.add('active');
        checkCookiesStatus();
    });
    
    const closeSettings = () => settingsModal.classList.remove('active');
    settingsModalClose.addEventListener('click', closeSettings);
    settingsModalCloseBtn.addEventListener('click', closeSettings);

    saveCookiesBtn.addEventListener('click', async () => {
        const cookies = cookiesInput.value.trim();
        if (!cookies) return alert('Please enter cookies data first.');
        
        try {
            const res = await fetch('/api/settings/cookies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookies })
            });
            const data = await res.json();
            if (res.ok) {
                alert(data.message);
                cookiesInput.value = '';
                checkCookiesStatus();
            } else {
                alert('Error: ' + data.error);
            }
        } catch (e) {
            alert('Failed to save cookies.');
        }
    });

    clearCookiesBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/settings/cookies', { method: 'DELETE' });
            if (res.ok) {
                alert('Cookies cleared.');
                checkCookiesStatus();
            }
        } catch (e) {
            alert('Failed to clear cookies.');
        }
    });

    // Extract Comments
    searchBtn.addEventListener('click', async () => {
        const url = videoUrl.value.trim();
        if (!url) {
            showError('Please enter a YouTube video URL');
            return;
        }

        hideError();
        resultsSection.style.display = 'none';
        loadingSpinner.style.display = 'block';

        try {
            const response = await fetch('/api/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url,
                    num_comments: numComments.value,
                    selection_mode: selectionMode.value
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to extract comments');
            }

            currentComments = data.comments;
            displayResults(data);

        } catch (error) {
            showError(error.message);
        } finally {
            loadingSpinner.style.display = 'none';
        }
    });

    function displayResults(data) {
        commentCount.textContent = data.count;
        totalCount.textContent = data.total_available;
        
        let infoText = `Showing ${data.count} `;
        infoText += data.selection_mode === 'random' ? 'randomly selected' : 'ordered';
        infoText += ' comments';
        
        if (data.total_available > 0) {
            const percentage = ((data.count / data.total_available) * 100).toFixed(1);
            infoText += ` (${percentage}% of total available)`;
        }
        
        selectionInfo.textContent = infoText;
        commentsList.innerHTML = '';
        
        data.comments.forEach(comment => {
            const tr = document.createElement('tr');
            
            const tdNick = document.createElement('td');
            tdNick.textContent = comment.nickname || 'Anonymous';
            
            const tdDate = document.createElement('td');
            tdDate.textContent = comment.date || 'Unknown';
            
            const tdComment = document.createElement('td');
            const commentSpan = document.createElement('span');
            commentSpan.className = 'comment-text';
            commentSpan.textContent = comment.comment || '';
            commentSpan.title = comment.comment || ''; 
            tdComment.appendChild(commentSpan);
            
            tr.appendChild(tdNick);
            tr.appendChild(tdDate);
            tr.appendChild(tdComment);
            commentsList.appendChild(tr);
        });

        resultsSection.style.display = 'block';
    }

    // CSV Download
    downloadCsvBtn.addEventListener('click', async () => {
        if (!currentComments.length) return;
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ comments: currentComments })
            });
            if (!response.ok) throw new Error('Download failed');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `youtube_comments_${new Date().toISOString().slice(0,19).replace(/[:-]/g, '')}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            showError('Failed to download CSV: ' + error.message);
        }
    });

    // JSON Download
    downloadJsonBtn.addEventListener('click', () => {
        if (!currentComments.length) return;
        const dataStr = JSON.stringify(currentComments, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `youtube_comments_${new Date().toISOString().slice(0,19).replace(/[:-]/g, '')}.json`;
        document.body.appendChild(a);
        a.click();
        URL.revokeObjectURL(url);
        document.body.removeChild(a);
    });

    // Copy to Clipboard
    copyBtn.addEventListener('click', () => {
        if (!currentComments.length) return;
        const text = currentComments.map(c => `Nickname: ${c.nickname}\nDate: ${c.date}\nComment: ${c.comment}\n---`).join('\n\n');
        navigator.clipboard.writeText(text).then(() => {
            const originalText = copyBtn.textContent;
            copyBtn.textContent = '✅ Copied!';
            setTimeout(() => copyBtn.textContent = originalText, 2000);
        }).catch(err => {
            showError('Failed to copy to clipboard');
        });
    });

    // View JSON Modal
    viewJsonBtn.addEventListener('click', () => {
        if (!currentComments.length) return;
        jsonContent.textContent = JSON.stringify(currentComments, null, 2);
        jsonModal.classList.add('active');
    });

    const closeJsonModal = () => jsonModal.classList.remove('active');
    jsonModalClose.addEventListener('click', closeJsonModal);
    jsonModalCloseBtn.addEventListener('click', closeJsonModal);

    copyJsonBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(jsonContent.textContent).then(() => {
            const originalText = copyJsonBtn.textContent;
            copyJsonBtn.textContent = '✅ Copied!';
            setTimeout(() => copyJsonBtn.textContent = originalText, 2000);
        });
    });

    window.addEventListener('click', (e) => {
        if (e.target === jsonModal) closeJsonModal();
        if (e.target === settingsModal) closeSettings();
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
        resultsSection.style.display = 'none';
    }

    function hideError() {
        errorMessage.style.display = 'none';
        errorMessage.textContent = '';
    }
});
