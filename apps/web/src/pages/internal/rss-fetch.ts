import type { APIRoute } from "astro";

export const prerender = false;

type ProxyPayload = {
  url?: string;
  headers?: Record<string, string>;
};

function getAllowedHosts() {
  return new Set(
    (import.meta.env.RSS_FETCH_PROXY_ALLOWED_HOSTS ?? "")
      .split(",")
      .map((host: string) => host.trim().toLowerCase())
      .filter(Boolean)
  );
}

function copyForwardHeaders(headers: Record<string, string> | undefined) {
  const forwardHeaders = new Headers({
    accept: "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "user-agent": "knowledge-rss-fetch-proxy/1.0"
  });

  const etag = headers?.["If-None-Match"] ?? headers?.["if-none-match"];
  const lastModified = headers?.["If-Modified-Since"] ?? headers?.["if-modified-since"];

  if (typeof etag === "string" && etag.trim()) {
    forwardHeaders.set("if-none-match", etag.trim());
  }

  if (typeof lastModified === "string" && lastModified.trim()) {
    forwardHeaders.set("if-modified-since", lastModified.trim());
  }

  return forwardHeaders;
}

function copyResponseHeaders(response: Response) {
  const headers = new Headers();

  for (const headerName of ["content-type", "etag", "last-modified", "cache-control"]) {
    const headerValue = response.headers.get(headerName);
    if (headerValue) {
      headers.set(headerName, headerValue);
    }
  }

  headers.set("x-rss-fetch-relayed", "cloudflare-worker");
  return headers;
}

export const POST: APIRoute = async ({ request }) => {
  const configuredToken = import.meta.env.RSS_FETCH_PROXY_TOKEN;
  if (!configuredToken) {
    return new Response("RSS fetch relay is not configured", { status: 503 });
  }

  const allowedHosts = getAllowedHosts();
  if (allowedHosts.size === 0) {
    return new Response("RSS fetch relay host allowlist is not configured", { status: 503 });
  }

  const providedToken = request.headers.get("x-rss-fetch-proxy-token");
  if (providedToken !== configuredToken) {
    return new Response("Unauthorized", { status: 401 });
  }

  let payload: ProxyPayload;
  try {
    payload = (await request.json()) as ProxyPayload;
  } catch {
    return new Response("Invalid JSON payload", { status: 400 });
  }

  if (!payload.url) {
    return new Response("Missing target url", { status: 400 });
  }

  let targetUrl: URL;
  try {
    targetUrl = new URL(payload.url);
  } catch {
    return new Response("Invalid target url", { status: 400 });
  }

  if (!["http:", "https:"].includes(targetUrl.protocol)) {
    return new Response("Unsupported protocol", { status: 400 });
  }

  if (!allowedHosts.has(targetUrl.hostname.toLowerCase())) {
    return new Response("Target host is not allowed", { status: 403 });
  }

  let response: Response;
  try {
    response = await fetch(targetUrl, {
      method: "GET",
      headers: copyForwardHeaders(payload.headers),
      redirect: "follow"
    });
  } catch {
    return new Response("Upstream RSS fetch failed", { status: 502 });
  }

  return new Response(response.body, {
    status: response.status,
    headers: copyResponseHeaders(response)
  });
};
