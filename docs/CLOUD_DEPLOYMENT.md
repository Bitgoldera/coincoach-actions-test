# Cloud deployment

## Recommended split

1. Signal backend: one Linux VM or container service.
2. Hourly worker: separate supervised container using the same database and configuration.
3. Cloud Android workers: persistent Android devices reachable only through private Appium endpoints.
4. Secret storage: one Square creator posting key per authorized account.

## Deploy in dry-run mode with one account

```bash
cp .env.example .env
```

Set only:

```env
BINANCE_SQUARE_KEY_ACCOUNT_01=YOUR_FIRST_AUTHORIZED_KEY
ACCOUNT_ACTIVATION_MODE=key_present
PUBLISH_ENABLED=false
MOBILE_CAPTURE_ENABLED=false
```

Deploy:

```bash
docker compose up -d --build
curl http://SERVER_IP:8080/health
curl http://SERVER_IP:8080/accounts/status
curl -X POST http://SERVER_IP:8080/cycles/dry-run
```

The API and hourly worker both mount `.env`. The worker reloads configuration at every hourly cycle.

## Add account 2 later

Add the second key to `.env`:

```env
BINANCE_SQUARE_KEY_ACCOUNT_02=YOUR_SECOND_AUTHORIZED_KEY
```

Check status:

```bash
curl http://SERVER_IP:8080/accounts/status
```

With a normal bind-mounted `.env`, it becomes active on the next configuration load. If your hosting provider injects secrets only at container creation, redeploy/recreate the services after updating the secret.

## Current live-mode limitation

v0.1.1 does not yet run the timed screenshot-and-publish queue. It creates routed dry-run previews. Do not enable publishing until the live worker is added and one-account capture/publishing tests pass.

## Production secret rules

- Never commit `.env`.
- Never log full keys.
- Use only authorized creator posting keys.
- Keep Appium/ADB private.
- No trading or withdrawal permission is needed.
