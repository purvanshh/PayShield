import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import type { ApiError } from "../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const apiKey = localStorage.getItem("api_key");
  if (apiKey && !token) {
    config.headers["X-API-Key"] = apiKey;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_URL}/v1/auth/refresh`, { refresh_token: refreshToken });
          localStorage.setItem("auth_token", res.data.access_token);
          if (error.config) {
            error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
            return client(error.config);
          }
        } catch {
          localStorage.removeItem("auth_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      } else {
        localStorage.removeItem("auth_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export const setAuthToken = (token: string) => {
  localStorage.setItem("auth_token", token);
};

export const setApiKey = (key: string) => {
  localStorage.setItem("api_key", key);
};

export const clearAuth = () => {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("api_key");
};

export default client;
