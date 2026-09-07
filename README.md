# job-alert

Fetches recent job notifications, renders each one as a 1080×1350 poster, and
publishes it to Instagram — on a schedule, for free.

Everything runs on GitHub Actions in a **public** repository: unlimited free
runner minutes, free cron, and the repo itself hosts the poster images that
Instagram fetches. There is no server, no domain, and no paid tier anywhere.

```
cron (2×/day)
  └─ fetch    free job APIs           → jobs
  └─ filter   drop invalid + already-posted
  └─ render   Pillow                  → out/<id>.jpg
  └─ commit   push to main            → public raw.githubusercontent.com URL
  └─ publish  Instagram Graph API     → container → poll → publish
```

## What it covers, and what it does not

Sources are **free, documented APIs only** — no scraping, so there is no
terms-of-service or copyright exposure. The trade-off is coverage:

| Source | Key needed | Covers |
| --- | --- | --- |
| [Adzuna](https://developer.adzuna.com/) | yes, free (~1,000 calls/month) | India, private sector |
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | no | Europe, remote |
| [RemoteOK](https://remoteok.com/api) | no | Remote |

**No free API publishes Indian government recruitment notices.** Government
postings will therefore be rare — only those an aggregator happens to index and
that the heuristic in `sources/keywords.py` recognises. To cover them properly,
add a source that reads the official portals (UPSC, SSC, IBPS, RRB, state PSCs)
directly; those notices are public-domain government works. See
[`src/jobalert/sources/README.md`](src/jobalert/sources/README.md).

## Setup

### 1. Instagram and Meta

1. Create the Instagram account, then convert it to a **Professional** (Business
   or Creator) account. Personal accounts cannot publish through any API.
2. At [developers.facebook.com](https://developers.facebook.com), create an app
   and add the **Instagram** product using **"Instagram API with Instagram
   Login"** — that path needs no Facebook Page.
3. Under **Roles → Instagram Tester**, invite your own Instagram account, then
   accept the invite in Instagram (Settings → Website permissions).
4. Generate a token with `instagram_business_basic` and
   `instagram_business_content_publish`, then exchange it for a **long-lived**
   (60-day) token.

Leave the app in **Development mode**. Because you only publish to an account you
own, **no Meta App Review is required** — review only applies to publishing on
behalf of other people's accounts.

### 2. Credentials

Register for a free [Adzuna API key](https://developer.adzuna.com/), and create a
**fine-grained personal access token** scoped to this repository with
**Contents: write** and **Secrets: write**.

Repository **secrets**:

| Secret | Purpose |
| --- | --- |
| `IG_USER_ID` | Instagram professional account id |
| `IG_ACCESS_TOKEN` | Long-lived token (auto-refreshed weekly) |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna credentials |
| `GH_PAT` | Fine-grained PAT: writes the refreshed token back, and keeps the cron schedule alive |

Repository **variables** (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `IG_HANDLE` | `@jobalerts` | Shown in the poster footer and caption |
| `MAX_POSTS_PER_RUN` | `3` | Clamped to 10 |
| `PAUSED` | unset | Set to `true` to stop publishing without touching code |

## Local use

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Render posters and print captions without touching Instagram:

```bash
GITHUB_REPOSITORY=you/job-alert ADZUNA_APP_ID=... ADZUNA_APP_KEY=... .venv/bin/python -m jobalert.publish --dry-run
```

Run the tests:

```bash
.venv/bin/python -m pytest --cov=src/jobalert --cov-report=term-missing
```

## Landing page

Instagram captions are not clickable, so every poster says "link in bio". That
link points at `docs/index.html`, served free by GitHub Pages at
`https://prasad-tilicho.github.io/job-alert/`.

The page is regenerated from `state/published.json` in the same commit that
records a publish, so it never drifts from what the account has actually posted.
It is mobile-first (nearly every visitor arrives from the Instagram app), static,
and every job field is HTML-escaped - titles come from third-party APIs and land
on a public page. Links that are not https are rendered as plain text rather than
anchors.

To enable it once: **Settings -> Pages -> Source: Deploy from a branch ->
`main` / `/docs`**.

## Operational notes

- **Start slow.** A brand-new account posting via API from day one looks
  automated. Set `MAX_POSTS_PER_RUN=1` for the first week or two.
- **Publishing is fully automatic**, so `validate.py` is the only thing between a
  bad parse and your followers. It drops jobs with expired or implausible
  deadlines, missing employers, and non-HTTPS links. Widen it, never narrow it.
- **Salaries are only shown when the source states them.** Adzuna's predicted
  salaries are deliberately discarded rather than presented as fact.
- **Captions are not clickable on Instagram**, hence "link in bio". Keep a link
  to a landing page or Linktree in the account bio.
- **A failed publish is not recorded**, so the job is retried on the next run.
- **GitHub disables cron after 60 days of repository inactivity.** The workflow
  pushes as the `GH_PAT` owner to keep the clock reset; GitHub also emails you
  before disabling, and any manual run re-enables it.
- **Attribution is required** by Adzuna's and RemoteOK's terms. It is built into
  every caption and poster footer — do not remove it.

## Layout

```
src/jobalert/
  config.py      validated settings, loaded once at startup
  models.py      the frozen Job type
  sources/       one module per feed  (see its README to add more)
  validate.py    the quality gate before anything is published
  dedupe.py      stable job ids and the posted-state file
  poster/        theme (constants) → layout (pure text fitting) → render (Pillow)
  caption.py     caption text, hashtags, required attribution
  instagram.py   create container → poll → publish; token refresh
  publish.py     orchestration and CLI
```
