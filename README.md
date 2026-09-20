# Haryana + UP RERA new-registration email monitor

This service polls the official statewide Haryana RERA registered-project list and the official UP RERA Gautam Buddha Nagar district feed. It emails each newly appearing registration to `bharadwajr278@gmail.com`.

Priority coverage:

- Gurugram and Faridabad on Haryana RERA
- Noida, Greater Noida, and Yamuna Expressway projects registered under Gautam Buddha Nagar on UP RERA

All Haryana districts remain monitored.

## What the alert contains

- Project name
- RERA registration/certificate number and portal project ID
- Developer/builder
- Location and city/district
- Registration approval date (looked up from the official detail page)
- Project type when a strong public category phrase is available
- Official RERA project/search link

SQLite stores every observed registration key with its authority source. Each source gets its own first-run baseline, so adding UP RERA does **not** send hundreds of historical emails. A newly detected record is queued until email succeeds and then marked notified, preventing normal restart/poll duplicates.

## Quick start on Windows

1. Install Python 3.11 or newer.
2. Copy `.env.example` to `.env`.
3. Enable Google two-step verification on the sending Gmail account, create a Google App Password, and put that 16-character app password in `SMTP_PASSWORD`. Do not use your normal Google password.
4. Fill `SMTP_USERNAME` and `EMAIL_FROM`. `EMAIL_TO` is already set to `bharadwajr278@gmail.com`.
5. Run:

   ```powershell
   .\run.ps1
   ```

Leave the process running. For reliable 24/7 monitoring, run it on an always-on VPS or use Docker below.

## Docker / VPS (recommended)

Copy `.env.example` to `.env`, fill the SMTP fields, then:

```bash
docker compose up -d --build
docker compose logs -f
```

The `data` directory is mounted so the deduplication database survives restarts and upgrades.

## Safe verification

To verify scraping without sending email, set `DRY_RUN=true` and `ALERT_ON_FIRST_RUN=false`, then run:

```powershell
python monitor.py --once
```

The initial run logs the baseline size. Set `DRY_RUN=false` for real alerts. Do not set `ALERT_ON_FIRST_RUN=true` on the live database unless you intentionally want an email for every currently listed project.

After adding SMTP credentials, send one clearly labelled test message with:

```powershell
python monitor.py --test-email
```

## Operations

- Default polling is every 120 seconds, giving an expected detection delay of roughly 0–2 minutes after an authority feed publishes a record, plus email delivery time.
- The monitor never bypasses authentication, CAPTCHA, or access controls.
- HTTP failures retry with backoff; a partial-looking page is rejected instead of being treated as a new state.
- Failed emails stay queued and retry on a later poll.
- Keep `.env` private and back up `data/haryana_rera.sqlite3`.

## Official sources

`https://haryanarera.gov.in/admincontrol/registered_projects/1`

`https://www.up-rera.in/View_projects.aspx`

The UP RERA browser search is CAPTCHA-protected and is not automated or bypassed. The monitor uses the public Gautam Buddha Nagar district service called by UP RERA's own project map.

The monitor can only detect a registration after the relevant authority publishes it in its public feed. Portal maintenance, delayed publication, or email-provider delays are outside the monitor's control.
