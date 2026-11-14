import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Mail,
  Printer,
  Send,
  FileText,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import suratService from '../services/suratService';
import { extractErrorMessage } from '../services/api';
import type { SuratRequestDetail } from '../types';
interface SuratActionCardProps {
  suratRequest: SuratRequestDetail;
  defaultEmail?: string;
  onUpdated: () => Promise<void>;
  onPreviewPdf: (requestId: number) => void;
}
async function dispatchPrintViaAgentOrBrowser(requestId: number): Promise<string> {
  try {
    const res = await fetch('http://127.0.0.1:38911/print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requestId }),
    });
    if (res.ok) {
      const data = await res.json();
      return `Dokumen dicetak otomatis ke printer (${data.deviceName || 'Printer Default'}) oleh ASURA Agent.`;
    }
  } catch {
    // Fallback jika ASURA Desktop Agent sedang tidak berjalan
  }
  const blobUrl = await suratService.fetchPdfBlobUrl(requestId);
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '1px';
  iframe.style.height = '1px';
  iframe.style.opacity = '0';
  iframe.src = blobUrl;
  iframe.onload = () => {
    window.setTimeout(() => {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
    }, 300);
  };
  document.body.appendChild(iframe);
  return 'Menyiapkan pencetakan dokumen ke printer...';
}
export const SuratActionCard: React.FC<SuratActionCardProps> = ({
  suratRequest,
  defaultEmail = '',
  onUpdated,
  onPreviewPdf,
}) => {
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [recipientEmail, setRecipientEmail] = useState(
    suratRequest.target_destination_address || defaultEmail
  );
  const [busyAction, setBusyAction] = useState<'email' | 'print' | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const isApprovedOrDone = ['APPROVED', 'SENT', 'PRINTED'].includes(suratRequest.status);
  const handleSendEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipientEmail.trim()) return;
    setBusyAction('email');
    setFeedback(null);
    try {
      const res = await suratService.deliverSuratEmail(suratRequest.id, recipientEmail.trim());
      setFeedback({ type: 'ok', text: res.message || `Terkirim ke ${recipientEmail}` });
      setShowEmailForm(false);
      await onUpdated();
    } catch (err) {
      setFeedback({ type: 'err', text: extractErrorMessage(err, 'Gagal mengirim surat ke email.') });
    } finally {
      setBusyAction(null);
    }
  };
  const handlePrintToPrinter = async () => {
    setBusyAction('print');
    setFeedback(null);
    try {
      await suratService.markSuratPrinted(suratRequest.id);
      const msg = await dispatchPrintViaAgentOrBrowser(suratRequest.id);
      setFeedback({ type: 'ok', text: msg });
      await onUpdated();
    } catch (err) {
      setFeedback({ type: 'err', text: extractErrorMessage(err, 'Gagal mencetak surat ke printer.') });
    } finally {
      setBusyAction(null);
    }
  };
  return (
    <div className="my-3 rounded-2xl border border-[#eadfd7] bg-white p-4 shadow-2xs max-w-xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#d76b3e]">
            Status Permohonan Surat
          </span>
          <h4 className="text-sm font-bold text-[#27211e] mt-0.5">{suratRequest.nama_surat}</h4>
          {suratRequest.nomor_surat_resmi && (
            <p className="text-xs font-mono text-[#857870] mt-0.5">
              Nomor: {suratRequest.nomor_surat_resmi}
            </p>
          )}
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold ${
            isApprovedOrDone
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : suratRequest.status === 'REJECTED'
              ? 'bg-rose-50 text-rose-700 border border-rose-200'
              : 'bg-[#fbf5f0] text-[#d76b3e] border border-[#eadfd7]'
          }`}
        >
          {isApprovedOrDone ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : (
            <Clock className="w-3.5 h-3.5" />
          )}
          {suratRequest.status}
        </span>
      </div>
      {!isApprovedOrDone && suratRequest.status !== 'REJECTED' && (
        <p className="text-xs text-[#857870] mt-2.5 leading-relaxed">
          Permohonan sedang menunggu persetujuan (ACC) dari dosen. Setelah di-ACC, pilihan untuk
          mengirim ke <strong className="text-[#27211e]">Email</strong> atau mencetak ke{' '}
          <strong className="text-[#27211e]">Printer</strong> akan muncul di sini.
        </p>
      )}
      {isApprovedOrDone && (
        <div className="mt-3 pt-3 border-t border-[#eadfd7] space-y-3">
          <p className="text-xs text-[#27211e] font-medium">
            Surat sudah di-ACC dosen. Pilih tindakan selanjutnya:
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setShowEmailForm((prev) => !prev)}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#d76b3e] hover:bg-[#c35d32] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-60"
            >
              <Mail className="w-3.5 h-3.5" />
              Kirim ke Email
            </button>
            <button
              type="button"
              onClick={() => void handlePrintToPrinter()}
              disabled={busyAction !== null}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#27211e] hover:bg-[#3d3430] text-white text-xs font-semibold transition cursor-pointer disabled:opacity-60"
            >
              {busyAction === 'print' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Printer className="w-3.5 h-3.5" />
              )}
              Cetak ke Printer
            </button>
            <button
              type="button"
              onClick={() => onPreviewPdf(suratRequest.id)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#eadfd7] bg-[#fbf5f0] hover:bg-[#f3ebe4] text-[#27211e] text-xs font-semibold transition cursor-pointer"
            >
              <FileText className="w-3.5 h-3.5" />
              Lihat PDF
            </button>
          </div>
          {showEmailForm && (
            <form onSubmit={(e) => void handleSendEmail(e)} className="flex gap-2 pt-1">
              <input
                type="email"
                required
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                placeholder="Masukkan alamat email tujuan..."
                className="flex-1 px-3 py-2 text-xs rounded-xl border border-[#eadfd7] bg-[#fffdfa] focus:outline-none focus:border-[#d76b3e]"
              />
              <button
                type="submit"
                disabled={busyAction === 'email'}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold cursor-pointer disabled:opacity-60"
              >
                {busyAction === 'email' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                Kirim
              </button>
            </form>
          )}
        </div>
      )}
      {feedback && (
        <div
          className={`mt-2.5 flex items-center gap-1.5 text-xs px-3 py-2 rounded-xl ${
            feedback.type === 'ok'
              ? 'bg-emerald-50 text-emerald-700'
              : 'bg-rose-50 text-rose-700'
          }`}
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{feedback.text}</span>
        </div>
      )}
    </div>
  );
};
export default SuratActionCard;
