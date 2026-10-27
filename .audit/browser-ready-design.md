# Browser readiness design

The browser imports 12 synthetic evaluation messages directly. It filters by expected relevance and renders source, gold facts, and prohibited strings as escaped Svelte text. The existing digest is only a list filter. No processing, durable storage, or release service exists.

## Options

| Shape | Benefit | Cost |
|---|---|---|
| Extend the current inbox/detail shell with digest cards, local status, session-only filter simulation, dates, and setup view | Keeps existing selection and source inspection. Independent of the failed model pipeline. | All actions must clearly describe demo behavior. |
| Add a companion, persistence, review lifecycle, and real release preview now | Advances production integration | Assumes a model and boundary implementation that have not passed acceptance. Violates the current phase gate. |

Choose the first shape under Rick's request to continue the browser version. Retain the existing selected layout rather than introduce a new visual design. On narrow screens, show the list first and open selected detail with a back action.

The data shape is a `View` union, a `DemoScenario` union, and sender-keyed relevance overrides. Synthetic display dates live outside the evaluation corpus and are labelled as demo dates. Withholding derives from fixture language and local-only labels independently of simulated relevance. Partial processing excludes pending messages from the digest. Offline keeps loaded fixtures readable. Reload resets session changes. Gold facts remain immutable. No approved state or outgoing DTO is constructed.

Browser acceptance covers digest, search and inclusive date ranges, empty results and reset, withheld reasons, exact-sender simulation and undo, offline/partial/empty scenarios, setup readiness, and narrow-screen navigation. Production capabilities remain disabled with specific blockers.
