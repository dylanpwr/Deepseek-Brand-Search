import json
import pytest
from grenade.analysis import frames,visibility,score,compare,gaps
from grenade.classify import normalize,matches,mentions
from grenade.runner import load_queries,select_queries,plan,ROOT,run_audit,report

BRANDS={'Grenade':[r'\bgrenade\b'],'Quest':[r'\bquest\b'],'ONE':[r'\bONE bars?\b']}
DOMAINS={'official':[{'domain':'brand.test','brand':'Grenade','evidence_url':'https://brand.test/legal','evidence_note':'Test fixture only'}],'retailers':['retailer.test']}

def test_brand_boundaries_and_ownership():
    assert not matches('fakebrand.test','brand.test')
    assert not matches('brand.test.evil.test','brand.test')
    assert matches('ca.brand.test','brand.test')
    assert not mentions('one of the best bars',BRANDS)
    assert mentions('ONE bar',BRANDS)==['ONE']
    r=normalize({'title':'Protein bars','url':'https://brand.test/product'},1,BRANDS,DOMAINS)
    assert r['official_brand']=='Grenade' and 'Grenade' in r['brands']
    assert r['authority_tier']=='Unknown / not supplied'

def test_metrics_unique_queries_and_error_denominator(store,query):
    run=store.start('same',{})
    store.search(run,query,'ok')
    for rank in [2,4]:store.result(run,'q1',normalize({'title':'Grenade review','url':f'https://publisher.test/{rank}'},rank,BRANDS,DOMAINS))
    q2=dict(query,id='q2');store.search(run,q2,'ok',raw={'items':[]})
    store.search(run,dict(query,id='q3'),'error',error='network')
    q,r=frames(store,run);v=visibility(q,r)
    assert v['successful_queries']==2 and v['failed_queries']==1
    assert v['mentions_top3_pct']==50 and v['mentions_top20_pct']==50
    assert v['mentions_avg_best_position']==2 and v['official_top20_pct']==0
    assert visibility(q[q.status=='error'],r.iloc[:0])['mentions_top20_pct'] is None

def test_empty_result_is_observed_gap(store,query):
    run=store.start('same',{})
    store.search(run,query,'ok',raw={'items':[]})
    ops=gaps(store,run,BRANDS,DOMAINS)
    assert len(ops)==1 and ops[0]['best_grenade_position'] is None
    assert 'unverified' in ops[0]['equivalent_status']
    assert ops[0]['confidence']=='Low'

def test_score_transparent_bounds():
    from grenade.analysis import WEIGHTS
    assert sum(WEIGHTS.values())==1
    assert score({k:5 for k in WEIGHTS})==100
    assert score({k:0 for k in WEIGHTS})==0
    with pytest.raises(ValueError):score({})

def test_comparison_paired_success_and_fingerprint(store,query):
    a=store.start('same',{});b=store.start('same',{})
    store.search(a,query,'ok');store.search(b,query,'ok')
    store.search(a,dict(query,id='q2'),'error');store.search(b,dict(query,id='q2'),'ok')
    assert compare(store,b,a)['paired_successful_queries']==1
    c=store.start('other',{})
    with pytest.raises(ValueError,match='Incomparable'):compare(store,c,a)

def test_query_library_reproducible_and_nonbranded():
    rows=load_queries(ROOT/'config/queries.csv')
    assert len(rows)>=100 and sum(q['branded'] for q in rows)/len(rows)<.2
    small=select_queries(rows,10)
    assert len(small)==10 and len({q['category'] for q in small})==5
    assert small==select_queries(rows,10)
    a,h1=plan(ROOT/'config/queries.csv',{},BRANDS,DOMAINS,10,20,5,5)
    b,h2=plan(ROOT/'config/queries.csv',{},BRANDS,DOMAINS,11,20,5,5)
    assert h1!=h2

def test_blocked_run_preserves_status_without_fake_data(store,contract,tmp_path):
    contract['verified']=False
    manifest={'contract':contract,'brands':BRANDS,'domains':DOMAINS}
    run,error=run_audit(store,manifest,'blocked')
    assert error and store.rows('SELECT status FROM runs')[0]['status']=='blocked'
    result=report(store,run,tmp_path)
    assert result['metrics']['mentions_top20_pct'] is None and not result['opportunities']

def test_full_pipeline_with_synthetic_transport(store,contract,query,monkeypatch,tmp_path):
    # Only synthetic fixtures, never written into the distributed audit dataset.
    class FakeClient:
        def __init__(self,*args,**kwargs):pass
        def search(self,*args):
            return ([{'title':'Quest best protein bars','url':'https://publisher.test/review','snippet':'Quest bars review'}],{'fixture':'synthetic'},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*args):
            return ('<h1>Comparison</h1><p>Quest protein bars nutrition and availability</p>',{'fixture':'synthetic'},'2026-01-01T00:00:00+00:00',False)
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    manifest={'contract':contract,'queries':[query],'brands':BRANDS,'domains':{'official':[],'retailers':[]},'top':20,'fetch_limit':1,'technical_limit':0}
    run,error=run_audit(store,manifest,'synthetic-test')
    assert not error
    result=report(store,run,tmp_path)
    assert result['metrics']['mentions_top20_pct']==0
    assert result['opportunities'][0]['competitors']=='Quest'
    assert result['opportunities'][0]['evidence'][0]['provided_information'].startswith('Comparison')
    assert store.rows('SELECT * FROM pages')[0]['raw']=='{"fixture": "synthetic"}'

def test_unverified_official_scope_is_not_zero(store,query):
    run=store.start('unverified',{})
    store.search(run,query,'ok')
    q,r=frames(store,run)
    metrics=visibility(q,r,official_validated=False)
    assert metrics['mentions_top20_pct']==0
    assert metrics['official_top20_pct'] is None
