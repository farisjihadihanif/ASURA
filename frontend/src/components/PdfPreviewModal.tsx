import React, { useEffect, useRef, useState } from 'react';
import { X, Printer, Loader2, CheckCircle2 } from 'lucide-react';
import suratService from '../services/suratService';
interface PdfPreviewModalProps {
  requestId: number | null;
  onClose: () => void;
}
export const PdfPreviewModal: React.FC<PdfPreviewModalProps> = ({ requestId, onClose }) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [printing, setPrinting] = useState<boolean>(false);
  const [printSuccess, setPrintSuccess] = useState<string | null>(null);
  const [errText, setErrText] = useState<string | null>(null);
  const activeUrlRef = useRef<string | null>(null);
  useEffect(() => {
    if (!requestId) {
      setBlobUrl(null);
      setPrintSuccess(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErrText(null);
    setPrintSuccess(null);
    suratService
      .fetchPdfBlobUrl(requestId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        if (activeUrlRef.current) {
          URL.revokeObjectURL(activeUrlRef.current);
        }
        activeUrlRef.current = url;
        setBlobUrl(url);
      })
      .catch(() => {
        if (!cancelled) setErrText('Gagal memuat pratinjau dokumen PDF.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);
  const handleClose = () => {
    if (activeUrlRef.current) {
      URL.revokeObjectURL(activeUrlRef.current);
      activeUrlRef.current = null;
    }
    setBlobUrl(null);
    setPrintSuccess(null);
    onClose();
  };
  useEffect(() => {
    if (!requestId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]);
  if (!requestId) return null;
  const handleDirectPrint = async () => {
    setPrinting(true);
    setErrText(null);
    try {
      await suratService.markSuratPrinted(requestId);
      try {
        const res = await fetch('http://127.0.0.1:38911/print', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ requestId }),
        });
        if (res.ok) {
          const data = await res.json();
          setPrintSuccess(`Dicetak otomatis ke ${data.deviceName || 'Printer Default'}.`);
          return;
        }
      } catch {}
      const frame = document.getElementById('asura-preview-iframe') as HTMLIFrameElement | null;
      if (frame?.contentWindow) {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      }
      setPrintSuccess('Perintah cetak dikirim ke printer.');
    } catch {
      setErrText('Gagal mencetak dokumen ke printer.');
    } finally {
      setPrinting(false);
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div
      className="fixed inset-0 z-50 bg-[#27211e]/50 backdrop-blur-xs flex items-center justify-center p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="bg-white rounded-2xl w-full max-w-4xl h-[86vh] flex flex-col overflow-hidden shadow-2xl border border-[#eadfd7]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#eadfd7] bg-[#fbf5f0]">
          <span className="text-xs font-bold text-[#27211e]">Pratinjau Dokumen Resmi ASURA</span>
          <div className="flex items-center gap-2">
            {printSuccess && (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {printSuccess}
              </span>
            )}
            {blobUrl && (
              <button
                type="button"
                onClick={() => void handleDirectPrint()}
                disabled={printing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#27211e] text-white text-xs font-semibold hover:bg-[#3d3430] cursor-pointer disabled:opacity-60"
              >
                {printing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Printer className="w-3.5 h-3.5" />}
                Cetak ke Printer
              </button>
            )}
            <button
              type="button"
              onClick={handleClose}
              className="p-1.5 rounded-lg text-[#857870] hover:bg-[#eadfd7]/60 cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 bg-[#f5efe9] flex items-center justify-center">
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-[#857870]">
              <Loader2 className="w-4 h-4 animate-spin text-[#d76b3e]" />
              <span>Memuat dokumen PDF...</span>
            </div>
          ) : errText ? (
            <div className="text-xs text-rose-600">{errText}</div>
          ) : blobUrl ? (
            <iframe
              id="asura-preview-iframe"
              src={`${blobUrl}#toolbar=0&navpanes=0`}
              title="Pratinjau PDF"
              className="w-full h-full border-0"
            />
          ) : null}
        </div>
      </div>
    </div>
  );
};
export default PdfPreviewModal;
