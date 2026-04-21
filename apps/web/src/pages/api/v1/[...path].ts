export const prerender = false;

function getBackendApiBaseUrl() {
  const configured =
    import.meta.env.API_ORIGIN?.replace(/\/$/, "") ??
    import.meta.env.PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8000";

  return configured.endsWith("/api/v1") ? configured : `${configured}/api/v1`;
}

function buildTargetUrl(path: string | undefined, requestUrl: URL) {
  const backendApiBaseUrl = getBackendApiBaseUrl();
  const target = new URL(path || "", `${backendApiBaseUrl}/`);
  target.search = requestUrl.search;
  return target;
}

function copyResponseHeaders(response: Response) {
  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  const cacheControl = response.headers.get("cache-control");

  if (contentType) {
    headers.set("content-type", contentType);
  }

  if (cacheControl) {
    headers.set("cache-control", cacheControl);
  }

  return headers;
}

export async function GET({ params, request, url }: { params: { path?: string }; request: Request; url: URL }) {
  const targetUrl = buildTargetUrl(params.path, url);
  const response = await fetch(targetUrl, {
    method: "GET",
    headers: {
      accept: request.headers.get("accept") ?? "application/json"
    }
  });

  return new Response(response.body, {
    status: response.status,
    headers: copyResponseHeaders(response)
  });
}
