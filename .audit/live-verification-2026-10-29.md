# Live verification and remote MCP plan (2026-10-29)

Rick asked the agent (Opus 5.5) to pair a browser with the running companion, judge whether the released email data is clean, and check whether the MCP server can be connected to ChatGPT or Claude on the web. Rick authorized the agent to read the local source view for this review. The agent read the bodies of 7 of the 21 imported messages. It approved, dismissed, and edited no facts.

## What works

| Check | Result | Evidence |
|---|---|---|
| Pairing | Pass | Code from the running `serve` output, entered in the T3 preview browser. Session cookie set. Only the expected pre-pairing 401 appeared. |
| Browser views | Pass | Review queue has 2 facts. Approved has 1. All 21, Included 3, Deprioritized 16, Withheld 2, Pending 0. |
| Released text contains no identity | Pass | The single approved fact is "A new sign-in was detected on a Mac OS device." The source contains the Gmail address and Google's postal address, and neither is released. |
| Identity probes | Pass | `search_facts` over stdio for Rick's first name, last name, and handle, two company names, GDPR, erasure, google, and a request ID returned no facts. |
| Preview and MCP parity | Pass | The `get_digest(since=2026-10-20)` text from the browser preview equals the stdio MCP text byte for byte. |
| Real client | Pass | `claude -p` with `--mcp-config` ran `get_status` and `get_digest` against the stdio server. It received one fact and saw no names or addresses. |

## Quality findings

1. Recall is very low for this mailbox. 15 of 21 messages are replies to Rick's GDPR or privacy requests. The model proposed one fact from them. It deprioritized messages that ask Rick to act: Company B (through a privacy vendor) asks him to verify his identity, and Company A says it holds no data and names the next step. A confirmation request from a privacy vendor produced malformed output. The prompt `6-security-scope` was tuned for security alerts and a small synthetic corpus. It does not cover "a company needs something from you" well.
2. Facts drop the counterparty. "The GDPR data erasure request was completed." does not say which company completed it. With 15 replies in the inbox, the fact cannot answer "which ones are done". The model omitted the name, so aliasing did not cause this. Business sender names are low-risk and high-value here. Whether to release them is Rick's call.
3. Two Google sign-in alerts on different days produce identical fact text. The release includes the date, so the client can tell them apart. Not a defect.
4. A developer newsletter is withheld as `sensitive_topic`. This is a false positive, and the cost is only a lost newsletter.
5. The Company A body keeps a quoted Outlook reply. Its header is one line (`From: … Sent: … To: … Subject: …`), and `_QUOTE_HEADERS` expects `Sent:` on the next line. The same body still shows `&lt;` and `&gt;`, so HTML entities are not decoded on this path. Both stay local, but the model reads extra, noisy text.
6. The browser preview creates a new `ReleaseSession` per call. `get_source_facts` in the preview therefore always returns `unknown reference`. Over stdio it works.
7. Still open from 2026-10-28: SIGTERM on `serve` orphans the MLX server on port 18229.

## Remote MCP readiness

- Claude Desktop and Claude Code: ready now. Both run the stdio server locally. Configuration is in `companion/README.md` step 5.
- ChatGPT: close. OpenAI's Secure MCP Tunnel runs `tunnel-client` on this Mac. It polls OpenAI outbound, and `--mcp-command` accepts a stdio server. The existing `python -m companion mcp` should work without code changes. No inbound port opens.
- Claude on the web (claude.ai): not ready. Custom connectors are called from Anthropic's servers and need a public HTTPS Streamable HTTP endpoint. Without OAuth, anyone with the URL could read approved facts, so OAuth is required in practice. The companion has neither.

## Plan

### A. ChatGPT through Secure MCP Tunnel (about half a day, mostly Rick's account steps)

1. Rick confirms that his ChatGPT plan shows Developer mode and the Tunnel connection option. He also authorizes approved facts going to OpenAI.
2. Rick creates a tunnel in OpenAI Platform settings and associates it with his ChatGPT workspace. This needs a Platform API key with Tunnels permissions.
3. Code: add `annotations: {"readOnlyHint": true}` to each tool in `companion/mcp_server.py` so that ChatGPT does not treat the tools as write actions. Add an `everything-proxy tunnel` note to the README.
4. Run `tunnel-client init --mcp-command "<repo>/.venv-eval/bin/python -W ignore -m companion mcp"` with `PYTHONPATH=<repo>`. Then run `doctor` and `run`.
5. In ChatGPT, add a custom MCP server with Connection set to Tunnel.
6. Verify: ChatGPT's `get_digest` result matches the browser preview byte for byte, identity probes return nothing, and stopping `tunnel-client` cuts access.

### B. Claude on the web (2 to 3 days, needs Rick's authorization to publish an endpoint)

1. `companion/mcp_http.py`: a Streamable HTTP `/mcp` endpoint on its own loopback port. It calls the same `handle()` and `ReleaseService`. No UI or source routes share the port.
2. OAuth 2.1 with PKCE and dynamic client registration. Protected-resource and authorization-server metadata. Consent happens in the paired local UI, so only Rick can approve a client. Short-lived tokens, plus revocation in Setup & MCP.
3. Public reachability: a Cloudflare named tunnel or similar that forwards only `/mcp`, `/.well-known/*`, and the OAuth endpoints to that port.
4. Verify: add the connector in claude.ai, check that unauthenticated calls get 401, check digest parity with the preview, and confirm that revoking the token cuts access.

Recommendation: do A first, and use Claude Desktop for Claude until B is worth the public endpoint. Fix recall (finding 1) before either. A connector that returns one fact out of 21 messages will not feel useful.

### C. Make the facts worth connecting (1 to 2 days)

1. Add 6 to 8 synthetic fixtures shaped like these replies: verification needed, completed, no data held, and contact the controller. Score the current prompt on them.
2. Add a prompt variant that extracts "a company needs X from you" and "a company completed X", and names the business sender. Keep the reviewed gate. Accept the variant only if it passes the existing cases as well.
3. Decide on finding 2: release business sender names (not people) as plain text.
4. Done 2026-10-29: findings 4, 5, 6, and 7 are fixed (see `progress.md`).
