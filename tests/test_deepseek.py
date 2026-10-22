"""Contract tests from the user-supplied official guide; all responses are synthetic."""
import hashlib
import json
import sqlite3
from unittest.mock import Mock

import pytest
from grenade.client import Client, APIError
from grenade.classify import normalize
from grenade.storage import Store
from grenade.runner import ROOT,run_audit


def response(code,data):
    r=Mock(status_code=code,headers={})
    r.json.return_value=data
    return r


def client(store,contract,responses):
    session=Mock();session.request.side_effect=responses
    return Client(store,1,contract,key='synthetic-key-for-tests',session=session,sleep=lambda x:None),session


def test_saved_documentation_provenance(deepseek_contract):
    saved=(ROOT/deepseek_contract['documentation_snapshot']).read_bytes()
    assert hashlib.sha256(saved).hexdigest()==deepseek_contract['documentation_sha256']
    assert 'User-supplied' in deepseek_contract['documentation_source']


def test_documented_search_and_fetch_request_and_field_mapping(store,deepseek_contract):
    # Synthetic result follows the saved guide's schema. It is not a real SERP.
    raw={'results':[{'title':'Test bar','url':'https://example.test/bar','snippet':'Test',
        'summary':'Test summary','rerank_score':2.4,'authority':0,'date':'2026-06-01T00:00:00+00:00',
        'content':'','site_name':None,'site_icon':None}]}
    c,session=client(store,deepseek_contract,[response(200,raw),response(200,{'title':'Test bar','content':'# Test bar\n\nFacts'})])
    rows,original,*_=c.search('meilleures barres protéinées Canada')
    args=session.request.call_args
    assert args.args==('POST','https://api.deepseek.com/v1/tools/search')
    assert args.kwargs['json']=={'need_content':False,'query':'meilleures barres protéinées Canada','count':20}
    assert args.kwargs['headers']['Content-Type']=='application/json'
    assert rows[0]['authority_tier']==0 and rows[0]['publication_date']==raw['results'][0]['date']
    normalized=normalize(rows[0],1,{}, {'official':[],'retailers':[]})
    assert normalized['authority_tier']==0
    assert c.fetch('https://example.test/bar')[0]=='# Test bar\n\nFacts'
    assert session.request.call_args.args==('POST','https://api.deepseek.com/v1/tools/fetch')
    assert session.request.call_args.kwargs['json']=={'url':'https://example.test/bar'}
    ledger=store.rows('SELECT * FROM requests')
    assert sum(x['cost'] for x in ledger)==.0015
    assert all(x['billable']==1 for x in ledger)


@pytest.mark.parametrize('status,payload,cost,billable',[
    (200,{'results':[]},0,0),
    (200,{'results':[{'title':'Test','url':'https://example.test'}]},.00075,1),
    (401,{'error':{'message':'invalid key'}},0,0),
    (402,{'error':{'message':'balance'}},0,0),
    (200,{'unexpected':'schema'},None,None),
])
def test_documented_billability(store,deepseek_contract,status,payload,cost,billable):
    c,_=client(store,deepseek_contract,[response(status,payload)])
    try:c.search('test bars')
    except APIError:pass
    row=store.rows('SELECT * FROM requests')[0]
    assert row['cost']==cost and row['billable']==billable
    assert json.loads(row['raw'])==payload


def test_fetch_empty_is_not_billed_or_recorded_as_page(store,deepseek_contract):
    c,_=client(store,deepseek_contract,[response(200,{'title':'','content':''})])
    with pytest.raises(APIError,match='no usable'):c.fetch('https://example.test')
    assert store.rows('SELECT cost FROM requests')[0]['cost']==0


@pytest.mark.parametrize('query',['','  ','é'*129])
def test_invalid_query_never_requests_or_charges(store,deepseek_contract,query):
    c,session=client(store,deepseek_contract,[])
    with pytest.raises(APIError,match='Unicode'):c.search(query)
    session.request.assert_not_called()
    assert not store.rows('SELECT * FROM requests')


def test_unicode_length_and_query_operators_preserved(store,deepseek_contract):
    c,session=client(store,deepseek_contract,[response(200,{'results':[]})])
    query='é'*128
    c.search(query)
    assert session.request.call_args.kwargs['json']['query']==query
    c.session.request.side_effect=[response(200,{'results':[]})]
    query='barres site:example.test lang:fr'
    c.search(query)
    assert session.request.call_args.kwargs['json']['query']==query


@pytest.mark.parametrize('url',['ftp://example.test','https://user:pass@example.test','https://user@example.test','https://','x'*8193])
def test_invalid_fetch_url_never_requests(store,deepseek_contract,url):
    c,session=client(store,deepseek_contract,[])
    with pytest.raises(APIError,match='Fetch URL'):c.fetch(url)
    session.request.assert_not_called()


def test_documented_retries_and_independent_limits(store,deepseek_contract,monkeypatch):
    monkeypatch.setenv('REQUESTS_PER_MINUTE','100000')
    c,session=client(store,deepseek_contract,[response(408,{'error':{}}),response(504,{'error':{}}),response(200,{'results':[]})])
    assert c.intervals=={'search':.01,'fetch':.04}
    c.search('test bars')
    assert session.request.call_count==3
    assert sum(row['cost'] for row in store.rows('SELECT * FROM requests'))==0


