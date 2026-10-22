# Grenade Search Visibility Intelligence

A local Python/Streamlit research workbench for Canadian protein-bar acquisition visibility. SQLite stores reproducible run manifests, query outcomes, returned results, fetched evidence and raw API JSON; Pandas calculates coverage; Plotly displays comparisons. **No finding of poor Grenade visibility is assumed.**

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
```

Open `.env` in your text editor, put your key after `DEEPSEEK_API_KEY=`, and save it. If `.env` already exists, keep it; do not overwrite your key with the blank example. Restart Streamlit after changing the file:

```bash
streamlit run app.py
```

The application now includes the documented DeepSeek Search/Fetch configuration. **You do not need to edit `verified`, endpoints or response schemas.** `.env` is read from the project folder even if Streamlit starts from another directory; existing environment variables take precedence. Your key is never committed or shown in the dashboard.

In the sidebar:

1. **Check DeepSeek connection** validates the key using List Models and explains authentication, network, balance or rate-limit errors. This alone does not prove Search/Fetch access.
2. **Test Search & Fetch** makes one real search and fetches one returned page, even if Grenade already appears prominently. It reports the two service outcomes separately and stores the evidence in a run labeled `connection_probe`. Maximum successful-call cost at published rates is $0.0015; provider billing exceptions may reduce actual cost. Empty Search results leave Fetch explicitly untested. Cached results are bypassed for this check.
3. **Start audit** runs the repeatable 10-query sample. Increase the query budget only after reviewing results, costs and classification.

Terminal equivalents:

```bash
python -m grenade.runner check
python -m grenade.runner probe
python -m grenade.runner plan --limit 10
python -m grenade.runner run --limit 10 --fetch-limit 5 --technical-limit 5 --refresh
```

The dashboard also opens without credentials, showing actual query-library coverage and “not measured” for visibility. Run `python tools/generate_preview.py` to create a self-contained HTML preview at `reports/dashboard-preview.html` without synthetic SERPs.

## DeepSeek integration and documentation provenance

The supplied [official Search & Fetch guide](https://api-docs.deepseek.com/guides/search/) documents these bearer-authenticated JSON endpoints:

| Service | Request | Response |
|---|---|---|
| Search | `POST https://api.deepseek.com/v1/tools/search` with `query`, `count`, `need_content` | `results` array; result title, URL, snippet, summary, rerank score, authority and date |
| Fetch | `POST https://api.deepseek.com/v1/tools/fetch` with `url` | page `title` and Markdown `content` |

Direct documentation retrieval was blocked in the build environment. The user supplied the official guide's text, saved verbatim in `docs/deepseek-search-fetch-guide.txt`. Its SHA-256, source URL, supplied-copy provenance and review timestamp are recorded in `config/api_contract.json`. A test verifies the snapshot hash. This is documentation-based implementation, **not a claim of a successful authenticated live call from the build environment**. A local API key is still required; the service-test button verifies live account access.

The client sends `Authorization: Bearer ...` and `Content-Type: application/json`. Query text must contain 1–128 Unicode characters and cannot be all whitespace. Operators and accents are preserved. The API supports 1–50 results; this application deliberately requests at most 20. `need_content` defaults to false to use snippets/summaries for search analysis and separate Fetch for selected evidence. Fetch accepts HTTP(S) URLs up to 8192 characters with a host and no embedded username/password. The saved guide documents optional `ori_question` and IP-based `localization`; no IP address or Canadian geographic result origin is invented. Canadian relevance initially comes from query intent.

Result `authority` maps to `authority_tier` (0 is preserved; -1 means unknown), and `date` maps to `publication_date`. `rerank_score` stays separate from returned rank and is never used as volume or Google rank. Fetch Markdown headings are captured as evidence. Raw Search/Fetch JSON and HTTP error bodies are retained in SQLite with credential redaction; request headers are not logged.

Maintainers can change the versioned contract when the provider changes its official specification. Normal users only configure `.env`. Changing a contract changes the run fingerprint, so old measurements are not silently mixed with a new API configuration.

## Query library and low-cost audit

`config/queries.csv` contains 115 unique queries in five intents. Thirteen mention Grenade; 102 do not. `branded` means the query names Grenade, not that it contains no competitor or retailer name. All user-specified seed queries are included. French queries are a separate intent. Priority 1/2 and purchase-intent scores are qualitative planning judgments, not volume estimates. Edit the CSV to change scope.

