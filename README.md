# CatFacts

A web catalogue and single-workspace Slack bot for sourced feline discoveries.
The seed contains 137 paraphrased facts, with Wikipedia revision links and
Wikimedia image attribution where available, plus a Library of Congress source.
Twenty preserved Wikipedia articles supply a larger candidate pool for review.

## Run locally

Python 3.12 or newer; no third-party packages required.

```sh
make run
```

Open http://localhost:3000. Search, select a topic, shuffle, or copy a fact with
its citation. SQLite is created automatically in `data/catalog.sqlite3`.

```sh
make check
```

## Connect Slack

1. Deploy this server behind an HTTPS reverse proxy with a persistent database.
2. Replace both `https://YOUR-DOMAIN` URLs in `slack-manifest.json`. Create a Slack
   app from that manifest at https://api.slack.com/apps.
3. Obtain the signing secret from Basic Information. Install the app in your
   workspace, copy the bot token, and obtain the workspace's team ID.
4. Set `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`, and `SLACK_TEAM_ID` in your hosting
   provider's secret environment. `.env.example` lists all options; the application
   reads process environment variables and does not automatically load `.env`.
5. Start/restart the server and enable Event Subscriptions. Slack verifies the
   signed challenge at `/slack/events`. Invite the bot to a channel and mention it,
   DM it, or use `/catfact`. `/catfact Senses` limits the result to that category.

Mentions and DMs receive threaded replies. Slash commands return an ephemeral
fact. Normal channel messages are not subscribed to. No live Slack messages have
been sent during development. Credential status in the web UI means variables
are configured, not that Slack has verified the installation.

## Grow the database

```sh
python3 scripts/catalog.py wikipedia
python3 scripts/catalog.py candidates
python3 scripts/catalog.py review FACT_ID approved
python3 scripts/catalog.py review FACT_ID rejected
python3 scripts/catalog.py import path/to/facts.json
```

The Wikipedia importer saves source snapshots and revision IDs. Existing snapshots
are reused; move one aside to fetch a new revision. Imported sentences are **raw
candidates**, not independently verified claims. Review context and references,
edit/paraphrase a candidate if needed, and approve only accurate, self-contained
facts. For additional internet sources, import a JSON array with `text`, `category`,
`source` (HTTPS), and `source_title`. Optional `image` and `image_credit` fields
must point to Wikimedia and its file attribution page. Imported approval flags are
ignored. `data/seed.json` demonstrates the format.

The seed was checked against the gathered article text, not independently against
every underlying scientific paper. Sources can disagree or evolve; review new
evidence before updating facts. Wikipedia adaptations are provided under
CC BY-SA 4.0; each fact links its source revision. Article snapshots retain original
text under Wikipedia's terms. Image licenses and creators are on linked Wikimedia
file pages. Images are illustrative and may fail independently of fact delivery.

## Design and operations

[The specification](specs/component.md) is the behavioral authority. Small modules
explain the catalogue, request boundary, and delivery flow; acceptance tests check
the public promises. This follows the principles of
[Literate AI](https://github.com/ElementalDevelopment/literate-ai), without claiming
formal LitAI onboarding, generated-source receipts, or framework certification.

The server verifies Slack HMAC signatures against raw bytes and rejects stale
requests, persists event IDs before acknowledgement, and processes a durable queue
with bounded retries. Configure one server process and one worker. SQLite must
live on persistent local storage. Do not run multiple replicas against this queue.
Back up SQLite using its backup API. An uncertain delivery outcome can duplicate a
message; this is at-least-once delivery, not exactly-once delivery.

`/api/status` reports pending/sent/dead counts. Dead deliveries retain the error
class without secrets. Inspect local jobs and resolve configuration errors before
retrying with `python3 scripts/catalog.py retry EVENT_ID`.

For Docker, build with `docker build -t catfacts .`, provide the three Slack secret
environment variables and mount a writable volume at `/store`. Publish port 3000
behind your HTTPS proxy. The image runs as an unprivileged user. This project does
not include hosting credentials or a public OAuth flow for multiple workspaces.

References: [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/),
[Events API](https://docs.slack.dev/apis/events-api/),
[posting messages](https://docs.slack.dev/reference/methods/chat.postMessage/).
