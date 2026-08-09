# Account activation

## Default production behavior

`ACCOUNT_ACTIVATION_MODE=key_present` means an account runs only when:

1. Its entry in `config/accounts.yaml` has `enabled: true`.
2. Its `key_env` environment variable contains a non-empty key.

Blank account slots are ignored safely.

## Start with one account

```env
BINANCE_SQUARE_KEY_ACCOUNT_01=YOUR_FIRST_KEY
BINANCE_SQUARE_KEY_ACCOUNT_02=
BINANCE_SQUARE_KEY_ACCOUNT_03=
BINANCE_SQUARE_KEY_ACCOUNT_04=
BINANCE_SQUARE_KEY_ACCOUNT_05=
BINANCE_SQUARE_KEY_ACCOUNT_06=
```

Expected status:

```text
account_01: active
account_02–account_06: waiting_for_key
```

## Add another account later

Add the next key to `.env`:

```env
BINANCE_SQUARE_KEY_ACCOUNT_02=YOUR_SECOND_KEY
```

The hourly worker reloads `.env` before the next cycle. Check:

```bash
curl http://SERVER_IP:8080/accounts/status
```

## Temporarily pause an account

Change its YAML entry to:

```yaml
enabled: false
```

The key may remain in the secret store; the disabled account will not receive work.

## Preview six accounts without keys

For local synthetic/demo previews only:

```env
ACCOUNT_ACTIVATION_MODE=enabled_only
```

Do not use this mode for live publishing.
