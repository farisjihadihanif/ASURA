import api from "./api";
import type { AuthResponse, User } from "../types";

const ACCOUNTS_KEY = "asura_accounts";

export interface RegisterLookup {
  nama: string;
  role: "STUDENT" | "LECTURER";
  nip_nim: string;
  fakultas: string;
  prodi: string;
  angkatan?: number;
  semester_aktif?: number;
  jabatan?: string;
}

export interface RegisterPayload {
  nip_nim: string;
  email?: string;
  password: string;
}

export interface SavedAccount {
  nip_nim: string;
  nama: string;
  role: string;
  access: string;
  refresh: string;
  user: User;
}

function readAccounts(): SavedAccount[] {
  try {
    return JSON.parse(localStorage.getItem(ACCOUNTS_KEY) || "[]") as SavedAccount[];
  } catch {
    return [];
  }
}

function writeAccounts(list: SavedAccount[]) {
  try {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(list));
  } catch {
    // abaikan jika penyimpanan lokal tidak tersedia
  }
}

function snapshotActive() {
  const access = localStorage.getItem("asura_access_token");
  const refresh = localStorage.getItem("asura_refresh_token");
  const raw = localStorage.getItem("asura_user_info");
  if (!access || !refresh || !raw) return;
  try {
    const user = JSON.parse(raw) as User;
    const list = readAccounts().filter((a) => a.nip_nim !== user.nip_nim);
    list.unshift({ nip_nim: user.nip_nim, nama: user.nama, role: String(user.role), access, refresh, user });
    writeAccounts(list.slice(0, 5));
  } catch {
    // abaikan data rusak
  }
}

export const authService = {
  async login(nip_nim: string, password: string): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>("/api/accounts/login/", {
      nip_nim,
      password,
    });
    const data = response.data;
    if (data.access) {
      localStorage.setItem("asura_access_token", data.access);
      localStorage.setItem("asura_refresh_token", data.refresh);
      localStorage.setItem("asura_user_info", JSON.stringify(data.user));
      snapshotActive();
    }
    return data;
  },

  async lookupRegister(nipNim: string): Promise<RegisterLookup> {
    const response = await api.get<{ data: RegisterLookup }>("/api/accounts/register/lookup/", {
      params: { nip_nim: nipNim },
    });
    return response.data.data;
  },

  async register(payload: RegisterPayload): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>("/api/accounts/register/", payload);
    const data = response.data;
    if (data.access) {
      localStorage.setItem("asura_access_token", data.access);
      localStorage.setItem("asura_refresh_token", data.refresh);
      localStorage.setItem("asura_user_info", JSON.stringify(data.user));
      snapshotActive();
    }
    return data;
  },

  async logout(): Promise<void> {
    const refresh = localStorage.getItem("asura_refresh_token");
    try {
      if (refresh) {
        await api.post("/api/accounts/logout/", { refresh });
      }
    } catch {
      // Abaikan error network saat logout
    } finally {
      const raw = localStorage.getItem("asura_user_info");
      try {
        const me = raw ? (JSON.parse(raw) as User) : null;
        if (me) writeAccounts(readAccounts().filter((a) => a.nip_nim !== me.nip_nim));
      } catch {
        // abaikan
      }
      localStorage.removeItem("asura_access_token");
      localStorage.removeItem("asura_refresh_token");
      localStorage.removeItem("asura_user_info");
    }
  },

  async getMe(): Promise<User> {
    const response = await api.get<User>("/api/accounts/me/");
    localStorage.setItem("asura_user_info", JSON.stringify(response.data));
    return response.data;
  },

  getSavedAccounts(): SavedAccount[] {
    snapshotActive();
    return readAccounts();
  },

  /** Simpan akun aktif lalu kosongkan sesi aktif tanpa logout, agar bisa login akun lain. */
  addAccount(): void {
    snapshotActive();
    localStorage.removeItem("asura_access_token");
    localStorage.removeItem("asura_refresh_token");
    localStorage.removeItem("asura_user_info");
  },

  /** Pindah ke akun tersimpan tanpa password. Mengembalikan user, atau null jika sesi sudah kedaluwarsa. */
  async switchTo(nip_nim: string): Promise<User | null> {
    snapshotActive();
    const target = readAccounts().find((a) => a.nip_nim === nip_nim);
    if (!target) return null;
    localStorage.setItem("asura_access_token", target.access);
    localStorage.setItem("asura_refresh_token", target.refresh);
    localStorage.setItem("asura_user_info", JSON.stringify(target.user));
    try {
      return await this.getMe();
    } catch {
      try {
        const res = await api.post<{ access: string }>("/api/accounts/token/refresh/", { refresh: target.refresh });
        localStorage.setItem("asura_access_token", res.data.access);
        const me = await this.getMe();
        snapshotActive();
        return me;
      } catch {
        writeAccounts(readAccounts().filter((a) => a.nip_nim !== nip_nim));
        localStorage.removeItem("asura_access_token");
        localStorage.removeItem("asura_refresh_token");
        localStorage.removeItem("asura_user_info");
        return null;
      }
    }
  },

  getToken(): string | null {
    return localStorage.getItem("asura_access_token");
  },

  getCurrentUser(): User | null {
    const raw = localStorage.getItem("asura_user_info");
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  },
};

export default authService;
