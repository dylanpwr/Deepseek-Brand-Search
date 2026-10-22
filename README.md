# Grenade Search Visibility Intelligence

A local Python/Streamlit research workbench for Canadian protein-bar acquisition visibility. SQLite stores immutable run manifests, query outcomes, returned results, fetched evidence and raw API JSON; Pandas calculates coverage; Plotly displays comparisons. **No finding of poor Grenade visibility is assumed.**

## Delivery status — read first

The local application, query library, analysis, technical inspection, dashboard and automated tests work. **The DeepSeek provider integration is not verified or live-ready.** The supplied official documentation URL (`https://api-docs.deepseek.com/guides/search/`) was blocked by the build environment's outbound policy (proxy CONNECT 403). No `DEEPSEEK_API_KEY` was configured. It would be misleading to invent endpoints, authentication, response schemas, API limits or prices. `config/api_contract.json` therefore deliberately contains null settings and `verified: false`. Live execution fails closed and records a blocked run.

This is a real local research application with a contract-driven HTTP adapter, not a claim of completed or tested DeepSeek Search/Fetch integration. Complete the verification step below on a machine with access to the official documentation and credentials before using it for live research. There are **no fabricated SERPs, initial rankings, brand findings or revenue estimates**. Synthetic API schemas and result fixtures exist only in tests and their temporary databases.

## Install and open

Requires Python 3.11+.

