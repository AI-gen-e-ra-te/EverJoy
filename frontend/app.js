/* DigiPeople Core — Chat UI */

const API = 'http://localhost:8002';

let avatarId = null;
let sending = false;
let rendererTs = null;
let rendererTimer = null;

// ── Bootstrap ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  bindUpload();
  bindChat();
  bindMic();
  document.getElementById('btn-health').addEventListener('click', refreshHealth);
  refreshHealth();
  startRendererPolling();
});

// ── Upload ─────────────────────────────────────────────────
function bindUpload() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = 'var(--c-primary)'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor = ''; });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.style.borderColor = '';
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => { if (input.files[0]) handleFile(input.files[0]); });
}

async function handleFile(file) {
  if (file.type !== 'video/mp4') { toast('请选择 MP4 视频文件', 'warning'); return; }

  const zone = document.getElementById('upload-zone');
  zone.classList.add('has-file');
  zone.innerHTML = `<i class="fas fa-check-circle"></i><p>${file.name} (${(file.size/1048576).toFixed(1)} MB)</p>`;

  toast('正在上传...');
  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('avatar_name', `Avatar_${Date.now()}`);
    const res = await fetch(`${API}/api/avatars/upload`, { method:'POST', body:fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.status);
    const data = await res.json();
    avatarId = data.avatar_id;
    toast('上传成功，正在预处理...', 'success');
    pollTask(data.task_id);
    setRendererAvatar(avatarId);
  } catch(e) {
    toast('上传失败: ' + e.message, 'error');
    zone.classList.remove('has-file');
    zone.innerHTML = `<i class="fas fa-cloud-upload-alt"></i><p>拖放或点击上传 MP4</p>`;
  }
}

async function pollTask(taskId) {
  const poll = async () => {
    try {
      const res = await fetch(`${API}/api/tasks/${taskId}/status`);
      if (!res.ok) return;
      const d = await res.json();
      if (d.status === 'completed') {
        toast('头像预处理完成', 'success');
        showAvatarInfo();
        updateChatHint('头像就绪，可以开始对话');
        return;
      }
      if (d.status === 'failed') { toast('预处理失败: ' + (d.error_message||''), 'error'); return; }
      setTimeout(poll, 2000);
    } catch(e) { setTimeout(poll, 3000); }
  };
  poll();
}

async function showAvatarInfo() {
  if (!avatarId) return;
  try {
    const res = await fetch(`${API}/api/avatars/${avatarId}/info`);
    if (!res.ok) return;
    const d = await res.json();
    const info = d.info || {};
    const sec = document.getElementById('avatar-section');
    sec.style.display = '';
    document.getElementById('avatar-name').textContent = avatarId.substring(0,20);
    document.getElementById('avatar-status').textContent = info.status || 'ready';
    const thumb = document.getElementById('avatar-thumb');
    if (info.metadata?.first_frame) {
      thumb.src = `${API}/files/avatars/${avatarId}/first_frame.png`;
    }
  } catch(e) { /* ignore */ }
}

async function setRendererAvatar(id) {
  try {
    await fetch(`${API}/api/renderer/set-default-avatar`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({avatar_id: id})
    });
  } catch(e) { /* ignore */ }
}

function updateChatHint(text) {
  const el = document.getElementById('chat-hint');
  if (el) el.textContent = text;
}

// ── Chat ───────────────────────────────────────────────────
function bindChat() {
  const input = document.getElementById('msg-input');
  const sendBtn = document.getElementById('btn-send');

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  input.addEventListener('input', autoResize);
}

function autoResize() {
  const ta = document.getElementById('msg-input');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
}

async function sendMessage() {
  if (sending) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  autoResize();
  sending = true;
  document.getElementById('btn-send').disabled = true;

  addMessage('user', text);

  const botId = addMessage('bot', '', true);

  let streamOk = false;
  try {
    streamOk = await streamReply(text, botId);
  } catch(e) {
    console.warn('SSE stream failed, falling back:', e);
  }

  if (!streamOk) {
    updateBubble(botId, '');
    await fallbackReply(text, botId);
  }

  sending = false;
  document.getElementById('btn-send').disabled = false;
}

