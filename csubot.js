// ── Config ────────────────────────────────────────────────────
const PREFIX  = window.CSUBOT_PREFIX || '';
const API_URL = PREFIX + '/chat';
const CHAT_STORAGE_KEY = 'csubot_chat';
// ─────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const inputEl    = document.getElementById('userInput');
const sendBtn    = document.getElementById('sendBtn');
const emptyState = document.getElementById('emptyState');
const errorToast = document.getElementById('errorToast');

let conversationHistory = [];
let isGenerating = false;

function saveChat() {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(conversationHistory));
  } catch { /* quota / private mode */ }
}

function loadChat() {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function restoreChat() {
  conversationHistory = loadChat();
  if (!conversationHistory.length) return;

  emptyState.style.display = 'none';
  for (const msg of conversationHistory) {
    if (msg.role === 'user') {
      addMessage('user', msg.content);
    } else if (msg.role === 'assistant') {
      addMessage('ai', msg.content);
    }
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

document.querySelector('form[action$="/logout"]')?.addEventListener('submit', () => {
  localStorage.removeItem(CHAT_STORAGE_KEY);
});

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
  saveChat();
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
    if (content) {
      renderAIContent(bubble, content);
    } else {
      bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    }
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
      html += formatMarkdown(text.slice(lastIndex, match.index));
    }
    html += `<div class="think-block"><span class="think-label">💭 thinking</span>${escapeHtml(match[1].trim())}</div>`;
    lastIndex = thinkRegex.lastIndex;
  }

  const remaining = text.slice(lastIndex);
  if (remaining) html += formatMarkdown(remaining);
  bubble.innerHTML = html || '&nbsp;';
}

function formatMarkdown(text) {
  let s = escapeHtml(text);

  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/gi, (_, label, url) => {
    const shown = label === url ? url : label;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${shown}</a>`;
  });

  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');

  let insideLink = false;
  s = s.split(/(<[^>]+>)/).map(part => {
    if (part.startsWith('<')) {
      if (/^<a\b/i.test(part)) insideLink = true;
      if (/^<\/a>/i.test(part)) insideLink = false;
      return part;
    }
    if (insideLink) return part;
    part = part.replace(/(https?:\/\/[^\s<]+)/gi, raw => {
      const url = raw.replace(/[.,;:]+$/, '');
      const tail = raw.slice(url.length);
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${tail}`;
    });
    part = part.replace(
      /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
      email => `<a href="mailto:${email}">${email}</a>`
    );
    part = part.replace(
      /\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}/g,
      phone => `<a href="tel:${phone.replace(/[^\d+]/g, '')}">${phone}</a>`
    );
    return part;
  }).join('');

  const lines = s.split('\n');
  const out = [];
  let list = null;

  const closeList = () => {
    if (!list) return;
    out.push(list === 'ul' ? '</ul>' : '</ol>');
    list = null;
  };

  for (const line of lines) {
    const ul = line.match(/^[-*] (.+)$/);
    const ol = line.match(/^\d+\. (.+)$/);
    if (ul) {
      if (list !== 'ul') {
        closeList();
        out.push('<ul>');
        list = 'ul';
      }
      out.push(`<li>${ul[1]}</li>`);
    } else if (ol) {
      if (list !== 'ol') {
        closeList();
        out.push('<ol>');
        list = 'ol';
      }
      out.push(`<li>${ol[1]}</li>`);
    } else {
      closeList();
      out.push(line === '' ? '<br>' : `${line}<br>`);
    }
  }
  closeList();
  return out.join('').replace(/(<br>)+$/g, '');
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
  saveChat();
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
      window.location.href = PREFIX + '/login';
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
          if (json.error) {
            throw new Error(json.error);
          }
          if (json.message?.content) {
            fullResponse += json.message.content;
            renderAIContent(aiBubble, fullResponse);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } catch (parseErr) {
          if (parseErr instanceof SyntaxError) continue; /* partial JSON line */
          throw parseErr;
        }
      }
    }

    if (!fullResponse) {
      throw new Error('The model returned an empty response.');
    }

    conversationHistory.push({ role: 'assistant', content: fullResponse });
    saveChat();

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

restoreChat();