```bash
git clone https://github.com/dylanpwr/Deepseek-Brand-Search.git
cd Deepseek-Brand-Search
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

The dashboard works with an empty database and shows the actual configured query coverage. Run `python tools/generate_preview.py` to generate `reports/dashboard-preview.html`, a self-contained example of this honest, unmeasured state, including an interactive query-library chart. It does not contain sample search results. Never commit `.env` or share databases containing proprietary imported data.

## Verify the official API contract before live use

1. Open the supplied official Search guide and follow its official Fetch reference. Confirm that your account actually has access to both services. If those APIs are unavailable, stop; do not substitute the chat-completions endpoint or another search provider while labeling it DeepSeek.
2. Save the official documentation locally for reproducibility. Record its SHA-256 in `documentation_sha256`, source URL in `documentation_url`, and verification date in `verified_at`. This field is a manual provenance record, not cryptographic verification by the application.
3. Populate `auth.header` and `auth.prefix` exactly as documented. A prefix includes any required trailing space. The credential is read only from `DEEPSEEK_API_KEY` in the environment or local `.env`; no key is stored in the contract, requests ledger or manifests.
4. For each service populate its absolute HTTPS `url`, `method` (`GET` or `POST`), fixed `payload`, and request field names. Search needs `query_field`, `limit_field`, and `results_path`. Fetch needs `url_field` and `content_path`. Fixed payload can encode supported region, language or mode parameters; no unsupported Canadian geolocation is assumed. Queries themselves express Canadian intent.
5. Populate Search `fields`: normalized keys are `title`, `url`, `snippet`, `summary`, `rerank_score`, `authority_tier`, `publication_date`. Values are dotted paths relative to each result object; `title` and `url` are required. Only map fields the provider really returns. Unmapped optional fields become empty/unknown. Do not map a score to authority or rank.
6. Dotted response paths traverse objects and numerical list indices; the empty string selects the full response. Search output must resolve to a list and Fetch content to a string. Request fields are currently flat scalar fields. If actual documentation uses nested requests, pagination, batched Fetch, a different authentication flow or streamed responses, adapt `grenade/client.py` and add tests before setting `verified: true`. The adapter does not guess those formats.
7. Enter the documented `max_results`, `max_rpm`, `retry_statuses` and `retry_after_header` (null if absent). Local Search requests are capped at 20 even if the provider supports more; if the provider allows fewer, fewer will be collected. Confirm pricing separately; optional per-request environment costs are estimates in your chosen currency, not billed costs. Token-dependent pricing requires extending the cost model.
8. Set `verified: true` only after these checks, configure `DEEPSEEK_API_KEY` in `.env`, and run a 10-query audit. Validate actual returned order, field mappings, errors and Fetch content against raw responses before expanding. A user-set verification flag does not prove the service works; a successful live test remains necessary.

No actual API endpoint or contract example is supplied because it could be mistaken for official documentation. Tests explicitly mark their `example.test` schemas as synthetic.

## Query library and low-cost audit

`config/queries.csv` contains 115 unique queries in five intents. Thirteen mention Grenade; 102 do not. `branded` means the query names Grenade, not that it contains no competitor or retailer name. All user-specified seed queries are included. French queries are a separate intent. Priority 1/2 and purchase-intent scores are qualitative planning judgments, not volume estimates. Edit the CSV to change scope.

```bash
# No API calls; deterministic round-robin sampling gives each intent coverage.
python -m grenade.runner plan --limit 10
# Once contract and credentials are verified:
python -m grenade.runner run --limit 10 --fetch-limit 5 --technical-limit 5 --refresh
# Full library; review the plan and request budget before executing.
MAX_REQUESTS=200 python -m grenade.runner run --limit 115 --fetch-limit 20 --refresh
python -m grenade.runner report --run-id 1 --out reports
python -m pytest -q
```

The default budget is 100 API attempts, including retries, so a full run needs a larger explicitly configured budget. The default 10-query run selects the same queries and parameters every time. Search retrieves up to 20 returned results per query. Search gaps select the top three pages per absent/underrepresented query, deduplicate globally and Fetch up to the configured budget. Unfetched leaders remain marked “not fetched”; the application never implies all gaps were fully researched. Raise `--fetch-limit` for broader evidence. Zero-result successful queries are included in coverage; failed queries are excluded and reported separately.

## Validate official domains and Canadian distribution

`config/domains.json` has one **unvalidated discovery seed**, not a claim of ownership. Official coverage and technical/GEO inspection require entries in `official` with:

```json
{"domain":"validated-domain.example","brand":"Grenade","evidence_url":"https://validated-domain.example/legal","evidence_note":"Describe the independently reviewed ownership evidence"}
```

This is the shape of an entry, not a real Grenade domain finding. First inspect brand legal/organization information and controlled links to regional sites. Verify Canadian and global variants, record that evidence, then add each domain. The app requires the fields but cannot independently prove ownership from your note. Domain matching uses host boundaries; misleading lookalike hosts are not accepted. A redirect to an unvalidated host cannot contribute official technical findings. Until domains are validated, official coverage is **unverified**, even if the arithmetic is zero for configured domains.

Canadian retailer hosts (Amazon, Walmart, Costco, major grocery and supplement retailers) classify web results, not marketplace rankings. Confirm product availability with SKU-level retailer evidence before adding `distribution` records with `retailer`, `brand`, `url`, `verified_at`, `note`. Unknown distribution scores conservatively, not as confirmed stock. Review time-sensitive availability before decisions.

Add discovered brand candidates from Competitor Intelligence to `config/brands.json` only after human review. Detection uses case-insensitive regex on result titles/snippets/summaries; official ownership adds the owning brand. Full-page mentions are stored separately after Fetch and do not retroactively change search-result coverage. Ambiguous “ONE” requires “ONE bar(s)” or “ONE Brands”; Built requires Built bar/puff. This reduces false positives but may miss abbreviated names. Review aliases and page classifications before drawing conclusions.

## Dashboard pages

- **Executive Overview:** Grenade mention/official coverage, successful/failed query counts, competitive result mentions, branded split, leading opportunities, comparable baseline and request ledger.
- **Keyword Explorer:** intent filters, query status and cache timestamps, returned results with clickable URLs, all-brand comparison, historical best mention positions and CSV export.
- **Competitor Intelligence:** category coverage, leading domains, retailers/reviews/guides, exploratory title themes and candidate additional brands.
- **Technical & GEO Audit:** affected URLs, captured evidence, missing/inaccessible distinctions, raw-HTML limitations and page-level diagnostic checks.
- **Action Plan:** scored recommendations, evidence and competitor pages, equivalent-page candidates, owner, effort, confidence, impact qualification and next steps; JSON export and imported-data register.

Result-brand counts can exceed result count because a comparison can mention several brands. They are labeled appearances, not market share or demand share.

## Metric definitions and historical integrity

Coverage = successful queries with at least one matching result at/before cutoff / all successful queries in selection. Cutoffs are Top 3, 10 and 20. Average position is the average **best** returned position among queries where the brand is present, not an average of every mention. An empty successful result list is measured absence in this response. Failed searches and blocked runs are not absence.

Returned order is the only rank definition. `rerank_score` is stored independently and never interpreted as Google rank or volume. Authority tier and publication date are provider supplied or unknown. “Official” means a reviewed ownership entry matched; third-party mentions remain separate. No query result can establish that a URL is absent from any index.

SQLite preserves each run's query set, API contract, analysis version, brand/domain rules, parameters and SHA-256 fingerprint. Weekly comparisons require identical fingerprints and use only query IDs successful in both runs. Failed queries are never silently counted as losses. Cache hits retain original observation timestamps; `--refresh` bypasses cache for a fresh weekly measure. Changing query rules or audit budgets starts a different comparable series. The earliest matching run is the baseline. Store UTC timestamps; dashboard labels UTC explicitly.

Example weekly local scheduler (after verification; adjust path and preserve the same scope):

```cron
0 9 * * 1 cd /absolute/path/Deepseek-Brand-Search && .venv/bin/python -m grenade.runner run --limit 10 --fetch-limit 5 --technical-limit 5 --refresh >> data/weekly.log 2>&1
```

This is an example only; no scheduler is installed by this delivery. Use a Toronto-time scheduler if 09:00 Toronto is desired. Scheduler host timezone determines cron interpretation.

## Technical and GEO evidence

Technical requests honor this crawler's robots directives, use normal HTTPS verification, cap response sizes and follow only public HTTP(S) destinations with redirects checked. The crawler checks robots and up to three declared sitemap URLs (or a conventional fallback), HTML title/description/canonical, robots meta and HTTP directives, H1/headings, JSON-LD Product/Organization/Offer structures, internal links, word count, language and Canadian text signals. HTTP page inspection is bounded by `--technical-limit`. It does not render JavaScript, crawl an entire site, validate schema against a complete vocabulary, or establish Google indexing. Missing JSON-LD is not absence of microdata/RDFa/rendered schema. Thin content is contextual, not a proven word-count ranking rule. Robots errors cause conservative skips and are recorded as inaccessible evidence.

GEO readiness gives seven equal-weight page signals: structured product facts, organization entity, offers, extractable descriptions, Canadian information, language identification and comparison-friendly text. This is a **diagnostic heuristic**, not an empirically calibrated probability or a measure of ChatGPT, Perplexity or Google AI Overviews. Cross-source SKU fact consistency, authoritative citations and brand entity consistency require further evidence and are explicitly unmeasured. Fetched excerpts and detected mentions support review; a presence count does not establish factual accuracy.

Gap categories include missing category/comparison content, third-party coverage and retailer visibility; technical findings can flag product structured data and topical coverage. They describe investigation tracks. “No equivalent page observed” only refers to this result set, not the entire Grenade site. Missing content, weak descriptions, technical causes and insufficient authority must be verified before implementation. The MVP does not automatically infer causal ranking factors or complete a site-wide equivalent-content inventory.

## Opportunity score

Each factor is scored 0–5. Priority = `20 × sum(weight × factor)`:

| Factor | Weight | Basis |
|---|---:|---|
| Purchase intent | 25% | CSV intent judgment: transactional 5, comparison 4, other 3 |
| Current visibility gap | 20% | Absent 5; best returned position >10: 4; 4–10: 3 |
| Competitor dominance | 15% | Rival-bearing slots in top five, capped at 5 |
| Distribution relevance | 15% | Confirmed matching retailer 5; other confirmed Grenade distribution 3; unknown 1 |
| Ease | 10% | Publisher/retailer work 3; other content 2 (estimates) |
| Diagnosis confidence | 15% | At least one leader fetched 3; only results 2 |

Scores rank investigations, not forecast revenue. Fetch presence gives additional evidence, not proof of causation. Retailer opportunities are web-discovery observations; marketplace search needs direct platform tests. For reliable commercial prioritization, supply GSC, Ads, retailer stock/sales, implementation estimates and query demand data. Qualitative Canadian relevance is stored in query metadata; confirmed distribution drives the score.

## Costs, reliability and raw evidence

- Attempt-level SQLite ledger counts retries and optional per-request costs. Unknown price remains NULL and displays “Unknown”, never zero/free.
- Environment rate is capped by documented `max_rpm`; total Search/Fetch attempts are capped by `MAX_REQUESTS` across that run. Technical HTTP calls are separate; each page can make robots, sitemap and page requests.
- Default timeout is 30 seconds, at most three attempts per API call. Only documented retry HTTP statuses retry; connection/timeout/JSON failures also retry. Documented Retry-After is respected; delays over 60 seconds stop with a retry-later error rather than retrying early. Authentication failures do not retry unless explicitly configured to.
- API requests do not follow redirects, preventing authorization-header forwarding. Schema mismatches fail visibly. Successful raw JSON, including schema-mismatched responses, is retained in cache; successful query raw JSON is retained per run; Fetch raw JSON and technical raw HTML are in pages. HTTP error bodies are not retained; status/error classes and attempt counts are retained. No credentials or request auth headers are logged.
- Caching keys include endpoint mapping and payload. Default TTL is 24 hours. A cached schema mismatch requires `--refresh` after fixing the mapping. Query errors do not stop unrelated queries; partial runs remain reportable.
- This is a local single-user application. Do not expose Streamlit on a public network without authentication and a deployment review. SQLite/raw HTML are for debugging, not HTML execution.

## Import additional data

```bash
python -m grenade.runner import-data --source gsc --file path/to/gsc.csv
python -m grenade.runner import-data --source google_ads --file path/to/ads.csv
python -m grenade.runner import-data --source retailer --file path/to/retailer.csv
```

CSV requires a `query` column. Extra columns (date, country, device, impressions, clicks, cost, orders, retailer, SKU) are preserved as supplied. Imports are stored separately and listed in the dashboard; automatic joins, volume attribution and revenue models are intentionally not implemented. Validate date ranges, market, platform semantics and SKU matching before extending prioritization.

## Files and tests

`app.py` is the dashboard; `grenade/client.py` is the gated transport; `runner.py` orchestrates and exports; `storage.py` defines SQLite; `analysis.py` contains metrics/scoring; `technical.py` inspects source HTML; `classify.py` contains transparent brand/domain rules. `config/` contains the editable research setup. `tests/` exercises transport and error handling, caching, metrics, gap evidence, fingerprints, HTML audit and all five dashboard pages in empty and synthetic populated states.

`reports/EXECUTIVE_SUMMARY.md` documents supported build findings and the remaining evidence needed. Generated audit exports and runtime databases are not committed. `reports/verification.json` and `reports/tests.txt` record build verification; they are not search measurements.