```bash
# No API calls; deterministic round-robin sampling gives each intent coverage.
python -m grenade.runner plan --limit 10
# With your key saved in .env:
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

Example weekly local scheduler (after a successful service test; adjust path and preserve the same scope):

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

- The supplied guide lists **$0.75 per 1,000 successful requests**, or **$0.00075** for each billable Search or Fetch request. Count does not affect the per-request price. The plan shows the estimate if all planned calls are billable: 10 Searches plus 5 Fetches cost $0.01125 at the published rate.
- Billing requires HTTP 200 and actual output: a non-empty `results` array for Search, or non-empty page content for Fetch. Failed requests, empty results, timeouts and cache hits add no estimated cost. An unexpected successful schema has unknown billability (NULL), not an invented zero. Price overrides in `.env` are optional; blank uses the saved guide's rate.
- These are list-price estimates, not invoices. The supplied guide also mentions a temporary free period for server-side tools through DeepSeek Harness/Claude Code/Codex until 00:00 Beijing time November 1, 2026. Do not assume that exception applies to direct calls from this local app; check your account's actual billing.
- Account limits are independent: **Search 100 QPS**, **Fetch 25 QPS**, plus an unspecified per-domain Fetch limit. The client caps each service independently; the conservative local default is 10 requests per minute per service. Other clients sharing an account can still cause 429 responses. No per-domain allowance is invented.
- `MAX_REQUESTS` caps total Search/Fetch attempts including retries. HTTP metadata inspection is separate; each technical page can involve robots, sitemap and page requests. The default budget is 100; the full 115-query audit needs a larger explicit budget.
- Timeout defaults to 30 seconds, with at most three attempts per call. HTTP 408, 429 and 5xx retry with backoff, as the guide instructs. HTTP 400/401/402/403/404/413 do not retry unchanged. HTTP 402 directs you to top up your account. Fetch 403/404 is missing/inaccessible evidence, not proof of index exclusion or an SEO defect.
- If a standard `Retry-After` header is supplied, the client honors it. Delays over 60 seconds stop with “retry later” rather than retrying before the requested delay. Connection/timeouts retry; malformed successful JSON/schema does not trigger a potentially billable repeat.
- API calls do not follow redirects, preventing authorization-header forwarding. The SQLite request ledger stores status, billability, estimated cost and raw responses, including error bodies, but no request authorization headers. Existing SQLite databases upgrade the ledger additively without losing history. JSON fields containing a long credential are redacted before persistence.
- Search/Fetch caching uses endpoint configuration and payload, with a default 24-hour TTL. Cache hits retain original observation timestamps. Use `--refresh` for weekly measurements and service tests. Raw schema-mismatched JSON is retained for debugging; after correcting a mapping, use `--refresh`.
- This is a local, single-user application. Keep `.env` private and do not expose Streamlit publicly without authentication. Raw HTML is evidence for inspection, not executable dashboard content.

## Import additional data

```bash
python -m grenade.runner import-data --source gsc --file path/to/gsc.csv
python -m grenade.runner import-data --source google_ads --file path/to/ads.csv
python -m grenade.runner import-data --source retailer --file path/to/retailer.csv
```

CSV requires a `query` column. Extra columns (date, country, device, impressions, clicks, cost, orders, retailer, SKU) are preserved as supplied. Imports are stored separately and listed in the dashboard; automatic joins, volume attribution and revenue models are intentionally not implemented. Validate date ranges, market, platform semantics and SKU matching before extending prioritization.

## Files and tests

`app.py` is the dashboard; `grenade/client.py` is the documented Search/Fetch transport; `runner.py` orchestrates and exports; `connection.py` checks authentication; `storage.py` defines SQLite; `analysis.py` contains metrics/scoring; `technical.py` inspects source HTML; `classify.py` contains transparent brand/domain rules. `config/` contains the editable research setup. `tests/` exercises transport and error handling, caching, metrics, gap evidence, fingerprints, HTML audit and all five dashboard pages in empty and synthetic populated states.

`reports/EXECUTIVE_SUMMARY.md` documents supported build findings and the remaining evidence needed. Generated audit exports and runtime databases are not committed. `reports/verification.json` and `reports/tests.txt` record build verification; they are not search measurements.
