# Solved notifications

The middleware checks tickets in `ticket_mapping.json` every 30 seconds. A
transition to GLPI status `5` (Solved) sends the mapped WhatsApp requester:

> ✅ Update Tiket #16
>
> Status laporan Anda sudah *Solved (Selesai)*.
> Tim IT telah menyelesaikan penanganan laporan Anda.
>
> Jika kendala masih terjadi, silakan balas pesan ini. Terima kasih.

Each ticket's first observation establishes a baseline without sending a
notification, including tickets already solved or closed before deployment.
Only mapped tickets are monitored. Closed (status `6`) does not send another
notification. A reopened ticket can trigger a new notification when solved again.

State and pending sends persist in the existing SQLite state database, in the
additive `ticket_status_notifications` table. Failed API requests or sends are
retried on subsequent polls without blocking other tickets. A pending Solved
notification is cancelled if the ticket changes status before a successful send.
GLPI reads require verified TLS.

Before triaging a new inbound message for an existing conversation, the
middleware reads its GLPI ticket status. Solved/Closed conversations expire
before AI receives context, so the next incident creates a fresh ticket without
reusing the previous incident's collected fields. Failed GLPI status reads defer
message processing for retry rather than appending to an unchecked ticket.
Once triage has enough information, a conversation-scoped confirmation tells
the requester the report is complete and has been passed to IT; successful
confirmations are recorded to prevent repeated polling sends.

Successful sends are recorded to suppress repeat polling notifications. Like the
existing WhatsApp sender, delivery is not transactional with SQLite: a crash
after WAHA accepts a message but before the local commit can cause a duplicate
on retry. Transitions that occur entirely between polls cannot be observed.

Validation: `python -m pytest -q wa-glpi/tests`. The status notifier tests cover
baseline behavior, Solved-only notifications, duplicate suppression, send retry,
reopen/solve cycles, cancellation, per-ticket failure isolation, and TLS.

## Public dashboard replies

Public Ticket follow-ups are read across all GLPI result pages using stable ID
ordering and the actual `Content-Range`, including servers with a smaller page
size than requested. Private notes, other item types, and marked inbound
WhatsApp follow-ups are excluded. HTML is converted to plain text before send.
Successful sends are recorded per follow-up ID in `outbound_replies`, so a later
failure does not resend earlier successful replies when the cursor is retried.
All pages must load successfully before any replies are sent or the cursor moves.

Deployment recovery on 2026-10-28 preserved the old cursor (`15`) in the server
backup and established `101` as the historical baseline before ticket #18.
Pending public follow-ups #103 and #105 were then delivered and cursor advanced
to `105`; historical GLPI records were retained without replaying old messages.

## Greeting auto response

Simple greetings such as `HI`, `Halo`, and `Selamat pagi` receive a welcome
message with instructions for reporting an issue. These greetings bypass AI and
GLPI, create no ticket, and do not alter active conversation fields. Successful
welcome sends are persisted by hashed recipient in `welcome_replies`, with a
10-minute cooldown that survives restarts. Failed sends remain retryable.
Greeting-only AI classifications also use this welcome path when no conversation
is active. Messages combining a greeting with an issue still go through triage.
