import React, { useCallback, useEffect, useState } from "react";
import { FileText, Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import suratService from "../services/suratService";
import LecturerSidebar from "../components/LecturerSidebar";
import NotificationBell from "../components/NotificationBell";
import PdfPreviewModal from "../components/PdfPreviewModal";
import type { SuratRequestDetail, SuratRequestListItem } from "../types";

export const LecturerApprovalsPage: React.FC = () => {
  const { user, logout } = useAuth();
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SuratRequestDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [previewPdfId, setPreviewPdfId] = useState<number | null>(null);

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

  if (!user) return null;

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
              Mode Pantau Otomatis (Read-Only)
            </div>
            <h2 className="text-sm font-bold text-[#27211e]">
              Monitoring &amp; Arsip Surat Kampus
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadList()}
              className="p-2 rounded-xl text-[#857870] hover:bg-[#fbf5f0] cursor-pointer"
              title="Muat ulang arsip surat"
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
                  value={detail.final_approved_content || detail.ai_original_draft || ""}
                  className="w-full rounded-xl border border-[#eadfd7] bg-[#fffdfa] p-3.5 text-sm leading-relaxed text-[#27211e] focus:outline-none"
                />
              </div>
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