// ── SSE streaming ──────────────────────────────────────────
async function streamReply(text, bubbleId) {
  const res = await fetch(`${API}/api/conversations/reply-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, username: 'User', avatar_id: avatarId || null })
  });

  if (!res.ok) return false;
  if (!res.body) return false;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let fullText = '';
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const payload = JSON.parse(line.slice(6));
        if (payload.error) {
          updateBubble(bubbleId, fullText + '\n[Error] ' + payload.error);
          return true;
        }
        if (payload.done) {
          hideTyping(bubbleId);
          return true;
        }
        if (payload.chunk) {
          fullText += payload.chunk;
          updateBubble(bubbleId, fullText);
        }
        if (payload.audio_url) {
          appendMedia(bubbleId, 'audio', payload.audio_url);
        }
        if (payload.video_generating) {
          toast('MuseTalk 视频生成中，请稍候...', 'info');
        }
      } catch(e) { /* skip bad JSON */ }
    }
  }

  if (fullText) { hideTyping(bubbleId); return true; }
  return false;
}

// ── Fallback non-stream ────────────────────────────────────
async function fallbackReply(text, bubbleId) {
  try {
    const res = await fetch(`${API}/api/conversations/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, username: 'User', avatar_id: avatarId || null })
    });

    if (!res.ok) {
      updateBubble(bubbleId, '请求失败，请检查后端服务');
      return;
    }

    const data = await res.json();
    const reply = data.reply || '(空回复)';
    updateBubble(bubbleId, reply);
    hideTyping(bubbleId);

    if (data.audio_url) {
      appendMedia(bubbleId, 'audio', data.audio_url);
    }
    if (data.video_url) {
      appendMedia(bubbleId, 'video', data.video_url);
      playVideo(`${API}${data.video_url}`);
    }
  } catch(e) {
    updateBubble(bubbleId, '网络错误: ' + e.message);
  }
}

// ── Message DOM helpers ────────────────────────────────────
let msgCounter = 0;

function addMessage(role, text, typing) {
  const id = 'msg-' + (++msgCounter);
  const list = document.getElementById('messages');

  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.id = id;

  const now = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});

  if (role === 'user') {
    div.innerHTML = `
      <div class="msg-avatar"><i class="fas fa-user"></i></div>
      <div class="msg-body">
        <div class="msg-bubble">${esc(text)}</div>
        <div class="msg-time">${now}</div>
      </div>`;
  } else {
    const content = typing
      ? '<div class="typing-dots"><span></span><span></span><span></span></div>'
      : esc(text);
    div.innerHTML = `
      <div class="msg-avatar"><i class="fas fa-robot"></i></div>
      <div class="msg-body">
        <div class="msg-bubble" data-bubble>${content}</div>
        <div class="msg-media" data-media></div>
        <div class="msg-time">${now}</div>
      </div>`;
  }

  list.appendChild(div);
  scrollBottom();
  return id;
}

function updateBubble(id, text) {
  const el = document.querySelector(`#${id} [data-bubble]`);
  if (el) { el.textContent = text; scrollBottom(); }
}

function hideTyping(id) {
  const el = document.querySelector(`#${id} .typing-dots`);
  if (el) el.remove();
}

function appendMedia(id, type, url) {
  const container = document.querySelector(`#${id} [data-media]`);
  if (!container) return;

  const fullUrl = `${API}${url}`;
  const badge = document.createElement('span');
  badge.className = 'badge';

  if (type === 'audio') {
    badge.innerHTML = `<i class="fas fa-volume-up"></i> 播放音频`;
    badge.onclick = () => new Audio(fullUrl).play();
  } else {
    badge.innerHTML = `<i class="fas fa-play-circle"></i> 播放视频`;
    badge.onclick = () => playVideo(fullUrl);
  }
  container.appendChild(badge);
}

