export function buildApiUrl(
  baseUrl: string,
  pathname: string,
  search?: Record<string, string | number | undefined>
) {
  const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const isAbsolute = /^https?:\/\//i.test(baseUrl);
  const url = isAbsolute
    ? new URL(normalizedPath, `${baseUrl}/`)
    : new URL(`${baseUrl.replace(/\/$/, "")}${normalizedPath}`, "http://internal");

  for (const [key, value] of Object.entries(search ?? {})) {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  return isAbsolute ? url.toString() : `${url.pathname}${url.search}`;
}
