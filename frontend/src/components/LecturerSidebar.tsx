import React from "react";
import {
  Clock,
  CheckCircle2,
  LogOut,
  Sparkles,
  FileText,
  MessageSquare,
} from "lucide-react";
import AccountSwitcher from "./AccountSwitcher";
import type {
  AiDraftGroup,
  AiDraftItem,
  SuratRequestListItem,
  User,
} from "../types";

export type LecturerSidebarMode = "monitoring" | "ai_drafts";

interface LecturerSidebarProps {
  user: User;
  mode: LecturerSidebarMode;
  onChangeMode: (mode: LecturerSidebarMode) => void;
  onOpenChatCreator: () => void;
  requests: SuratRequestListItem[];
  selectedRequestId: number | null;
  onSelectRequest: (id: number) => void;
  aiCategories: string[];
  selectedCategory: string;
  onChangeCategory: (kategori: string) => void;
  aiGroups: AiDraftGroup[];
  selectedAiDraftId: number | null;
  onSelectAiDraft: (draft: AiDraftItem) => void;
  onLogout: () => void;
}

export const LecturerSidebar: React.FC<LecturerSidebarProps> = ({
  user,
  mode,
  onChangeMode,
  onOpenChatCreator,
  requests,
  selectedRequestId,
  onSelectRequest,
  aiCategories,
  selectedCategory,
  onChangeCategory,
  aiGroups,
  selectedAiDraftId,
  onSelectAiDraft,
  onLogout,
}) => {
  const inProgressList = requests.filter((r) =>
    ["PENDING_APPROVAL", "IN_REVIEW", "SUBMITTED", "REVISION_REQUIRED"].includes(
      r.status,
    ),
  );
  const issuedList = requests.filter((r) =>
    ["APPROVED", "SENT", "PRINTED", "REJECTED", "FAILED"].includes(r.status),
  );

  const visibleAiGroups = selectedCategory
    ? aiGroups.filter(
        (g) => g.kategori.toLowerCase() === selectedCategory.toLowerCase(),
      )
    : aiGroups;

  return (
    <aside className="w-80 h-full bg-[#fbf5f0] text-[#27211e] flex flex-col border-r border-[#eadfd7] select-none">
      {/* Header Dosen */}
      <div className="px-4 pt-4 pb-3 border-b border-[#eadfd7] space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#d76b3e]" />
          <div>
            <span className="font-bold text-sm text-[#27211e] block">
              ASURA Dosen
            </span>
            <span className="text-[10px] text-[#857870] block">
              Monitoring Arsip &amp; Kalibrasi Draf AI
            </span>
          </div>
        </div>

        {/* Shortcut Buat Surat Otomatis untuk Dosen/Penanggung Jawab */}
        <button
          type="button"
          onClick={onOpenChatCreator}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-[#27211e] hover:bg-[#3d3430] text-white text-xs font-semibold transition cursor-pointer"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Buat Surat Otomatis (Chat AI)</span>
        </button>

        {/* Tabs Menu Sidebar */}
        <div className="grid grid-cols-2 gap-1.5 bg-[#f2e8e0] p-1 rounded-xl">
          <button
            type="button"
            onClick={() => onChangeMode("monitoring")}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition cursor-pointer ${
              mode === "monitoring"
                ? "bg-white text-[#27211e] shadow-2xs"
                : "text-[#857870] hover:text-[#27211e]"
            }`}
          >
            <FileText className="w-3 h-3" />
            <span>Monitoring</span>
          </button>
          <button
            type="button"
            onClick={() => onChangeMode("ai_drafts")}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition cursor-pointer ${
              mode === "ai_drafts"
                ? "bg-white text-[#d76b3e] shadow-2xs"
                : "text-[#857870] hover:text-[#27211e]"
            }`}
          >
            <Sparkles className="w-3 h-3" />
            <span>Draft Surat AI</span>
          </button>
        </div>
      </div>

      {/* Konten Sidebar sesuai Mode */}
      {mode === "monitoring" ? (
        <div className="flex-1 overflow-y-auto p-3.5 space-y-5">
          <div>
            <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-[#d76b3e] mb-2 px-1">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Sedang Diproses Sistem
              </span>
              <span className="px-2 py-0.5 rounded-full bg-[#d76b3e]/15 text-[#d76b3e]">
                {inProgressList.length}
              </span>
            </div>
            <div className="space-y-1.5">
              {inProgressList.length === 0 ? (
                <p className="text-[11px] text-[#857870] px-2 py-2">
                  Tidak ada surat yang sedang diproses.
                </p>
              ) : (
                inProgressList.map((req) => (
                  <button
                    key={req.id}
                    type="button"
                    onClick={() => onSelectRequest(req.id)}
                    className={`w-full text-left p-2.5 rounded-xl border transition cursor-pointer ${
                      selectedRequestId === req.id
                        ? "bg-white border-[#d76b3e] text-[#27211e] shadow-2xs"
                        : "bg-white/60 border-[#eadfd7] text-[#27211e] hover:bg-white"
                    }`}
                  >
                    <div className="text-xs font-semibold truncate">
                      {req.nama_surat}
                    </div>
                    <div className="text-[11px] text-[#857870] truncate mt-0.5">
                      {req.nama_mahasiswa} ({req.nim_mahasiswa})
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-[#857870] mb-2 px-1">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                Arsip Surat Terbit
              </span>
              <span className="px-2 py-0.5 rounded-full bg-white border border-[#eadfd7] text-[#857870]">
                {issuedList.length}
              </span>
            </div>
            <div className="space-y-1.5">
              {issuedList.length === 0 ? (
                <p className="text-[11px] text-[#857870] px-2 py-2">
                  Belum ada arsip surat terbit.
                </p>
              ) : (
                issuedList.map((req) => (
                  <button
                    key={req.id}
                    type="button"
                    onClick={() => onSelectRequest(req.id)}
                    className={`w-full text-left p-2.5 rounded-xl border transition cursor-pointer ${
                      selectedRequestId === req.id
                        ? "bg-white border-[#27211e]/40 text-[#27211e]"
                        : "bg-white/40 border-[#eadfd7] text-[#857870] hover:bg-white hover:text-[#27211e]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium truncate">
                        {req.nama_surat}
                      </span>
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#fbf5f0] border border-[#eadfd7] text-[#27211e]">
                        {req.status}
                      </span>
                    </div>
                    <div className="text-[11px] text-[#857870] truncate mt-0.5">
                      {req.nama_mahasiswa} •{" "}
                      {req.nomor_surat_resmi || req.nim_mahasiswa}
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
          {/* Filter Kategori */}
          <div className="space-y-1.5">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870] px-1">
              Filter Kategori Surat
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => onChangeCategory("")}
                className={`px-2 py-1 rounded-lg text-[10px] font-semibold border transition cursor-pointer ${
                  selectedCategory === ""
                    ? "bg-[#27211e] text-white border-[#27211e]"
                    : "bg-white text-[#857870] border-[#eadfd7] hover:text-[#27211e]"
                }`}
              >
                Semua
              </button>
              {aiCategories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => onChangeCategory(cat)}
                  className={`px-2 py-1 rounded-lg text-[10px] font-semibold border transition cursor-pointer ${
                    selectedCategory === cat
                      ? "bg-[#d76b3e] text-white border-[#d76b3e]"
                      : "bg-white text-[#857870] border-[#eadfd7] hover:text-[#27211e]"
                  }`}
                >
                  {cat.replace("Surat ", "")}
                </button>
              ))}
            </div>
          </div>

          {/* Daftar 5 Draf Terakhir per Jenis Surat */}
          {visibleAiGroups.length === 0 ? (
            <p className="text-[11px] text-[#857870] px-2 py-4 text-center">
              Tidak ada jenis surat pada kategori ini.
            </p>
          ) : (
            visibleAiGroups.map((group) => (
              <div key={group.kode_surat} className="space-y-1.5">
                <div className="flex items-center justify-between gap-2 px-1">
                  <div className="min-w-0">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#d76b3e] block">
                      {group.kode_surat}
                    </span>
                    <span className="text-[11px] font-bold text-[#27211e] truncate block">
                      {group.nama_surat}
                    </span>
                  </div>
                  {group.active_rule_count > 0 && (
                    <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                      {group.active_rule_count} aturan
                    </span>
                  )}
                </div>

                {group.drafts.length === 0 ? (
                  <p className="text-[10px] text-[#857870] px-2 py-1.5 rounded-lg bg-white/50 border border-dashed border-[#eadfd7]">
                    Belum ada draf AI untuk jenis ini.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {group.drafts.map((draft) => (
                      <button
                        key={draft.id}
                        type="button"
                        onClick={() => onSelectAiDraft(draft)}
                        className={`w-full text-left p-2 rounded-xl border transition cursor-pointer ${
                          selectedAiDraftId === draft.id
                            ? "bg-white border-[#d76b3e] text-[#27211e] shadow-2xs"
                            : "bg-white/60 border-[#eadfd7] text-[#27211e] hover:bg-white"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1.5">
                          <span className="text-[11px] font-semibold truncate">
                            {draft.pemohon_nama}
                          </span>
                          {draft.feedback_count > 0 ? (
                            <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-700">
                              Terkalibrasi
                            </span>
                          ) : (
                            <span className="shrink-0 text-[9px] font-semibold text-[#857870]">
                              {draft.self_critique_score
                                ? `${draft.self_critique_score}/10`
                                : `#${draft.id}`}
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-[#857870] truncate mt-0.5">
                          {draft.nomor_surat_resmi || draft.pemohon_identitas}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Pojok Kiri Bawah: Informasi Account & Logout */}
      <div className="p-4 border-t border-[#eadfd7] space-y-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-[#27211e] text-white font-bold text-xs flex items-center justify-center shrink-0">
            {user.nama?.charAt(0)?.toUpperCase() || "D"}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold text-[#27211e] truncate">
              {user.nama}
            </p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[#857870] truncate">
              LECTURER • NIP {user.nip_nim}
            </p>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <AccountSwitcher />
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[#27211e] hover:bg-[#eadfd7]/50 hover:text-[#d76b3e] font-medium transition cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5 text-[#857870] shrink-0" />
            <span>Keluar</span>
          </button>
        </div>
      </div>
    </aside>
  );
};

export default LecturerSidebar;
