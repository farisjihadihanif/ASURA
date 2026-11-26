import RichMessageText from '../components/RichMessageText';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Send,
  Paperclip,
  Menu,
  Sparkles,
  CheckCircle2,
  Loader2,
  FileCheck2,
  PanelLeftOpen,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import { extractErrorMessage } from '../services/api';
import StudentSidebar from '../components/StudentSidebar';
import NotificationBell from '../components/NotificationBell';
import SuratActionCard from '../components/SuratActionCard';
import PdfPreviewModal from '../components/PdfPreviewModal';
import type {
  ChatActionOption,
  ChatMessageItem,
  ChatThreadItem,
  NotificationItem,
  SuratRequestDetail,
  SuratType,
} from '../types';
const SUBMIT_TRIGGER_PHRASES = new Set([
  'terbitkan',
  'terbitkan surat',
  'terbitkan ulang',
  'buat dan terbitkan surat',
  'buat & terbitkan surat',
  'buat surat',
  'buat surat custom',
  'ajukan',
  'ajukan surat',
  'ajukan ulang',
  'ajukan sekarang',
  'lanjut',
  'submit',
]);
export const StudentChatPage: React.FC = () => {
  const { user, logout } = useAuth();
  const { threadId } = useParams<{ threadId?: string }>();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [suratTypes, setSuratTypes] = useState<SuratType[]>([]);
  const [threads, setThreads] = useState<ChatThreadItem[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | undefined>(threadId);
  const [threadTitle, setThreadTitle] = useState<string>('Permohonan Surat Baru');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [detectedIntent, setDetectedIntent] = useState<string | null>(null);
  const [collectedSlots, setCollectedSlots] = useState<Record<string, unknown>>({});
  const [isReadyToDraft, setIsReadyToDraft] = useState<boolean>(false);
  const [actionOptions, setActionOptions] = useState<ChatActionOption[]>([]);
  const [latestRequest, setLatestRequest] = useState<SuratRequestDetail | null>(null);
  const [inputText, setInputText] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [previewPdfId, setPreviewPdfId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const canSubmitNow = Boolean(
    isReadyToDraft &&
      detectedIntent &&
      (!latestRequest || ['FAILED', 'REJECTED'].includes(latestRequest.status))
  );
  const loadSidebarData = useCallback(async () => {
    try {
      const [typesList, threadsList] = await Promise.all([
        suratService.getSuratTypes(),
        suratService.getChatThreads(),
      ]);
      setSuratTypes(typesList);
      setThreads(threadsList);
    } catch {
      // Abaikan error sementara
    }
  }, []);
  const loadThreadDetail = useCallback(async (tid: string) => {
    try {
      const detail = await suratService.getChatSession(tid);
      setActiveThreadId(detail.thread_id);
      setThreadTitle(detail.title || 'Permohonan Surat Baru');
      setMessages(detail.messages || []);
      setDetectedIntent(detail.kode_surat || detail.intent || null);
      setCollectedSlots(detail.collected_slots || {});
      setIsReadyToDraft(Boolean(detail.is_ready_to_draft));
      setActionOptions(detail.action_options || []);
      setLatestRequest(detail.latest_surat_request || null);
    } catch {
      // Thread tidak ditemukan
    }
  }, []);
  useEffect(() => {
    void loadSidebarData();
  }, [loadSidebarData]);
  useEffect(() => {
    setActiveThreadId(threadId);
    if (threadId) {
      void loadThreadDetail(threadId);
    } else {
      setThreadTitle('Permohonan Surat Baru');
      setMessages([]);
      setDetectedIntent(null);
      setCollectedSlots({});
      setIsReadyToDraft(false);
      setActionOptions([]);
      setLatestRequest(null);
    }
  }, [threadId, loadThreadDetail]);
  // Sinkron realtime lintas perangkat (web <-> desktop): polling thread aktif, daftar riwayat, dan saat jendela kembali fokus
  useEffect(() => {
    const tick = () => {
      if (document.hidden || sending) return;
      if (activeThreadId) void loadThreadDetail(activeThreadId);
      void loadSidebarData();
    };
    const timer = window.setInterval(tick, 3000);
    window.addEventListener('focus', tick);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', tick);
    };
  }, [activeThreadId, sending, loadThreadDetail, loadSidebarData]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending, latestRequest, canSubmitNow]);
  const handleDeleteThread = async (tid: string) => {
    try {
      await suratService.deleteChatThread(tid);
      await loadSidebarData();
      if (activeThreadId === tid) {
        navigate('/chat');
      }
    } catch {
      // Abaikan
    }
  };

  const handleNewChat = async () => {
    setMobileMenuOpen(false);
    try {
      const initRes = await suratService.initChat('Permohonan Surat Baru');
      await loadSidebarData();
      navigate(`/chat/${initRes.thread_id}`);
    } catch {
      navigate('/chat');
    }
  };
  const handleCreateAndIssueSurat = async () => {
    if (!detectedIntent || !activeThreadId || submittingRequest) return;
    setSubmittingRequest(true);
    try {
      const contextSummary = messages
        .filter((m) => m.sender === 'user')
        .map((m) => m.text)
        .join('\n');
      await suratService.createSuratRequest({
        kode_surat: detectedIntent,
        user_prompt_context: contextSummary || `Permohonan ${detectedIntent}`,
        payload_data: collectedSlots,
        thread_id: activeThreadId,
      });
      await Promise.all([loadThreadDetail(activeThreadId), loadSidebarData()]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-sub-${Date.now()}`,
          sender: 'assistant',
          text: extractErrorMessage(err, 'Gagal memproses dan menerbitkan surat.'),
        },
      ]);
    } finally {
      setSubmittingRequest(false);
    }
  };
  const handleSendMessage = async (overrideText?: string) => {
    const textToSend = (overrideText ?? inputText).trim();
    if (!textToSend && attachments.length === 0) return;
    if (sending) return;
    // Jika data sudah lengkap dan user mengetik kata kunci terbitkan/buat surat, langsung proses
    if (
      canSubmitNow &&
      attachments.length === 0 &&
      SUBMIT_TRIGGER_PHRASES.has(textToSend.toLowerCase())
    ) {
      setInputText('');
      await handleCreateAndIssueSurat();
      return;
    }
    setSending(true);
    setInputText('');
    const currentFiles = [...attachments];
    setAttachments([]);
    let targetThreadId = activeThreadId;
    try {
      if (!targetThreadId) {
        const initRes = await suratService.initChat('Permohonan Surat Baru');
        targetThreadId = initRes.thread_id;
        setActiveThreadId(targetThreadId);
        navigate(`/chat/${targetThreadId}`, { replace: true });
      }
      const optimisticUserMsg: ChatMessageItem = {
        id: `temp-${Date.now()}`,
        sender: 'user',
        text: textToSend || `Mengunggah ${currentFiles.length} berkas lampiran`,
        timestamp: new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, optimisticUserMsg]);
      await suratService.sendChatMessage(targetThreadId, textToSend, currentFiles);
      await Promise.all([loadThreadDetail(targetThreadId), loadSidebarData()]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: extractErrorMessage(err, 'Maaf, pesan gagal diproses oleh ASURA.'),
        },
      ]);
    } finally {
      setSending(false);
    }
  };
  const handleNotificationSelect = async (notif: NotificationItem) => {
    if (notif.surat_request_id) {
      try {
        const detail = await suratService.getSuratRequestDetail(notif.surat_request_id);
        setLatestRequest(detail);
        if (activeThreadId) await loadThreadDetail(activeThreadId);
      } catch {
        // Abaikan
      }
    }
  };
  if (!user) return null;
  return (
    <div className="h-screen flex bg-[#fffdfa] text-[#27211e] overflow-hidden">
      {sidebarOpen && (
        <div className="hidden lg:block h-full shrink-0">
          <StudentSidebar
            user={user}
            suratTypes={suratTypes}
            threads={threads}
            activeThreadId={activeThreadId}
            onNewChat={() => void handleNewChat()}
            onSelectThread={(tid) => navigate(`/chat/${tid}`)}
            onDeleteThread={(tid) => void handleDeleteThread(tid)}
            onPickSuratPrompt={(st) => {
              setInputText(`Saya ingin membuat ${st.nama_surat} (${st.kode_surat}). `);
            }}
            onLogout={() => void logout()}
            onCollapseSidebar={() => setSidebarOpen(false)}
          />
        </div>
      )}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <StudentSidebar
            user={user}
            suratTypes={suratTypes}
            threads={threads}
            activeThreadId={activeThreadId}
            onNewChat={() => void handleNewChat()}
            onSelectThread={(tid) => {
              setMobileMenuOpen(false);
              navigate(`/chat/${tid}`);
            }}
            onDeleteThread={(tid) => void handleDeleteThread(tid)}
            onPickSuratPrompt={(st) => {
              setMobileMenuOpen(false);
              setInputText(`Saya ingin membuat ${st.nama_surat} (${st.kode_surat}). `);
            }}
            onLogout={() => void logout()}
            onCollapseSidebar={() => setMobileMenuOpen(false)}
          />
          <div className="flex-1 bg-[#27211e]/40" onClick={() => setMobileMenuOpen(false)} />
        </div>
      )}
      <div className="flex-1 flex flex-col min-w-0 h-full bg-[#fffdfa]">
        <header className="h-16 px-4 sm:px-6 border-b border-[#eadfd7] flex items-center justify-between shrink-0 bg-[#fffdfa]">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-xl text-[#857870] hover:bg-[#fbf5f0] cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>
            {!sidebarOpen && (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                className="hidden lg:inline-flex p-2 rounded-xl border border-[#eadfd7] bg-[#fbf5f0] text-[#857870] hover:text-[#27211e] cursor-pointer"
                title="Tampilkan sidebar"
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
            )}
            <div className="min-w-0">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870]">
                Percakapan Aktif
              </div>
              <h2 className="text-sm font-bold text-[#27211e] truncate">{threadTitle}</h2>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#857870]">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Online
            </span>
            <NotificationBell onSelectNotification={(n) => void handleNotificationSelect(n)} />
          </div>
        </header>
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          <div className="max-w-3xl mx-auto space-y-5">
            {messages.length === 0 ? (
              <div className="py-14 text-center space-y-5">
                <div className="w-12 h-12 rounded-2xl bg-[#fbf5f0] border border-[#eadfd7] text-[#d76b3e] mx-auto flex items-center justify-center">
                  <Sparkles className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-[#27211e]">
                    Halo, {user.nama.split(' ')[0]}
                  </h3>
                  <p className="text-xs text-[#857870] mt-1.5 max-w-md mx-auto leading-relaxed">
                    Ceritakan surat akademik yang kamu butuhkan. ASURA akan mengumpulkan detail,
                    menyiapkan draf, dan langsung menerbitkan surat kampus secara otomatis tanpa antrean persetujuan dosen.
                    Surat custom (pribadi) juga langsung jadi tanpa kop pejabat. Setelah terbit, kamu siap mengunduh PDF,
                    mengirim ke email, atau mencetak ke printer.
                  </p>
                </div>
                <div className="flex flex-wrap justify-center gap-2 pt-2">
                  {[
                    'Saya ingin membuat Surat Keterangan Masih Kuliah (SK-MK).',
                    'Saya butuh Surat Permohonan Izin Magang (SI-MAG) ke PT Telkom Indonesia.',
                    'Tolong buatkan Surat Rekomendasi Beasiswa Djarum.',
                  ].map((sample) => (
                    <button
                      key={sample}
                      type="button"
                      onClick={() => void handleSendMessage(sample)}
                      className="px-3.5 py-2 rounded-2xl border border-[#eadfd7] bg-[#fbf5f0] hover:bg-white text-xs text-[#27211e] transition cursor-pointer text-left"
                    >
                      {sample}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg) => {
                const isUser = msg.sender === 'user';
                if (isUser) {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-[80%] sm:max-w-[72%] rounded-2xl rounded-br-sm px-4 py-3 bg-[#f3ebe4] text-[#27211e] text-xs sm:text-sm leading-relaxed whitespace-pre-wrap">
                        <RichMessageText text={msg.text} isUser={msg.sender === 'user'} />
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={msg.id} className="flex items-start gap-3 justify-start">
                    <div className="w-7 h-7 rounded-lg bg-[#f7eee8] border border-[#eadfd7] flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-3.5 h-3.5 text-[#d76b3e]" />
                    </div>
                    <div className="max-w-[85%] text-[#27211e] text-xs sm:text-sm leading-relaxed whitespace-pre-wrap pt-1">
                      <RichMessageText text={msg.text} isUser={msg.sender === 'user'} />
                    </div>
                  </div>
                );
              })
            )}
            {actionOptions.length > 0 && (
              <div className="flex flex-wrap gap-2 pl-10">
                {actionOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => void handleSendMessage(opt.value)}
                    className="px-3.5 py-2 rounded-xl bg-[#fbf5f0] border border-[#eadfd7] text-[#d76b3e] hover:bg-white text-xs font-semibold transition cursor-pointer"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
            {/* Tombol Buat & Terbitkan Surat */}
            {canSubmitNow && (
              <div className="ml-10 rounded-2xl border border-[#eadfd7] bg-[#fbf5f0] p-4 max-w-xl">
                <div className="flex items-center gap-2 text-xs font-bold text-[#27211e]">
                  <FileCheck2 className="w-4 h-4 text-[#d76b3e]" />
                  <span>Data Permohonan Lengkap ({detectedIntent})</span>
                </div>
                <p className="text-xs text-[#857870] mt-1">
                  {String(detectedIntent || '').toUpperCase().startsWith('CUSTOM')
                    ? 'Klik tombol di bawah agar ASURA langsung menyusun suratmu. Surat pribadi ini tidak memakai kop pejabat.'
                    : 'Klik tombol di bawah agar ASURA menyusun draf resmi dan langsung menerbitkan surat Anda secara otomatis.'}
                </p>
                <button
                  type="button"
                  onClick={() => void handleCreateAndIssueSurat()}
                  disabled={submittingRequest}
                  className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#d76b3e] hover:bg-[#c35d32] text-white text-xs font-bold transition cursor-pointer disabled:opacity-60"
                >
                  {submittingRequest ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4" />
                  )}
                  <span>
                    {String(detectedIntent || '').toUpperCase().startsWith('CUSTOM')
                      ? 'Buat Surat Custom'
                      : 'Buat & Terbitkan Surat'}
                  </span>
                </button>
              </div>
            )}
            {/* Kartu Status & Opsi PDF / Email / Print setelah Terbit */}
            {latestRequest && (
              <div className="pl-10">
                <SuratActionCard
                  suratRequest={latestRequest}
                  defaultEmail={user.email || ''}
                  onUpdated={async () => {
                    if (activeThreadId) await loadThreadDetail(activeThreadId);
                  }}
                  onPreviewPdf={(reqId) => setPreviewPdfId(reqId)}
                />
              </div>
            )}
            {sending && (
              <div className="flex items-center gap-2.5 pl-10 text-xs text-[#857870]">
                <Loader2 className="w-4 h-4 animate-spin text-[#d76b3e]" />
                <span>ASURA sedang memproses...</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="px-4 sm:px-8 pt-2 pb-4 bg-[#fffdfa] shrink-0">
          <div className="max-w-3xl mx-auto">
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {attachments.map((file, idx) => (
                  <span
                    key={`${file.name}-${idx}`}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#fbf5f0] border border-[#eadfd7] text-xs text-[#27211e]"
                  >
                    {file.name}
                    <button
                      type="button"
                      onClick={() =>
                        setAttachments((prev) => prev.filter((_, itemIdx) => itemIdx !== idx))
                      }
                      className="text-[#857870] hover:text-rose-600 font-bold cursor-pointer"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSendMessage();
              }}
              className="flex items-center gap-2 rounded-2xl border border-[#eadfd7] bg-white px-4 py-2.5 shadow-2xs focus-within:border-[#d76b3e] transition"
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,image/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) {
                    setAttachments((prev) => [...prev, ...Array.from(e.target.files!)]);
                  }
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                title="Lampirkan dokumen pendukung (PDF / Gambar)"
                className="p-2 rounded-xl text-[#857870] hover:text-[#27211e] hover:bg-[#fbf5f0] transition cursor-pointer"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <textarea
                rows={1}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void handleSendMessage();
                  }
                }}
                placeholder="Ceritakan surat yang ingin kamu buat..."
                className="flex-1 bg-transparent resize-none border-0 text-xs sm:text-sm text-[#27211e] placeholder:text-[#857870] focus:outline-none py-1 max-h-36"
              />
              <button
                type="submit"
                disabled={sending || (!inputText.trim() && attachments.length === 0)}
                className="w-9 h-9 rounded-xl bg-[#f3ebe4] hover:bg-[#d76b3e] text-[#857870] hover:text-white flex items-center justify-center transition cursor-pointer disabled:opacity-40"
                aria-label="Kirim pesan"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
            <p className="text-center text-[10px] text-[#857870] mt-2">
              ASURA dapat membantu mengumpulkan detail, menyiapkan draf, dan meneruskan surat sesuai
              alur persetujuan.
            </p>
          </div>
        </div>
      </div>
      <PdfPreviewModal requestId={previewPdfId} onClose={() => setPreviewPdfId(null)} />
    </div>
  );
};
export default StudentChatPage;




