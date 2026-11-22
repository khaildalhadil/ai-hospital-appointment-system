// AI assistant widget: sends messages to /chat and renders replies (textContent only, never innerHTML).
const $ = (id) => document.getElementById(id);
const panel = $('chat'), log = $('chat-log'), input = $('chat-input'), toggle = $('chat-toggle');

function add(text, who, slots = []) {
  const msg = document.createElement('div');
  msg.className = `msg ${who}`;
  msg.textContent = text;
  for (const s of slots) {
    const a = document.createElement('a');
    a.className = 'slot-link';
    a.href = s.url;
    a.textContent = `${s.doctor} · ${s.label}`;
    msg.append(a);
  }
  log.append(msg);
  log.scrollTop = log.scrollHeight;
}

function openChat() {
  panel.hidden = false;
  toggle.setAttribute('aria-expanded', 'true');
  if (!log.children.length) add("Hi! I'm the AI patient assistant. Describe your symptoms or ask about appointments, hours or contact details.", 'bot');
  input.focus();
}

async function send(text) {
  openChat();
  add(text, 'me');
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    add(data.reply, 'bot', data.slots);
  } catch {
    add('Sorry, I could not reach the server. Please try again.', 'bot');
  }
}

toggle.addEventListener('click', () => (panel.hidden ? openChat() : (panel.hidden = true, toggle.setAttribute('aria-expanded', 'false'))));
$('chat-close').addEventListener('click', () => { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); });
$('chat-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (text) { input.value = ''; send(text); }
});
document.querySelectorAll('[data-ask]').forEach((b) => b.addEventListener('click', () => send(b.dataset.ask)));
document.querySelectorAll('[data-open-chat]').forEach((b) => b.addEventListener('click', openChat));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) $('chat-close').click(); });
