import argparse, csv, hashlib, json, os, re
from pathlib import Path
from bs4 import BeautifulSoup
from .connection import load_settings, check_key, project_path
from .storage import Store, now
from .client import Client, APIError
from .classify import normalize, mentions, discovered_candidates
from .technical import audit_site
from .analysis import frames, visibility, gaps

ROOT=Path(__file__).resolve().parents[1]

def load_queries(path):
    with open(path,encoding='utf-8') as file: rows=list(csv.DictReader(file))
    if len({x['id'] for x in rows})!=len(rows) or len({x['query'] for x in rows})!=len(rows):raise ValueError('Duplicate query ID or text')
    for r in rows:
        for key in ('priority','purchase_intent','canada_relevance'):r[key]=int(r[key])
        r['branded']=str(r['branded']).lower() in ('true','1','yes')
    return rows

def select_queries(rows,limit):
    # Round robin across categories; deterministic coverage in low-cost mode.
    groups={cat:sorted([q for q in rows if q['category']==cat],key=lambda q:(q['priority'],q['id'])) for cat in dict.fromkeys(q['category'] for q in rows)}
    out=[]
    while any(groups.values()) and len(out)<limit:
        for values in groups.values():
            if values and len(out)<limit:out.append(values.pop(0))
    return out

def plan(queries,contract,brands,domains,limit,top,fetch_limit,technical_limit):
    rows=select_queries(load_queries(queries),limit)
    # Settings affecting measurement are immutable per run; caches have their own observed timestamps.
    manifest={'queries':rows,'contract':contract,'brands':brands,'domains':domains,
        'top':top,'fetch_limit':fetch_limit,'technical_limit':technical_limit,'analysis_version':1}
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return manifest,fingerprint

def probe_plan(queries,contract,brands,domains):
    manifest,_=plan(queries,contract,brands,domains,1,5,1,0)
    manifest.update(purpose='connection_probe',probe_fetch=True)
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return manifest,fingerprint


def probe_result(store,run):
    searches=store.rows('SELECT status,error,raw FROM searches WHERE run_id=?',(run,))
    pages=store.rows("SELECT status,evidence FROM pages WHERE run_id=? AND kind='fetch'",(run,))
    search_ok=bool(searches and searches[0]['status']=='ok')
    fetch_ok=bool(pages and pages[0]['status']=='ok')
    if search_ok and fetch_ok:
        message='Search and Fetch both succeeded for your account. You can start the 10-query audit.'
    elif not search_ok:
        message='Search did not succeed. '+(searches[0]['error'] if searches else 'Check the API key and service configuration.')
    elif not pages:
        message='Search succeeded but returned no pages. Fetch was not tested; retry later or run a broader audit.'
    else:
        message='Search succeeded, but Fetch did not. '+json.loads(pages[0]['evidence']).get('error','Inspect the request ledger.')
    return {'run':run,'search_ok':search_ok,'fetch_ok':fetch_ok,'message':message}


