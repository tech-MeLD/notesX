<script lang="ts">
  import type { Session } from "@supabase/supabase-js";
  import { onDestroy, onMount } from "svelte";

  import { getAuthRedirectUrl, getBrowserSupabase } from "../../lib/supabase";

  let session: Session | null = null;
  let email = "";
  let loading = false;
  let notice = "";
  let error = "";
  let panelOpen = false;
  let cooldownSeconds = 0;
  let unsubscribe = () => {};
  let cooldownTimer: ReturnType<typeof setInterval> | null = null;

  const supabase = getBrowserSupabase();

  function getUserLabel() {
    if (!session?.user) {
      return "登录";
    }

    return session.user.email ?? session.user.user_metadata.user_name ?? "账户";
  }

  function readAuthErrorFromUrl() {
    if (typeof window === "undefined") {
      return "";
    }

    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const search = new URLSearchParams(window.location.search);
    return hash.get("error_description") ?? search.get("error_description") ?? "";
  }

  async function refreshSession() {
    if (!supabase) {
      return;
    }

    const { data, error: sessionError } = await supabase.auth.getSession();
    if (sessionError) {
      error = sessionError.message;
      return;
    }

    session = data.session;
  }

  async function signInWithGitHub() {
    if (!supabase) {
      error = "Supabase is not configured yet.";
      return;
    }

    loading = true;
    error = "";
    notice = "";

    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: "github",
      options: {
        redirectTo: getAuthRedirectUrl()
      }
    });

    if (authError) {
      error = authError.message;
      loading = false;
    }
  }

  async function signInWithEmail() {
    if (!supabase) {
      error = "Supabase is not configured yet.";
      return;
    }

    if (!email.trim()) {
      error = "请输入邮箱地址。";
      return;
    }

    loading = true;
    error = "";
    notice = "";

    const { error: authError } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: getAuthRedirectUrl(),
        shouldCreateUser: true
      }
    });

    loading = false;

    if (authError) {
      const normalizedMessage = authError.message.toLowerCase();
      if (normalizedMessage.includes("rate limit")) {
        error = "邮箱发送过于频繁。Supabase 默认对同一邮箱有 60 秒冷却，内置邮件服务也有项目级限流。";
      } else {
        error = authError.message;
      }
      return;
    }

    cooldownSeconds = 60;
    notice = "登录邮件已发送，请使用最新一封邮件中的链接完成登录。旧链接会失效。";
    email = "";
  }

  async function signOut() {
    if (!supabase) {
      return;
    }

    loading = true;
    error = "";
    notice = "";

    const { error: authError } = await supabase.auth.signOut();
    loading = false;

    if (authError) {
      error = authError.message;
      return;
    }

    session = null;
    panelOpen = false;
    notice = "已退出登录。";
  }

  onMount(async () => {
    if (!supabase) {
      return;
    }

    const authError = readAuthErrorFromUrl();
    if (authError) {
      error = decodeURIComponent(authError);
    }

    await refreshSession();

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      session = nextSession;
      if (nextSession) {
        error = "";
        notice = "登录成功。";
        cooldownSeconds = 0;
      }
    });

    unsubscribe = () => data.subscription.unsubscribe();
    cooldownTimer = window.setInterval(() => {
      if (cooldownSeconds > 0) {
        cooldownSeconds -= 1;
      }
    }, 1000);
  });

  onDestroy(() => {
    unsubscribe();
    if (cooldownTimer) {
      clearInterval(cooldownTimer);
    }
  });
</script>

<div class="relative">
  <button class="header-auth-trigger" type="button" on:click={() => (panelOpen = !panelOpen)}>
    {getUserLabel()}
  </button>

  {#if panelOpen}
    <div class="header-auth-panel">
      {#if session}
        <div class="space-y-3">
          <p class="text-sm font-semibold text-[var(--ink)]">{session.user.email ?? "当前账户"}</p>
          <p class="text-sm leading-6 text-[var(--muted)]">收藏的订阅源只对你自己可见，最多可收藏 50 个。</p>
          <button class="header-auth-primary" type="button" on:click={signOut} disabled={loading}>
            {loading ? "处理中..." : "退出登录"}
          </button>
        </div>
      {:else}
        <div class="space-y-4">
          <div class="space-y-2">
            <p class="text-sm font-semibold text-[var(--ink)]">登录后可收藏订阅源</p>
            <p class="text-sm leading-6 text-[var(--muted)]">
              支持 GitHub 登录和邮箱登录。邮箱链接为单次有效，重新发送后请只使用最新邮件。
            </p>
          </div>

          <button class="header-auth-primary" type="button" on:click={signInWithGitHub} disabled={loading}>
            {loading ? "处理中..." : "使用 GitHub 登录"}
          </button>

          <form class="space-y-2" on:submit|preventDefault={signInWithEmail}>
            <input
              bind:value={email}
              class="header-auth-input"
              type="email"
              inputmode="email"
              autocomplete="email"
              placeholder="name@example.com"
            />
            <button class="header-auth-secondary" type="submit" disabled={loading || cooldownSeconds > 0}>
              {#if cooldownSeconds > 0}
                {cooldownSeconds} 秒后可重发
              {:else}
                发送邮箱登录链接
              {/if}
            </button>
          </form>
        </div>
      {/if}

      {#if notice}
        <p class="mt-3 text-sm text-[var(--success)]">{notice}</p>
      {/if}

      {#if error}
        <p class="mt-3 text-sm text-[var(--danger)]">{error}</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .header-auth-trigger {
    border-radius: 999px;
    border: 1px solid rgba(19, 20, 24, 0.1);
    background: rgba(255, 255, 255, 0.62);
    padding: 0.65rem 1rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--ink);
    transition: all 180ms ease;
  }

  .header-auth-trigger:hover {
    border-color: rgba(177, 86, 49, 0.24);
    color: var(--accent);
  }

  .header-auth-panel {
    position: absolute;
    right: 0;
    top: calc(100% + 0.8rem);
    width: min(20rem, 82vw);
    border-radius: 1.2rem;
    border: 1px solid rgba(19, 20, 24, 0.08);
    background: rgba(255, 250, 244, 0.96);
    padding: 1rem;
    box-shadow: 0 20px 54px rgba(19, 20, 24, 0.12);
    backdrop-filter: blur(12px);
  }

  .header-auth-primary,
  .header-auth-secondary,
  .header-auth-input {
    width: 100%;
    border-radius: 0.95rem;
    font: inherit;
  }

  .header-auth-primary,
  .header-auth-secondary {
    border: 1px solid rgba(19, 20, 24, 0.1);
    padding: 0.72rem 0.95rem;
    font-size: 0.88rem;
    font-weight: 600;
    transition: all 180ms ease;
  }

  .header-auth-primary {
    background: var(--ink);
    color: white;
  }

  .header-auth-primary:hover,
  .header-auth-secondary:hover {
    cursor: pointer;
    transform: translateY(-1px);
  }

  .header-auth-primary:hover {
    background: var(--accent);
  }

  .header-auth-secondary {
    background: rgba(255, 255, 255, 0.72);
    color: var(--ink);
  }

  .header-auth-secondary:hover {
    border-color: rgba(177, 86, 49, 0.24);
    color: var(--accent);
  }

  .header-auth-input {
    border: 1px solid rgba(19, 20, 24, 0.1);
    background: rgba(255, 255, 255, 0.78);
    padding: 0.72rem 0.9rem;
    font-size: 0.88rem;
    color: var(--ink);
  }

  .header-auth-input:focus {
    outline: 2px solid rgba(177, 86, 49, 0.18);
    outline-offset: 2px;
  }
</style>
