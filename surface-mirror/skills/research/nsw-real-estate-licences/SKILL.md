---
name: nsw-real-estate-licences
description: NSW real estate licence data via open-data XLSX.
---

# NSW Real Estate Licence Data — Source-of-truth path

## The right path (do this first)

**Do NOT scrape verify.licence.nsw.gov.au directly** for bulk enumeration. The site:
- Caps search results at 200 records per query (no documented way to bypass)
- Uses CONTAINS (substring) matching, not starts-with — so any letter-prefix returns the same first 200 alphabetical results
- Has a hidden `publicregisterapi/api/v1` endpoint but it's Cloudflare rate-limited (HTTP 429, error 1015) for non-browser sessions
- Returns no phone numbers in the public register (privacy)

**Use the NSW Government open-data bulk XLSX instead:**

| File | URL | Size | Rows |
|---|---|---|---|
| Property - Corporation (agencies) | `https://onegov.nsw.gov.au/agencies/oft/Property%20-%20Corporation.xlsx` | 910 KB | ~9,599 |
| Property - Individual (agents) | `https://onegov.nsw.gov.au/agencies/oft/Property%20-%20Individual.xlsx` | 2.9 MB | ~34,000 |

No auth, no rate limit. Direct `curl -sL <url> -o <file>` works.

## Caveats

- Both extracts dated **03 Dec 2023** (Last-Modified header). No auto-refresh. ~3 years stale.
- "Currently licensed" filtering by `Expiry Date >= today` is **conservative** — agencies who renewed since Dec 2023 still show as "lapsed" in this file because the renewal isn't recorded.
- Phone numbers NOT included in either extract. ABR/ASIC don't publish business phones publicly.
- For live status of a specific agency: search ACN at verify.licence.nsw.gov.au (Cloudflare 429-prone, wait 5+ min between batches).

## Pipeline

```python
from openpyxl import load_workbook
from datetime import datetime, date

wb = load_workbook('Property_Corporation.xlsx', read_only=True, data_only=True)
ws = wb['Sheet2']
rows = list(ws.iter_rows(values_only=True))[2:]  # skip banner + header
header = ['Licence Number', 'Issue Date', 'Expiry Date', 'Licensee', 'Address Type', 'Address', 'Birth Year', 'ACN', 'ABN']

today = date.today()
current = [dict(zip(header, r)) for r in rows
           if isinstance(r[2], datetime) and isinstance(r[1], datetime)
           and r[2].date() >= today and r[1].date() <= today]
```

## Phone enrichment (for active agencies)

1. realestate.com.au agency pages show phone publicly. Use their suburb-based agency search.
2. domain.com.au/real-estate-agencies/<suburb>-nsw-<postcode>/ — but Domain blocks headless browsers with Akamai (Access Denied).
3. Google's site: query: `site:realestate.com.au "<agency name>" <suburb>` usually surfaces the phone directly.
4. Yellow Pages Australia: `yellowpages.com.au/find/<suburb>/real-estate-agents` — usually works without blocks.

## Working script in TESSERACT

`scripts/build_nsw_master.py` — given the bulk XLSXs in `output/_bulk/`, produces:
- `nsw_agencies_full.csv` (unique current agencies by ACN)
- `nsw_corporations_all.csv` (all 9,599 corporations with Active/Lapsed flag)
- `nsw_agents.csv` (current individual agents)
