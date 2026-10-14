import { accessToken, getConfig, sessionExpired } from "./auth";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const config = await getConfig();
  // Never automatically repeat a mutation: a lost response can still mean an applied write.
  const token = await accessToken();
  const send = (credential: string) =>
    fetch(config.apiUrl + path, {
      method: options.method ?? "GET",
      headers: {
        Authorization: `Bearer ${credential}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(20000)])
        : AbortSignal.timeout(20000),
    });
  let response = await send(token);
  if (response.status === 401 && (!options.method || options.method === "GET"))
    response = await send(await accessToken(true));
  if (response.status === 401) sessionExpired();
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback =
      response.status === 403
        ? "Your current role does not allow this action."
        : response.status === 401
          ? "Please sign in again."
          : "The service is temporarily unavailable. Try again.";
    throw new ApiError(payload.error || fallback, response.status);
  }
  return payload as T;
}
