import json
from unittest.mock import Mock
import pytest,requests
from grenade.client import Client,APIError

def response(status=200,data=None,headers=None):
    r=Mock(status_code=status,headers=headers or {});r.json.return_value=data
    return r

def test_contract_is_fail_closed(store,contract):
    contract['verified']=False
    with pytest.raises(APIError,match='unverified'):Client(store,1,contract,key='test')

def test_missing_credentials(store,contract,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    with pytest.raises(APIError,match='not configured'):Client(store,1,contract)

def test_mapping_auth_limit_cache_and_raw(store,contract):
    session=Mock();payload={'items':[{'title':'A','url':'https://example.test/a','snippet':'Grenade'}]}
    session.request.return_value=response(data=payload)
    c=Client(store,1,contract,key='test',session=session,sleep=lambda x:None)
    rows,raw,stamp,cached=c.search('bars',20)
    assert rows[0]['title']=='A' and raw==payload and not cached
    assert session.request.call_args.kwargs['json']=={'q':'bars','n':20}
    assert session.request.call_args.kwargs['headers']=={'Authorization':'Bearer test','Content-Type':'application/json'}
    assert c.search('bars')[3] is True and session.request.call_count==1
    assert store.rows('SELECT raw FROM cache')[0]['raw']==json.dumps(payload)
    assert len(store.rows('SELECT * FROM requests'))==1
    c.search('bars',refresh=True)
    assert session.request.call_count==2

def test_retry_after_and_budget(store,contract,monkeypatch):
    session=Mock();session.request.side_effect=[response(429,headers={'Retry-After':'4'}),response(data={'items':[]})]
    waits=[];c=Client(store,1,contract,key='x',session=session,sleep=waits.append)
    assert c.search('bars')[0]==[] and 4 in waits
    assert len(store.rows('SELECT * FROM requests'))==2
    monkeypatch.setenv('MAX_REQUESTS','1')
    c=Client(store,2,contract,key='x',session=Mock(),sleep=lambda x:None)
    c.count=1
    with pytest.raises(APIError,match='budget'):c.search('different')

def test_nonretry_auth_and_schema_failure(store,contract):
    session=Mock();session.request.return_value=response(401)
    c=Client(store,1,contract,key='x',session=session,sleep=lambda x:None)
    with pytest.raises(APIError,match='401'):c.search('bars')
    assert session.request.call_count==1
    session.request.return_value=response(data={'unexpected':True})
    with pytest.raises(APIError,match='schema'):c.search('new')
    assert store.rows('SELECT * FROM cache') # preserve raw schema mismatch

def test_timeout_retry_and_unknown_cost(store,contract):
    session=Mock();session.request.side_effect=requests.Timeout()
    c=Client(store,1,contract,key='x',session=session,sleep=lambda x:None)
    with pytest.raises(APIError,match='network'):c.search('bars')
    assert session.request.call_count==3
    assert all(r['cost'] is None for r in store.rows('SELECT * FROM requests'))

def test_fetch_mapping(store,contract):
    session=Mock();session.request.return_value=response(data={'content':'<h1>Test</h1>'})
    c=Client(store,1,contract,key='x',session=session,sleep=lambda x:None)
    assert c.fetch('https://example.test')[0]=='<h1>Test</h1>'

def test_long_retry_delay_does_not_retry_early(store,contract):
    session=Mock();session.request.return_value=response(429,headers={'Retry-After':'120'})
    c=Client(store,1,contract,key='x',session=session,sleep=lambda x:None)
    with pytest.raises(APIError,match='retry later'):c.search('bars')
    assert session.request.call_count==1

def test_missing_optional_field_is_unknown(store,contract):
    contract['search']['fields']['publication_date']='date'
    session=Mock();session.request.return_value=response(data={'items':[{'title':'Test','url':'https://example.test','snippet':'Test'}]})
    c=Client(store,1,contract,key='x',session=session,sleep=lambda x:None)
    assert c.search('new query')[0][0]['publication_date'] is None