function scrollBottom() {
  const el = document.getElementById('messages');
  requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Video ──────────────────────────────────────────────────
function playVideo(url) {
  const ph = document.getElementById('video-placeholder');
  const vid = document.getElementById('output-video');
  if (ph) ph.style.display = 'none';
  vid.style.display = 'block';
  vid.src = url;
  vid.load();
  vid.play().catch(() => { vid.controls = true; });
}

// ── Renderer polling ───────────────────────────────────────
function startRendererPolling() {
  if (rendererTimer) clearInterval(rendererTimer);
  rendererTimer = setInterval(pollRenderer, 3000);
}

async function pollRenderer() {
  try {
    const res = await fetch(`${API}/api/renderer/latest`);
    if (!res.ok) return;
    const d = await res.json();
    if (!d.has_result) return;
    const r = d.result;
    if (r.timestamp === rendererTs) return;
    rendererTs = r.timestamp;
    updateRenderInfo(r);

    if (r.status === 'completed' && r.video_url) {
      playVideo(`${API}${r.video_url}`);
      addMessage('bot', `[Fay WS] ${r.text || '视频已生成'}`);
      appendMedia('msg-' + msgCounter, 'video', r.video_url);
    }
  } catch(e) { /* silent */ }
}

function updateRenderInfo(r) {
  const box = document.getElementById('render-info');
  const statusCls = r.status === 'completed' ? 'ok' : r.status === 'failed' ? 'fail' : 'skip';
  const statusTxt = r.status === 'completed' ? '完成' : r.status === 'failed' ? '失败' : r.status;
  const time = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '--';
  const dur = r.duration ? r.duration.toFixed(1) + 's' : '--';

  box.innerHTML = `
    <div class="render-row"><span class="render-label">状态</span><span class="render-val ${statusCls}">${statusTxt}</span></div>
    <div class="render-row"><span class="render-label">时间</span><span class="render-val">${time}</span></div>
    <div class="render-row"><span class="render-label">耗时</span><span class="render-val">${dur}</span></div>
    ${r.error ? `<div class="render-row"><span class="render-label">错误</span><span class="render-val fail">${r.error}</span></div>` : ''}
    ${r.text ? `<div class="render-row"><span class="render-label">文本</span><span class="render-val">${r.text.substring(0,40)}${r.text.length>40?'...':''}</span></div>` : ''}
  `;
}

// ── Health ──────────────────────────────────────────────────
async function refreshHealth() {
  const ids = {
    backend:  { dot:'dot-backend',  val:'st-backend' },
    fay:      { dot:'dot-fay',      val:'st-fay' },
    fayws:    { dot:'dot-fayws',    val:'st-fayws' },
    tts:      { dot:'dot-tts',      val:'st-tts' },
    musetalk: { dot:'dot-musetalk', val:'st-musetalk' },
  };

  function set(key, ok, label) {
    const d = document.getElementById(ids[key].dot);
    const v = document.getElementById(ids[key].val);
    d.className = 'dot ' + (ok ? 'ok' : ok === false ? 'err' : 'warn');
    v.textContent = label;
  }

  try {
    const res = await fetch(`${API}/api/health/`);
    if (!res.ok) throw new Error();
    const d = await res.json();
    const s = d.services || {};

    set('backend', true, 'OK');
    set('fay',      s.fay,         s.fay ? 'OK' : 'N/A');
    set('fayws',    s.renderer_ws, s.renderer_ws ? '已连接' : '未连接');
    set('tts',      s.tts,         s.tts ? 'OK' : 'N/A');
    set('musetalk', s.musetalk,    s.musetalk ? 'OK' : 'N/A');
  } catch(e) {
    set('backend', false, '离线');
    ['fay','fayws','tts','musetalk'].forEach(k => set(k, null, '--'));
  }
}

// ── Microphone (press-and-hold) ─────────────────────────────
let mediaRecorder = null;
let audioChunks = [];
let recording = false;

function bindMic() {
  const btn = document.getElementById('btn-mic');

  const startRec = (e) => { e.preventDefault(); startRecording(); };
  const stopRec  = (e) => { e.preventDefault(); stopRecording(); };

  btn.addEventListener('mousedown',  startRec);
  btn.addEventListener('mouseup',    stopRec);
  btn.addEventListener('mouseleave', stopRec);
  btn.addEventListener('touchstart', startRec);
  btn.addEventListener('touchend',   stopRec);
}

async function startRecording() {
  if (recording || sending) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';

    mediaRecorder = new MediaRecorder(stream, { mimeType });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      if (audioChunks.length) sendVoice();
    };

    mediaRecorder.start();
    recording = true;
    document.getElementById('btn-mic').classList.add('recording');
    toast('正在录音...松开发送', 'info');

  } catch (err) {
    console.error('麦克风访问失败:', err);
    toast('无法访问麦克风，请检查浏览器权限', 'error');
  }
}

function stopRecording() {
  if (!recording || !mediaRecorder) return;
  recording = false;
  document.getElementById('btn-mic').classList.remove('recording');
  if (mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

async function sendVoice() {
  const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
  if (blob.size < 1000) {
    toast('录音过短，请按住久一点', 'warning');
    return;
  }

  sending = true;
  document.getElementById('btn-send').disabled = true;
  document.getElementById('btn-mic').disabled = true;

  const userBubbleId = addMessage('user', '[语音消息]');
  const botBubbleId  = addMessage('bot', '', true);
  toast('语音处理中，请等待 Fay 回复...', 'info');

  try {
    const fd = new FormData();
    fd.append('file', blob, 'voice.webm');
    fd.append('username', 'User');

    const res = await fetch(`${API}/api/voice/oneshot`, { method: 'POST', body: fd });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();

    if (data.question) {
      updateBubble(userBubbleId, data.question);
    } else {
      updateBubble(userBubbleId, '[语音消息] (未识别)');
    }

    if (data.answer) {
      updateBubble(botBubbleId, data.answer);
      hideTyping(botBubbleId);
    } else {
      updateBubble(botBubbleId, data.success ? '(Fay 未返回文字)' : '语音处理失败，请检查 Fay 服务');
      hideTyping(botBubbleId);
    }

    if (data.success) {
      toast('语音处理完成', 'success');
    }

  } catch (err) {
    console.error('语音发送失败:', err);
    updateBubble(botBubbleId, '语音处理失败: ' + err.message);
    hideTyping(botBubbleId);
    toast('语音发送失败: ' + err.message, 'error');
  } finally {
    sending = false;
    document.getElementById('btn-send').disabled = false;
    document.getElementById('btn-mic').disabled = false;
  }
}

// ── Toast ──────────────────────────────────────────────────
function toast(msg, type) {
  type = type || 'info';
  const icons = { success:'check-circle', error:'exclamation-circle', warning:'exclamation-triangle', info:'info-circle' };
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = `<i class="fas fa-${icons[type]}"></i><span>${msg}</span>`;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity .3s';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}
