/* Rav Itamar — SPA Frontend */

const API = '/api';
let currentConversationId = null;
let searchTimeout = null;

// ─── Init ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadConversations();
    loadPDFs();
    autoResizeTextarea();
});

// ─── API helpers ───────────────────────────────────
async function api(path, opts = {}) {
    const url = API + path;
    const config = { ...opts };
    if (opts.body && !(opts.body instanceof FormData)) {
        config.headers = { 'Content-Type': 'application/json', ...opts.headers };
        config.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(url, config);
    if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err);
    }
    return resp.json();
}

// ─── Toast ────────────────────────────────────────
function toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

// ─── Conversations ────────────────────────────────
async function loadConversations() {
    try {
        const convos = await api('/conversations');
        const list = document.getElementById('conversationList');
        list.innerHTML = '';
        convos.forEach(c => {
            const li = document.createElement('li');
            li.className = 'conversation-item' + (c.id === currentConversationId ? ' active' : '');
            li.innerHTML = `
                <div class="conv-title">${escapeHtml(c.title)}</div>
                <span class="conv-meta">${c.message_count || 0}</span>
                <span class="conv-delete" onclick="event.stopPropagation(); deleteConversation('${c.id}')" title="Delete">&times;</span>
            `;
            li.onclick = () => openConversation(c.id, c.title);
            list.appendChild(li);
        });
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

async function newConversation() {
    currentConversationId = null;
    document.getElementById('welcomeScreen').style.display = 'none';
    const chatView = document.getElementById('chatView');
    chatView.style.display = 'flex';
    document.getElementById('chatTitle').textContent = 'New Conversation';
    document.getElementById('chatMessages').innerHTML = '';
    document.getElementById('chatInput').focus();
    closeSearch();
    closeProfile();
    // Mark none as active
    document.querySelectorAll('.conversation-item').forEach(el => el.classList.remove('active'));
}

async function openConversation(id, title) {
    currentConversationId = id;
    closeSearch();
    closeProfile();
    document.getElementById('welcomeScreen').style.display = 'none';
    const chatView = document.getElementById('chatView');
    chatView.style.display = 'flex';
    document.getElementById('chatTitle').textContent = title || 'Conversation';

    // Highlight in sidebar
    document.querySelectorAll('.conversation-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.conversation-item').forEach(el => {
        if (el.querySelector('.conv-title').textContent === title) {
            el.classList.add('active');
        }
    });

    // Load messages
    try {
        const data = await api(`/conversations/${id}`);
        document.getElementById('chatTitle').textContent = data.title;
        renderMessages(data.messages);
    } catch (e) {
        toast('Failed to load conversation', 'error');
    }
}

function renderMessages(messages) {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';
    messages.forEach(m => appendMessage(m.role, m.content, m.id));
    container.scrollTop = container.scrollHeight;
}

function appendMessage(role, content, id) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (id) div.setAttribute('data-message-id', id);
    div.innerHTML = `
        <div class="message-role">${role === 'user' ? 'You' : 'Rav Itamar'}</div>
        <div class="message-content">${escapeHtml(content)}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function appendLoading() {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'loadingMessage';
    div.innerHTML = `
        <div class="message-role">Rav Itamar</div>
        <div class="loading"></div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function removeLoading() {
    const el = document.getElementById('loadingMessage');
    if (el) el.remove();
}

async function deleteConversation(id) {
    if (!confirm('Delete this conversation?')) return;
    try {
        await api(`/conversations/${id}`, { method: 'DELETE' });
        if (currentConversationId === id) {
            currentConversationId = null;
            document.getElementById('chatView').style.display = 'none';
            document.getElementById('welcomeScreen').style.display = 'flex';
        }
        loadConversations();
        toast('Conversation deleted', 'success');
    } catch (e) {
        toast('Failed to delete', 'error');
    }
}

// ─── Chat ─────────────────────────────────────────
async function sendMessage() {
    const input = document.getElementById('chatInput');
    let message = input.value.trim();
    if (!message) return;

    // If citations toggle is on, prepend request
    const citationsOn = document.getElementById('citationsToggle').checked;
    if (citationsOn && !message.toLowerCase().includes('citation')) {
        message = message + '\n[Show citations]';
    }

    input.value = '';
    input.style.height = 'auto';

    appendMessage('user', message);
    appendLoading();

    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;

    try {
        const data = await api('/chat', {
            method: 'POST',
            body: {
                conversation_id: currentConversationId,
                message: message,
            },
        });

        removeLoading();
        appendMessage('assistant', data.response, data.message_id);

        // Update conversation id if new
        if (!currentConversationId) {
            currentConversationId = data.conversation_id;
        }

        loadConversations();
    } catch (e) {
        removeLoading();
        appendMessage('assistant', 'Error: ' + e.message);
        toast('Failed to send message', 'error');
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResizeTextarea() {
    const textarea = document.getElementById('chatInput');
    if (!textarea) return;
    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    });
}

// ─── PDFs ─────────────────────────────────────────
async function loadPDFs() {
    try {
        const pdfs = await api('/pdfs');
        const list = document.getElementById('pdfList');
        list.innerHTML = '';
        if (pdfs.length === 0) {
            list.innerHTML = '<li class="pdf-item" style="color: var(--text-muted); cursor: default;">No PDFs uploaded yet</li>';
            return;
        }
        pdfs.forEach(p => {
            const li = document.createElement('li');
            li.className = 'pdf-item';
            li.innerHTML = `
                <span>${escapeHtml(p.title)} (${p.total_pages}p)</span>
                <span class="conv-delete" onclick="event.stopPropagation(); deletePDF('${p.id}')" title="Delete">&times;</span>
            `;
            list.appendChild(li);
        });
    } catch (e) {
        console.error('Failed to load PDFs:', e);
    }
}

function showUploadModal() {
    document.getElementById('uploadModal').classList.add('active');
}

function closeUploadModal() {
    document.getElementById('uploadModal').classList.remove('active');
    document.getElementById('pdfFile').value = '';
    document.getElementById('pdfTitle').value = '';
}

async function uploadPDF() {
    const fileInput = document.getElementById('pdfFile');
    const titleInput = document.getElementById('pdfTitle');

    if (!fileInput.files.length) {
        toast('Select a PDF file', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    if (titleInput.value.trim()) {
        formData.append('title', titleInput.value.trim());
    }

    const uploadBtn = document.getElementById('uploadBtn');
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';

    try {
        const result = await fetch(API + '/pdfs/upload', {
            method: 'POST',
            body: formData,
        }).then(r => {
            if (!r.ok) throw new Error('Upload failed');
            return r.json();
        });

        closeUploadModal();
        loadPDFs();
        toast(`Uploaded: ${result.title} (${result.pages} pages, ${result.chunks} chunks)`, 'success');
    } catch (e) {
        toast('Upload failed: ' + e.message, 'error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload';
    }
}

async function deletePDF(id) {
    if (!confirm('Delete this PDF and its chunks from the KB?')) return;
    try {
        await api(`/pdfs/${id}`, { method: 'DELETE' });
        loadPDFs();
        toast('PDF deleted', 'success');
    } catch (e) {
        toast('Failed to delete PDF', 'error');
    }
}

// ─── Search ───────────────────────────────────────
function onSearchInput(value) {
    clearTimeout(searchTimeout);
    if (!value.trim()) {
        closeSearch();
        return;
    }
    searchTimeout = setTimeout(() => runSearch(value.trim()), 400);
}

async function runSearch(query) {
    try {
        const results = await api(`/search/messages?q=${encodeURIComponent(query)}`);
        const panel = document.getElementById('searchResults');
        const list = document.getElementById('searchResultsList');
        panel.classList.add('active');

        if (results.length === 0) {
            list.innerHTML = '<p style="color: var(--text-muted);">No results found.</p>';
            return;
        }

        list.innerHTML = '';
        results.forEach(r => {
            const div = document.createElement('div');
            div.className = 'search-result-item';
            div.innerHTML = `
                <div class="sr-conv">${escapeHtml(r.conversation_title)}</div>
                <div class="sr-role">${r.role}</div>
                <div class="sr-content">${escapeHtml(r.content)}</div>
            `;
            div.onclick = () => {
                closeSearch();
                openConversation(r.conversation_id, r.conversation_title);
                // Scroll to message after loading
                setTimeout(() => scrollToMessage(r.message_id), 500);
            };
            list.appendChild(div);
        });
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function scrollToMessage(messageId) {
    const el = document.querySelector(`[data-message-id="${messageId}"]`);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.style.outline = '2px solid var(--accent)';
        setTimeout(() => { el.style.outline = 'none'; }, 2000);
    }
}

function closeSearch() {
    document.getElementById('searchResults').classList.remove('active');
    document.getElementById('searchInput').value = '';
}

// ─── Profile ──────────────────────────────────────
async function showProfile() {
    closeSearch();
    document.getElementById('profilePanel').classList.add('active');
    try {
        const prof = await api('/profile');
        const fields = ['identity', 'values', 'goals', 'constraints', 'preferences',
                         'recurring_patterns', 'decision_history', 'vocabulary', 'raw_notes'];
        fields.forEach(f => {
            const el = document.getElementById(`prof-${f}`);
            if (el) el.value = prof[f] || '';
        });
    } catch (e) {
        toast('Failed to load profile', 'error');
    }
}

async function saveProfile() {
    const fields = ['identity', 'values', 'goals', 'constraints', 'preferences',
                     'recurring_patterns', 'decision_history', 'vocabulary', 'raw_notes'];
    const data = {};
    fields.forEach(f => {
        const el = document.getElementById(`prof-${f}`);
        if (el && el.value.trim()) data[f] = el.value.trim();
    });

    try {
        await api('/profile/update', { method: 'POST', body: data });
        toast('Profile saved', 'success');
    } catch (e) {
        toast('Failed to save profile', 'error');
    }
}

function closeProfile() {
    document.getElementById('profilePanel').classList.remove('active');
}

// ─── KB Management ────────────────────────────────
async function reindexKB() {
    toast('Reindexing KB...', 'info');
    try {
        const result = await api('/kb/reindex', { method: 'POST' });
        toast(`KB reindexed: ${result.pdfs?.length || 0} PDFs processed`, 'success');
    } catch (e) {
        toast('Reindex failed: ' + e.message, 'error');
    }
}

async function rebuildPrinciples() {
    toast('Rebuilding Principle Map...', 'info');
    try {
        const result = await api('/principles/rebuild', { method: 'POST' });
        toast(`Principle Map rebuilt: ${result.principles_created || 0} principles`, 'success');
    } catch (e) {
        toast('Rebuild failed: ' + e.message, 'error');
    }
}

// ─── Util ─────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