def run_audit(store,manifest,fingerprint,refresh=False):
    run=store.start(fingerprint,manifest);failed=False
    try: client=Client(store,run,manifest['contract'])
    except APIError as e:
        store.finish(run,'blocked');return run,str(e)
    leaders=[]
    for q in manifest['queries']:
        try:
            results,raw,stamp,cached=client.search(q['query'],manifest['top'],refresh)
            normalized=[normalize(r,i,manifest['brands'],manifest['domains']) for i,r in enumerate(results,1)]
            store.search(run,q,'ok',raw=raw,observed_at=stamp,cache_hit=cached)
            for row in normalized:store.result(run,q['id'],row)
            if manifest.get('probe_fetch') or (q['priority']<=2 and not any('Grenade' in r['brands'] and r['rank']<=3 for r in normalized)):
                leaders.extend(r['url'] for r in normalized[:3])
        except (APIError,ValueError,TypeError) as e:
            failed=True;store.search(run,q,'error',error=str(e))
    for url in list(dict.fromkeys(leaders))[:manifest['fetch_limit']]:
        try:
            content,raw,stamp,cached=client.fetch(url,refresh)
            soup=BeautifulSoup(content,'html.parser');text=soup.get_text(' ',strip=True)
            evidence={'excerpt':text[:1800],'brands':mentions(text,manifest['brands']),
                'headings':list(dict.fromkeys([x.get_text(' ',strip=True) for x in soup.find_all(['h1','h2','h3'])]+re.findall(r'^#{1,6}\s+(.+?)(?:\s+#+)?$',content,re.M)))[:30],
                'title':raw.get('title') if isinstance(raw,dict) else None,
                'content_format':'Markdown from Fetch API',
                'candidate_brands':discovered_candidates(text,manifest['brands']),
                'observed_at':stamp,'cache_hit':cached,'scope':'Fetched content; heuristic extraction, not causal ranking analysis'}
            store.page(run,url,'fetch','ok',evidence,json.dumps(raw,ensure_ascii=False))
        except APIError as e:
            failed=True
            store.page(run,url,'fetch','error',{'error':str(e)},'')
    # Only ownership-validated domains may contribute technical/GEO findings.
    official=[x for x in manifest['domains'].get('official',[]) if x.get('brand')=='Grenade' and x.get('evidence_url') and x.get('evidence_note')]
    from .classify import official as official_brand, domain
    found=store.rows('SELECT DISTINCT url FROM results WHERE run_id=? AND official_brand=?',(run,'Grenade'))
    urls=[x['url'] for x in found]+['https://'+x['domain']+'/' for x in official]
    for url in list(dict.fromkeys(urls))[:manifest['technical_limit']]:
        result=audit_site(url)
        # A redirect to an unvalidated host cannot establish official content.
        final=result.get('page',{}).get('url',url)
        if official_brand(domain(final),manifest['domains'])!='Grenade':
            result={'url':url,'status':'ownership_unverified_after_redirect','redirect_url':final}
        raw=result.pop('raw_html','')
        store.page(run,url,'technical',result['status'],result,raw)
    store.finish(run,'partial' if failed else 'complete')
    return run,None

