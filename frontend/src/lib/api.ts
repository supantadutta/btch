// Thin typed API client. Secrets never touch the frontend; this only reads
// data and issues paper-mode actions to the backend.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body?.detail ?? res.statusText);
  }
  const json = await res.json();
  return (json.data ?? json) as T;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: any) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

export const post = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T = any>(path: string) => api<T>(path, { method: "DELETE" });
