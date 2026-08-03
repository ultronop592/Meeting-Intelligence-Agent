import { apiRequest } from "./client";

export type User = {
  id: string;
  email: string;
  full_name?: string | null;
  created_at?: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type RegisterPayload = {
  email: string;
  password: string;
  full_name?: string;
};

const TOKEN_KEY = "mia_token";
const USER_KEY = "mia_user";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const data = localStorage.getItem(USER_KEY);
  if (!data) return null;
  try {
    return JSON.parse(data) as User;
  } catch {
    return null;
  }
}

export function setStoredSession(token: string, user: User): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function loginApi(payload: LoginPayload): Promise<TokenResponse> {
  const data = await apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setStoredSession(data.access_token, data.user);
  return data;
}

export async function registerApi(payload: RegisterPayload): Promise<TokenResponse> {
  const data = await apiRequest<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setStoredSession(data.access_token, data.user);
  return data;
}

export async function getMeApi(): Promise<User> {
  const user = await apiRequest<User>("/auth/me", {
    method: "GET",
  });
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  return user;
}
