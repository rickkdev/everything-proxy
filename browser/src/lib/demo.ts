import fixtureData from "../../../fixtures/email-evaluation.json";

export const demoMessages = fixtureData.messages;
export type DemoMessage = (typeof demoMessages)[number];
export type ExpectedRelevance = DemoMessage["expected"]["relevance"];
export const relevanceValues: ExpectedRelevance[] = ["include", "deprioritize", "skip", "inspect"];
const supportedLanguages = new Set<string>(fixtureData.language_support);

export const relevanceLabels: Record<ExpectedRelevance, string> = {
  include: "Expected include",
  deprioritize: "Expected deprioritize",
  skip: "Expected skip",
  inspect: "Expected inspect",
};

export type View =
  | { kind: "all" }
  | { kind: "digest" }
  | { kind: "withheld" }
  | { kind: "setup" }
  | { kind: "relevance"; value: ExpectedRelevance };
export type DemoScenario = "loaded" | "offline" | "partial" | "empty";
export type SenderOverride = "include" | "skip";
export type SenderOverrides = Partial<Record<string, SenderOverride>>;

export const scenarioLabels: Record<DemoScenario, string> = {
  loaded: "Loaded fixtures",
  offline: "Offline demo",
  partial: "Partial processing demo",
  empty: "Empty mailbox demo",
};

const partialPendingIds = new Set(demoMessages.slice(0, 3).map((message) => message.id));

export function isPending(message: DemoMessage, scenario: DemoScenario): boolean {
  return scenario === "partial" && partialPendingIds.has(message.id);
}

export function demoDate(message: DemoMessage): string {
  return `2026-10-${String(15 + demoMessages.indexOf(message)).padStart(2, "0")}`;
}

export function withholdingReason(message: DemoMessage): string | undefined {
  if (!supportedLanguages.has(message.language)) {
    return "Unsupported language. Extraction support has not been evaluated for this language.";
  }
  if (message.expected.local_only_facts?.length) {
    return message.expected.local_only_facts.map((fact) => fact.reason).join(" ");
  }
  return undefined;
}

export function effectiveRelevance(message: DemoMessage, overrides: SenderOverrides): ExpectedRelevance {
  return overrides[message.sender] ?? message.expected.relevance;
}

export const relevanceReasons: Record<ExpectedRelevance, string> = {
  include: "The evaluation expects a direct request, commitment, decision, or meaningful change.",
  deprioritize: "The evaluation treats this newsletter as lower priority. Automation alone is not an exclusion rule.",
  skip: "The evaluation expects this routine receipt or shipment notice to be omitted from task facts.",
  inspect: "The evaluation requires local inspection. Relevance does not grant permission to disclose content.",
};

export function filterMessages(options: {
  view: View;
  scenario: DemoScenario;
  query: string;
  startDate: string;
  endDate: string;
  overrides: SenderOverrides;
}): DemoMessage[] {
  const { view, scenario, startDate, endDate, overrides } = options;
  const query = options.query.trim().toLocaleLowerCase();
  if (scenario === "empty" || view.kind === "setup") return [];
  return demoMessages.filter((message) => {
    const relevance = effectiveRelevance(message, overrides);
    const matchesView = view.kind === "all"
      || (view.kind === "withheld" && !!withholdingReason(message))
      || (view.kind === "relevance" && relevance === view.value)
      || (view.kind === "digest" && relevance === "include"
        && !withholdingReason(message) && !isPending(message, scenario)
        && message.expected.facts.length > 0);
    const date = demoDate(message);
    const searchable = [message.id, message.sender, message.subject, message.body,
      ...message.expected.facts.map((fact) => fact.text)].join(" ").toLocaleLowerCase();
    return matchesView && (!startDate || date >= startDate) && (!endDate || date <= endDate)
      && (!query || searchable.includes(query));
  });
}
