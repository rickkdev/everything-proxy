<script lang="ts">
  import { onMount } from "svelte";
  import {
    api, blockLabels, holdLabels, pair, reasonLabels,
    type Fact, type MessageDetail, type MessageSummary, type Status, type View,
  } from "./lib/api";

  let { paired: initiallyPaired }: { paired: boolean } = $props();

  let paired = $state(false);
  let pairingCode = $state("");
  let pairingError = $state("");
  let status = $state<Status | null>(null);
  let view = $state<View | "setup">("review");
  let query = $state("");
  let from = $state("");
  let to = $state("");
  let messages = $state<MessageSummary[]>([]);
  let facts = $state<Fact[]>([]);
  let selectedId = $state<string | null>(null);
  let detail = $state<MessageDetail | null>(null);
  let editing = $state<Record<string, string>>({});
  let announcement = $state("");
  let mobileDetail = $state(false);
  let previewTool = $state<"get_digest" | "search_facts" | "get_source_facts" | "get_status">("get_digest");
  let previewSince = $state(new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10));
  let previewQuery = $state("");
  let previewRef = $state("src_1");
  let previewResult = $state("");

  const factView = $derived(view === "review" || view === "approved");
  const busy = $derived(status?.progress.phase && status.progress.phase !== "idle");
  const titles: Record<View | "setup", string> = {
    review: "Review queue", approved: "Approved for AI", all: "All imported", included: "Included",
    deprioritized: "Deprioritized", skipped: "Skipped", withheld: "Withheld locally", pending: "Pending & failed", setup: "Setup & MCP",
  };

  $effect(() => { paired = initiallyPaired; });

  async function submitPairing(event: SubmitEvent) {
    event.preventDefault();
    try {
      await pair(pairingCode);
      paired = true;
      pairingError = "";
      await load();
    } catch {
      pairingError = "That code was not accepted. Codes are single-use and expire after 5 minutes — press Enter in the companion terminal for a new one.";
    }
  }

  async function guard<T>(work: () => Promise<T>): Promise<T | undefined> {
    try {
      return await work();
    } catch (error) {
      const failure = error as Error & { status?: number; payload?: { flags?: string[] } };
      if (failure.status === 401) { paired = false; return; }
      announcement = failure.payload?.flags ? `Blocked by the privacy check: ${failure.payload.flags.join(", ")}. Edit the fact to remove it.` : `Request failed: ${failure.message}`;
    }
  }

  async function load() {
    await guard(async () => {
      status = await api.status();
      if (view === "setup") return;
      if (factView) {
        facts = (await api.facts(view === "review" ? "proposed" : "approved")).facts;
      } else {
        messages = (await api.messages(view as View, query, from, to)).messages;
        if (!selectedId && messages[0]) selectedId = messages[0].id;
      }
      if (selectedId) detail = await api.message(selectedId);
    });
  }

  function navigate(next: View | "setup") {
    view = next;
    selectedId = null;
    detail = null;
    mobileDetail = false;
    load();
  }

  async function select(id: string) {
    selectedId = id;
    mobileDetail = true;
    await guard(async () => { detail = await api.message(id); });
  }

  async function act(fact: Fact, action: "approve" | "dismiss" | "reopen" | "edit") {
    const text = action === "edit" ? editing[fact.id] : undefined;
    const result = await guard(() => api.factAction(fact.id, action, text));
    if (!result) return;
    if (action === "edit") { const next = { ...editing }; delete next[fact.id]; editing = next; }
    announcement = action === "approve" ? "Approved. This fact can now be returned to ChatGPT or Claude through MCP."
      : action === "dismiss" ? "Dismissed. It will never be released." : action === "edit" ? "Edited and re-checked. Approve it when it reads right." : "Moved back to review.";
    await load();
  }

  async function setSender(action: "include" | "exclude" | null) {
    if (!detail) return;
    await guard(() => api.sender(detail!.sender_address, action));
    announcement = action ? `Sender ${action}d. Its messages are being reprocessed locally.` : "Sender rule removed.";
    await load();
  }

  async function refresh() {
    await guard(() => api.refresh());
    announcement = "Refresh started. New mail is fetched read-only and processed locally.";
    await load();
  }

  async function runPreview() {
    const args = previewTool === "get_digest" ? { since: previewSince } : previewTool === "search_facts" ? { query: previewQuery || "deadline" }
      : previewTool === "get_source_facts" ? { ref: previewRef.trim() } : {};
    const result = await guard(() => api.preview(previewTool, args));
    if (result) previewResult = JSON.stringify(result.result, null, 2);
  }

  function when(value: string | null | undefined) {
    return value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "never";
  }

  function name(sender: string) {
    return sender.split(" <")[0].replaceAll('"', "") || sender;
  }

  function placement(message: MessageSummary) {
    if (message.privacy_hold) return "withheld";
    if (message.model_relevance) return message.model_relevance === "inspect" ? "held for local review" : message.model_relevance;
    return message.state === "filtered" ? message.relevance : message.state.replace("_", " ");
  }

  onMount(() => {
    if (initiallyPaired) load();
    const timer = setInterval(() => { if (paired) guard(async () => { status = await api.status(); }); }, 5000);
    return () => clearInterval(timer);
  });
