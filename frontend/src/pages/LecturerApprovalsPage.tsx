import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  RotateCcw,
  FileText,
  Loader2,
  RefreshCw,
  QrCode,
  PenTool,
  Upload,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import suratService from "../services/suratService";
import { extractErrorMessage } from "../services/api";
import LecturerSidebar from "../components/LecturerSidebar";
import NotificationBell from "../components/NotificationBell";
import PdfPreviewModal from "../components/PdfPreviewModal";
import type { SuratRequestDetail, SuratRequestListItem } from "../types";

export const LecturerApprovalsPage: React.FC = () => {
  const { user, logout, refreshUser } = useAuth();
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuratRequestDetail | null>(null);
  const [editedDraft, setEditedDraft] = useState<string>("");
  const [catatan, setCatatan] = useState<string>("");

  const [signerNama, setSignerNama] = useState<string>(user?.nama || "");
  const [signerNip, setSignerNip] = useState<string>(user?.nip_nim || "");
  const [saveToProfile, setSaveToProfile] = useState<boolean>(false);
  const [signatureMode, setSignatureMode] = useState<"qr" | "manual_image">(
    "qr",
  );
  const [signatureFile, setSignatureFile] = useState<File | null>(null);
  const [signaturePreviewUrl, setSignaturePreviewUrl] = useState<string | null>(
    null,
  );

  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{
    type: "ok" | "err";
    text: string;
  } | null>(null);
  const [previewPdfId, setPreviewPdfId] = useState<number | null>(null);

  useEffect(() => {
    if (user) {
      setSignerNama((prev) => prev || user.nama);
      setSignerNip((prev) => prev || user.nip_nim);
    }
  }, [user]);

  const loadList = useCallback(async () => {
    try {
      const list = await suratService.getSuratRequests();
      setRequests(list);
      setSelectedId((prev) => {
        if (prev && list.some((item) => item.id === prev)) return prev;
        const firstPending = list.find((item) =>
          ["PENDING_APPROVAL", "IN_REVIEW", "SUBMITTED"].includes(item.status),
        );
        return firstPending ? firstPending.id : (list[0]?.id ?? null);
      });
    } catch {
      // Abaikan gangguan sementara
    }
  }, []);

  const loadDetail = useCallback(
    async (id: number) => {
      setLoadingDetail(true);
      setFeedback(null);
      try {
        const data = await suratService.getSuratRequestDetail(id);
        setDetail(data);
        setEditedDraft(
          data.final_approved_content || data.ai_original_draft || "",
        );
        setSignerNama(data.signer_nama_override || user?.nama || "");
        setSignerNip(data.signer_nip_override || user?.nip_nim || "");
        setCatatan("");
      } catch {
        setDetail(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [user],
  );

  useEffect(() => {
    void loadList();
    const timer = window.setInterval(() => void loadList(), 2500);
    return () => window.clearInterval(timer);
  }, [loadList]);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [selectedId, loadDetail]);

  const handleSignatureFileChange = (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0] || null;
    setSignatureFile(file);
    if (file) {
      setSignaturePreviewUrl(URL.createObjectURL(file));
    } else {
      setSignaturePreviewUrl(null);
    }
  };

  const handleDecision = async (
    action: "APPROVE" | "REJECT" | "REVISION_REQUIRED",
  ) => {
    if (!detail) return;
    const activeApproval =
      detail.approvals.find((a) => a.status === "PENDING") ||
      detail.approvals[0];

    if (!activeApproval) {
      setFeedback({
        type: "err",
        text: "Langkah persetujuan tidak ditemukan pada surat ini.",
      });
      return;
    }

    if (
      (action === "REJECT" || action === "REVISION_REQUIRED") &&
      !catatan.trim()
    ) {
      setFeedback({
        type: "err",
        text: "Mohon isi catatan alasan penolakan atau revisi.",
      });
      return;
    }

    if (
      action === "APPROVE" &&
      signatureMode === "manual_image" &&
      !signatureFile
    ) {
      setFeedback({
        type: "err",
        text: "Mohon unggah file gambar tanda tangan (PNG/JPG) terlebih dahulu.",
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);
    try {
      const res = await suratService.submitApprovalAction(activeApproval.id, {
        action,
        catatan: catatan.trim(),
        final_approved_content: editedDraft,
        alasan_penolakan: catatan.trim(),
        signer_nama: signerNama.trim(),
        signer_nip: signerNip.trim(),
        save_to_profile: saveToProfile,
        signature_mode: signatureMode,
        signature_image:
          signatureMode === "manual_image" ? signatureFile : null,
      });

      if (saveToProfile) {
        await refreshUser();
      }

      setFeedback({
        type: "ok",
        text:
          res.message ||
          "Keputusan berhasil disimpan dan notifikasi dikirim ke mahasiswa.",
      });
      await Promise.all([loadList(), loadDetail(detail.id)]);
    } catch (err) {
      setFeedback({
        type: "err",
        text: extractErrorMessage(err, "Gagal memproses keputusan."),
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (!user) return null;

  const canAct =
    detail &&
    ["PENDING_APPROVAL", "IN_REVIEW", "SUBMITTED"].includes(detail.status);

  return (
    <div className="h-screen flex bg-[#fffdfa] text-[#27211e] overflow-hidden">
      <div className="h-full shrink-0">
        <LecturerSidebar
          user={user}
          requests={requests}
          selectedRequestId={selectedId}
          onSelectRequest={(id) => setSelectedId(id)}
          onLogout={() => void logout()}
        />
      </div>

      <div className="flex-1 flex flex-col min-w-0 h-full bg-[#fffdfa]">
        <header className="h-16 px-6 border-b border-[#eadfd7] flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870]">
              Tinjauan Dokumen
            </div>
            <h2 className="text-sm font-bold text-[#27211e]">
              Dashboard Persetujuan Surat (ACC)
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadList()}
              className="p-2 rounded-xl text-[#857870] hover:bg-[#fbf5f0] cursor-pointer"
              title="Muat ulang antrean"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <NotificationBell
              onSelectNotification={(n) => {
                if (n.surat_request_id) setSelectedId(n.surat_request_id);
              }}
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          {!selectedId || (!loadingDetail && !detail) ? (
            <div className="h-full flex items-center justify-center text-xs text-[#857870]">
              Pilih permohonan surat dari sidebar kiri untuk meninjau dan
              memberikan ACC.
            </div>
          ) : loadingDetail || !detail ? (
            <div className="h-full flex items-center justify-center gap-2 text-xs text-[#857870]">
              <Loader2 className="w-4 h-4 animate-spin text-[#d76b3e]" />
              <span>Memuat detail surat...</span>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto space-y-5">
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

              {/* Editor Naskah Surat */}
              <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-[#857870]">
                    Naskah Surat Resmi (Dapat Disunting Sebelum ACC)
                  </h4>
                  {detail.self_critique_score && (
                    <span className="text-[11px] font-semibold text-emerald-700">
                      Skor Kualitas AI: {detail.self_critique_score}/10
                    </span>
                  )}
                </div>
                <textarea
                  rows={10}
                  value={editedDraft}
                  disabled={!canAct}
                  onChange={(e) => setEditedDraft(e.target.value)}
                  className="w-full rounded-xl border border-[#eadfd7] bg-[#fffdfa] p-3.5 text-sm leading-relaxed text-[#27211e] focus:outline-none focus:border-[#d76b3e]"
                />
              </div>

              {/* Identitas Penandatangan & Metode TTD (QR vs Upload Gambar Manual) */}
              {canAct && (
                <div className="rounded-2xl border border-[#eadfd7] bg-white p-4 space-y-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-[#857870]">
                    Identitas Penandatangan & Metode Tanda Tangan
                  </h4>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-[#27211e] mb-1">
                        Nama Penandatangan (Dapat Diubah)
                      </label>
                      <input
                        type="text"
                        value={signerNama}
                        onChange={(e) => setSignerNama(e.target.value)}
                        placeholder="Nama lengkap & gelar pejabat"
                        className="w-full px-3 py-2 text-xs rounded-xl border border-[#eadfd7] bg-[#fffdfa] focus:outline-none focus:border-[#d76b3e]"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[#27211e] mb-1">
                        NIP Penandatangan (Dapat Diubah)
                      </label>
                      <input
                        type="text"
                        value={signerNip}
                        onChange={(e) => setSignerNip(e.target.value)}
                        placeholder="NIP pejabat penandatangan"
                        className="w-full px-3 py-2 text-xs rounded-xl border border-[#eadfd7] bg-[#fffdfa] focus:outline-none focus:border-[#d76b3e]"
                      />
                    </div>
                  </div>

                  <label className="inline-flex items-center gap-2 text-xs text-[#857870] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={saveToProfile}
                      onChange={(e) => setSaveToProfile(e.target.checked)}
                      className="rounded border-[#eadfd7] text-[#d76b3e] focus:ring-[#d76b3e]"
                    />
                    <span>
                      Simpan perubahan Nama & NIP ini ke akun profil dosen saya
                    </span>
                  </label>

                  <div className="pt-2 border-t border-[#eadfd7] space-y-3">
                    <div className="text-xs font-semibold text-[#27211e]">
                      Pilih Jenis Tanda Tangan pada Dokumen PDF:
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setSignatureMode("qr")}
                        className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                          signatureMode === "qr"
                            ? "bg-[#27211e] text-white border-[#27211e]"
                            : "bg-[#fbf5f0] text-[#27211e] border-[#eadfd7] hover:bg-white"
                        }`}
                      >
                        <QrCode className="w-4 h-4" />
                        Gunakan QR Code TTE Otomatis
                      </button>

                      <button
                        type="button"
                        onClick={() => setSignatureMode("manual_image")}
                        className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                          signatureMode === "manual_image"
                            ? "bg-[#d76b3e] text-white border-[#d76b3e]"
                            : "bg-[#fbf5f0] text-[#27211e] border-[#eadfd7] hover:bg-white"
                        }`}
                      >
                        <PenTool className="w-4 h-4" />
                        TTD Manual (Upload Gambar Pengganti QR)
                      </button>
                    </div>

                    {signatureMode === "manual_image" && (
                      <div className="p-3.5 rounded-xl border border-dashed border-[#d76b3e] bg-[#fbf5f0] space-y-2.5">
                        <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-[#eadfd7] text-xs font-semibold text-[#27211e] hover:bg-[#fffdfa] cursor-pointer">
                          <Upload className="w-3.5 h-3.5 text-[#d76b3e]" />
                          <span>
                            {signatureFile
                              ? signatureFile.name
                              : "Pilih Gambar TTD (PNG / JPG)"}
                          </span>
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            onChange={handleSignatureFileChange}
                            className="hidden"
                          />
                        </label>
                        <p className="text-[11px] text-[#857870]">
                          Gambar tanda tangan ini akan menggantikan posisi QR
                          Code di atas Nama & NIP penandatangan pada PDF resmi.
                        </p>
                        {signaturePreviewUrl && (
                          <div className="p-2 bg-white rounded-lg border border-[#eadfd7] inline-block">
                            <img
                              src={signaturePreviewUrl}
                              alt="Preview TTD Manual"
                              className="max-h-20 object-contain"
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Panel Aksi ACC / Revisi / Tolak */}
              {canAct && (
                <div className="rounded-2xl border border-[#eadfd7] bg-[#fbf5f0] p-4 space-y-3">
                  <div>
                    <label className="block text-xs font-bold text-[#27211e] mb-1">
                      Catatan Dosen (Opsional untuk ACC, Wajib untuk Revisi /
                      Tolak)
                    </label>
                    <input
                      type="text"
                      value={catatan}
                      onChange={(e) => setCatatan(e.target.value)}
                      placeholder="Tulis catatan persetujuan atau alasan revisi/penolakan..."
                      className="w-full px-3.5 py-2 text-xs rounded-xl border border-[#eadfd7] bg-white focus:outline-none focus:border-[#d76b3e]"
                    />
                  </div>

                  <div className="flex flex-wrap items-center gap-2.5">
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => void handleDecision("APPROVE")}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition cursor-pointer disabled:opacity-60"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      ACC & Terbitkan Surat
                    </button>

                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => void handleDecision("REVISION_REQUIRED")}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold transition cursor-pointer disabled:opacity-60"
                    >
                      <RotateCcw className="w-4 h-4" />
                      Minta Revisi
                    </button>

                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => void handleDecision("REJECT")}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition cursor-pointer disabled:opacity-60"
                    >
                      <XCircle className="w-4 h-4" />
                      Tolak Surat
                    </button>
                  </div>
                </div>
              )}

              {feedback && (
                <div
                  className={`p-3.5 rounded-xl text-xs font-medium ${
                    feedback.type === "ok"
                      ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                      : "bg-rose-50 text-rose-800 border border-rose-200"
                  }`}
                >
                  {feedback.text}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <PdfPreviewModal
        requestId={previewPdfId}
        onClose={() => setPreviewPdfId(null)}
      />
    </div>
  );
};

export default LecturerApprovalsPage;


