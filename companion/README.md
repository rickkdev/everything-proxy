# Test with your Gmail and Bonsai 2

The local companion reads Gmail with `gmail.readonly`. Ternary-Bonsai-2-27B runs on your Mac to propose facts. You approve each fact in the browser. AI clients receive only facts you approved, after a final privacy check, with people and organizations aliased.

Everything runs on this Mac. Nothing is deployed or hosted.

## 1. Create a Google OAuth client (one time, about 5 minutes)

Google requires your own OAuth client for a personal read-only app.

1. Open <https://console.cloud.google.com/>, create a project such as `everything-proxy`.
2. **APIs & Services → Library**: enable **Gmail API**.
3. **Google Auth Platform → Branding/Audience**: user type **External**, publishing status **Testing**. Add your Gmail address under **Test users**.
4. **Data Access**: add the scope `https://www.googleapis.com/auth/gmail.readonly`. Add no other scope.
5. **Clients → Create client**: type **Desktop app**. Download the JSON file.

> In *Testing* status, Google expires the refresh token after 7 days. When that happens, the UI shows "Gmail access expired". Run step 2 again.
>
> For a Google Workspace address, such as a company domain, the admin may block unverified third-party apps. A personal `@gmail.com` account avoids this.

## 2. Connect Gmail

```sh
cd ~/.t3/projects/everything-proxy
.venv-eval/bin/python -m companion connect --client-secrets ~/Downloads/client_secret_XXXX.json
```

Your browser opens Google's consent screen. Confirm that it asks only to *read* your email. The companion refuses and revokes any grant whose scope differs from `gmail.readonly`. The refresh token goes into the macOS Keychain under the service name `everything-proxy.gmail`.

## 3. Start the companion

```sh
(cd browser && npm install && npm run build)   # once, and after UI changes
.venv-eval/bin/python -m companion serve --open
```

- The terminal prints a **pairing code**. Paste it into the page. Press Enter in the terminal for a new code.
- The first import reads up to the **100 most recent messages from the last 30 days**. Spam, trash, drafts, and chats are excluded. Change the limit with `--max-messages 300` or `--window-days 14`.
- Bonsai 2 loads on the first message that needs it, in about 10 s. It then needs about 8 s per message or thread. The UI shows progress. Use `--no-model` to test sync and filtering only.
- The companion polls Gmail every 5 minutes. **Refresh** in the UI triggers a sync immediately.

## 4. Review

- **Review queue** shows the facts Bonsai proposes. Each fact shows the local text, the exact text an AI would receive, and the evidence. Use **Approve**, **Edit** (the edited text is rechecked), or **Dismiss**.
- You cannot approve a fact that contains a detected identifier. Edit the identifier out first. For example, GLiNER sometimes treats counts like "84" as a PIN.
- **Mailbox** views show each message's local placement and why it got there. **Always include sender** or **Always skip sender** corrects a sender. Its messages are then reprocessed.
- **Setup & MCP → MCP preview** shows the exact JSON that an MCP client receives.

## 5. Connect Claude Desktop or Claude Code

Claude Desktop, in `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "everything-proxy": {
      "command": "/Users/rickkdev/.t3/projects/everything-proxy/.venv-eval/bin/python",
      "args": ["-m", "companion", "mcp"],
      "env": { "PYTHONPATH": "/Users/rickkdev/.t3/projects/everything-proxy" }
    }
  }
}
```

Claude Code:

```sh
claude mcp add everything-proxy --env PYTHONPATH=$PWD -- $PWD/.venv-eval/bin/python -m companion mcp
```

Tools: `get_status`, `get_digest`, `search_facts`, `get_source_facts`. The MCP server reads the local database directly. It returns approved facts even while `serve` is stopped, but sync only runs while `serve` runs. ChatGPT needs a remote tunnel, which this version does not include.

## What stays local, and the known limits

- Original email, evidence quotes, real names, Gmail IDs, and credentials stay in `~/Library/Application Support/everything-proxy/` (directory mode 0700, database mode 0600) and the Keychain. The database is **not encrypted**.
- Only **English** mail is processed. German and other languages are withheld locally and never reach the model. A German-heavy inbox will show many withheld messages.
- Medical, financial, and intimate topics, detected by keyword rules, are withheld locally.
- Attachments, images, and links are not read. Quoted replies and signatures are stripped before processing.
- Synthetic evaluation scored Bonsai 2 at 12 of 16 expanded thread checkpoints. It can miss or misstate facts, which is why every fact needs your approval.
- Aliases ("Person A") reduce exposure but do not guarantee anonymity.

## Disconnect

```sh
.venv-eval/bin/python -m companion disconnect      # revokes the grant at Google and deletes it from the Keychain
rm -rf ~/Library/Application\ Support/everything-proxy   # deletes all local mail data
```

## Verify

```sh
.venv-eval/bin/python -W ignore -m unittest companion.tests.test_companion   # 24 synthetic tests, no network
.venv-eval/bin/python -W ignore -m companion.tests.smoke_real_model         # real Bonsai 2 + GLiNER + MCP stdio, fake Gmail
```
