# Local browser API threat design

Status is design complete, implementation and security verification pending. This is the next boundary after the static synthetic checkpoint. No sensitive data is connected by this document.

## Assets and attackers

Protect original email, OAuth credentials, identity mappings, review state, and privacy settings from remote websites, DNS rebinding, forged browser requests, compromised email HTML, and accidental public binding. A process running as the same OS user can already read application memory and files and is outside this HTTP boundary. Browser extensions and a compromised browser remain risks.

## One origin and explicit pairing

The companion serves bundled UI assets and its private API from one fixed `http://127.0.0.1:<port>` origin. Bind the socket to `127.0.0.1` only. Fail startup on a busy port rather than bind more broadly or silently change origins. Do not enable a wildcard CORS response, reverse proxy, LAN listener, or hosted UI access. MCP uses a separate local stdio adapter with no private HTTP route forwarding.

An unauthenticated asset request may return only public static assets. At startup the companion generates a cryptographically random, single-use 256-bit pairing secret and displays it in its local terminal. Open the plain local URL. The user enters the secret into the pairing form. Never place it in a query string, fragment, browser storage, process arguments, or logs. The terminal display is intentional local delivery. Expire the secret after five minutes or one successful use. Rate-limit pairing attempts globally and per process instance. There is no API that reveals or regenerates this secret remotely.

`POST /session` authenticates with that secret in an Authorization header. It accepts only the configured Origin, `Sec-Fetch-Site: same-origin` when present, JSON content type, and a fixed pairing DTO. Reject absent Origin for this browser-only route. On success, issue a random in-memory session cookie with HttpOnly, SameSite=Strict, Path=/, and no Domain. Since this design uses loopback HTTP, do not claim transport encryption or rely on the Secure flag. Cookie expiry is 30 minutes of inactivity, bounded by eight hours absolute. Restart revokes every session. Return a separate random CSRF token in the JSON response and retain it in UI memory only. A browser reload retrieves the CSRF token through an authenticated same-origin read. Never persist it in web storage.

## Request validation order

1. Validate Host before static assets, pairing, API handling, or error construction. Accept only the exact configured `127.0.0.1:<port>` authority. Reject alternative IP encodings, arbitrary hostnames, forwarded-host overrides, and multiple Host values. Do not trust forwarding headers. This stops a hostname that rebinds to loopback from becoming an accepted origin.
2. For every request with Origin, require an exact configured-origin match. Reject `null`, suffix matches, and other loopback ports. For requests with Sec-Fetch-Site, require `same-origin`. A top-level static navigation may use `none`. Static requests without those headers still receive only public assets.
3. Authenticate every `/api/` request with the current session cookie, including status, source viewing, CSRF reads, and preview. API requests without browser metadata still require authentication. Pairing is the only alternative credential exchange and verifies its bootstrap Authorization secret. Reject unauthorized requests with fixed responses before inspecting private state.
4. Mutations require POST, PUT, or DELETE, exact Origin, same-origin Fetch Metadata when present, JSON content type, and the session-bound CSRF header. GET never changes review, sync, settings, or account state. Reject form and text/plain submissions. Logout also needs CSRF validation. Rotate CSRF state with the session and revoke it on logout.
5. Parse closed DTOs with strict size and range limits. Reject unknown fields, arbitrary paths, provider IDs, fetch URLs, and executable input. Use fixed route registries. No arbitrary filesystem or proxy endpoint exists. Apply local request deadlines and bounded concurrency.

Return no CORS permission headers. Handle OPTIONS through the same Host/origin checks and deny cross-origin preflights. Set Cache-Control: no-store on API, pairing, and private responses, including failures. Set Referrer-Policy: no-referrer, X-Content-Type-Options: nosniff, and frame-ancestors 'none'. No service worker or private response cache is allowed.

## Content and service isolation

Serve production scripts and CSS from local assets. CSP is `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'`. Use external CSS and no inline event handlers or dynamic code evaluation. Set CSP as an HTTP response header. Vite development exceptions do not apply to the companion release.

Render email as text, without HTML execution, linkification, remote images, attachments, or embedded frames. Source access stays behind the authenticated private API and requires an internal opaque local message handle. It cannot accept an arbitrary Gmail ID or URL. Do not include private exception details in errors. Session and OAuth secrets never enter routine logs.

Private UI operations call account, review, source, and settings services. Preview calls the same ReleaseService as MCP. Only ReleaseService public DTOs cross MCP stdio. MCP has no route to pairing, settings, source text, approval, OAuth, or identity mappings. Approval remains insufficient without current evidence and a successful final privacy check.

## Required implementation evidence

- Bind check proves no LAN listener. Requests with forged Host, DNS-rebinding hostname, alternate port, null Origin, cross-site Fetch Metadata, and duplicate Host fail before private handlers.
- Public assets contain no credentials or private data. URL and access logs contain no bootstrap secret. Pairing rejects expired, reused, and incorrect secrets and throttles retries.
- Every private read fails without a valid session. Restart, logout, idle expiry, and absolute expiry revoke access. Cookie attributes and no-store headers are inspected in a real browser.
- Same-origin authenticated review works with the correct CSRF token. Missing, forged, other-session, cross-site form, and GET mutation requests fail without changing state.
- CSP blocks remote resources, inline scripts, framing, and injected email HTML. Browser console and network inspection confirm this on the production companion, not Vite.
- MCP cannot invoke private UI operations. Preview equals MCP output for the same snapshot. Source and policy invalidation fail closed during release.

These are acceptance checks for future implementation. No pass is claimed. Supported operating systems and browsers, OS storage protection, target memory, and a useful safe extraction pipeline remain separate gates.
