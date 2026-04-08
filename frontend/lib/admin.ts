/**
 * admin.ts
 *
 * Server-side only — BFF (Backend-For-Frontend) layer for admin operations.
 *
 * These functions run exclusively on the Next.js server (API routes / Server
 * Actions).  They inject the INTERNAL_ADMIN_SECRET into every request to the
 * FastAPI backend.  The secret is NEVER exposed to the browser.
 *
 * The browser calls Next.js API routes (/api/v1/admin/*), which call these
 * functions, which call FastAPI (/api/v1/admin/*).  Two hops, but the secret
 * stays server-side.
 */

import type { User, ApiKey, ApiKeyWithSecret } from "@/types";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const ADMIN_SECRET = process.env.INTERNAL_ADMIN_SECRET ?? "";

/** Shared headers for every admin request to FastAPI. */
function adminHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${ADMIN_SECRET}`,
  };
}

/** Unwrap a FastAPI response or throw with the detail message. */
async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function listUsers(): Promise<User[]> {
  const res = await fetch(`${BACKEND_URL}/api/v1/admin/users`, {
    headers: adminHeaders(),
  });
  const data = await unwrap<{ users: User[] }>(res);
  return data.users;
}

export async function createUser(
  username: string,
  password: string,
  name: string,
  role: string = "user",
): Promise<User> {
  // User creation goes through the existing /api/auth/register endpoint,
  // but we protect it with the admin secret header too.  FastAPI's register
  // endpoint does not require admin auth (it was designed for self-signup),
  // so we call it directly.  The admin UI is the only place that exposes
  // this — the route is not in Next.js rewrites for the browser.
  const res = await fetch(`${BACKEND_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, name, role }),
  });
  return unwrap<User>(res);
}

export async function deleteUser(userId: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/api/v1/admin/users/${userId}`, {
    method: "DELETE",
    headers: adminHeaders(),
  });
  await unwrap<{ message: string }>(res);
}

export async function changePassword(
  userId: string,
  oldPassword: string,
  newPassword: string,
): Promise<void> {
  const res = await fetch(
    `${BACKEND_URL}/api/v1/admin/users/${userId}/change-password`,
    {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    },
  );
  await unwrap<{ message: string }>(res);
}

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------

export async function listApiKeys(userId: string): Promise<ApiKey[]> {
  const res = await fetch(
    `${BACKEND_URL}/api/v1/admin/api-keys?user_id=${encodeURIComponent(userId)}`,
    { headers: adminHeaders() },
  );
  const data = await unwrap<{ api_keys: ApiKey[] }>(res);
  return data.api_keys;
}

export async function createApiKey(
  userId: string,
  label: string,
): Promise<ApiKeyWithSecret> {
  const res = await fetch(`${BACKEND_URL}/api/v1/admin/api-keys`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ user_id: userId, label }),
  });
  return unwrap<ApiKeyWithSecret>(res);
}

export async function revokeApiKey(keyId: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/api/v1/admin/api-keys/${keyId}`, {
    method: "DELETE",
    headers: adminHeaders(),
  });
  await unwrap<{ message: string }>(res);
}
