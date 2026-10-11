# Sequential cURL Testing Guide

Run these commands from Git Bash in the project directory. Keep the Django
server running in one terminal and execute the cURL sequence in another.

## 1. Install, migrate, test, and run

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

The remaining commands assume the API is running at `http://127.0.0.1:8000`.

```bash
BASE_URL="http://127.0.0.1:8000"
```

## 2. Register a user and provider

```bash
curl -s -X POST "$BASE_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "curl_user",
    "email": "curl_user@example.com",
    "password": "StrongPass123!",
    "role": "USER"
  }'
```

Capture the provider ID while registering:

```bash
PROVIDER_ID=$(
  curl -s -X POST "$BASE_URL/api/auth/register/" \
    -H "Content-Type: application/json" \
    -d '{
      "username": "curl_provider",
      "email": "curl_provider@example.com",
      "password": "StrongPass123!",
      "role": "PROVIDER"
    }' |
  python -c "import json,sys; print(json.load(sys.stdin)['id'])"
)

echo "Provider ID: $PROVIDER_ID"
```



## 3. Obtain authentication tokens

```bash
USER_TOKEN=$(
  curl -s -X POST "$BASE_URL/api/auth/token/" \
    -H "Content-Type: application/json" \
    -d '{"username":"curl_user","password":"StrongPass123!"}' |
  python -c "import json,sys; print(json.load(sys.stdin)['token'])"
)

PROVIDER_TOKEN=$(
  curl -s -X POST "$BASE_URL/api/auth/token/" \
    -H "Content-Type: application/json" \
    -d '{"username":"curl_provider","password":"StrongPass123!"}' |
  python -c "import json,sys; print(json.load(sys.stdin)['token'])"
)

echo "User token: $USER_TOKEN"
echo "Provider token: $PROVIDER_TOKEN"
```

Verify both accounts:

```bash
curl -s "$BASE_URL/api/auth/me/" \
  -H "Authorization: Token $USER_TOKEN"

curl -s "$BASE_URL/api/auth/me/" \
  -H "Authorization: Token $PROVIDER_TOKEN"
```



## 4. Recharge the user wallet

Create a unique reference and initiate a ₹500 recharge:

```bash
RECHARGE_REF="curl-recharge-$(date +%s)"

curl -s -X POST "$BASE_URL/api/wallet/recharges/" \
  -H "Authorization: Token $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"amount\": \"500.00\",
    \"reference\": \"$RECHARGE_REF\"
  }"
```

Complete the recharge using the mock callback:

```bash
curl -s -X POST \
  "$BASE_URL/api/wallet/recharges/$RECHARGE_REF/callback/" \
  -H "Content-Type: application/json" \
  -d '{"status":"success"}'
```

Send the same callback again to verify idempotency:

```bash
curl -s -X POST \
  "$BASE_URL/api/wallet/recharges/$RECHARGE_REF/callback/" \
  -H "Content-Type: application/json" \
  -d '{"status":"success"}'
```

The balance must still be `500.00`, not `1000.00`:

```bash
curl -s "$BASE_URL/api/wallet/" \
  -H "Authorization: Token $USER_TOKEN"
```



## 5. Create and assign a consultation

Create a session with a ₹50 per-minute rate and capture its ID:

```bash
SESSION_ID=$(
  curl -s -X POST "$BASE_URL/api/sessions/" \
    -H "Authorization: Token $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"per_minute_cost":"50.00"}' |
  python -c "import json,sys; print(json.load(sys.stdin)['id'])"
)

echo "Session ID: $SESSION_ID"
```

The initial state is `unassigned`. Assign the provider:

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/assign/" \
  -H "Authorization: Token $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_id\":$PROVIDER_ID}"
```

The returned state should be `assigned`.

## 6. Provider accepts the session

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/accept/" \
  -H "Authorization: Token $PROVIDER_TOKEN"
```

The returned state should be `accepted_by_provider`.

## 7. User starts the session

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/start/" \
  -H "Authorization: Token $USER_TOKEN"
```

The returned state should be `in_progress`. Starting is allowed because the
₹500 balance covers the required minimum of five minutes at ₹50 per minute.

## 8. Trigger per-minute billing

An immediate billing call should charge zero because no full minute has elapsed:

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/bill/" \
  -H "Authorization: Token $USER_TOKEN"
```

For a real-time two-minute test, wait slightly longer than two minutes:

```bash
sleep 125
```

Trigger billing:

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/bill/" \
  -H "Authorization: Token $USER_TOKEN"
```

Expected values include:

```json
{
  "status": "in_progress",
  "billed_minutes": 2,
  "billed_amount": "100.00"
}
```

Immediately call billing again to verify duplicate billing protection:

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/bill/" \
  -H "Authorization: Token $USER_TOKEN"
```

`billed_minutes` must remain `2`, and the wallet balance must remain `400.00`:

```bash
curl -s "$BASE_URL/api/wallet/" \
  -H "Authorization: Token $USER_TOKEN"
```



## 9. End the session

The provider can end the active session:

```bash
curl -s -X POST "$BASE_URL/api/sessions/$SESSION_ID/end/" \
  -H "Authorization: Token $PROVIDER_TOKEN"
```

Expected values include:

```json
{
  "status": "completed",
  "billed_minutes": 2,
  "billed_amount": "100.00",
  "ended_by": "provider",
  "end_reason": "Ended by provider"
}
```

Fetch the final session and wallet:

```bash
curl -s "$BASE_URL/api/sessions/$SESSION_ID/" \
  -H "Authorization: Token $USER_TOKEN"

curl -s "$BASE_URL/api/wallet/" \
  -H "Authorization: Token $USER_TOKEN"
```



## 10. Verify an invalid transition

Trying to start the completed session must return HTTP 400:

```bash
curl -i -X POST "$BASE_URL/api/sessions/$SESSION_ID/start/" \
  -H "Authorization: Token $USER_TOKEN"
```

The response includes a meaningful message similar to:

```json
{
  "detail": "Cannot start a session while it is 'completed'."
}
```



## 11. Automated regression result

Run all authentication, wallet, recharge, state-machine, permission, and billing
tests at any time:

```bash
python manage.py test --verbosity 2
```

The current suite contains 29 tests.