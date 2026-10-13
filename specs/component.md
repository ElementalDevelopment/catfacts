# CatFacts: a small fact, a better day

This specification is the authority for application behavior. The implementation
is inspired by Literate AI's specification-led approach, not onboarded into its CLI.

## Catalogue contract
Keep facts in SQLite with stable identifiers, category, source URL, provenance,
review status, and optional image plus attribution link. Serve only reviewed facts.
Preserve imported Wikipedia article snapshots and revision identifiers. Imports
produce candidates, never automatically publish unreviewed claims. A local CLI
handles review; the public web interface cannot modify the catalogue.

## Slack contract
For one configured workspace, respond to app mentions, human direct messages,
and /catfact. Ignore bot messages and message subtypes. Authenticate raw request
bytes with HMAC SHA256 and reject timestamps older than five minutes. Acknowledge
events after durable enqueue, then deliver in a background worker. Deduplicate
event identifiers. Retry transient delivery failures with bounded backoff and
retain failures. Replies include a source link and optional attributed image.
Commands return an ephemeral reply immediately. No credentials enter browser code.

## Browser contract
Show a random reviewed fact, source and optional image, searchable catalogue,
category filters, real database totals, and Slack configuration status. Render
external text as text, not HTML. Work without Slack credentials.

## Acceptance
Prove forged/stale requests cannot enqueue work; valid signed challenges succeed;
duplicate events enqueue once; bot events do not enqueue; candidates never reach
random output; source/image attribution survives formatting; HTTP routes work.

## Operating boundary
Single server and single worker, SQLite on persistent disk, HTTPS reverse proxy in
deployment. This is a single-workspace app, not a public OAuth installation service.
Slack delivery is at least once: a crash after Slack accepts a post and before the
database commit may duplicate that post. Dead jobs need local operator review.
