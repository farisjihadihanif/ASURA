import api from "./api";
import type { AuthResponse, User } from "../types";

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
