<img src="assets/icon.svg" width="64" height="64" alt="">

# everything-proxy

A local privacy gateway between your Gmail and AI assistants.

You want ChatGPT or Claude to answer questions like "what do I owe people this week?" or "did that deadline move?". Giving an assistant your whole mailbox sends every message, name, address, and security code to a hosted model. everything-proxy sits in between. It reads your mail on your own Mac, turns it into short task facts, and lets you approve each fact before any AI client can see it. The assistant connects over MCP and receives only approved facts, with people and organizations replaced by aliases.

Original email, credentials, and the alias mapping never leave the machine.

> **Status: personal prototype.** It runs on one macOS arm64 MacBook (36 GiB) with one Gmail account. It is not packaged, hosted, or audited. Read [Limits](#limits) before you point it at a mailbox you care about.

## How it works

```
Gmail ──(gmail.readonly)──▶ local companion ──▶ SQLite on disk (originals stay here)
                                  │
                                  ├─ 1. rules filter noise (spam, newsletters, receipts)
                                  ├─ 2. local model proposes facts (Ternary-Bonsai 2 27B, MLX)
                                  ├─ 3. identifier checks (rules + GLiNER) and aliasing
                                  ▼
                     browser review UI (127.0.0.1)
                     you approve, edit, or dismiss each fact
                                  │
                                  ▼
                 final privacy check, one serializer
                                  │
                                  ▼
              stdio MCP server ──▶ Claude Desktop, Claude Code, ...
```

1. **Read-only sync.** The companion asks Google for `gmail.readonly` and nothing else. It refuses and revokes any grant with a different scope. It imports a bounded recent window (100 messages, 30 days by default), then polls Gmail history every 5 minutes. The refresh token lives in the macOS Keychain.
2. **Deterministic filtering.** Rules sort each message into include, deprioritize, skip, or inspect, and record why. Spam, trash, drafts, and chats are skipped. Medical, financial, and intimate topics are held locally. Mail in a language other than English is withheld and never reaches the model.
3. **Local extraction.** A quantized 27B model runs on the Mac through MLX and proposes up to two short facts per message or thread, each tied to evidence in the source. The model never talks to the network.
4. **Privacy checks.** Regex rules and the [Gretel GLiNER PII](https://huggingface.co/gretelai/gretel-gliner-bi-small-v1.0) detector scan every proposed fact. People and organizations become aliases such as "Person A". A fact that still contains a detected identifier cannot be approved until you edit it.
5. **Human approval.** The browser UI shows each proposal, the exact text an AI would receive, and the evidence it came from. Nothing is released until you approve it.
6. **One release path.** The UI's MCP preview and the real MCP server use the same serializer and the same final privacy check, so the preview shows exactly what the client gets.

### MCP tools

All tools are read-only. No tool can send, draft, delete, label, or archive mail, or change a privacy setting.

| Tool | Returns |
|---|---|
| `get_status` | Sync coverage, pending work, and policy version. |
| `get_digest` | Approved facts since a date, or since an earlier digest checkpoint. |
| `search_facts` | Approved facts that match a question, optionally by date range and category. |
| `get_source_facts` | The other approved facts from the same conversation as an earlier result, by its session ref. |

## Quick start

Requirements:
- macOS on Apple silicon. The default model needs about 9 GB of disk and runs comfortably with 36 GiB RAM.
- Python 3.13 for the companion, and a separate Python 3.12 environment with `mlx-vlm` for the model.
- Node 22 to build the browser UI.
- Your own Google Cloud OAuth client (Desktop app type). [`companion/README.md`](companion/README.md) walks through creating it.

```sh
git clone https://github.com/rickkdev/everything-proxy.git
cd everything-proxy

python3.13 -m venv .venv-eval
.venv-eval/bin/pip install -r requirements-model-evaluation.txt
.venv-eval/bin/python scripts/download_models.py gliner
.venv-eval/bin/python scripts/download_models.py ternary-bonsai-2-27b-mlx-2bit

(cd browser && npm install && npm run build)

.venv-eval/bin/python -m companion connect --client-secrets ~/Downloads/client_secret_XXXX.json
.venv-eval/bin/python -m companion serve --open
```

The model runtime is expected at `~/.cache/everything-proxy/venvs/bonsai-mlx/` (Python 3.12 with `mlx-vlm`). Without it, `serve` still syncs and filters, and it tells you that extraction is disabled. Use `--no-model` to run that way on purpose.

`serve` prints a pairing code. Paste it into the page to unlock the UI. Then review proposed facts and connect an MCP client:

```sh
claude mcp add everything-proxy --env PYTHONPATH=$PWD -- $PWD/.venv-eval/bin/python -m companion mcp
```

The full guide covers the OAuth client, Claude Desktop config, review workflow, and how to disconnect. See [`companion/README.md`](companion/README.md).

## Privacy model

What stays on the Mac:
- Original messages, evidence quotes, real names, Gmail IDs, and the alias mapping, in `~/Library/Application Support/everything-proxy/` (directory mode 0700, database mode 0600).
- The Gmail refresh token, in the Keychain.
- All model inference and privacy detection.

What an AI client can receive:
- Fact text you approved, after the final privacy check, with aliases applied.
- The fact's date and category, plus a session-scoped ref such as `src_1`. Refs are not Gmail IDs and mean nothing outside the session.
- Coverage and status counts.

The browser UI binds to `127.0.0.1` only. It requires a single-use pairing code, checks the Host and Origin headers, uses CSRF tokens on every change, and sets a restrictive CSP. Email renders as untrusted text, with no HTML execution and no remote images.

## Limits

- **Aliases are not anonymity.** Context can still identify a person or reveal something confidential. Read each fact before you approve it.
- **The model is imperfect.** In synthetic evaluation, Bonsai 2 passed 12 of 16 expanded thread checkpoints. In live use it misses many useful facts. Approval exists because extraction cannot be trusted alone.
- **English only.** Other languages are withheld.
- **No attachments, images, or links** are read.
- **The database is not encrypted.**
- **macOS only**, tested on one machine.
- **Google Testing mode** expires the refresh token after 7 days. Run `connect` again when the UI says access expired.
- **Remote clients.** ChatGPT and claude.ai connectors need a remote endpoint, which is not built yet. Claude Desktop and Claude Code work today over local stdio.

## Repository layout

| Path | Contents |
|---|---|
| `companion/` | The local companion: Gmail OAuth and sync, filtering, model runner, privacy checks, release serializer, loopback HTTP server, and stdio MCP server. |
| `browser/` | Svelte review UI that the companion serves. `App.svelte` is a synthetic demo. `LiveApp.svelte` is the live UI. |
| `scripts/` | Filter rules, local store, model download, and the model and privacy evaluation harnesses. |
| `fixtures/` | Synthetic email, thread, and filter cases with expected results. No real mail. |
| `model-lock.json` | Pinned model repos, revisions, file sizes, and SHA-256 hashes. |
| `plan.md`, `build-plan.md`, `progress.md` | Product scope and privacy rules, the ordered build plan, and the build log with evidence. |
| `.audit/` | Evaluation reports, design notes, and verification records behind the decisions in `progress.md`. |

## Verify

```sh
.venv-eval/bin/python -W ignore -m unittest companion.tests.test_companion   # synthetic, no network
.venv-eval/bin/python scripts/verify_filter_rules.py                         # filter rule cases
.venv-eval/bin/python -W ignore -m companion.tests.smoke_real_model          # real model, fake Gmail
(cd browser && npm run check)
```

## License

No license yet. All rights reserved by the author until one is added.
