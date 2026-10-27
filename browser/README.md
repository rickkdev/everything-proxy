# Everything Proxy synthetic browser demo

This browser demo loads the repository's 12 synthetic evaluation fixtures. It includes an inbox, digest cards, search, inclusive demo-date filters, withheld-message reasons, source evidence, and setup readiness. The Vite server binds to `127.0.0.1` only.

The displayed references are evaluation gold labels. They are not model output, approved facts, or MCP responses. Gmail access, model inference, persistence, and disclosure are disabled. The app makes no external runtime requests and writes no app-managed data; Vite serves the fixture bundle from localhost.

## Run in a browser

Use Node 22.18.0 or another Node 22 release satisfying the `engines` range. From this directory:

```sh
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://127.0.0.1:5173`. Stop the server with Ctrl+C when finished. For a production frontend bundle, use `npm run build`; preview that bundle locally with `npm run preview`.

This is only the synthetic fixture UI. Production use still requires a local companion for Gmail, storage, inference, privacy enforcement, and MCP. No public hosting or deployment is configured.

## Try the browser workflows

1. Open **Digest examples** to see seven gold references across six messages. Select a card to inspect its source evidence.
2. Search for `workshop`. Use **From** and **Through** to select October 21, 2026. Both endpoints include that day.
3. Open **Locally withheld** to inspect financial, medical, and unsupported-language examples. Relevance and disclosure restrictions are independent.
4. Open **Expected skip**, expand **Simulate a sender correction**, and select **Simulate include**. The exact sender moves out of the skipped list. Use **Undo sender simulations** to restore the original view. This does not reprocess messages or create a stored rule.
5. Use **Demo scenario** to try offline, partial-processing, and empty-mailbox states. **Reload fixtures** restores the loaded snapshot except in offline mode. **Reset demo** also clears filters and sender simulations.
6. Open **Setup & privacy** to see the production requirements. Gmail, processing, and client connection controls remain disabled.

Demo dates are invented display metadata from October 15 to 26, 2026. They are not received dates or dates extracted from source text. Browser reload clears all session-only changes. Narrow screens open message details separately with **Back to messages**.

## Verify the demo

Run `npm run check` and `npm run build`. Start `npm run preview`, then open `http://127.0.0.1:4173` in the shared preview or a local Chromium browser.

Evaluate the contents of `scripts/verify-demo.js` in that page's browser console or T3 Preview evaluate tool. The expression returns 17 passing behavior checks and finishes in the digest view. It resets current demo state. The checks use DOM events against the real built UI. They do not verify a production API, model quality, actual offline caching, or MCP parity.

Resize to 390 by 844 and verify message selection and **Back to messages**. At 320 by 568, scroll the message column to reach cards below the controls. These are viewport checks, not claims of Safari, Firefox, or mobile-device compatibility.
