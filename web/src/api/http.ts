/** Same-origin JSON POST transport with explicit HTTP errors. */

/** One failed same-origin request with its HTTP status. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Post JSON to a same-origin endpoint and return its typed JSON response. */
export async function postJson<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    if (response.status === 422) {
      const payload: unknown = await response.json();
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? (payload as { detail?: unknown }).detail
          : undefined;
      throw new ApiError(
        typeof detail === "string" ? detail : "Invalid request",
        response.status,
      );
    }
    throw new ApiError(`Request failed (${response.status})`, response.status);
  }
  return (await response.json()) as T;
}
