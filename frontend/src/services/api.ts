import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem("asura_access_token");
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response && error.response.status === 401) {
      const path = window.location.pathname;
      if (!path.includes("/login") && !path.includes("/verify")) {
        localStorage.removeItem("asura_access_token");
        localStorage.removeItem("asura_refresh_token");
        localStorage.removeItem("asura_user_info");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export function extractErrorMessage(
  error: unknown,
  fallback = "Terjadi kesalahan pada server.",
): string {
  const err = error as {
    response?: { data?: Record<string, unknown> };
    message?: string;
  };
  const data = err?.response?.data;
  if (!data) return err?.message || fallback;
  if (typeof data.error === "string") return data.error;
  if (typeof data.detail === "string") return data.detail;
  if (data.errors && typeof data.errors === "object") {
    const msgs: string[] = [];
    Object.values(data.errors as Record<string, unknown>).forEach((val) => {
      if (Array.isArray(val)) msgs.push(val.join(", "));
      else if (typeof val === "string") msgs.push(val);
    });
    if (msgs.length > 0) return msgs.join(" ");
  }
  if (typeof data.message === "string") return data.message;
  return fallback;
}

export default api;
