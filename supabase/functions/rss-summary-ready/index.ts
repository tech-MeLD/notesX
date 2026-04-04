import { createClient } from "npm:@supabase/supabase-js@2";

type WebhookPayload = {
  type?: string;
  table?: string;
  schema?: string;
  record?: {
    id?: string;
    title?: string;
    url?: string;
    tags?: string[];
    ai_summary?: string | null;
    summary_status?: string | null;
    published_at?: string | null;
  };
  old_record?: {
    summary_status?: string | null;
  };
};

const jsonHeaders = { "Content-Type": "application/json" };

Deno.serve(async (request) => {
  if (request.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: jsonHeaders,
    });
  }

  const payload = (await request.json()) as WebhookPayload;
  const record = payload.record;
  const oldRecord = payload.old_record;

  const summaryJustCompleted =
    record?.summary_status === "completed" &&
    Boolean(record?.ai_summary) &&
    oldRecord?.summary_status !== "completed";

  if (!summaryJustCompleted || !record?.id) {
    return new Response(JSON.stringify({ ok: true, skipped: true }), { headers: jsonHeaders });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) {
    return new Response(JSON.stringify({ error: "Missing Supabase env vars" }), {
      status: 500,
      headers: jsonHeaders,
    });
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false },
  });

  const liveEvent = {
    entry_id: record.id,
    event_type: "summary.ready",
    payload: {
      title: record.title,
      url: record.url,
      summary: record.ai_summary,
      published_at: record.published_at,
      tags: record.tags ?? [],
    },
  };

  const { error } = await supabase.from("rss_live_events").insert(liveEvent);
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: jsonHeaders,
    });
  }

  return new Response(JSON.stringify({ ok: true, event_type: liveEvent.event_type }), {
    headers: jsonHeaders,
  });
});