def report(store,run,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    row=store.rows('SELECT * FROM runs WHERE id=?',(run,))[0];manifest=json.loads(row['manifest'])
    q,r=frames(store,run);metrics=visibility(q,r,official_validated=any(x.get('brand')=='Grenade' and x.get('evidence_url') and x.get('evidence_note') for x in manifest['domains'].get('official',[])))
    opportunities=gaps(store,run,manifest['brands'],manifest['domains']) if not q.empty else []
    data={'run':run,'status':row['status'],'started':row['started'],'fingerprint':row['fingerprint'],
        'purpose':manifest.get('purpose','audit'),'metrics':metrics,'opportunities':opportunities,'limitations':[
        'DeepSeek returned order is not Google ranking. No search volume or conversion data used.',
        'No direct ChatGPT, Perplexity or AI Overview tests. GEO is a diagnostic heuristic.',
        'Brand detection uses result text and validated ownership, not full page mentions unless fetched.',
        'Missing results do not demonstrate index exclusion. Hypotheses require validation.',
        'Authority tier is provider supplied or unknown; never inferred from rerank score.']}
    (dest/f'run-{run}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    q.to_csv(dest/f'queries-{run}.csv',index=False);r.to_csv(dest/f'results-{run}.csv',index=False)
    text=f'# Grenade executive evidence summary\n\nRun {run}: {row["status"]}. Purpose: {manifest.get("purpose","audit")}.\n\n'
    if not metrics['successful_queries']:text+='No successful live searches. Grenade visibility, competitor dominance and commercial opportunity rankings are **not measured**. No conclusion about poor visibility is supported.\n'
    else:
        official_value=str(metrics['official_top20_pct'])+'%' if metrics['official_top20_pct'] is not None else 'Unverified ownership scope'
        text+=f'Successful queries: {metrics["successful_queries"]}; failed queries excluded: {metrics["failed_queries"]}. Grenade Top-20 mention coverage: {metrics["mentions_top20_pct"]}%. Official-domain coverage: {official_value}.\n\n'
        for i,o in enumerate(opportunities[:10],1):text+=f'{i}. {o["query"]} — {o["priority_score"]}/100. {o["recommendation"]} Confidence: {o["confidence"]}.\n'
    text+='\n'+ '\n'.join('- '+x for x in data['limitations'])
    (dest/f'executive-{run}.md').write_text(text)
    return data

def main():
    load_settings()
    parser=argparse.ArgumentParser(description='Evidence-first Grenade search audit')
    parser.add_argument('command',choices=['check','probe','plan','run','report','import-data'])
    parser.add_argument('--db',default=os.getenv('AUDIT_DB','data/audits.sqlite'))
    parser.add_argument('--queries',default=str(ROOT/'config/queries.csv'))
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--top',type=int,default=20)
    parser.add_argument('--fetch-limit',type=int,default=5)
    parser.add_argument('--technical-limit',type=int,default=5)
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--run-id',type=int)
    parser.add_argument('--out',default='reports')
    parser.add_argument('--file');parser.add_argument('--source',choices=['gsc','google_ads','retailer'])
    args=parser.parse_args()
    if min(args.limit,args.top)<1 or args.top>20 or min(args.fetch_limit,args.technical_limit)<0:parser.error('Invalid limits')
    if args.command=='check':
        checked=check_key()
        print(json.dumps(checked,ensure_ascii=False,indent=2))
        raise SystemExit(0 if checked['authenticated'] else 2)
    store=Store(project_path(args.db))
    if args.command=='import-data':
        if not args.file or not args.source:parser.error('--file and --source required')
        with open(args.file,encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        if not rows or 'query' not in rows[0]:parser.error('CSV must contain query column')
        store.execute('INSERT INTO imports(source,timestamp,raw) VALUES(?,?,?)',(args.source,now(),json.dumps(rows)))
        print(f'Imported {len(rows)} rows. Stored separately; not automatically joined or treated as revenue evidence.');return
    if args.command=='report':
        if not args.run_id:parser.error('--run-id required')
        report(store,args.run_id,args.out);print('Report exported');return
    contract=json.loads(project_path(os.getenv('API_CONTRACT','config/api_contract.json')).read_text())
    brands=json.loads((ROOT/'config/brands.json').read_text());domains=json.loads((ROOT/'config/domains.json').read_text())
    if args.command=='probe':
        manifest,fingerprint=probe_plan(args.queries,contract,brands,domains)
        run,error=run_audit(store,manifest,fingerprint,refresh=True)
        outcome=probe_result(store,run)
        if error:outcome['message']=error
        print(json.dumps(outcome,ensure_ascii=False,indent=2))
        raise SystemExit(0 if outcome['search_ok'] and outcome['fetch_ok'] else 2)
    manifest,fingerprint=plan(args.queries,contract,brands,domains,args.limit,args.top,args.fetch_limit,args.technical_limit)
    if args.command=='plan':
        pricing=contract.get('pricing',{})
        def unit(kind):
            override=os.getenv(kind.upper()+'_COST_PER_REQUEST')
            return float(override) if override else pricing.get(kind+'_per_successful_request')
        search_price,fetch_price=unit('search'),unit('fetch')
        potential_cost=round(len(manifest['queries'])*search_price+args.fetch_limit*fetch_price,6) if search_price is not None and fetch_price is not None else None
        print(json.dumps({'queries':len(manifest['queries']),'query_set_fingerprint':fingerprint,
            'planned_search_calls':len(manifest['queries']),'max_fetch_calls':args.fetch_limit,
            'http_technical_pages':args.technical_limit,'request_budget':os.getenv('MAX_REQUESTS','100'),
            'search_price_per_billable_request':search_price,'fetch_price_per_billable_request':fetch_price,
            'estimated_cost_if_all_planned_calls_billable':potential_cost,'currency':pricing.get('currency','Unknown'),
            'billing_note':'Failures, empty search results, empty Fetch content and cache hits are not billable. List-price estimate; provider free periods can differ.',
            'contract_verified':contract['verified'],'queries_selected':manifest['queries']},ensure_ascii=False,indent=2));return
    run,error=run_audit(store,manifest,fingerprint,args.refresh);report(store,run,args.out)
    print(json.dumps({'run':run,'error':error},ensure_ascii=False))
    if error:raise SystemExit(2)

if __name__=='__main__':main()
