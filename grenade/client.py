"""DeepSeek Search/Fetch transport, using the saved official guide and audited contract."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from .storage import now


class APIError(RuntimeError):
    pass


def at(value, path):
    if path in ('', None):
        return value
    for key in path.split('.'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


class Client:
    def __init__(self, store, run, contract, key=None, session=None, sleep=time.sleep):
        self.store, self.run, self.contract = store, run, contract
        self.key = key or os.getenv('DEEPSEEK_API_KEY', '')
        self.session = session or requests.Session()
        self.sleep = sleep
        self.count = self.cache_hits = 0
        self.last = {'search': 0, 'fetch': 0}
        self.budget = int(os.getenv('MAX_REQUESTS', '100'))
        self.timeout = float(os.getenv('REQUEST_TIMEOUT', '30'))
        self.ttl = float(os.getenv('CACHE_TTL_HOURS', '24')) * 3600
        self.validate()
        self.intervals = {}
        for kind in ('search', 'fetch'):
            cap = contract.get('max_rpm_by_kind', {}).get(kind, contract['max_rpm'])
            rpm = min(float(os.getenv('REQUESTS_PER_MINUTE', '10')), float(cap))
            if rpm <= 0:
                raise APIError('Request rate must be positive')
            self.intervals[kind] = 60 / rpm

    def validate(self):
        c = self.contract
        if not c.get('verified') or not c.get('verified_at') or not c.get('documentation_sha256'):
            raise APIError('Search/Fetch integration is unverified in this configuration. Restore the shipped config/api_contract.json; a valid key alone does not supply endpoint mappings.')
        if not self.key.strip():
            raise APIError('DEEPSEEK_API_KEY is not configured')
        self.key = self.key.strip()
        if not c.get('auth', {}).get('header') or c['auth'].get('prefix') is None:
            raise APIError('Documented authentication mapping missing')
        for kind in ('search', 'fetch'):
            spec = c.get(kind, {})
            if urlparse(spec.get('url') or '').scheme != 'https' or spec.get('method') not in ('GET', 'POST'):
                raise APIError('Documented HTTPS endpoint and method required for ' + kind)
        if not c.get('max_results') or not c.get('max_rpm'):
            raise APIError('Documented limits missing')
        if not c['search'].get('query_field') or not c['search'].get('limit_field') or c['search'].get('results_path') is None:
            raise APIError('Documented search schema missing')
        if not {'url', 'title'}.issubset(c['search'].get('fields', {})):
            raise APIError('Documented result field mapping missing')
        if not c['fetch'].get('url_field') or c['fetch'].get('content_path') is None:
            raise APIError('Documented fetch schema missing')

    def estimate_cost(self, kind, status, data):
        """Return (estimated USD cost, billable); unknown contracts remain unknown."""
        pricing = self.contract.get('pricing', {})
        if not pricing.get('billable_only_on_http_200_with_output'):
            price = os.getenv(kind.upper() + '_COST_PER_REQUEST', '')
            return (float(price) if price else None), None
        if status != 200:
            return 0.0, False
        try:
            if kind == 'search':
                output = at(data, self.contract['search']['results_path'])
                if not isinstance(output, list):
                    return None, None
            else:
                output = at(data, self.contract['fetch']['content_path'])
                if not isinstance(output, str):
                    return None, None
            billable = bool(output)
        except (KeyError, TypeError, IndexError, ValueError):
            return None, None
        price = os.getenv(kind.upper() + '_COST_PER_REQUEST')
        price = float(price) if price else pricing[kind + '_per_successful_request']
        return (price if billable else 0.0), billable

    def safe_raw(self, value):
        raw = json.dumps(value, ensure_ascii=False)
        # Real credentials are long; short test-fixture keys must not corrupt fixture strings.
        return raw.replace(self.key, '[REDACTED]') if len(self.key) >= 12 else raw

    def call(self, kind, variable, refresh=False):
        spec = self.contract[kind]
        payload = dict(spec.get('payload', {}))
        payload.update(variable)
        cache_key = hashlib.sha256(json.dumps([kind, spec, payload], sort_keys=True).encode()).hexdigest()
        found = self.store.rows('SELECT * FROM cache WHERE key=?', (cache_key,))
        if found and not refresh and (datetime.now(timezone.utc) - datetime.fromisoformat(found[0]['timestamp'])).total_seconds() < self.ttl:
            self.cache_hits += 1
            return json.loads(found[0]['raw']), found[0]['timestamp'], True
        headers = {self.contract['auth']['header']: self.contract['auth']['prefix'] + self.key,
                   'Content-Type': 'application/json'}
        last_error = 'Request failed'
        for attempt in range(3):
            if self.count >= self.budget:
                raise APIError('Request budget exhausted (includes retries)')
            self.sleep(max(0, self.intervals[kind] - (time.monotonic() - self.last[kind])))
            self.last[kind] = time.monotonic()
            self.count += 1
            status, data, response_raw = None, None, None
            retry = False
            wait = min(2 ** attempt, 30)
            success = False
            try:
                kw = {'params': payload} if spec['method'] == 'GET' else {'json': payload}
                response = self.session.request(spec['method'], spec['url'], headers=headers,
                                                timeout=self.timeout, allow_redirects=False, **kw)
                status = response.status_code
                try:
                    data = response.json()
                    response_raw = self.safe_raw(data)
                except ValueError:
                    text = response.text if isinstance(response.text, str) else ''
                    response_raw = self.safe_raw({'non_json_body': text})
                if status == 200 and data is not None:
                    success = True
                else:
                    messages = {400: 'invalid request; check query or URL limits',
                                401: 'key missing or invalid; check .env and restart',
                                402: 'insufficient balance; top up your DeepSeek account',
                                403: 'request blocked by security or network policy',
                                404: 'no usable page content or endpoint unavailable; not an indexing diagnosis',
                                413: 'request body too large', 429: 'account or target-domain rate limit exceeded'}
                    last_error = f'{kind} HTTP {status}: ' + messages.get(status, 'request or response failure')
                    retry = status in self.contract.get('retry_statuses', [])
                    header = self.contract.get('retry_after_header')
                    value = response.headers.get(header) if header else None
                    if value:
                        try:
                            wait = max(wait, float(value))
                        except ValueError:
                            try:
                                wait = max(wait, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError):
                                pass
                    if wait > 60:
                        retry = False
                        last_error += '; server retry delay exceeds local 60-second ceiling; retry later'
            except requests.RequestException:
                last_error = f'{kind} network/timeout failure'
                retry = True
            cost, billable = self.estimate_cost(kind, status, data)
            self.store.execute('INSERT INTO requests(run_id,kind,timestamp,status,cost,error,raw,billable) VALUES(?,?,?,?,?,?,?,?)',
                               (self.run, kind, now(), status, cost, None if success else last_error, response_raw, billable))
            if success:
                stamp = now()
                raw = self.safe_raw(data)
                self.store.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)', (cache_key, stamp, raw))
                return json.loads(raw), stamp, False
            if not retry or attempt == 2:
                break
            self.sleep(wait)
        raise APIError(last_error)

    def search(self, query, limit=20, refresh=False):
        maximum = self.contract.get('max_query_characters', 128)
        if not isinstance(query, str) or not query.strip() or len(query) > maximum:
            raise APIError(f'Search query must contain 1–{maximum} Unicode characters and cannot be whitespace')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise APIError('Application result limit must be an integer from 1 to 20')
        spec = self.contract['search']
        raw, stamp, cached = self.call('search', {spec['query_field']: query,
                                               spec['limit_field']: min(limit, self.contract['max_results'])}, refresh)
        try:
            results = at(raw, spec['results_path'])
            if not isinstance(results, list):
                raise ValueError()
            mapped = []
            for r in results[:limit]:
                row = {}
                for name, path in spec['fields'].items():
                    try:
                        row[name] = at(r, path)
                    except (KeyError, IndexError, TypeError):
                        if name in ('url', 'title'):
                            raise
                        row[name] = None
                if not isinstance(row.get('url'), str) or not isinstance(row.get('title'), str):
                    raise ValueError()
                mapped.append(row)
            return mapped, raw, stamp, cached
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise APIError('Search response schema mismatch; raw response retained in cache') from e

    def fetch(self, url, refresh=False):
        maximum = self.contract.get('max_fetch_url_characters', 8192)
        try:
            parsed = urlparse(url) if isinstance(url, str) else None
            if not parsed or len(url) > maximum or parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                raise ValueError()
        except ValueError as e:
            raise APIError(f'Fetch URL must be HTTP(S), at most {maximum} characters, with a host and no username/password') from e
        spec = self.contract['fetch']
        raw, stamp, cached = self.call('fetch', {spec['url_field']: url}, refresh)
        try:
            content = at(raw, spec['content_path'])
            if not isinstance(content, str):
                raise ValueError()
            if not content.strip():
                raise APIError('Fetch returned no usable page content; no page evidence was recorded')
            return content, raw, stamp, cached
        except (KeyError, TypeError, IndexError, ValueError) as e:
            raise APIError('Fetch response schema mismatch; raw response retained in cache') from e
