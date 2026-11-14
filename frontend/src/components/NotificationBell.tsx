import React, { useCallback, useEffect, useRef, useState } from "react";
import { useDismiss } from "../hooks/useDismiss";
import { Bell, CheckCheck } from "lucide-react";
import suratService from "../services/suratService";
import type { NotificationItem } from "../types";

interface NotificationBellProps {
  onSelectNotification?: (notif: NotificationItem) => void;
}

export const NotificationBell: React.FC<NotificationBellProps> = ({
  onSelectNotification,
}) => {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const closePopup = useCallback(() => setOpen(false), []);
  useDismiss(wrapRef, open, closePopup);

  const loadNotifications = async () => {
    try {
      const [count, list] = await Promise.all([
        suratService.getUnreadNotificationCount(),
        suratService.getNotifications(),
      ]);
      setUnreadCount(count);
      setItems(list);
    } catch {
      // Abaikan gangguan polling sementara
    }
  };

  useEffect(() => {
    void loadNotifications();
    const timer = window.setInterval(() => void loadNotifications(), 2500);
    return () => window.clearInterval(timer);
  }, []);

  const handleReadAll = async () => {
    await suratService.markAllNotificationsRead();
    await loadNotifications();
  };

  const handleItemClick = async (item: NotificationItem) => {
    if (!item.is_read) {
      await suratService.markNotificationRead(item.id);
      await loadNotifications();
    }
    setOpen(false);
    if (onSelectNotification) {
      onSelectNotification(item);
    }
  };

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="relative p-2 rounded-xl text-[#857870] hover:text-[#27211e] hover:bg-[#fbf5f0] transition cursor-pointer"
        aria-label="Notifikasi"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[17px] h-[17px] px-1 rounded-full bg-[#d76b3e] text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white border border-[#eadfd7] rounded-2xl shadow-xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#eadfd7] bg-[#fbf5f0]">
            <span className="text-xs font-bold text-[#27211e]">
              Notifikasi ASURA
            </span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void handleReadAll()}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#d76b3e] hover:underline cursor-pointer"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                Tandai dibaca
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-[#eadfd7]/60">
            {items.length === 0 ? (
              <div className="p-6 text-center text-xs text-[#857870]">
                Belum ada notifikasi masuk.
              </div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void handleItemClick(item)}
                  className={`w-full text-left px-4 py-3 hover:bg-[#fbf5f0]/70 transition cursor-pointer ${
                    !item.is_read ? "bg-[#fbf5f0]" : "bg-white"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-[#27211e]">
                      {item.title}
                    </p>
                    {!item.is_read && (
                      <span className="w-2 h-2 rounded-full bg-[#d76b3e] mt-1 shrink-0" />
                    )}
                  </div>
                  <p className="text-[11px] text-[#857870] mt-1 leading-relaxed">
                    {item.body}
                  </p>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;