</script>

{#if !paired}
  <div class="pair-screen">
    <form class="pair-card" onsubmit={submitPairing}>
      <span class="brand-mark" aria-hidden="true">e</span>
      <h1>Pair this browser</h1>
      <p>Paste the pairing code shown in the terminal running <code>python -m companion serve</code>. The code never travels in a URL and works once.</p>
      <input type="password" autocomplete="off" bind:value={pairingCode} aria-label="Pairing code" placeholder="Pairing code" />
      {#if pairingError}<p class="range-error" role="alert">{pairingError}</p>{/if}
      <button class="primary-button" type="submit" disabled={!pairingCode.trim()}>Pair</button>
    </form>
  </div>
{:else}
<div class="app-shell">
  <header class="topbar">
    <a class="brand" href="#review" onclick={() => navigate("review")} aria-label="Everything Proxy home">
      <span class="brand-mark" aria-hidden="true">e</span><span>everything<span class="brand-muted">proxy</span></span>
    </a>
    <div class="demo-status">
      <span class="status-dot" class:live-dot={status?.connected && !status?.sync_error}></span>
      {status?.account ?? "Gmail not connected"} <span class="status-divider">·</span>
      {#if status?.sync_error}<strong class="error-text">{status.sync_error === "offline" ? "Offline — showing last sync" : "Gmail access expired — reconnect"}</strong>
      {:else if busy}{status?.progress.detail || status?.progress.phase}
      {:else}synced {when(status?.last_sync_at)}{/if}
    </div>
    <div class="action-row">
      <button class="text-button" onclick={refresh} disabled={!status?.connected}>Refresh</button>
      <button class="text-button" onclick={() => navigate("setup")}>Setup & MCP</button>
    </div>
  </header>

  <main class="workspace" class:show-detail={mobileDetail} class:show-setup={view === "setup"}>
    <aside class="sidebar" aria-label="Views">
      <div class="sidebar-label">FOR AI</div>
      {#each [["review", "◎", status?.fact_states.proposed ?? 0], ["approved", "✓", status?.fact_states.approved ?? 0]] as [key, icon, count]}
        <button class="nav-item" class:active={view === key} onclick={() => navigate(key as View)}><span class="nav-icon">{icon}</span><span>{titles[key as View]}</span><span class="nav-count">{count}</span></button>
      {/each}
      <div class="sidebar-label category-label">MAILBOX (LOCAL ONLY)</div>
      {#each ["all", "included", "deprioritized", "skipped", "withheld", "pending"] as key}
        <button class="nav-item" class:active={view === key} onclick={() => navigate(key as View)}><span class="nav-icon">▤</span><span>{titles[key as View]}</span><span class="nav-count">{status?.views[key] ?? 0}</span></button>
      {/each}
      <div class="sidebar-bottom">
        <div class="local-status"><span class="status-dot" class:live-dot={!status?.model_unavailable}></span><div><strong>{status?.model_unavailable ? "Local model unavailable" : "Bonsai 2 · local"}</strong><small>{status?.model_unavailable ?? `Policy ${status?.policy_version ?? ""}`}</small></div></div>
        {#if status?.coverage.listed !== undefined}<small class="coverage-note">Imported {status.coverage.listed} messages from the last {status.coverage.window_days} days{status.coverage.capped ? ` (capped at ${status.coverage.max_messages})` : ""}.</small>{/if}
      </div>
    </aside>

    {#if view === "setup"}
      <section class="setup-panel" aria-label="Setup and MCP">
        <p class="eyebrow">LOCAL GMAIL PRIVACY GATEWAY</p>
        <h1>Setup & MCP</h1>
        <div class="readiness-grid">
          <article class="setup-card"><span class="demo-pill">{status?.connected ? "CONNECTED" : "NOT CONNECTED"}</span><h2>Gmail read-only</h2><p>{status?.account ?? "Run python -m companion connect --client-secrets <file>"}. Scope: gmail.readonly. The app never sends, deletes, labels, or marks mail read.</p></article>
          <article class="setup-card"><span class="demo-pill">{status?.model_unavailable ? "UNAVAILABLE" : "LOCAL"}</span><h2>Local processing</h2><p>Ternary-Bonsai-2-27B on this Mac via MLX, with rules + GLiNER identifier checks. Facts are proposals until you approve them.</p></article>
          <article class="setup-card"><span class="demo-pill">STDIO</span><h2>Claude & ChatGPT</h2><p>Add <code>python -m companion mcp</code> as a local MCP server. It can only return facts you approved, aliased per session.</p></article>
        </div>
        <section class="setup-card preview-card">
          <h2>MCP preview</h2>
          <p>This is the exact JSON an AI client receives for the same request — produced by the same serializer and privacy check as the MCP server.</p>
          <div class="action-row">
            <select bind:value={previewTool} aria-label="Tool"><option value="get_digest">get_digest</option><option value="search_facts">search_facts</option><option value="get_source_facts">get_source_facts</option><option value="get_status">get_status</option></select>
            {#if previewTool === "get_digest"}<input type="date" bind:value={previewSince} aria-label="Since" />{/if}
            {#if previewTool === "search_facts"}<input bind:value={previewQuery} placeholder="question or keywords" aria-label="Search query" />{/if}
            {#if previewTool === "get_source_facts"}<input bind:value={previewRef} placeholder="ref from an earlier result, e.g. src_1" aria-label="Source reference" />{/if}
            <button class="primary-button" onclick={runPreview}>Preview</button>
          </div>
          {#if previewResult}<pre class="preview-json">{previewResult}</pre>{/if}
        </section>
        <div class="notice"><span>i</span><p>Aliases reduce exposure but do not guarantee anonymity — context can still identify someone. Copying original email into a cloud chat bypasses the gateway.</p></div>
      </section>
    {:else if factView}
      <section class="message-column fact-column" aria-label={titles[view]}>
        <div class="list-heading"><div><p class="eyebrow">{view === "review" ? "PROPOSED BY THE LOCAL MODEL" : "ELIGIBLE FOR MCP"}</p><h1>{titles[view]}</h1>
          <p class="list-subtitle">{facts.length} facts · {view === "review" ? "nothing here leaves your Mac until you approve it" : "returned to AI clients with aliases"}</p></div></div>
        <div class="message-list">
          {#each facts as fact (fact.id)}
            <article class="fact-card review-card" class:selected-card={fact.message?.id === selectedId}>
              <div class="fact-card-head"><span class="fact-kind">{fact.category}</span>
                {#if fact.message}<button class="text-button" onclick={() => select(fact.message!.id)}>{name(fact.message.sender)} · {fact.message.subject.slice(0, 60)}</button>{/if}</div>
              {#if editing[fact.id] !== undefined}
                <textarea bind:value={editing[fact.id]} rows="3" aria-label="Edit fact"></textarea>
                <div class="action-row"><button class="primary-button" onclick={() => act(fact, "edit")}>Save & re-check</button><button class="text-button" onclick={() => { const next = { ...editing }; delete next[fact.id]; editing = next; }}>Cancel</button></div>
              {:else}
                <p class="local-text">{fact.local_text}</p>
                <div class="outgoing"><span>AI receives</span><p>{fact.outgoing_text}</p></div>
              {/if}
              {#if fact.privacy_flags.length}<p class="withheld-reason"><strong>Privacy check:</strong> detected {fact.privacy_flags.join(", ")}. Edit it out before approving.</p>{/if}
              <details class="evidence"><summary>Evidence (local only)</summary>{#each fact.evidence as item}<blockquote>{item.quote}</blockquote>{/each}</details>
              <div class="action-row">
                {#if fact.status === "proposed"}
                  <button class="primary-button" disabled={fact.privacy_flags.length > 0} onclick={() => act(fact, "approve")}>Approve</button>
                  <button class="text-button" onclick={() => (editing = { ...editing, [fact.id]: fact.local_text })}>Edit</button>
                  <button class="text-button" onclick={() => act(fact, "dismiss")}>Dismiss</button>
                {:else}
                  {#if fact.release_blocked}<span class="error-text">{blockLabels[fact.release_blocked] ?? fact.release_blocked}</span>{/if}
                  <button class="text-button" onclick={() => act(fact, "reopen")}>Withdraw approval</button>
                {/if}
              </div>
            </article>
          {:else}
            <div class="empty-list"><span>◎</span><strong>{view === "review" ? "Nothing to review" : "No approved facts yet"}</strong>
              <p>{busy ? `Working: ${status?.progress.detail}` : view === "review" ? "New proposals appear here after the local model reads included mail." : "Approve proposals in the review queue to make them available to AI clients."}</p></div>
          {/each}
        </div>
      </section>
      {@render messagePane()}
    {:else}
      <section class="message-column" aria-label="Messages">
        <div class="list-heading"><div><p class="eyebrow">YOUR GMAIL · STORED ON THIS MAC</p><h1>{titles[view]}</h1><p class="list-subtitle">{messages.length} messages</p></div><span class="demo-pill">LOCAL ONLY</span></div>
        <label class="search-box"><span aria-hidden="true">⌕</span><input bind:value={query} onkeydown={(event) => event.key === "Enter" && load()} placeholder="Search subject, sender, facts" aria-label="Search" /></label>
        <div class="date-filters"><label>From<input type="date" bind:value={from} onchange={load} /></label><label>Through<input type="date" bind:value={to} onchange={load} /></label></div>
        {#if view === "pending" && (status?.message_states.failed ?? 0) > 0}<div class="sync-strip"><strong>{status?.message_states.failed} failed</strong><p>Local model processing failed; the mail is kept and nothing was released.</p><button class="text-button" onclick={() => guard(() => api.retryFailed()).then(load)}>Retry</button></div>{/if}
        <div class="message-list">
          {#each messages as message (message.id)}
            <button class="message-row" class:selected={message.id === selectedId} onclick={() => select(message.id)}>
              <span class="sender-avatar">{name(message.sender).slice(0, 1).toUpperCase()}</span>
              <span class="message-row-content">
                <span class="message-row-top"><strong>{name(message.sender)}</strong><span class="row-type">{when(message.received_at)}</span></span>
                <span class="message-subject">{message.subject || "(no subject)"}</span>
                <span class="row-badges">{placement(message)} · {reasonLabels[message.reason] ?? message.reason}{message.fact_counts?.approved ? ` · ${message.fact_counts.approved} approved` : ""}{message.fact_counts?.proposed ? ` · ${message.fact_counts.proposed} to review` : ""}</span>
              </span>
            </button>
          {:else}
            <div class="empty-list"><span>⌕</span><strong>{status?.views.all ? "No matching messages" : "No mail imported yet"}</strong><p>{busy ? status?.progress.detail : status?.connected ? "Press Refresh to import recent mail." : "Connect Gmail from the terminal first."}</p></div>
          {/each}
        </div>
      </section>
      {@render messagePane()}
    {/if}
  </main>

  {#if announcement}<div class="announcement" role="status">{announcement}<button class="text-button" onclick={() => (announcement = "")} aria-label="Dismiss notification">×</button></div>{/if}
  <footer class="app-footer"><span><span class="footer-dot live-dot"></span> Local companion · 127.0.0.1</span><span>Read-only Gmail · nothing leaves without your approval</span><span>Policy {status?.policy_version}</span></footer>
</div>
{/if}

{#snippet messagePane()}
  <section class="detail-column" aria-label="Selected message">
    {#if detail}
      <div class="detail-scroll">
        <div class="detail-toolbar"><button class="text-button mobile-back" onclick={() => (mobileDetail = false)}>← Back</button><span class="source-label"><span class="source-dot"></span> PRIVATE SOURCE · NEVER SENT TO AI</span><a class="text-button" href={detail.gmail_url} target="_blank" rel="noreferrer noopener">Open in Gmail ↗</a></div>
        <div class="message-header"><div class="sender-avatar large">{name(detail.sender).slice(0, 1).toUpperCase()}</div><div class="sender-details"><strong>{name(detail.sender)}</strong><span>{detail.sender_address}</span></div><span class="detail-date">{when(detail.received_at)}</span></div>
        <h2 class="subject">{detail.subject || "(no subject)"}</h2>
        <section class="decision-card"><h3>Why it is {placement(detail)}</h3>
          <p>{reasonLabels[detail.reason] ?? detail.reason}{detail.model_relevance ? ` · local model chose “${detail.model_relevance}”` : ""}{detail.error ? ` · ${detail.error.replaceAll("_", " ")}` : ""}</p>
          {#if detail.privacy_hold}<p class="withheld-reason"><strong>Withheld locally.</strong> {holdLabels[detail.privacy_hold] ?? detail.privacy_hold}</p>{/if}
          {#if detail.coverage.attachments_skipped || detail.coverage.truncated}<p class="coverage-note">{detail.coverage.attachments_skipped ? "Attachments were not read. " : ""}{detail.coverage.truncated ? "Long body truncated for processing." : ""}</p>{/if}
          <div class="action-row">
            {#if detail.sender_override}<span>Rule: always {detail.sender_override} this sender</span><button class="text-button" onclick={() => setSender(null)}>Remove rule</button>
            {:else}<button class="text-button" onclick={() => setSender("include")}>Always include sender</button><button class="text-button" onclick={() => setSender("exclude")}>Always skip sender</button>{/if}
          </div>
        </section>
        {#if detail.facts.length}
          <section class="references-section"><div class="section-heading"><div><p class="eyebrow">THREAD FACTS</p><h3>Proposed and approved</h3></div></div>
            <div class="fact-list">{#each detail.facts as fact (fact.id)}<article class="fact-card" class:muted-card={fact.status === "superseded" || fact.status === "dismissed"}><div class="fact-card-head"><span class="fact-kind">{fact.category}</span><span class="fact-number">{fact.status.toUpperCase()}</span></div><p>{fact.local_text}</p>
              {#if fact.status === "proposed"}<div class="action-row"><button class="primary-button" disabled={fact.privacy_flags.length > 0} onclick={() => act(fact, "approve")}>Approve</button><button class="text-button" onclick={() => act(fact, "dismiss")}>Dismiss</button></div>{/if}</article>{/each}</div>
          </section>
        {/if}
        <article class="source-card"><div class="card-heading"><span>MESSAGE TEXT (QUOTES & SIGNATURES REMOVED)</span><span class="private-tag">LOCAL ONLY</span></div><p class="source-body">{detail.body ?? "Body not fetched — metadata rules skipped this message."}</p></article>
        {#if detail.thread.length > 1}<p class="coverage-note">Thread of {detail.thread.length} imported messages.</p>{/if}
      </div>
    {:else}
      <div class="empty-detail"><span>▤</span><h2>Select a message</h2><p>The private source view stays on this Mac. Only approved, privacy-checked facts are available to AI clients.</p></div>
    {/if}
  </section>
{/snippet}
