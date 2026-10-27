<script lang="ts">
  import {
    demoMessages, demoDate, effectiveRelevance, filterMessages, isPending,
    relevanceLabels, relevanceReasons, relevanceValues, scenarioLabels, withholdingReason,
    type DemoMessage, type DemoScenario, type SenderOverrides, type View,
  } from "./lib/demo";

  let view = $state<View>({ kind: "all" });
  let scenario = $state<DemoScenario>("loaded");
  let query = $state("");
  let startDate = $state("");
  let endDate = $state("");
  let selectedId = $state(demoMessages[0]?.id ?? "");
  let overrides = $state<SenderOverrides>({});
  let mobileDetail = $state(false);
  let announcement = $state("");

  const invalidRange = $derived(!!startDate && !!endDate && startDate > endDate);
  const visibleMessages = $derived(filterMessages({ view, scenario, query, startDate, endDate, overrides }));
  const selected = $derived(visibleMessages.find((message) => message.id === selectedId) ?? visibleMessages[0]);
  const pendingCount = $derived(scenario === "empty" ? 0 : demoMessages.filter((message) => isPending(message, scenario)).length);
  const withheldCount = $derived(scenario === "empty" ? 0 : demoMessages.filter((message) => withholdingReason(message)).length);
  const referenceCount = $derived(visibleMessages.reduce((count, message) => count + message.expected.facts.length, 0));
  const title = $derived(view.kind === "digest" ? "Digest examples" : view.kind === "withheld" ? "Locally withheld"
    : view.kind === "relevance" ? relevanceLabels[view.value] : "All fixtures");

  function navigate(next: View) {
    view = next;
    mobileDetail = false;
    announcement = "";
  }

  function selectMessage(message: DemoMessage) {
    selectedId = message.id;
    mobileDetail = true;
  }

  function resetFilters() {
    query = "";
    startDate = "";
    endDate = "";
  }

  function reloadFixtures() {
    if (scenario === "offline") return;
    scenario = "loaded";
    announcement = "Synthetic fixtures reloaded. No Gmail sync or model processing occurred. Session sender simulations are retained.";
  }

  function resetDemo() {
    overrides = {};
    scenario = "loaded";
    view = { kind: "all" };
    selectedId = demoMessages[0]?.id ?? "";
    resetFilters();
    mobileDetail = false;
    announcement = "Demo reset. Sender simulations and filters cleared.";
  }
</script>

