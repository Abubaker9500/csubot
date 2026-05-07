// ── Config ────────────────────────────────────────────────────
const API_URL = 'https://hpc1.csub.edu/ab-sayed/chat';
// ─────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const inputEl    = document.getElementById('userInput');
const sendBtn    = document.getElementById('sendBtn');
const emptyState = document.getElementById('emptyState');
const errorToast = document.getElementById('errorToast');

let conversationHistory = [];
let isGenerating = false;

// Logout is handled by a plain form POST in index.html — no JS needed.

// ── Input handling ────────────────────────────────────────────
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
});

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isGenerating) sendMessage();
  }
});

function showError(msg) {
  errorToast.textContent = msg;
  errorToast.style.display = 'block';
  setTimeout(() => errorToast.style.display = 'none', 5000);
}

function clearChat() {
  conversationHistory = [];
  messagesEl.innerHTML = '';
  messagesEl.appendChild(emptyState);
  emptyState.style.display = 'block';
}

function addMessage(role, content) {
  emptyState.style.display = 'none';

  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? 'You' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (role === 'ai') {
    bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
  } else {
    bubble.textContent = content;
  }

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  return bubble;
}

function renderAIContent(bubble, text) {
  const thinkRegex = /<think>([\s\S]*?)<\/think>/g;
  let html = '';
  let lastIndex = 0;
  let match;

  while ((match = thinkRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      html += escapeHtml(text.slice(lastIndex, match.index));
    }
    html += `<div class="think-block"><span class="think-label">💭 thinking</span>${escapeHtml(match[1].trim())}</div>`;
    lastIndex = thinkRegex.lastIndex;
  }

  const remaining = text.slice(lastIndex);
  if (remaining) html += escapeHtml(remaining).replace(/\n/g, '<br>');
  bubble.innerHTML = html || '&nbsp;';
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isGenerating) return;

  conversationHistory.push({ role: 'user', content: text });
  addMessage('user', text);

  inputEl.value = '';
  inputEl.style.height = 'auto';
  isGenerating = true;
  sendBtn.disabled = true;

  const aiBubble = addMessage('ai', '');
  let fullResponse = '';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ messages: conversationHistory })
    });

    // Session expired or not logged in — redirect to login
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }

    if (response.status === 429) {
      throw new Error('Rate limit reached. Please wait before sending more messages.');
    }

    if (!response.ok) {
      throw new Error(`Server error ${response.status}: ${await response.text()}`);
    }

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value, { stream: true }).split('\n').filter(l => l.trim());

      for (const line of lines) {
        try {
          const json = JSON.parse(line);
          if (json.message?.content) {
            fullResponse += json.message.content;
            renderAIContent(aiBubble, fullResponse);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } catch { /* partial JSON line */ }
      }
    }

    conversationHistory.push({ role: 'assistant', content: fullResponse });

  } catch (err) {
    console.error(err);
    aiBubble.innerHTML = `<span style="color:#dc2626;">⚠️ ${escapeHtml(err.message)}</span>`;
    showError(err.message);
  } finally {
    isGenerating = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}
