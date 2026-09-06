export const browserApiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const serverApiUrl = process.env.API_INTERNAL_URL ?? browserApiUrl;

export async function apiRequest<T>(
  input: string,
  init?: RequestInit,
  fallbackError = "Request failed",
): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const value =
      body && typeof body === "object" && "detail" in body ? body.detail : null;
    const detail =
      typeof value === "string"
        ? value
        : Array.isArray(value)
          ? value
              .map((item: unknown) =>
                item &&
                typeof item === "object" &&
                "msg" in item &&
                typeof item.msg === "string"
                  ? item.msg
                  : "Invalid field",
              )
              .join(". ")
          : fallbackError;
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
