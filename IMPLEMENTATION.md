# Implementation Decisions

This backend bills prepaid one-to-one consultations by the minute. The important
decisions below follow the money through the system: who can change a session,
how the wallet stays valid, how minutes are charged, what happens when balance
runs out, how retries stay safe, and what the tests lock in.

## State transitions

Sessions are a strict state machine. Only one next action is legal from each
state:

```text
unassigned
  → assigned              (user assigns a provider)
  → accepted_by_provider  (that provider accepts)
  → in_progress           (user starts)
  → completed             (user, provider, or system ends)
```

Business rules live in `sessions/services.py`, not in the views. Each service
function:

1. Opens a database transaction.
2. Locks the session row with `select_for_update()`.
3. Checks the actor and the current status.
4. Applies one transition or raises a validation error.

Role rules:

| Action | Who |
| --- | --- |
| Create | Customer (`USER`) only |
| Assign | Session customer (or staff) |
| Accept | Assigned provider only |
| Start | Session customer only |
| End | Customer or assigned provider |
| Insufficient-balance end | System |

Invalid jumps are rejected with a clear message, for example:

```text
Cannot start a session while it is 'unassigned'.
Cannot end a session while it is 'completed'.
```

A partial unique constraint also allows only one `in_progress` session per user.
If two start requests race, the database constraint is the final guard and the
service turns `IntegrityError` into a readable API error.

`completed` is terminal. A finished session cannot be billed, restarted, or
reassigned.

## Wallet balance

Money uses `DecimalField`, not floats, so amounts stay exact.

A wallet is created automatically when a user registers (`post_save` signal).
Balance starts at `0.00` and has a database check constraint:

```text
balance >= 0
```

Recharge does not credit immediately. Creating a recharge writes a `pending`
row. Balance changes only after a successful mock payment callback.

Credit and debit both happen inside `transaction.atomic()` with the wallet row
locked. Updates use `F("balance")` so the database, not Python, computes the new
value. That avoids stale read-modify-write races.

Starting a session does **not** deduct money. It only checks that the wallet
covers at least five minutes at the session rate:

```text
minimum_required = per_minute_cost × 5
```

Exact five-minute balance is allowed. Anything less stays `accepted_by_provider`
and returns HTTP 400.

## Per-minute billing

Billing charges elapsed **full** minutes only.

```text
elapsed_seconds = now - started_at
elapsed_minutes = elapsed_seconds // 60
minutes_due     = elapsed_minutes - billed_minutes
```

Examples at ₹50/minute:

| Elapsed | Newly due | Charge |
| --- | --- | --- |
| 59 seconds | 0 | ₹0 |
| 60 seconds | 1 | ₹50 |
| 2 minutes 5 seconds | 2 | ₹100 |

`billed_minutes` is a cursor. If two minutes were already billed and four
minutes have now elapsed, only minutes 3 and 4 are charged.

Each billed minute also writes a `SessionCharge` with a unique
`(session, minute_number)` constraint. Session totals (`billed_minutes`,
`billed_amount`) stay aligned with those charge rows.

Actual talk time is stored separately as `actual_talk_seconds`. A 125-second
call bills 2 minutes but still records 125 seconds for reporting.

Billing is on-demand: it runs on `POST /bill/` and again as the first step of
`POST /end/`. There is no background ticker in this assignment.

## Insufficient balance

If more minutes are due than the wallet can pay, affordable minutes are charged
in order and the rest are not. The wallet never goes negative.

```text
affordable_minutes = balance // per_minute_cost
minutes_to_charge  = min(minutes_due, affordable_minutes)
```

When the next due minute cannot be paid, the session is completed by the
system:

```text
status     = completed
ended_by   = system
end_reason = Insufficient balance
```

Example: rate ₹50, balance ₹120, 3 minutes due.

```text
Charge 2 minutes → ₹100
Remaining balance → ₹20
Billed minutes → 2
Session ends; minute 3 is never charged
```

That same path runs during `/bill/` and during `/end/`. If the system already
closed the session for insufficient funds, `/end/` returns that completed
session instead of overwriting `ended_by`.

## Idempotency

Retries must not credit a payment twice or bill the same minute twice.

**Recharges**

- `reference` is unique, so one payment cannot create two recharge rows.
- The callback locks the recharge with `select_for_update()`.
- `success` and `failed` are terminal. Repeating the same callback is a no-op.
- Changing a terminal status (success → failed, or the reverse) is rejected.
- `credited_at` is written only on the first successful credit.

**Billing**

- `billed_minutes` makes a second `/bill/` compute `minutes_due = 0`.
- `SessionCharge(session, minute_number)` is unique, so a raced insert cannot
  create a second row for the same minute.
- The session row is locked for the whole billing transaction.

**Active sessions**

- Application check plus the `one_active_session_per_user` constraint stop two
  concurrent starts for the same customer.

The mock callback is intentionally unauthenticated to model a payment webhook.
A real gateway must still verify signatures; idempotency here only prevents
duplicate ledger effects after a payload is accepted.

## Tests

The suite is API-level (`APITestCase`) and asserts both HTTP responses and
database state: wallet balance, session status, charge rows, and end metadata.

Covered cases:

- Registration creates a user and a wallet; weak passwords and invalid roles
  are rejected.
- Token login and `/me/` require authentication.
- Pending recharge does not change balance.
- Duplicate success callback credits once.
- Failed callback is idempotent and does not credit.
- Terminal callback cannot be reversed.
- Recharge list is scoped to the authenticated user.
- Provider cannot create a customer session.
- Non-provider cannot be assigned; only the assigned provider can accept.
- Invalid transitions (`end` before start, `start` while unassigned, `bill`
  after complete) return 400.
- Exact ₹250 at ₹50/minute can start; ₹249.99 cannot.
- 59 seconds bills nothing; duplicate `/bill/` charges a minute once.
- Balance exhaustion charges affordable minutes, then system-ends the session.
- Provider end records `ended_by=provider`.
- One user cannot start a second active session.
- Session list and detail are visible only to participants.
- Per-minute rate cannot be changed after create (no PATCH).

Run:

```bash
python manage.py test
```
