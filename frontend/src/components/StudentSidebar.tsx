import React from 'react';
import {
  Plus,
  FileText,
  MessageSquare,
  LogOut,
  Sparkles,
  PanelLeftClose,
  Trash2,
  ArrowLeft,
} from 'lucide-react';
import AccountSwitcher from "./AccountSwitcher";
import type { ChatThreadItem, SuratType, User } from '../types';
interface StudentSidebarProps {
  user: User;
  suratTypes: SuratType[];
  threads: ChatThreadItem[];
  activeThreadId?: string;
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (threadId: string) => void;
  onPickSuratPrompt: (suratType: SuratType) => void;
  onLogout: () => void;
  onCollapseSidebar?: () => void;
  onBackToLecturerDashboard?: () => void;
}
export const StudentSidebar: React.FC<StudentSidebarProps> = ({
  user,
  suratTypes,
  threads,
  activeThreadId,
  onNewChat,
  onSelectThread,
  onDeleteThread,
  onPickSuratPrompt,
  onLogout,
  onCollapseSidebar,
  onBackToLecturerDashboard,
}) => {
  return (
    <aside className="w-[270px] h-full bg-[#fbf5f0] text-[#27211e] flex flex-col border-r border-[#eadfd7] select-none">
      <div className="px-4 pt-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#d76b3e]" />
          <span className="font-bold text-sm tracking-wide text-[#27211e]">ASURA</span>
        </div>
        {onCollapseSidebar && (
          <button
            type="button"
            onClick={onCollapseSidebar}
            className="p-1.5 rounded-lg border border-[#eadfd7] bg-white text-[#857870] hover:text-[#27211e] transition cursor-pointer"
            title="Sembunyikan sidebar"
          >
            <PanelLeftClose className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="px-3 pb-3 space-y-2">
        {onBackToLecturerDashboard && (
          <button
            type="button"
            onClick={onBackToLecturerDashboard}
            className="w-full flex items-center gap-2 px-3.5 py-2 rounded-xl bg-[#27211e] hover:bg-[#3d3430] text-white text-xs font-medium transition cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5 shrink-0" />
            <span>Kembali ke Dashboard Dosen</span>
          </button>
        )}
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white hover:bg-[#fffdfa] text-[#27211e] text-xs font-medium border border-[#eadfd7] shadow-2xs transition cursor-pointer"
        >
          <Plus className="w-4 h-4 text-[#857870]" />
          <span>Chat baru</span>
        </button>
      </div>
      {/* JENIS SURAT KAMPUS */}
      <div className="px-3 pt-1 pb-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870] mb-1.5 px-1.5">
          Jenis Surat Kampus
        </div>
        <div className="max-h-56 overflow-y-auto space-y-0.5 pr-1">
          {suratTypes.map((item) => (
            <button
              key={item.kode_surat}
              type="button"
              onClick={() => onPickSuratPrompt(item)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-xs text-[#27211e] hover:bg-white transition cursor-pointer"
              title={item.nama_surat}
            >
              <FileText className="w-3.5 h-3.5 text-[#857870] shrink-0" />
              <span className="truncate">{item.nama_surat}</span>
            </button>
          ))}
        </div>
      </div>
      {/* RIWAYAT CHAT + TOMBOL HAPUS */}
      <div className="flex-1 min-h-0 flex flex-col px-3 pt-3 pb-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-[#857870] mb-1.5 px-1.5">
          Riwayat Chat
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {threads.length === 0 ? (
            <p className="text-[11px] text-[#857870] px-2 py-1">Belum ada riwayat chat.</p>
          ) : (
            threads.map((thread) => {
              const isActive = thread.thread_id === activeThreadId;
              return (
                <div
                  key={thread.thread_id}
                  className={`group flex items-center justify-between gap-1 px-2.5 py-2 rounded-xl text-xs transition ${
                    isActive
                      ? 'bg-white text-[#27211e] font-semibold border border-[#eadfd7] shadow-2xs'
                      : 'text-[#27211e]/85 hover:bg-white/80'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectThread(thread.thread_id)}
                    className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer"
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-[#857870] shrink-0" />
                    <span className="truncate">{thread.title || 'Permohonan Surat Baru'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteThread(thread.thread_id);
                    }}
                    title="Hapus riwayat chat"
                    className="p-1 rounded-md text-[#857870] hover:text-rose-600 hover:bg-rose-50 opacity-70 group-hover:opacity-100 transition cursor-pointer shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="p-4 border-t border-[#eadfd7] space-y-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-[#d76b3e] text-white font-bold text-xs flex items-center justify-center shrink-0">
            {user.nama?.charAt(0)?.toUpperCase() || 'M'}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold text-[#27211e] truncate">{user.nama}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[#857870] truncate">
              {user.role} • {user.nip_nim}
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
export default StudentSidebar;
