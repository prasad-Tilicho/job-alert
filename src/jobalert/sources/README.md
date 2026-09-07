# Adding a job source

A source is any object with a `name` and a `fetch(client) -> list[Job]`. Drop a new
module in this package, register it in `registry.build_sources()`, and it joins the
pipeline — `fetch_all()` already isolates it so a failure there cannot break a run.

```python
class MySource:
    name = "mysource"

    def fetch(self, client: httpx.Client) -> List[Job]:
        response = client.get(API_URL)
        response.raise_for_status()
        return [job for job in map(self._to_job, response.json()) if job is not None]
```

Rules the existing sources follow, and yours should too:

- **Return `None` for unusable rows.** A posting with no employer or no link can
  never render or be applied to; drop it at the source rather than downstream.
- **Never invent a field.** If a salary is a prediction or a deadline is a guess,
  leave it `None`. Publishing is automatic, so anything set here is stated as fact.
- **Let HTTP errors propagate.** `fetch_all()` catches and logs them per source.
- **Do not clean up titles yourself.** `Job` runs `tidy_title()` on construction,
  which fixes spacing and punctuation but never spelling or wording.
- **Add a fixture test.** Save a real response under `tests/fixtures/` and assert
  against it with `respx`; no test may touch the network.

## Adding government sources

The free job APIs cover private and remote roles well and Indian government
recruitment barely at all. The fix is to read the official portals directly —
UPSC, SSC, IBPS, RRB, and the state PSCs all publish their notices as public
notice boards or RSS feeds. Those notices are government works in the public
domain, so parsing them carries none of the terms-of-service or copyright risk
that comes with scraping aggregator sites like Sarkari Result or FreeJobAlert.

An RSS-backed source is the same shape as the above, with `feedparser` or a small
XML parse in place of `response.json()`. Set `category=Category.GOVERNMENT`
directly rather than relying on the keyword heuristic in `keywords.py`, and be
careful to parse the closing date correctly — `validate.py` will drop anything
already expired, but it cannot catch a date parsed into the wrong year.