<div class="app-shell">
  <header class="topbar">
    <a class="brand" href="#inbox" onclick={() => navigate({ kind: "all" })} aria-label="Everything Proxy home">
      <span class="brand-mark" aria-hidden="true">e</span>
      <span>everything<span class="brand-muted">proxy</span></span>
    </a>
    <div class="demo-status"><span class="status-dot"></span> Synthetic demo <span class="status-divider">·</span> local only</div>
    <button class="text-button" onclick={() => navigate({ kind: "setup" })}>Setup & privacy</button>
  </header>

  <main class="workspace" class:show-detail={mobileDetail} class:show-setup={view.kind === "setup"}>
    <aside class="sidebar" aria-label="Fixture views">
      <div class="sidebar-label">WORKSPACE</div>
      <button class:active={view.kind === "all"} aria-current={view.kind === "all" ? "page" : undefined} class="nav-item" onclick={() => navigate({ kind: "all" })}>
        <span class="nav-icon">▤</span><span>All fixtures</span><span class="nav-count">{scenario === "empty" ? 0 : demoMessages.length}</span>
      </button>
      <button class:active={view.kind === "digest"} aria-current={view.kind === "digest" ? "page" : undefined} class="nav-item" onclick={() => navigate({ kind: "digest" })}>
        <span class="nav-icon">✳</span><span>Digest examples</span>
      </button>
      <button class:active={view.kind === "withheld"} aria-current={view.kind === "withheld" ? "page" : undefined} class="nav-item" onclick={() => navigate({ kind: "withheld" })}>
        <span class="nav-icon">⌑</span><span>Locally withheld</span><span class="nav-count">{withheldCount}</span>
      </button>
      <div class="sidebar-label category-label">EVALUATION LABELS</div>
      {#each relevanceValues as relevance}
        <button class:active={view.kind === "relevance" && view.value === relevance} class="nav-item" onclick={() => navigate({ kind: "relevance", value: relevance })}>
          <span class="label-dot" class:include={relevance === "include"} class:inspect={relevance === "inspect"} class:skip={relevance === "skip"}></span>
          <span>{relevanceLabels[relevance]}</span>
          <span class="nav-count">{scenario === "empty" ? 0 : demoMessages.filter((message) => effectiveRelevance(message, overrides) === relevance).length}</span>
        </button>
      {/each}
      <div class="sidebar-bottom">
        <label class="scenario-label" for="scenario">DEMO SCENARIO</label>
        <select id="scenario" bind:value={scenario} onchange={() => { mobileDetail = false; announcement = ""; }}>
          {#each Object.entries(scenarioLabels) as [value, label]}<option {value}>{label}</option>{/each}
        </select>
        <div class="local-status"><span class="status-dot"></span><div><strong>No account connected</strong><small>Processing & disclosure disabled</small></div></div>
        <button class="text-button reset-demo" onclick={resetDemo}>Reset demo</button>
      </div>
    </aside>

    {#if view.kind === "setup"}
      <section class="setup-panel" aria-label="Setup and privacy">
        <p class="eyebrow">LOCAL GMAIL PRIVACY GATEWAY</p>
        <h1>Your browser workspace</h1>
        <p class="setup-intro">Explore the email workflows with synthetic data. Real email stays disconnected until the local companion and privacy checks are verified.</p>
        <div class="readiness-grid">
          <article class="setup-card"><span class="demo-pill">AVAILABLE</span><h2>Browser demo</h2><p>Search 12 fixtures, inspect source evidence, explore digest references, and simulate sender corrections. Changes last only for this tab.</p></article>
          <article class="setup-card"><span class="demo-pill">NOT CONNECTED</span><h2>Gmail read-only</h2><p>The companion and OAuth integration are not implemented. No account access is requested here. The planned scope is gmail.readonly.</p><button disabled>Connect Gmail</button></article>
          <article class="setup-card"><span class="demo-pill">BLOCKED</span><h2>Local processing</h2><p>No evaluated model passed useful and safe extraction checks. Total-system memory and long-thread behavior on a 10 GB machine remain unverified.</p><button disabled>Start processing</button></article>
          <article class="setup-card"><span class="demo-pill">UNAVAILABLE</span><h2>ChatGPT & Claude</h2><p>No MCP server, final privacy gate, or client connection exists. Evaluation references cannot be approved or released from this demo.</p><button disabled>Connect a client</button></article>
        </div>
        <section class="setup-card privacy-defaults"><h2>Planned privacy defaults</h2><ul>
          <li>Keep original email, credentials, identity mappings, and model processing on your device.</li>
          <li>Approve each proposed fact locally. Approval still requires the final privacy check.</li>
          <li>Alias people and organizations. Context can still identify someone, so aliases do not guarantee anonymity.</li>
          <li>Withhold credentials, authentication links, sensitive topics, and unsupported languages.</li>
          <li>Exclude attachments, OCR, remote images, and link following.</li>
        </ul><p>Thirty days of history and five-minute polling are proposed defaults. No import, polling, retention, or privacy-policy changes run in this demo.</p></section>
        <div class="notice"><span>i</span><p>Copying original email into a cloud chat bypasses the gateway. Source text and evidence are private views, even when shown beside a future disclosure preview.</p></div>
        <button class="primary-button" onclick={() => navigate({ kind: "all" })}>Explore fixtures</button>
      </section>
    {:else}
      <section class="message-column" aria-label="Messages">
        <div class="list-heading"><div><p class="eyebrow">LOCAL FIXTURE LIBRARY</p><h1>{title}</h1>
          <p class="list-subtitle" aria-live="polite">{visibleMessages.length} synthetic messages{view.kind === "digest" ? ` · ${referenceCount} references` : ""}</p>
        </div><span class="demo-pill">TEST DATA</span></div>
        <label class="search-box"><span aria-hidden="true">⌕</span>
          <input bind:value={query} placeholder="Search fixtures or references" aria-label="Search fixtures or references" />
          {#if query}<button class="clear-search" onclick={() => (query = "")} aria-label="Clear search">×</button>{/if}
        </label>
        <div class="date-filters"><label>From<input type="date" aria-label="From demo date" bind:value={startDate} /></label><label>Through<input type="date" aria-label="Through demo date" bind:value={endDate} /></label></div>
        <div class="filter-caption"><span>Demo dates · Oct 15 to 26, 2026</span>{#if query || startDate || endDate}<button class="text-button" onclick={resetFilters}>Clear filters</button>{/if}</div>
        {#if invalidRange}<p class="range-error" role="alert">The start date must be on or before the end date.</p>{/if}
        <div class="sync-strip" role="status"><strong>{scenarioLabels[scenario]}</strong>
          <p>{scenario === "offline" ? "Loaded fixtures remain readable. Reload is unavailable while offline is simulated."
            : scenario === "partial" ? `${pendingCount} messages simulate pending processing. Their references stay out of the digest.`
            : scenario === "empty" ? "No messages in this simulated mailbox. Reload fixtures to restore the library."
            : "Static fixture snapshot. No Gmail sync has run."}</p>
          <button class="text-button" onclick={reloadFixtures} disabled={scenario === "offline"}>Reload fixtures</button>
        </div>
        {#if view.kind === "digest"}<div class="digest-notice">Hand-written evaluation references. Nothing here is approved or available to MCP.</div>{/if}
        <div class="message-list">
          {#each visibleMessages as message (message.id)}
            <button class:selected={message.id === selected?.id} aria-pressed={message.id === selected?.id} class="message-row" class:digest-row={view.kind === "digest"} onclick={() => selectMessage(message)}>
              <span class="sender-avatar">{message.sender.slice(0, 1).toUpperCase()}</span>
              <span class="message-row-content">
                <span class="message-row-top"><strong>{message.sender.split(" <")[0]}</strong><span class="row-type">{demoDate(message).slice(5)}</span></span>
                <span class="message-subject">{message.subject}</span>
                {#if view.kind === "digest"}
                  {#each message.expected.facts as fact}<span class="digest-fact"><span class="fact-kind">{fact.type}</span>{fact.text}</span>{/each}
                  <span class="row-type">Inspect source & evidence →</span>
                {:else}<span class="message-excerpt">{message.body}</span>{/if}
                <span class="row-badges">{effectiveRelevance(message, overrides)}{overrides[message.sender] ? " · simulated override" : ""}{withholdingReason(message) ? " · withheld" : ""}{isPending(message, scenario) ? " · pending demo" : ""}</span>
              </span>
            </button>
          {:else}
            <div class="empty-list"><span>⌕</span><strong>{scenario === "empty" ? "No messages yet" : "No matching fixtures"}</strong><p>{scenario === "empty" ? "This is the empty mailbox scenario." : "Try a different search or demo date range."}</p>
              <button class="text-button" onclick={scenario === "empty" ? reloadFixtures : resetFilters}>{scenario === "empty" ? "Load synthetic fixtures" : "Clear filters"}</button>
            </div>
          {/each}
        </div>
        <footer class="list-footer">Coverage is synthetic only. No mailbox imported.</footer>
      </section>

      <section class="detail-column" aria-label="Selected fixture details">
        {#if selected}
          <div class="detail-scroll">
            <div class="detail-toolbar"><button class="text-button mobile-back" onclick={() => (mobileDetail = false)}>← Back to messages</button><span class="source-label"><span class="source-dot"></span> SYNTHETIC SOURCE</span><span class="message-id">{selected.id}</span></div>
            <div class="message-header"><div class="sender-avatar large">{selected.sender.slice(0, 1).toUpperCase()}</div><div class="sender-details"><strong>{selected.sender.split(" <")[0]}</strong><span>{selected.sender.match(/<([^>]+)>/)?.[1] ?? "Synthetic sender"}</span></div><span class="detail-date">Demo date {demoDate(selected)}</span></div>
            <h2 class="subject">{selected.subject}</h2>
            <div class="expected-label"><span class="label-dot" class:include={selected.expected.relevance === "include"} class:inspect={selected.expected.relevance === "inspect"} class:skip={selected.expected.relevance === "skip"}></span>Evaluation label <strong>{relevanceLabels[selected.expected.relevance]}</strong></div>
            <section class="decision-card"><h3>Why this label?</h3><p>{relevanceReasons[selected.expected.relevance]}</p>
              {#if withholdingReason(selected)}<p class="withheld-reason"><strong>Locally withheld.</strong> {withholdingReason(selected)}</p>{/if}
              {#if isPending(selected, scenario)}<p class="withheld-reason">Pending processing demo. References are hidden until you reload the fixture snapshot.</p>{/if}
              <details class="sender-simulation"><summary>Simulate a sender correction</summary><p>Applies to this exact synthetic sender in this tab. It changes list placement only. Gold labels, privacy restrictions, and disclosure stay unchanged.</p>
                <div class="action-row"><button class="text-button" onclick={() => { if (selected) { overrides = { ...overrides, [selected.sender]: "include" }; announcement = "Sender inclusion simulated. No reprocessing or disclosure occurred."; } }}>Simulate include</button><button class="text-button" onclick={() => { if (selected) { overrides = { ...overrides, [selected.sender]: "skip" }; announcement = "Sender exclusion simulated. No stored rule changed."; } }}>Simulate skip</button></div>
              </details>
            </section>
            <article class="source-card"><div class="card-heading"><span>MESSAGE SOURCE</span><span class="private-tag">LOCAL ONLY</span></div><p class="source-body">{selected.body}</p></article>
            <section class="references-section">
              <div class="section-heading"><div><p class="eyebrow">GOLD LABELS</p><h3>Evaluation references</h3></div><span class="reference-count">{isPending(selected, scenario) ? 0 : selected.expected.facts.length}</span></div>
              <div class="notice"><span>i</span><p>Hand-written labels, not model output or approved facts. Source and evidence stay local. No content is available to MCP.</p></div>
              {#if isPending(selected, scenario)}<div class="no-references">References hidden in the partial-processing scenario.</div>
              {:else if selected.expected.facts.length > 0}<div class="fact-list">{#each selected.expected.facts as fact, index}<article class="fact-card"><div class="fact-card-head"><span class="fact-kind">{fact.type}</span><span class="fact-number">REF {String(index + 1).padStart(2, "0")}</span></div><p>{fact.text}</p><div class="evidence"><span>Evidence in source</span><blockquote>{fact.evidence}</blockquote></div></article>{/each}</div>
              {:else}<div class="no-references">No outgoing facts expected for this example.</div>{/if}
              {#if selected.expected.local_only_facts?.length}<div class="fact-list">{#each selected.expected.local_only_facts as fact}<article class="fact-card local-fact"><span class="fact-kind">Local-only evaluation reference</span><p>{fact.text}</p><p>{fact.reason}</p></article>{/each}</div>{/if}
            </section>
            {#if selected.expected.prohibited_disclosures.length > 0}<details class="restricted-section"><summary><span>Restricted strings in fixture</span><span class="restricted-count">{selected.expected.prohibited_disclosures.length}</span></summary><p class="restricted-hint">Evaluation labels, not a runtime detector.</p><ul>{#each selected.expected.prohibited_disclosures as value}<li>{value}</li>{/each}</ul></details>{/if}
            <div class="preview-blocked"><div class="lock-badge">⌑</div><div><strong>Disclosure preview unavailable</strong><p>No extraction pipeline or final privacy gate is active. Approval, editing, and MCP release are disabled.</p><button class="text-button" onclick={() => navigate({ kind: "setup" })}>View setup requirements</button></div></div>
          </div>
        {:else}<div class="empty-detail"><button class="text-button mobile-back" onclick={() => (mobileDetail = false)}>← Back to messages</button><span>▤</span><h2>No selected fixture</h2><p>Choose a matching message to inspect its synthetic source. Empty results disclose no facts.</p></div>{/if}
      </section>
    {/if}
  </main>

  {#if Object.keys(overrides).length > 0}<div class="override-bar"><span>{Object.keys(overrides).length} sender simulation active. Gold labels unchanged.</span><button class="text-button" onclick={() => { overrides = {}; announcement = "Sender simulations cleared."; }}>Undo sender simulations</button></div>{/if}
  {#if announcement}<div class="announcement" role="status">{announcement}<button class="text-button" onclick={() => (announcement = "")} aria-label="Dismiss notification">×</button></div>{/if}
  <footer class="app-footer"><span><span class="footer-dot"></span> Local demo</span><span>No external service · no app-managed storage</span><span>Policy gate inactive</span></footer>
</div>
