import React, { useCallback, useRef, useState } from "react";
import { useDismiss } from "../hooks/useDismiss";
import { RefreshCw, UserPlus, Check } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import authService from "../services/authService";

export const AccountSwitcher: React.FC = () => {
  const { user, switchAccount, addAccount } = useAuth();
  const [open, setOpen] = useState(false);
  const accounts = open ? authService.getSavedAccounts() : [];
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const closePopup = useCallback(() => setOpen(false), []);
  useDismiss(wrapRef, open, closePopup);

  return (
    <div className="w-full" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[#27211e] hover:bg-[#eadfd7]/50 hover:text-[#d76b3e] font-medium transition cursor-pointer"
      >
        <RefreshCw className="w-3.5 h-3.5 text-[#857870] shrink-0" />
        <span>Ganti akun</span>
      </button>
      {open && (
        <div className="mt-1 mb-1 rounded-xl border border-[#eadfd7] bg-white p-1 shadow-sm">
          {accounts.map((a) => {
            const active = a.nip_nim === user?.nip_nim;
            return (
              <button
                key={a.nip_nim}
                type="button"
                disabled={active}
                onClick={() => void switchAccount(a.nip_nim)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-[#fbf5f0] disabled:cursor-default cursor-pointer"
              >
                <span className="w-6 h-6 rounded-full bg-[#d76b3e] text-white font-bold text-[10px] flex items-center justify-center shrink-0">
                  {a.nama?.charAt(0)?.toUpperCase() || "?"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-[#27211e]">{a.nama}</span>
                  <span className="block truncate text-[10px] text-[#857870]">{a.nip_nim}</span>
                </span>
                {active && <Check className="w-3.5 h-3.5 text-[#d76b3e] shrink-0" />}
              </button>
            );
          })}
          <button
            type="button"
            onClick={addAccount}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-semibold text-[#27211e] hover:bg-[#fbf5f0] cursor-pointer"
          >
            <UserPlus className="w-3.5 h-3.5 text-[#857870] shrink-0" />
            <span>Tambah akun lain</span>
          </button>
        </div>
      )}
    </div>
  );
};
export default AccountSwitcher;
