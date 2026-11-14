const $ = (id) => document.getElementById(id);
const SUBMIT_TRIGGER_PHRASES = new Set([
  'ajukan',
  'ajukan surat',
  'ajukan ulang',
  'ajukan sekarang',
  'kirim ke dosen',
  'lanjut',
  'submit',
]);
const state = {
  user: null,
  threadId: null,
  intent: null,
  slots: {},
  isReadyToDraft: false,
  latestRequest: null,
  lastKnownStatus: null,
  pollTimer: null,
  showEmailBox: false,
  isPrinting: false,
  lastMessagesSig: '',
  lastActionSig: '',
};
function canSubmitNow() {
  return Boolean(
    state.isReadyToDraft &&
      state.intent &&
      (!state.latestRequest || ['FAILED', 'REJECTED'].includes(state.latestRequest.status))
  );
}
function stripEmojiText(str) {
  return String(str || '')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F]/gu, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}
function formatRichBubbleHtml(rawText) {
  const cleanedRaw = stripEmojiText(rawText);
  const escaped = cleanedRaw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return '<div style="height:6px;"></div>';
      let formatted = line
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
        .replace(
          /`([^`\n]+?)`/g,
          '<code style="background:#fbf5f0;border:1px solid #eadfd7;padding:1px 5px;border-radius:5px;font-family:monospace;font-size:11px;color:#b85328;">$1</code>'
        )
        .replace(/\*\*/g, '')
        .replace(/`/g, '');
      if (/^[-•]\s+/.test(trimmed)) {
        formatted = formatted.replace(
          /^\s*[-•]\s+/,
          '<span style="color:#d76b3e;font-weight:bold;margin-right:5px;">•</span>'
        );
        return `<div style="padding-left:4px;margin:2px 0;">${formatted}</div>`;
      }
      return `<div style="margin:2px 0;">${formatted}</div>`;
    })
    .join('');
}
function appendBubble(text, sender = 'assistant') {
  const div = document.createElement('div');
  div.className = `bubble ${sender}`;
  div.style.animation = 'none';
  div.style.transition = 'none';
  div.innerHTML = formatRichBubbleHtml(text);
  $('messages-box').appendChild(div);
  $('messages-box').scrollTop = $('messages-box').scrollHeight;
}
function renderActionBar(options = [], force = false) {
  const actionSig = JSON.stringify({
    options,
    canSubmit: canSubmitNow(),
    reqId: state.latestRequest?.id || null,
    reqStatus: state.latestRequest?.status || null,
    showEmailBox: state.showEmailBox,
    isPrinting: state.isPrinting,
  });
  if (!force && actionSig === state.lastActionSig) {
    return;
  }
  state.lastActionSig = actionSig;
  const bar = $('action-bar');
  bar.innerHTML = '';
  bar.style.flexDirection = 'column';
  bar.style.alignItems = 'stretch';
  const row = document.createElement('div');
  row.style.display = 'flex';
  row.style.flexWrap = 'wrap';
  row.style.gap = '6px';
  options.forEach((opt) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip-btn';
    btn.textContent = stripEmojiText(opt.label);
    btn.onclick = () => void sendMessage(opt.value);
    row.appendChild(btn);
  });
  if (canSubmitNow()) {
    const submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'chip-btn primary-chip';
    submitBtn.textContent = 'Ajukan Surat ke Dosen';
    submitBtn.onclick = () => void submitSuratToLecturer();
    row.appendChild(submitBtn);
  }
  if (state.latestRequest && ['APPROVED', 'SENT', 'PRINTED'].includes(state.latestRequest.status)) {
    const emailBtn = document.createElement('button');
    emailBtn.type = 'button';
    emailBtn.className = 'chip-btn primary-chip';
    emailBtn.textContent = 'Kirim ke Email';
    emailBtn.onclick = () => {
      state.showEmailBox = !state.showEmailBox;
      renderActionBar(options, true);
    };
    row.appendChild(emailBtn);
    const printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.className = 'chip-btn dark-chip';
    printBtn.disabled = state.isPrinting;
    printBtn.textContent = state.isPrinting ? 'Mencetak Otomatis...' : 'Cetak ke Printer';
    printBtn.onclick = () => void printApprovedSurat(state.latestRequest.id);
    row.appendChild(printBtn);
  }
  bar.appendChild(row);
  if (state.showEmailBox && state.latestRequest) {
    const box = document.createElement('div');
    box.style.marginTop = '8px';
    box.style.padding = '8px';
    box.style.background = '#ffffff';
    box.style.border = '1px solid #eadfd7';
    box.style.borderRadius = '12px';
    box.style.display = 'flex';
    box.style.gap = '6px';
    const inp = document.createElement('input');
    inp.type = 'email';
    inp.placeholder = 'Masukkan email tujuan...';
    inp.value = state.latestRequest.target_destination_address || state.user?.email || '';
    inp.style.flex = '1';
    inp.style.padding = '6px 9px';
    inp.style.fontSize = '11.5px';
    inp.style.border = '1px solid #eadfd7';
    inp.style.borderRadius = '8px';
    const sendBtn = document.createElement('button');
    sendBtn.type = 'button';
    sendBtn.className = 'chip-btn primary-chip';
    sendBtn.textContent = 'Kirim';
    sendBtn.onclick = async () => {
      const target = inp.value.trim();
      if (!target) return;
      sendBtn.disabled = true;
      sendBtn.textContent = '...';
      await sendEmailInline(state.latestRequest.id, target);
    };
    box.appendChild(inp);
    box.appendChild(sendBtn);
    bar.appendChild(box);
  }
}
async function loadHistoryList() {
  try {
    const threads = await window.asuraAPI.api.call({
      method: 'GET',
      endpoint: '/api/surat/chat/threads/',
    });
    const listEl = $('history-list');
    listEl.innerHTML = '';
    if (!Array.isArray(threads) || threads.length === 0) {
      listEl.innerHTML = '<div style="font-size:11px;color:#857870;">Belum ada riwayat chat.</div>';
      return;
    }
    threads.forEach((t) => {
      const row = document.createElement('div');
      row.className = `history-item ${t.thread_id === state.threadId ? 'active' : ''}`;
      const openBtn = document.createElement('button');
      openBtn.type = 'button';
      openBtn.className = 'history-open-btn';
      openBtn.textContent = t.title || 'Permohonan Surat Baru';
      openBtn.onclick = async () => {
        state.threadId = t.thread_id;
        state.lastMessagesSig = '';
        state.lastActionSig = '';
        $('history-drawer').hidden = true;
        await refreshThreadState(true);
      };
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'history-del-btn';
      delBtn.textContent = '×';
      delBtn.title = 'Hapus riwayat';
      delBtn.onclick = async (e) => {
        e.stopPropagation();
        await window.asuraAPI.api.call({
          method: 'DELETE',
          endpoint: `/api/surat/chat/${t.thread_id}/`,
        });
        if (state.threadId === t.thread_id) {
          await initNewThread();
        }
        await loadHistoryList();
      };
      row.appendChild(openBtn);
      row.appendChild(delBtn);
      listEl.appendChild(row);
    });
  } catch {}
}
async function openPopup() {
  $('mascot-btn').hidden = true;
  $('popup-panel').hidden = false;
  await window.asuraAPI.window.setMode(true);
}
async function closePopup() {
  $('popup-panel').hidden = true;
  $('mascot-btn').hidden = false;
  await window.asuraAPI.window.closePopup();
}
function applyAuthState(user) {
  state.user = user;
  const loggedIn = Boolean(user);
  $('view-login').hidden = loggedIn;
  $('view-chat').hidden = !loggedIn;
  $('btn-history').hidden = !loggedIn;
  $('btn-new-chat').hidden = !loggedIn;
  $('btn-logout').hidden = !loggedIn;
  if (loggedIn) {
    $('user-banner').textContent = `${user.nama} (${user.nip_nim})`;
    if (!state.threadId) {
      void initNewThread();
    }
  } else {
    state.threadId = null;
    state.intent = null;
    state.slots = {};
    state.isReadyToDraft = false;
    state.latestRequest = null;
    state.lastKnownStatus = null;
    state.lastMessagesSig = '';
    state.lastActionSig = '';
    $('messages-box').innerHTML = '';
    $('action-bar').innerHTML = '';
  }
}
async function initNewThread() {
  $('messages-box').innerHTML = '';
  $('action-bar').innerHTML = '';
  $('history-drawer').hidden = true;
  state.intent = null;
  state.slots = {};
  state.isReadyToDraft = false;
  state.latestRequest = null;
  state.lastKnownStatus = null;
  state.showEmailBox = false;
  state.isPrinting = false;
  state.lastMessagesSig = '';
  state.lastActionSig = '';
  try {
    const res = await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: '/api/surat/chat/init/',
      body: { title: 'Permohonan Surat (Desktop)' },
    });
    state.threadId = res.thread_id;
    appendBubble(
      'Halo, saya ASURA. Sebutkan surat akademik yang ingin kamu buat (termasuk surat custom), lalu saya bantu susun dan teruskan ke dosen untuk ACC.'
    );
    state.lastMessagesSig = 'init';
  } catch (err) {
    appendBubble(`Gagal terhubung ke server ASURA: ${err.message}`);
  }
}
async function refreshThreadState(forceRender = false) {
  if (!state.threadId) return;
  try {
    const detail = await window.asuraAPI.api.call({
      method: 'GET',
      endpoint: `/api/surat/chat/${state.threadId}/`,
    });
    const msgs = detail.messages || [];
    const newMsgSig = msgs.map((m) => `${m.sender}:${m.text}`).join('||');
    if (forceRender || newMsgSig !== state.lastMessagesSig) {
      state.lastMessagesSig = newMsgSig;
      $('messages-box').innerHTML = '';
      msgs.forEach((m) => appendBubble(m.text, m.sender));
    }
    state.intent = detail.kode_surat || detail.intent || null;
    state.slots = detail.collected_slots || {};
    state.isReadyToDraft = Boolean(detail.is_ready_to_draft);
    state.latestRequest = detail.latest_surat_request || null;
    const newStatus = state.latestRequest?.status || null;
    if (
      newStatus === 'APPROVED' &&
      state.lastKnownStatus &&
      state.lastKnownStatus !== 'APPROVED'
    ) {
      await window.asuraAPI.notifications.show({
        title: 'Surat Di-ACC Dosen',
        body: `${state.latestRequest.nama_surat} sudah disetujui. Pilih Kirim ke Email atau Cetak ke Printer.`,
      });
    }
    state.lastKnownStatus = newStatus;
    renderActionBar(detail.action_options || [], forceRender);
  } catch {}
}
async function sendMessage(text) {
  const clean = String(text || '').trim();
  if (!clean) return;
  if (!state.threadId) await initNewThread();
  if (canSubmitNow() && SUBMIT_TRIGGER_PHRASES.has(clean.toLowerCase())) {
    $('chat-input').value = '';
    await submitSuratToLecturer();
    return;
  }
  state.lastMessagesSig = '';
  appendBubble(clean, 'user');
  $('chat-input').value = '';
  $('btn-send').disabled = true;
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: `/api/surat/chat/${state.threadId}/`,
      body: { message: clean },
    });
    await refreshThreadState(true);
  } catch (err) {
    appendBubble(`Terjadi kendala: ${err.message}`);
  } finally {
    $('btn-send').disabled = false;
  }
}
async function submitSuratToLecturer() {
  if (!state.intent || !state.threadId) return;
  $('action-bar').innerHTML = '';
  state.lastActionSig = '';
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: '/api/surat/request/',
      body: {
        kode_surat: state.intent,
        user_prompt_context: `Permohonan ${state.intent} via ASURA Desktop`,
        payload_data: state.slots,
        thread_id: state.threadId,
      },
    });
    await refreshThreadState(true);
  } catch (err) {
    appendBubble(`Gagal mengajukan surat: ${err.message}`);
  }
}
async function sendEmailInline(requestId, targetEmail) {
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: `/api/surat/requests/${requestId}/deliver-email/`,
      body: { recipient_email: targetEmail },
    });
    state.showEmailBox = false;
    await refreshThreadState(true);
  } catch (err) {
    state.showEmailBox = false;
    renderActionBar([], true);
    appendBubble(`Gagal mengirim email: ${err.message}`);
  }
}
async function printApprovedSurat(requestId) {
  if (state.isPrinting) return;
  state.isPrinting = true;
  renderActionBar([], true);
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: `/api/surat/requests/${requestId}/mark-printed/`,
      body: {},
    });
    const printRes = await window.asuraAPI.printer.printRequest({ requestId, deviceName: '' });
    await refreshThreadState(true);
    appendBubble(`ASURA mencetak surat ke: ${printRes?.deviceName || 'Printer Default'}.`);
  } catch (err) {
    appendBubble(`Gagal mencetak otomatis: ${err.message}`);
  } finally {
    state.isPrinting = false;
    renderActionBar([], true);
  }
}
document.addEventListener('DOMContentLoaded', async () => {
  $('mascot-btn').addEventListener('click', () => void openPopup());
  $('btn-close').addEventListener('click', () => void closePopup());
  $('btn-new-chat').addEventListener('click', () => void initNewThread());
  $('btn-history').addEventListener('click', async () => {
    const drawer = $('history-drawer');
    drawer.hidden = !drawer.hidden;
    if (!drawer.hidden) {
      await loadHistoryList();
    }
  });
  $('btn-fill-demo').addEventListener('click', () => {
    $('input-nim').value = 'INF24001';
    $('input-pass').value = '12345678';
  });
  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('login-error').hidden = true;
    $('btn-login-submit').disabled = true;
    try {
      const user = await window.asuraAPI.auth.login({
        nip_nim: $('input-nim').value.trim(),
        password: $('input-pass').value,
      });
      applyAuthState(user);
    } catch (err) {
      $('login-error').textContent = err.message || 'Login gagal.';
      $('login-error').hidden = false;
    } finally {
      $('btn-login-submit').disabled = false;
    }
  });
  $('btn-logout').addEventListener('click', async () => {
    await window.asuraAPI.auth.logout();
    applyAuthState(null);
  });
  $('chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    void sendMessage($('chat-input').value);
  });
  $('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendMessage($('chat-input').value);
    }
  });
  const savedUser = await window.asuraAPI.auth.getUser();
  applyAuthState(savedUser);
  state.pollTimer = window.setInterval(() => {
    if (
      state.user &&
      state.threadId &&
      state.latestRequest &&
      !['SENT', 'PRINTED'].includes(state.latestRequest.status)
    ) {
      void refreshThreadState(false);
    }
  }, 3000);
});
