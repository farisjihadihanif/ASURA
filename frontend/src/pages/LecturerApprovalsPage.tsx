import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  RotateCcw,
  Save,
  BookOpen,
  MessageSquare,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import suratService from "../services/suratService";
import LecturerSidebar, {
  type LecturerSidebarMode,
} from "../components/LecturerSidebar";
import NotificationBell from "../components/NotificationBell";
import PdfPreviewModal from "../components/PdfPreviewModal";
import type {
  AiDraftGroup,
  AiDraftItem,
  AiFeedbackMemoryItem,
  SuratRequestDetail,
  SuratRequestListItem,
} from "../types";

export const LecturerApprovalsPage: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<LecturerSidebarMode>("monitoring");

  // Monitoring & Arsip state
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuratRequestDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [previewPdfId, setPreviewPdfId] = useState<number | null>(null);

  // Draft Surat AI & Calibration state
  const [aiCategories, setAiCategories] = useState<string[]>([]);
  const [aiGroups, setAiGroups] = useState<AiDraftGroup[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedAiDraftId, setSelectedAiDraftId] = useState<number | null>(
    null,
  );
  const [editedDraftText, setEditedDraftText] = useState<string>("");
  const lastInitializedDraftIdRef = React.useRef<number | null>(null);
  const [loadingAiDrafts, setLoadingAiDrafts] = useState<boolean>(false);
  const [submittingFeedback, setSubmittingFeedback] = useState<boolean>(false);
  const [feedbackNotice, setFeedbackNotice] = useState<{
    type: "success" | "info" | "error";
    text: string;
  } | null>(null);

  const [memories, setMemories] = useState<AiFeedbackMemoryItem[]>([]);
  const [loadingMemories, setLoadingMemories] = useState<boolean>(false);
  const [togglingMemoryId, setTogglingMemoryId] = useState<number | null>(null);

  const selectedAiDraft: AiDraftItem | null = useMemo(() => {
    if (!selectedAiDraftId) return null;
    for (const grp of aiGroups) {
      const found = grp.drafts.find((d) => d.id === selectedAiDraftId);
      if (found) return found;
    }
    return null;
  }, [aiGroups, selectedAiDraftId]);

  const loadList = useCallback(async () => {
    try {
      const list = await suratService.getSuratRequests();
      setRequests(list);
      setSelectedId((prev) => {
        if (prev && list.some((item) => item.id === prev)) return prev;
        return list[0]?.id ?? null;
      });
    } catch {
      // Abaikan gangguan sementara
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    setLoadingDetail(true);
    try {
      const data = await suratService.getSuratRequestDetail(id);
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const loadAiDrafts = useCallback(async () => {
    setLoadingAiDrafts(true);
    try {
      const data = await suratService.getAiDrafts();
      const cats = Array.isArray(data.categories) ? data.categories : [];
      const groups = Array.isArray(data.groups) ? data.groups : [];
      setAiCategories(cats);
      setAiGroups(groups);

      const allDrafts = groups.flatMap((g) => g.drafts);
      setSelectedAiDraftId((prev) => {
        if (prev && allDrafts.some((d) => d.id === prev)) return prev;
        return allDrafts[0]?.id ?? null;
      });
    } catch {
      // Abaikan gangguan sementara
    } finally {
      setLoadingAiDrafts(false);
    }
  }, []);

  const loadMemories = useCallback(async (kodeSurat: string) => {
    setLoadingMemories(true);
    try {
      const list = await suratService.getAiFeedbackMemories(kodeSurat);
      setMemories(list);
    } catch {
      setMemories([]);
    } finally {
      setLoadingMemories(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
    const timer = window.setInterval(() => void loadList(), 4000);
    return () => window.clearInterval(timer);
  }, [loadList]);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (mode === "ai_drafts") {
      void loadAiDrafts();
    }
  }, [mode, loadAiDrafts]);

  useEffect(() => {
    if (mode === "ai_drafts" && selectedAiDraft?.kode_surat) {
      void loadMemories(selectedAiDraft.kode_surat);
    }
  }, [mode, selectedAiDraft?.kode_surat, loadMemories]);

  useEffect(() => {
    if (
      selectedAiDraft &&
      lastInitializedDraftIdRef.current !== selectedAiDraft.id
    ) {
      lastInitializedDraftIdRef.current = selectedAiDraft.id;
      setEditedDraftText(
        selectedAiDraft.calibrated_draft || selectedAiDraft.ai_original_draft,
      );
    }
  }, [selectedAiDraft]);

  const handleSelectAiDraft = (draft: AiDraftItem) => {
    lastInitializedDraftIdRef.current = draft.id;
    setSelectedAiDraftId(draft.id);
    setEditedDraftText(draft.calibrated_draft || draft.ai_original_draft);
    setFeedbackNotice(null);
  };

  const handleSubmitCalibration = async () => {
    if (!selectedAiDraft) return;
    if (!editedDraftText.trim()) {
      setFeedbackNotice({
        type: "error",
        text: "Teks draf penyesuaian tidak boleh kosong.",
      });
      return;
    }

    setSubmittingFeedback(true);
    setFeedbackNotice(null);
    try {
      const res = await suratService.submitAiDraftFeedback(
        selectedAiDraft.id,
        editedDraftText,
      );
      setFeedbackNotice({
        type: res.learned ? "success" : "info",
        text: res.message,
      });
      await loadAiDrafts();
      await loadMemories(selectedAiDraft.kode_surat);
    } catch {
      setFeedbackNotice({
        type: "error",
        text: "Gagal menyimpan kalibrasi draf AI. Silakan coba lagi.",
      });
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const handleToggleMemory = async (mem: AiFeedbackMemoryItem) => {
    setTogglingMemoryId(mem.id);
    try {
      const updated = await suratService.toggleAiFeedbackMemory(
        mem.id,
        !mem.is_active,
      );
      setMemories((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item)),
      );
      await loadAiDrafts();
    } catch {
      // Abaikan gangguan sementara
    } finally {
      setTogglingMemoryId(null);
    }
  };

  if (!user) return null;

  return (
    <div className="h-screen flex bg-[#fffdfa] text-[#27211e] overflow-hidden">
      <div className="h-full shrink-0">
        <LecturerSidebar
          user={user}
          mode={mode}
          onChangeMode={(nextMode) => setMode(nextMode)}
          onOpenChatCreator={() => navigate("/chat")}
          requests={requests}
          selectedRequestId={selectedId}
          onSelectRequest={(id) => {
            setMode("monitoring");
            setSelectedId(id);
          }}
          aiCategories={aiCategories}
          selectedCategory={selectedCategory}
          onChangeCategory={(kat) => setSelectedCategory(kat)}
          aiGroups={aiGroups}
          selectedAiDraftId={selectedAiDraftId}
          onSelectAiDraft={handleSelectAiDraft}
          onLogout={() => void logout()}
        />
      </div>

      <div className="flex-1 flex flex-col min-w-0 h-full bg-[#fffdfa]">
        <header className="h-16 px-6 border-b border-[#eadfd7] flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870]">
              {mode === "monitoring"
                ? "Mode Pantau Otomatis (Read-Only)"
                : "Kalibrasi AgentFeedbackMemory (5 Draf Terakhir / Jenis)"}
            </div>
            <h2 className="text-sm font-bold text-[#27211e]">
              {mode === "monitoring"
                ? "Monitoring & Arsip Surat Kampus"
                : "Draft Surat AI & Pelatihan Gaya Bahasa"}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate("/chat")}
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#fbf5f0] border border-[#eadfd7] text-xs font-semibold text-[#27211e] hover:bg-[#f2e8e0] cursor-pointer"
            >
              <MessageSquare className="w-3.5 h-3.5 text-[#d76b3e]" />
              <span>Buat Surat (Chat AI)</span>
            </button>
            <button
              type="button"
              onClick={() =>
                void (mode === "monitoring" ? loadList() : loadAiDrafts())
              }
              className="p-2 rounded-xl text-[#857870] hover:bg-[#fbf5f0] cursor-pointer"
              title="Muat ulang data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <NotificationBell
              onSelectNotification={(n) => {
                if (n.surat_request_id) {
                  setMode("monitoring");
                  setSelectedId(n.surat_request_id);
                }
              }}
            />
          </div>
        </header>

        {mode === "monitoring" ? (
          <div className="flex-1 overflow-y-auto p-6">
            {!selectedId || (!loadingDetail && !detail) ? (
              <div className="h-full flex items-center justify-center text-xs text-[#857870]">
                Pilih surat kampus dari sidebar kiri untuk melihat arsip dan
                dokumen resmi yang diterbitkan otomatis.
              </div>
            ) : loadingDetail || !detail ? (
              <div className="h-full flex items-center justify-center gap-2 text-xs text-[#857870]">
                <Loader2 className="w-4 h-4 animate-spin text-[#d76b3e]" />
                <span>Memuat detail arsip surat...</span>
              </div>
            ) : (
              <div className="max-w-4xl mx-auto space-y-5">
                {/* Info Mode Read-Only */}
                <div className="rounded-xl border border-[#eadfd7] bg-[#fbf5f0]/70 px-4 py-2.5 text-xs text-[#857870]">
                  Surat kampus diterbitkan secara otomatis tanpa antrean
                  persetujuan (ACC) dosen. Halaman ini digunakan untuk memantau
                  status dan membuka arsip surat di prodi/fakultas Anda.
                </div>

                {/* Header Info Surat */}
                <div className="rounded-2xl border border-[#eadfd7] bg-[#fbf5f0] p-5 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-[#d76b3e]">
                      {detail.kode_surat}
                    </span>
                    <h3 className="text-lg font-extrabold text-[#27211e] mt-0.5">
                      {detail.nama_surat}
                    </h3>
                    <p className="text-xs text-[#857870] mt-1">
                      Pemohon:{" "}
                      <strong className="text-[#27211e]">
                        {detail.nama_mahasiswa}
                      </strong>{" "}
                      ({detail.nim_mahasiswa}) — {detail.prodi_mahasiswa},{" "}
                      {detail.fakultas_mahasiswa}
                    </p>
                    {detail.nomor_surat_resmi && (
                      <p className="text-xs font-mono text-emerald-700 mt-1">
                        Nomor Terbit: {detail.nomor_surat_resmi}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-white border border-[#eadfd7] text-[#27211e]">
                      {detail.status}
                    </span>
                    {["APPROVED", "SENT", "PRINTED"].includes(detail.status) && (
                      <button
                        type="button"
                        onClick={() => setPreviewPdfId(detail.id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#27211e] text-white text-xs font-semibold hover:bg-[#3d3430] cursor-pointer"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        Lihat PDF Resmi
                      </button>
                    )}
                  </div>
                </div>

                {/* Atribut Terstruktur */}
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-[#857870] mb-3">
                    Data Atribut Surat
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {Object.entries(detail.payload_data || {}).map(([k, v]) => (
                      <div
                        key={k}
                        className="p-2.5 rounded-xl bg-[#fbf5f0] border border-[#eadfd7]"
                      >
                        <div className="text-[10px] font-bold uppercase text-[#857870]">
                          {k}
                        </div>
                        <div className="text-xs font-semibold text-[#27211e] mt-0.5">
                          {String(v ?? "-")}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Naskah Surat Resmi (Read-Only) */}
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-[#857870]">
                      Naskah Surat Resmi (Terbit Otomatis)
                    </h4>
                    {detail.self_critique_score && (
                      <span className="text-[11px] font-semibold text-emerald-700">
                        Skor Kualitas AI: {detail.self_critique_score}/10
                      </span>
                    )}
                  </div>
                  <textarea
                    rows={10}
                    readOnly
                    value={
                      detail.final_approved_content ||
                      detail.ai_original_draft ||
                      ""
                    }
                    className="w-full rounded-xl border border-[#eadfd7] bg-[#fffdfa] p-3.5 text-sm leading-relaxed text-[#27211e] focus:outline-none"
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6">
            {loadingAiDrafts && !selectedAiDraft ? (
              <div className="h-full flex items-center justify-center gap-2 text-xs text-[#857870]">
                <Loader2 className="w-4 h-4 animate-spin text-[#d76b3e]" />
                <span>Memuat 5 draf AI terakhir per kategori surat...</span>
              </div>
            ) : !selectedAiDraft ? (
              <div className="h-full flex flex-col items-center justify-center text-center gap-2 text-xs text-[#857870]">
                <Sparkles className="w-6 h-6 text-[#d76b3e]" />
                <p>
                  Pilih salah satu dari 5 draf buatan AI terakhir di sidebar
                  kiri untuk menyesuaikan gaya bahasa dan melatih memori AI.
                </p>
              </div>
            ) : (
              <div className="max-w-4xl mx-auto space-y-5">
                {/* Banner Penjelasan Non-Destruktif */}
                <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-900">
                  Penyesuaian di halaman ini melatih{" "}
                  <strong>AgentFeedbackMemory</strong> (aturan gaya bahasa &amp;
                  contoh baku) agar generasi surat AI berikutnya mengikuti
                  ketentuan layanan akademik,{" "}
                  <strong>tanpa mengubah</strong> PDF/nomor surat mahasiswa yang
                  sudah terbit.
                </div>

                {/* Header Info Draf */}
                <div className="rounded-2xl border border-[#eadfd7] bg-[#fbf5f0] p-5 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-[#d76b3e]">
                        {selectedAiDraft.kode_surat}
                      </span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white border border-[#eadfd7] text-[#857870]">
                        {selectedAiDraft.kategori}
                      </span>
                    </div>
                    <h3 className="text-lg font-extrabold text-[#27211e] mt-0.5">
                      {selectedAiDraft.nama_surat}
                    </h3>
                    <p className="text-xs text-[#857870] mt-1">
                      Pemohon:{" "}
                      <strong className="text-[#27211e]">
                        {selectedAiDraft.pemohon_nama}
                      </strong>{" "}
                      ({selectedAiDraft.pemohon_identitas}) —{" "}
                      {selectedAiDraft.prodi_nama},{" "}
                      {selectedAiDraft.fakultas_nama}
                    </p>
                    {selectedAiDraft.nomor_surat_resmi && (
                      <p className="text-xs font-mono text-emerald-700 mt-1">
                        Nomor Terbit: {selectedAiDraft.nomor_surat_resmi}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedAiDraft.self_critique_score && (
                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-white border border-[#eadfd7] text-emerald-700">
                        Skor AI: {selectedAiDraft.self_critique_score}/10
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => setPreviewPdfId(selectedAiDraft.id)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-[#eadfd7] text-[#27211e] text-xs font-semibold hover:bg-[#f2e8e0] cursor-pointer"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      Lihat PDF Asli
                    </button>
                  </div>
                </div>

                {/* Draf Asli Buatan AI (Referensi Read-Only) */}
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-[#857870]">
                    Draf Asli Buatan AI (Referensi Sebelum Penyesuaian)
                  </h4>
                  <textarea
                    rows={7}
                    readOnly
                    value={selectedAiDraft.ai_original_draft}
                    className="w-full rounded-xl border border-[#eadfd7] bg-[#fbf5f0]/50 p-3 text-xs leading-relaxed text-[#5c514b] focus:outline-none"
                  />
                </div>

                {/* Editor Penyesuaian Dosen untuk Melatih AgentFeedbackMemory */}
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[#27211e]">
                        Penyesuaian Draf untuk Pelatihan AI (AgentFeedback)
                      </h4>
                      <p className="text-[11px] text-[#857870]">
                        Sunting redaksi atau struktur agar sesuai standar
                        layanan akademik.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setEditedDraftText(selectedAiDraft.ai_original_draft)
                      }
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[#eadfd7] bg-[#fbf5f0] text-[11px] font-semibold text-[#857870] hover:text-[#27211e] cursor-pointer"
                    >
                      <RotateCcw className="w-3 h-3" />
                      Reset ke Draf Asli AI
                    </button>
                  </div>

                  <textarea
                    rows={10}
                    value={editedDraftText}
                    onChange={(e) => setEditedDraftText(e.target.value)}
                    className="w-full rounded-xl border border-[#eadfd7] bg-[#fffdfa] p-3.5 text-sm leading-relaxed text-[#27211e] focus:border-[#d76b3e] focus:outline-none"
                    placeholder="Sesuaikan isi draf surat sesuai ketentuan layanan akademik..."
                  />

                  {feedbackNotice && (
                    <div
                      className={`rounded-xl px-3.5 py-2.5 text-xs border ${
                        feedbackNotice.type === "success"
                          ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                          : feedbackNotice.type === "error"
                            ? "bg-rose-50 border-rose-200 text-rose-800"
                            : "bg-sky-50 border-sky-200 text-sky-800"
                      }`}
                    >
                      {feedbackNotice.text}
                    </div>
                  )}

                  <div className="flex justify-end">
                    <button
                      type="button"
                      disabled={submittingFeedback}
                      onClick={() => void handleSubmitCalibration()}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#d76b3e] hover:bg-[#c25b30] text-white text-xs font-bold transition cursor-pointer disabled:opacity-50"
                    >
                      {submittingFeedback ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Save className="w-3.5 h-3.5" />
                      )}
                      <span>Simpan &amp; Latih AI (AgentFeedback)</span>
                    </button>
                  </div>
                </div>

                {/* Daftar Aturan AgentFeedbackMemory Aktif / Nonaktif */}
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-[#d76b3e]" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-[#27211e]">
                        Memori Gaya Bahasa AI ({selectedAiDraft.kode_surat})
                      </h4>
                    </div>
                    {loadingMemories && (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-[#857870]" />
                    )}
                  </div>

                  {memories.length === 0 ? (
                    <p className="text-xs text-[#857870] py-2">
                      Belum ada aturan hasil kalibrasi untuk jenis surat ini.
                      Sunting draf di atas untuk mulai melatih AI.
                    </p>
                  ) : (
                    <div className="space-y-2.5">
                      {memories.map((mem) => (
                        <div
                          key={mem.id}
                          className={`rounded-xl border p-3 flex items-start justify-between gap-3 ${
                            mem.is_active
                              ? "bg-[#fbf5f0]/70 border-[#eadfd7]"
                              : "bg-neutral-50 border-neutral-200 opacity-70"
                          }`}
                        >
                          <div className="space-y-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                  mem.is_active
                                    ? "bg-emerald-100 text-emerald-800"
                                    : "bg-neutral-200 text-neutral-700"
                                }`}
                              >
                                {mem.is_active ? "AKTIF" : "NONAKTIF"}
                              </span>
                              <span className="text-[10px] text-[#857870]">
                                {new Date(mem.created_at).toLocaleString("id-ID")}
                              </span>
                            </div>
                            <p className="text-xs font-semibold text-[#27211e]">
                              {mem.extracted_rule}
                            </p>
                            {mem.diff_summary && (
                              <p className="text-[11px] text-[#857870]">
                                {mem.diff_summary}
                              </p>
                            )}
                          </div>
                          <button
                            type="button"
                            disabled={togglingMemoryId === mem.id}
                            onClick={() => void handleToggleMemory(mem)}
                            className={`shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border transition cursor-pointer disabled:opacity-50 ${
                              mem.is_active
                                ? "bg-white border-rose-200 text-rose-700 hover:bg-rose-50"
                                : "bg-white border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                            }`}
                          >
                            {mem.is_active ? "Nonaktifkan" : "Aktifkan"}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <PdfPreviewModal
        requestId={previewPdfId}
        onClose={() => setPreviewPdfId(null)}
      />
    </div>
  );
};

export default LecturerApprovalsPage;


