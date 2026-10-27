(async () => {
  const results = [];
  const settle = () => new Promise((resolve) => requestAnimationFrame(resolve));
  function check(name, condition) {
    if (!condition) throw new Error(name);
    results.push({ check: name, passed: true });
  }
  async function click(selector) {
    const element = document.querySelector(selector);
    if (!(element instanceof HTMLElement)) throw new Error(`Missing ${selector}`);
    element.click();
    await settle();
  }
  async function input(selector, value) {
    const element = document.querySelector(selector);
    if (!(element instanceof HTMLInputElement)) throw new Error(`Missing ${selector}`);
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    await settle();
  }
  async function scenario(value) {
    const element = document.querySelector("#scenario");
    element.value = value;
    element.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();
  }
  const rows = () => document.querySelectorAll(".message-row").length;
  const text = (selector) => document.querySelector(selector)?.textContent ?? "";
  const nav = (number) => click(`.sidebar > button:nth-of-type(${number})`);

  await click(".reset-demo");
  check("All 12 synthetic fixtures load", rows() === 12);
  await nav(2);
  check("Digest has 6 sources and 7 gold references", rows() === 6 && document.querySelectorAll(".digest-fact").length === 7);
  await input(".search-box input", "workshop");
  check("Search selects the matching source", rows() === 1 && text(".subject") === "Workshop format confirmed");
  await click(".filter-caption button");
  await input("input[aria-label='From demo date']", "2026-10-21");
  await input("input[aria-label='Through demo date']", "2026-10-21");
  check("Date endpoints are inclusive", rows() === 1 && text(".subject") === "Workshop format confirmed");
  await input("input[aria-label='From demo date']", "2026-10-22");
  check("Reversed dates show an error and no source", rows() === 0 && !!document.querySelector(".range-error") && !document.querySelector(".source-body"));
  await click(".filter-caption button");
  await nav(3);
  check("Withheld view includes financial, medical, and unsupported examples", rows() === 3 && text(".withheld-reason").includes("Financial"));
  const unsupported = Array.from(document.querySelectorAll(".message-row")).find((row) => row.textContent.includes("Alex Martin"));
  unsupported.click();
  await settle();
  check("Unsupported language has a reason and no references", text(".withheld-reason").includes("Unsupported language") && !document.querySelector(".fact-card"));
  if (!document.querySelector(".sender-simulation").open) await click(".sender-simulation summary");
  await click(".sender-simulation button:first-child");
  check("Sender inclusion cannot remove withholding or change the gold label", rows() === 3 && text(".withheld-reason").includes("Unsupported language") && text(".expected-label").includes("Expected inspect"));
  await click(".override-bar button");
  await nav(6);
  if (!document.querySelector(".sender-simulation").open) await click(".sender-simulation summary");
  await click(".sender-simulation button:first-child");
  check("Sender correction moves a skipped fixture", rows() === 1 && text(".subject") === "Package is on the way");
  await click(".override-bar button");
  check("Undo restores skipped fixtures", rows() === 2);
  await nav(2);
  await scenario("partial");
  check("Pending messages stay out of the digest", rows() === 5 && document.querySelectorAll(".digest-fact").length === 5 && text(".sync-strip").includes("3 messages"));
  await scenario("offline");
  check("Offline keeps loaded sources and disables reload", rows() === 6 && document.querySelector(".sync-strip button").disabled);
  await scenario("empty");
  check("Empty mailbox has no source or facts", rows() === 0 && !document.querySelector(".source-body") && !document.querySelector(".fact-card"));
  await click(".empty-list button");
  check("Reload restores fixtures without a service", rows() === 6 && document.querySelector("#scenario").value === "loaded");
  await click(".topbar > button");
  check("Unavailable integrations remain disabled", document.querySelectorAll(".setup-card button:disabled").length === 3);
  await click(".primary-button");
  const alert = Array.from(document.querySelectorAll(".message-row")).find((row) => row.textContent.includes("New sign-in blocked"));
  alert.click();
  await settle();
  check("Source URLs render as text without active links or remote media", text(".source-body").includes("https://") && !document.querySelector(".source-card a, .source-card img, .source-card iframe"));
  check("No horizontal overflow", document.body.scrollWidth === innerWidth);
  await nav(2);
  return { passed: results.length, results };
})()
