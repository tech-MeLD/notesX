import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let browserClient: SupabaseClient | null = null;

export function getBrowserSupabase() {
  if (typeof window === "undefined") {
    return null;
  }

  if (browserClient) {
    return browserClient;
  }

  const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    return null;
  }

  browserClient = createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true
    }
  });

  return browserClient;
}

export function getAuthRedirectUrl() {
  if (typeof window === "undefined") {
    return undefined;
  }

  const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const callbackUrl = new URL("/auth/confirm", window.location.origin);
  callbackUrl.searchParams.set("next", next);
  return callbackUrl.toString();
}
