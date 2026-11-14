import React from "react";
import { Clock, CheckCircle2, LogOut, Sparkles } from "lucide-react";
import AccountSwitcher from "./AccountSwitcher";
import type { SuratRequestListItem, User } from "../types";

interface LecturerSidebarProps {
  user: User;
  requests: SuratRequestListItem[];
  selectedRequestId: number | null;
  onSelectRequest: (id: number) => void;
  onLogout: () => void;
}

export const LecturerSidebar: React.FC<LecturerSidebarProps> = ({
  user,
  requests,
  selectedRequestId,
  onSelectRequest,
  onLogout,
}) => {
  const pendingList = requests.filter((r) =>
    ["PENDING_APPROVAL", "IN_REVIEW", "SUBMITTED"].includes(r.status),
  );
  const processedList = requests.filter((r) =>
    ["APPROVED", "SENT", "PRINTED", "REJECTED", "REVISION_REQUIRED"].includes(
      r.status,
    ),
  );

  return (
    <aside className="w-80 h-full bg-[#fbf5f0] text-[#27211e] flex flex-col border-r border-[#eadfd7] select-none">
      {/* Header Dosen */}
      <div className="px-4 pt-4 pb-3 border-b border-[#eadfd7] flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-[#d76b3e]" />
        <div>
          <span className="font-bold text-sm text-[#27211e] block">
            ASURA Dosen
          </span>
          <span className="text-[10px] text-[#857870] block">
            Dashboard Persetujuan Surat
          </span>
        </div>
      </div>

      {/* Riwayat Surat Masuk (Untuk Di-ACC & Sudah Di-ACC) */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-5">
        <div>
          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-[#d76b3e] mb-2 px-1">
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              Surat Untuk Di-ACC
            </span>
            <span className="px-2 py-0.5 rounded-full bg-[#d76b3e]/15 text-[#d76b3e]">
              {pendingList.length}
            </span>
          </div>
          <div className="space-y-1.5">
            {pendingList.length === 0 ? (
              <p className="text-[11px] text-[#857870] px-2 py-2">
                Tidak ada surat menunggu ACC.
              </p>
            ) : (
              pendingList.map((req) => (
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
              Sudah Di-ACC / Diproses
            </span>
            <span className="px-2 py-0.5 rounded-full bg-white border border-[#eadfd7] text-[#857870]">
              {processedList.length}
            </span>
          </div>
          <div className="space-y-1.5">
            {processedList.length === 0 ? (
              <p className="text-[11px] text-[#857870] px-2 py-2">
                Belum ada surat yang diproses.
              </p>
            ) : (
              processedList.map((req) => (
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
