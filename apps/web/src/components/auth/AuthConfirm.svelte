<script lang="ts">
  import { onMount } from "svelte";

  import { getBrowserSupabase } from "../../lib/supabase";

  let status = "正在完成登录，请稍候...";
  let error = "";

  function resolveNextPath() {
    if (typeof window === "undefined") {
      return "/";
    }

    const url = new URL(window.location.href);
    const next = url.searchParams.get("next") || "/";
    return next.startsWith("/") ? next : "/";
  }

  async function finalizeAuth() {
    const supabase = getBrowserSupabase();
    if (!supabase || typeof window === "undefined") {
      error = "Supabase 前端鉴权尚未配置完成。";
      return;
    }

    const url = new URL(window.location.href);
    const hashParams = new URLSearchParams(url.hash.replace(/^#/, ""));
    const nextPath = resolveNextPath();
    const authError =
      url.searchParams.get("error_description") ??
      hashParams.get("error_description") ??
      "";

    if (authError) {
      error = decodeURIComponent(authError);
      return;
    }

    const code = url.searchParams.get("code");
    const tokenHash = url.searchParams.get("token_hash");
    const type = url.searchParams.get("type") ?? "email";

    try {
      if (code) {
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
        if (exchangeError) {
          throw exchangeError;
        }
      } else if (tokenHash) {
        const { error: verifyError } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type: type as "email" | "magiclink" | "recovery" | "invite" | "email_change"
        });
        if (verifyError) {
          throw verifyError;
        }
      } else {
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) {
          throw sessionError;
        }
        if (!data.session) {
          throw new Error("未检测到有效登录会话，请重新发送最新的邮箱登录链接。");
        }
      }

      status = "登录成功，正在跳转...";
      window.location.replace(nextPath);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "登录失败，请重新尝试。";
      error = message;
    }
  }

  onMount(() => {
    void finalizeAuth();
  });
</script>

<div class="space-y-3 rounded-[1.5rem] border border-black/8 bg-white/70 p-6 shadow-[0_18px_48px_rgba(30,32,36,0.06)]">
  <p class="text-sm font-semibold text-[var(--ink)]">{status}</p>
  {#if error}
    <p class="text-sm leading-7 text-[var(--danger)]">{error}</p>
  {/if}
</div>
