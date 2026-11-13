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
  showPrintBox: false,
  printers: [],
};
function canSubmitNow() {
  return Boolean(
    state.isReadyToDraft &&
      state.intent &&
      (!state.latestRequest || ['FAILED', 'REJECTED'].includes(state.latestRequest.status))
  );
}
function appendBubble(text, sender = 'assistant') {
  const div = document.createElement('div');
  div.className = `bubble ${sender}`;
  div.textContent = text;
  $('messages-box').appendChild(div);
  $('messages-box').scrollTop = $('messages-box').scrollHeight;
}
function renderActionBar(options = []) {
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
    btn.textContent = opt.label;
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
      state.showPrintBox = false;
      renderActionBar(options);
    };
    row.appendChild(emailBtn);
    const printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.className = 'chip-btn dark-chip';
    printBtn.textContent = 'Cetak ke Printer';
    printBtn.onclick = async () => {
      state.showPrintBox = !state.showPrintBox;
      state.showEmailBox = false;
      if (state.showPrintBox) {
        try {
          state.printers = await window.asuraAPI.printer.list();
        } catch {
          state.printers = [];
        }
      }
      renderActionBar(options);
    };
    row.appendChild(printBtn);
  }
  bar.appendChild(row);
  // Panel Kirim Email Inline (Pengganti window.prompt yang diblokir Electron)
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
  // Panel Pilih Printer Fisik Windows & Cetak Langsung
  if (state.showPrintBox && state.latestRequest) {
    const box = document.createElement('div');
    box.style.marginTop = '8px';
    box.style.padding = '8px';
    box.style.background = '#ffffff';
    box.style.border = '1px solid #eadfd7';
    box.style.borderRadius = '12px';
    box.style.display = 'flex';
    box.style.gap = '6px';
    const sel = document.createElement('select');
    sel.style.flex = '1';
    sel.style.padding = '6px 8px';
    sel.style.fontSize = '11.5px';
    sel.style.border = '1px solid #eadfd7';
    sel.style.borderRadius = '8px';
    sel.style.background = '#fffdfa';
    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = 'Dialog Printer Windows (Pilih Printer)';
    sel.appendChild(defaultOpt);
    (state.printers || []).forEach((p) => {
      const isVirtualPdf = /pdf|xps|onenote|fax/i.test(p.name || '');
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = isVirtualPdf ? `${p.displayName || p.name} (Virtual)` : `${p.displayName || p.name} (Printer)`;
      if (!isVirtualPdf && p.isDefault) opt.selected = true;
      sel.appendChild(opt);
    });
    const goPrintBtn = document.createElement('button');
    goPrintBtn.type = 'button';
    goPrintBtn.className = 'chip-btn dark-chip';
    goPrintBtn.textContent = 'Print';
    goPrintBtn.onclick = async () => {
      goPrintBtn.disabled = true;
      goPrintBtn.textContent = '...';
      await printApprovedSurat(state.latestRequest.id, sel.value);
    };
    box.appendChild(sel);
    box.appendChild(goPrintBtn);
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
        $('history-drawer').hidden = true;
        await refreshThreadState();
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
  state.showPrintBox = false;
  try {
    const res = await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: '/api/surat/chat/init/',
      body: { title: 'Permohonan Surat (Desktop)' },
    });
    state.threadId = res.thread_id;
    appendBubble(
      'Halo! Saya ASURA. Ceritakan surat akademik yang ingin kamu buat, lalu saya akan meneruskannya ke dosen untuk di-ACC.'
    );
  } catch (err) {
    appendBubble(`Gagal terhubung ke server ASURA: ${err.message}`);
  }
}
async function refreshThreadState() {
  if (!state.threadId) return;
  try {
    const detail = await window.asuraAPI.api.call({
      method: 'GET',
      endpoint: `/api/surat/chat/${state.threadId}/`,
    });
    $('messages-box').innerHTML = '';
    (detail.messages || []).forEach((m) => appendBubble(m.text, m.sender));
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
        title: 'Surat Di-ACC Dosen!',
        body: `${state.latestRequest.nama_surat} sudah disetujui. Pilih Kirim ke Email atau Cetak ke Printer.`,
      });
    }
    state.lastKnownStatus = newStatus;
    renderActionBar(detail.action_options || []);
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
  appendBubble(clean, 'user');
  $('chat-input').value = '';
  $('btn-send').disabled = true;
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: `/api/surat/chat/${state.threadId}/`,
      body: { message: clean },
    });
    await refreshThreadState();
  } catch (err) {
    appendBubble(`Terjadi kendala: ${err.message}`);
  } finally {
    $('btn-send').disabled = false;
  }
}
async function submitSuratToLecturer() {
  if (!state.intent || !state.threadId) return;
  $('action-bar').innerHTML = '';
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
    await refreshThreadState();
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
    await refreshThreadState();
  } catch (err) {
    state.showEmailBox = false;
    renderActionBar();
    appendBubble(`Gagal mengirim email: ${err.message}`);
  }
}
async function printApprovedSurat(requestId, deviceName = '') {
  try {
    await window.asuraAPI.api.call({
      method: 'POST',
      endpoint: `/api/surat/requests/${requestId}/mark-printed/`,
      body: {},
    });
    await window.asuraAPI.printer.printRequest({ requestId, deviceName });
    state.showPrintBox = false;
    await refreshThreadState();
  } catch (err) {
    state.showPrintBox = false;
    renderActionBar();
    appendBubble(`Gagal mencetak ke printer: ${err.message}`);
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
      void refreshThreadState();
    }
  }, 2500);
});
