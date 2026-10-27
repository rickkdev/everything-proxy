# Browser readiness verification

Verified on 2026-10-27 with Node 22.18.0 and T3 Preview Chromium against the built frontend at `http://127.0.0.1:4173/`. No companion, Gmail account, model, or MCP service was used.

## Checks

`npm run check` reports zero errors and zero warnings. `npm run build` succeeds. The repeatable browser expression in `browser/scripts/verify-demo.js` returns 17 passed behavior checks. Results are in `browser-ready-results.json`. It drives the actual rendered Svelte application through DOM events. Focused T3 click/type tools independently exercised search, source selection, sender corrections, undo, setup, and mobile back navigation.

The digest has six sources and seven gold references. Search for workshop selects its source. October 21 through October 21 includes the workshop. Reversed dates display an error and no source. Withheld view has three examples with explicit reasons. Including the unsupported-language sender in a simulation preserves withholding and the original inspect label. Correcting a skipped sender reduces that list from two to one, and undo restores two.

Partial processing simulates three pending messages, reduces the digest to five sources and five references, and hides pending source references in detail. Offline simulation keeps six digest sources readable and disables reload. Empty simulation shows no source or fact cards, and fixture reload restores the digest. Setup keeps Gmail, inference, and client controls disabled.

At 390 by 844, message selection opens detail and Back to messages restores the list. A sender correction that empties the current view retains a working Back action. At 320 by 568, document width equals viewport width, the message column scrolls, and its cards remain reachable below the controls. A scroll of 450 pixels moved the first digest card into view. These are desktop Chromium viewport checks, not physical mobile-device or cross-browser certification.

Browser inspection found zero external-origin resource loads on the built page and no links, images, or frames inside the source view. The final snapshot has no application console errors. All source is rendered as escaped text. This is evidence for these fixtures and interactions, not a production CSP or arbitrary hostile-content security test.

## Artifacts

- `browser-ready-digest.png` shows the chosen inbox/detail shell with digest cards.
- `browser-ready-setup.png` shows setup requirements and disabled integrations.
- `browser-ready-mobile.png` shows narrow-screen source inspection and Back to messages.
- `browser-ready-design.md` records the data shapes and alternatives.
- `loopback-http-boundary.md` specifies the next production API boundary and future security checks. It does not claim implementation passes.

The first browser pass exposed a grid row expanding beyond the viewport. A bounded grid row fixed the unreachable scenario controls. Short-viewport verification then exposed a zero-height message list. Scrolling the whole message column on narrow screens fixed card reachability. Both fixes were verified on the browser surface. Repeating the verifier exposed that Reset demo retained the selected message ID. Reset now restores the initial selection. The final verifier passed twice consecutively against the rebuilt app.

T3 text insertion does not fill native date inputs in this session. Date checks used native input values plus bubbling input events through T3 evaluate. An ambiguous Clear filters locator matched two buttons in the empty state. The check was corrected to target `.filter-caption button`. A sender-correction summary retained its open state when selection changed, so verification inspected that state before opening it. These tool/locator retries are not claimed as app behavior failures.

## Limits

Gold labels are immutable test references. Sender changes are tab-only list simulations. Dates are invented demo metadata. Reload is a static fixture reset, not sync. Offline and pending states are selected scenarios, not observed network or worker outages. No fact approval, final privacy gate, real tool response, persistence, API security guarantee, target-memory fit, or Gmail integration is claimed.

One agent performed the work per Rick's repository instructions. No independent review, commit, PR, deployment, or publication occurred. The production integration gate stays closed.
