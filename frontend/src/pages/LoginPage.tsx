import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  Lock,
  User as UserIcon,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { extractErrorMessage } from "../services/api";

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [nipNim, setNipNim] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const loggedUser = await login(nipNim.trim(), password);
      if (loggedUser.role === "LECTURER") {
        navigate("/approvals", { replace: true });
      } else {
        navigate("/chat", { replace: true });
      }
    } catch (err) {
      setError(
        extractErrorMessage(err, "NIM/NIP atau kata sandi tidak valid."),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fffdfa] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-lg border border-[#eadfd7] overflow-hidden">
        <div className="bg-[#fbf5f0] border-b border-[#eadfd7] p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#d76b3e] flex items-center justify-center shadow-xs">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-extrabold tracking-tight text-[#27211e]">
                ASURA
              </h1>
              <p className="text-xs text-[#857870]">
                Asisten Persuratan Resmi Akademik
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-bold text-[#27211e] mb-1.5">
              NIM / NIP
            </label>
            <div className="relative">
              <UserIcon className="w-4 h-4 text-[#857870] absolute left-3.5 top-3" />
              <input
                type="text"
                required
                value={nipNim}
                onChange={(e) => setNipNim(e.target.value)}
                placeholder="Contoh: INF24001 atau 198001012005011001"
                className="w-full pl-10 pr-3.5 py-2.5 text-sm rounded-xl border border-[#eadfd7] bg-[#fffdfa] text-[#27211e] focus:outline-none focus:border-[#d76b3e]"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-[#27211e] mb-1.5">
              Kata Sandi
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-[#857870] absolute left-3.5 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Masukkan kata sandi"
                className="w-full pl-10 pr-3.5 py-2.5 text-sm rounded-xl border border-[#eadfd7] bg-[#fffdfa] text-[#27211e] focus:outline-none focus:border-[#d76b3e]"
              />
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-[#d76b3e] hover:bg-[#c35d32] text-white text-sm font-bold flex items-center justify-center gap-2 transition cursor-pointer disabled:opacity-60"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Masuk ke ASURA</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          <div className="pt-2 border-t border-[#eadfd7] flex items-center justify-between text-[11px] text-[#857870]">
            <button
              type="button"
              onClick={() => {
                setNipNim("INF24001");
                setPassword("12345678");
              }}
              className="hover:text-[#d76b3e] underline cursor-pointer"
            >
              Isi Demo Mahasiswa
            </button>
            <button
              type="button"
              onClick={() => {
                setNipNim("198001012005011001");
                setPassword("12345678");
              }}
              className="hover:text-[#d76b3e] underline cursor-pointer"
            >
              Isi Demo Dosen
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
