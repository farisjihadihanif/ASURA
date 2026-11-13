import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ShieldCheck, ShieldAlert, ArrowLeft } from "lucide-react";
import suratService from "../services/suratService";
import type { VerificationData } from "../types";

export const VerifySuratPage: React.FC = () => {
  const { token } = useParams<{ token?: string }>();
  const [inputToken, setInputToken] = useState(token || "");
  const [result, setResult] = useState<VerificationData | null>(null);
  const [loading, setLoading] = useState(false);

  const checkToken = async (tok: string) => {
    if (!tok.trim()) return;
    setLoading(true);
    try {
      const data = await suratService.verifySurat(tok.trim());
      setResult(data);
    } catch {
      setResult({
        status: "INVALID",
        message: "Token TTE tidak ditemukan atau dokumen tidak terdaftar.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) void checkToken(token);
  }, [token]);

  return (
    <div className="min-h-screen bg-[#fffdfa] flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white rounded-3xl border border-[#eadfd7] shadow-lg p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-base font-extrabold text-[#27211e]">
            Verifikasi Keaslian TTE ASURA
          </h1>
          <Link
            to="/login"
            className="text-xs text-[#d76b3e] hover:underline inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Login
          </Link>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void checkToken(inputToken);
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={inputToken}
            onChange={(e) => setInputToken(e.target.value)}
            placeholder="Masukkan token verifikasi TTE..."
            className="flex-1 px-3.5 py-2 text-xs rounded-xl border border-[#eadfd7] bg-[#fffdfa]"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded-xl bg-[#27211e] text-white text-xs font-bold cursor-pointer"
          >
            {loading ? "Memeriksa..." : "Verifikasi"}
          </button>
        </form>

        {result && (
          <div
            className={`p-4 rounded-2xl border ${
              result.status === "VALID"
                ? "bg-emerald-50/70 border-emerald-200 text-emerald-900"
                : "bg-rose-50 border-rose-200 text-rose-900"
            }`}
          >
            <div className="flex items-center gap-2 font-bold text-sm">
              {result.status === "VALID" ? (
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
              ) : (
                <ShieldAlert className="w-5 h-5 text-rose-600" />
              )}
              <span>{result.status}</span>
            </div>
            <p className="text-xs mt-1">{result.message}</p>
            {result.detail_surat && (
              <div className="mt-3 pt-3 border-t border-emerald-200/70 text-xs space-y-1">
                <div>
                  Nomor:{" "}
                  <strong>{result.detail_surat.nomor_surat_resmi}</strong>
                </div>
                <div>
                  Jenis: <strong>{result.detail_surat.jenis_surat}</strong>
                </div>
                <div>
                  Mahasiswa:{" "}
                  <strong>
                    {result.mahasiswa?.nama} ({result.mahasiswa?.nim})
                  </strong>
                </div>
                <div>
                  Penandatangan:{" "}
                  <strong>{result.tte_info?.penandatangan}</strong>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default VerifySuratPage;
