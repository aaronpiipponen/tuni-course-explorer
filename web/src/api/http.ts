/** Same-origin JSON transport with explicit HTTP errors. */

/** One failed same-origin request with its HTTP status. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Decode one same-origin response, reporting a validation detail and any other status as an error. */
async function decode<T>(response: Response): Promise<T> {
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
  return decode<T>(response);
}

/** Read one same-origin endpoint without a stored response and return its typed JSON body. */
export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  return decode<T>(response);
}
