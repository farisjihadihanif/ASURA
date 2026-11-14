import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, Loader2, BadgeCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { extractErrorMessage } from "../services/api";
import authService from "../services/authService";
import type { RegisterLookup } from "../services/authService";

const inputCls =
  "w-full px-3.5 py-2.5 text-sm rounded-xl border border-[#eadfd7] bg-[#fffdfa] text-[#27211e] focus:outline-none focus:border-[#d76b3e]";
const labelCls = "block text-xs font-bold text-[#27211e] mb-1.5";

export const RegisterPage: React.FC = () => {
  const { register } = useAuth();
  const [nipNim, setNipNim] = useState("");
  const [profile, setProfile] = useState<RegisterLookup | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [checking, setChecking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleCheck = async () => {
    setError("");
    setProfile(null);
    if (nipNim.trim().length < 4) {
      setError("Masukkan NIM/NIP terlebih dahulu.");
      return;
    }
    setChecking(true);
    try {
      setProfile(await authService.lookupRegister(nipNim.trim()));
    } catch (err) {
      setError(extractErrorMessage(err, "NIM/NIP tidak ditemukan di data kampus."));
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) return;
    setError("");
    setLoading(true);
    try {
      await register({ nip_nim: profile.nip_nim, email: email.trim(), password });
    } catch (err) {
      setError(extractErrorMessage(err, "Pendaftaran gagal."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fffdfa] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-lg border border-[#eadfd7] overflow-hidden">
        <div className="bg-[#fbf5f0] border-b border-[#eadfd7] p-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[#d76b3e] flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-extrabold tracking-tight text-[#27211e]">Aktivasi Akun ASURA</h1>
            <p className="text-xs text-[#857870]">Gunakan NIM/NIP dari data kampus</p>
          </div>
        </div>
        <form onSubmit={(e) => void handleSubmit(e)} className="p-6 space-y-3.5">
          <div>
            <label className={labelCls}>NIM / NIP</label>
            <div className="flex gap-2">
              <input
                className={inputCls}
                value={nipNim}
                onChange={(e) => {
                  setNipNim(e.target.value);
                  setProfile(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleCheck();
                  }
                }}
                placeholder="Contoh: 23106050031"
              />
              <button
                type="button"
                onClick={() => void handleCheck()}
                disabled={checking}
                className="px-4 rounded-xl border border-[#eadfd7] bg-[#fbf5f0] text-xs font-bold text-[#d76b3e] hover:bg-white cursor-pointer disabled:opacity-60"
              >
                {checking ? <Loader2 className="w-4 h-4 animate-spin" /> : "Cek"}
              </button>
            </div>
          </div>

          {profile && (
            <>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-[#27211e] space-y-1">
                <div className="flex items-center gap-1.5 font-bold text-emerald-700">
                  <BadgeCheck className="w-4 h-4" /> Data ditemukan di master kampus
                </div>
                <div>
                  <span className="text-[#857870]">Nama:</span> <b>{profile.nama}</b>
                </div>
                <div>
                  <span className="text-[#857870]">Peran:</span>{" "}
                  {profile.role === "STUDENT" ? "Mahasiswa" : `Dosen${profile.jabatan ? ` - ${profile.jabatan}` : ""}`}
                </div>
                <div>
                  <span className="text-[#857870]">Fakultas:</span> {profile.fakultas}
                </div>
                <div>
                  <span className="text-[#857870]">Program Studi:</span> {profile.prodi}
                </div>
                {profile.role === "STUDENT" && (
                  <div>
                    <span className="text-[#857870]">Angkatan / Semester:</span> {profile.angkatan} / {profile.semester_aktif}
                  </div>
                )}
              </div>
              <div>
                <label className={labelCls}>Email (untuk pengiriman surat)</label>
                <input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Buat Kata Sandi (min. 8 karakter)</label>
                <input
                  className={inputCls}
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </>
          )}

          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">{error}</div>
          )}
          {profile && (
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-[#d76b3e] hover:bg-[#c35d32] text-white text-sm font-bold flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Aktifkan Akun dan Masuk"}
            </button>
          )}
          <p className="text-center text-[11px] text-[#857870]">
            Sudah punya akun?{" "}
            <Link to="/login" className="underline hover:text-[#d76b3e]">
              Masuk
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
};
export default RegisterPage;