@pytest.mark.parametrize('status',[400,401,402,403,404,413])
def test_other_4xx_never_retry(store,deepseek_contract,status):
    c,session=client(store,deepseek_contract,[response(status,{'error':{'message':'synthetic-key-for-tests'}})])
    with pytest.raises(APIError):c.fetch('https://example.test')
    assert session.request.call_count==1
    assert 'synthetic-key-for-tests' not in store.rows('SELECT raw FROM requests')[0]['raw']


def test_upgrade_existing_database_without_losing_history(tmp_path):
    path=tmp_path/'old.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE requests(id INTEGER PRIMARY KEY,run_id INTEGER,kind TEXT,timestamp TEXT,status INTEGER,cost REAL,error TEXT)')
        db.execute("INSERT INTO requests(kind,status) VALUES('search',401)")
    store=Store(path)
    assert store.rows('SELECT * FROM requests')[0]['status']==401
    assert {'raw','billable'}.issubset(store.rows('SELECT * FROM requests')[0])
    Store(path) # upgrade is idempotent


def test_markdown_headings_are_evidence(store,deepseek_contract,query,monkeypatch):
    class FakeClient:
        def __init__(self,*a,**k):pass
        def search(self,*a):return ([{'title':'Quest test','url':'https://example.test/bar'}],{'results':[]},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*a):return ('# Comparison\n\n## Nutrition facts\n\nQuest protein bars',{'title':'Test title'},'2026-01-01T00:00:00+00:00',False)
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    manifest={'contract':deepseek_contract,'queries':[query],'brands':{'Grenade':[r'\bgrenade\b'],'Quest':[r'\bquest\b']},'domains':{'official':[],'retailers':[]},'top':20,'fetch_limit':1,'technical_limit':0}
    run,error=run_audit(store,manifest,'synthetic-markdown-test')
    evidence=json.loads(store.rows('SELECT evidence FROM pages')[0]['evidence'])
    assert evidence['headings']==['Comparison','Nutrition facts'] and evidence['title']=='Test title'


def test_probe_fetches_even_when_grenade_leads(store,deepseek_contract,monkeypatch):
    from grenade.runner import probe_plan,probe_result
    calls=[]
    class FakeClient:
        def __init__(self,*a,**k):pass
        def search(self,*a):
            calls.append('search')
            return ([{'title':'Grenade protein bars','url':'https://example.test/grenade'}],{'synthetic':True},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*a):
            calls.append('fetch')
            return ('# Grenade bars',{'title':'Grenade bars'},'2026-01-01T00:00:00+00:00',False)
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    manifest,fingerprint=probe_plan(ROOT/'config/queries.csv',deepseek_contract,{'Grenade':[r'\bgrenade\b']},{'official':[],'retailers':[]})
    run,error=run_audit(store,manifest,fingerprint,refresh=True)
    assert calls==['search','fetch'] and manifest['purpose']=='connection_probe'
    assert probe_result(store,run)['fetch_ok'] and probe_result(store,run)['search_ok']
    assert manifest['technical_limit']==0 and len(manifest['queries'])==1


def test_probe_does_not_claim_fetch_access_on_empty_search(store,deepseek_contract,monkeypatch):
    from grenade.runner import probe_plan,probe_result
    class FakeClient:
        def __init__(self,*a,**k):pass
        def search(self,*a):return ([],{'results':[]},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*a):raise AssertionError('No page available for Fetch')
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    manifest,fingerprint=probe_plan(ROOT/'config/queries.csv',deepseek_contract,{}, {'official':[],'retailers':[]})
    run,error=run_audit(store,manifest,fingerprint)
    outcome=probe_result(store,run)
    assert outcome['search_ok'] and not outcome['fetch_ok']
    assert 'not tested' in outcome['message']


def test_probe_reports_fetch_security_failure_without_seo_claim(store,deepseek_contract,monkeypatch):
    from grenade.runner import probe_plan,probe_result
    class FakeClient:
        def __init__(self,*a,**k):pass
        def search(self,*a):return ([{'title':'Test bars','url':'https://example.test'}],{},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*a):raise APIError('fetch HTTP 403: request blocked by security or network policy')
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    manifest,fingerprint=probe_plan(ROOT/'config/queries.csv',deepseek_contract,{}, {'official':[],'retailers':[]})
    run,error=run_audit(store,manifest,fingerprint)
    outcome=probe_result(store,run)
    assert outcome['search_ok'] and not outcome['fetch_ok']
    assert '403' in outcome['message'] and store.rows('SELECT status FROM runs')[0]['status']=='partial'


def test_cached_billable_response_does_not_add_an_attempt_or_cost(store,deepseek_contract):
    c,session=client(store,deepseek_contract,[response(200,{'results':[{'title':'Test bar','url':'https://example.test'}]})])
    c.search('test bars')
    assert c.search('test bars')[3] is True
    assert session.request.call_count==1
    assert sum(x['cost'] for x in store.rows('SELECT * FROM requests'))==.00075


def test_authority_unknown_is_not_treated_as_a_rank():
    row=normalize({'title':'Test','url':'https://example.test','authority_tier':-1,'rerank_score':0},1,{}, {'official':[],'retailers':[]})
    assert row['authority_tier']=='Unknown (-1)' and row['rank']==1 and row['rerank_score']==0
