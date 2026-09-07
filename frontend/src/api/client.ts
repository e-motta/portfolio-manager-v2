const API_PREFIX = "";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item?.msg || item?.detail || JSON.stringify(item))
        .join(" ");
    }
    return response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    credentials: "include",
  });
  if (response.status === 401) {
    throw new AuthError();
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  return response.json() as Promise<T>;
}

export async function sendForm(
  path: string,
  data: Record<string, string | Blob | string[] | undefined>,
  method = "POST",
): Promise<Response> {
  const body = new FormData();
  for (const [key, value] of Object.entries(data)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const item of value) body.append(key, item);
    } else {
      body.append(key, value);
    }
  }
  const response = await fetch(`${API_PREFIX}${path}`, {
    method,
    body,
    credentials: "include",
    redirect: "manual",
  });
  if (response.status === 401) {
    throw new AuthError();
  }
  if (!response.ok && response.status !== 303 && response.status !== 0) {
    throw new ApiError(response.status, await parseError(response));
  }
  return response;
}

export async function deleteJson(path: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (response.status === 401) {
    throw new AuthError();
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
}

export function redirectLocation(response: Response): string | null {
  const header = response.headers.get("X-Finance-Redirect");
  if (header) return header;
  if (response.status === 303) {
    return response.headers.get("Location");
  }
  return null;
}

export function pathFromRedirect(location: string): string {
  try {
    const url = new URL(location, window.location.origin);
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return location;
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export class AuthError extends Error {
  constructor() {
    super("Not authenticated");
    this.name = "AuthError";
  }
}
