import json
import pandas as pd
from .classify import mentions

WEIGHTS={'purchase_intent':.25,'visibility_gap':.20,'competitor_dominance':.15,
         'distribution_relevance':.15,'ease':.10,'confidence':.15}

def score(factors):
    if set(factors)!=set(WEIGHTS) or any(not 0<=float(x)<=5 for x in factors.values()):
        raise ValueError('All priority factors must be in [0,5]')
    return round(20*sum(WEIGHTS[k]*factors[k] for k in WEIGHTS),1)

def frames(store,run):
    q=pd.DataFrame(store.rows('SELECT * FROM searches WHERE run_id=?',(run,)))
    r=pd.DataFrame(store.rows('SELECT * FROM results WHERE run_id=? ORDER BY query_id,rank',(run,)))
    if not r.empty: r['brands']=r.brands.apply(json.loads)
    return q,r

def visibility(q,r,brand='Grenade',official_validated=True):
    ok=q[q.status=='ok'] if not q.empty else q
    total=len(ok)
    result={'successful_queries':total,'failed_queries':int((q.status!='ok').sum()) if not q.empty else 0}
    hits=r[r.brands.apply(lambda x:brand in x)] if not r.empty else r
    official=r[r.official_brand==brand] if not r.empty else r
    for name,data in [('mentions',hits),('official',official)]:
        for cutoff in [3,10,20]:
            count=data[data['rank']<=cutoff].query_id.nunique() if not data.empty else 0
            result[f'{name}_top{cutoff}_pct']=round(100*count/total,1) if total else None
        if name=='official' and not official_validated:
            for cutoff in [3,10,20]:result[f'official_top{cutoff}_pct']=None
        result[f'{name}_avg_best_position']=round(float(data.groupby('query_id')['rank'].min().mean()),2) if not data.empty else None
    if not official_validated:result['official_avg_best_position']=None
    return result

def grouped_visibility(q,r,brands,group='category',official_validated=True):
    out=[]
    if q.empty:return pd.DataFrame()
    for value,qs in q.groupby(group):
        rs=r[r.query_id.isin(qs.query_id)] if not r.empty else r
        for brand in brands:
            out.append({group:value,'brand':brand,**visibility(qs,rs,brand,official_validated=official_validated)})
    return pd.DataFrame(out)

def fetched_pages(store,run):
    return [dict(x,evidence=json.loads(x['evidence'])) for x in store.rows('SELECT * FROM pages WHERE run_id=?',(run,))]

def gaps(store,run,brands,domains):
    q,r=frames(store,run);out=[];pages=fetched_pages(store,run)
    content={p['url']:p['evidence'] for p in pages if p['kind']=='fetch' and p['status']=='ok'}
    for item in q.to_dict('records'):
        if item['status']!='ok' or item['priority']>2:continue
        rows=r[r.query_id==item['query_id']] if not r.empty else r
        hits=rows[rows.brands.apply(lambda x:'Grenade' in x)] if not rows.empty else rows
        best=int(hits['rank'].min()) if not hits.empty else None
        if best and best<=3:continue
        leaders=rows[rows['rank']<=5].to_dict('records') if not rows.empty else []
        rivals=sorted(set(b for row in leaders for b in row['brands'] if b!='Grenade'))
        official_rows=rows[rows.official_brand=='Grenade'] if not rows.empty else rows
        equivalent=official_rows.url.tolist() if not official_rows.empty else []
        evidence=[]
        for row in leaders:
            page=content.get(row['url'])
            evidence.append({'rank':row['rank'],'url':row['url'],'title':row['title'],'classification':row['classification'],
                'provided_information':page.get('excerpt') if page else 'Not fetched / fetch budget exhausted',
                'headings':page.get('headings',[]) if page else [],'brands_in_page':page.get('brands',[]) if page else []})
        third_party=any(x['classification'] in ('Review','Comparison / guide') for x in leaders)
        retailer=any(x['classification']=='Retailer' for x in leaders)
        category='Insufficient third-party coverage' if third_party else 'Weak retailer visibility' if retailer else 'Unverified hypotheses requiring additional evidence'
        if item['category']=='Product comparison' and not equivalent: category='Missing comparison content'
        elif item['category']=='Category discovery' and not equivalent and not third_party: category='Missing category content'
        # Missing page equivalence in this result set is a hypothesis, not a site-wide absence claim.
        distribution=[x for x in domains.get('distribution',[]) if x.get('brand')=='Grenade' and x.get('url') and x.get('verified_at')]
        relevant=[x for x in distribution if str(x.get('retailer','')).lower() in item['query'].lower()]
        confidence=3 if any(x['url'] in content for x in leaders) else 2
        factors={'purchase_intent':float(item['purchase_intent']), 'visibility_gap':5 if best is None else 4 if best>10 else 3,
            'competitor_dominance':min(5,len([x for x in leaders if any(b!='Grenade' for b in x['brands'])])),
            'distribution_relevance':5 if relevant else 3 if distribution else 1,
            'ease':3 if retailer or third_party else 2,'confidence':confidence}
        action=('Review Canadian retailer listings, stock and product facts; improve listing content where authorized.' if retailer else
            'Pitch an evidence-based product evaluation to the cited publishers; provide Canadian availability and accurate SKU facts.' if third_party else
            'Inventory existing pages, then create or improve a Canadian intent-matched page if the gap is confirmed.')
        out.append({'query_id':item['query_id'],'query':item['query'],'category':category,'priority_score':score(factors),
            'best_grenade_position':best,'competitors':', '.join(rivals),'evidence':evidence,
            'equivalent_page_candidates':equivalent,'equivalent_status':'Candidate returned; manual intent review required' if equivalent else 'Not observed in this search; site-wide absence unverified',
            'diagnosis':'Observed returned-result gap; relevance, authority, stock and technical causes are unverified hypotheses.',
            'recommendation':action,'confidence':'Medium' if confidence==3 else 'Low',
            'effort':'Medium (estimate; validate with owner)','owner':'Ecommerce / retailer account manager' if retailer else 'SEO + content / PR',
            'channel':'Retailer listing opportunity inferred from web results; marketplace search untested' if retailer else 'Organic web search / earned coverage',
            'expected_impact':'Potential acquisition coverage; traffic and revenue lift unquantified',
            'next_steps':'Validate page intent, product availability and ownership; check GSC/retailer data; assign scope and measure next weekly run.',
            'factors':factors,'distribution_evidence':relevant or distribution})
    return sorted(out,key=lambda x:-x['priority_score'])

def compare(store,current,baseline):
    a=store.rows('SELECT * FROM runs WHERE id=?',(current,))[0]
    b=store.rows('SELECT * FROM runs WHERE id=?',(baseline,))[0]
    if a['fingerprint']!=b['fingerprint']:
        raise ValueError('Incomparable query sets, classification rules or parameters; use matching fingerprints')
    qa,ra=frames(store,current);qb,rb=frames(store,baseline)
    common=set(qa[qa.status=='ok'].query_id)&set(qb[qb.status=='ok'].query_id)
    def subset(q,r):
        return visibility(q[q.query_id.isin(common)],r[r.query_id.isin(common)] if not r.empty else r,official_validated=any(x.get('brand')=='Grenade' and x.get('evidence_url') and x.get('evidence_note') for x in json.loads(a['manifest']).get('domains',{}).get('official',[])))
    return {'paired_successful_queries':len(common),'baseline':subset(qb,rb),'current':subset(qa,ra)}
