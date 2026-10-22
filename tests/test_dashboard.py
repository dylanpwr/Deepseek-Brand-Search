from streamlit.testing.v1 import AppTest
from grenade.runner import ROOT

def test_dashboard_all_five_empty_pages(tmp_path,monkeypatch):
    monkeypatch.setenv('AUDIT_DB',str(tmp_path/'empty.sqlite'))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    assert not app.exception
    for page in ['Executive Overview','Keyword Explorer','Competitor Intelligence','Technical & GEO Audit','Action Plan']:
        app.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not app.exception, page

def test_dashboard_all_five_with_synthetic_test_data(tmp_path,monkeypatch):
    import json
    from grenade.storage import Store
    from grenade.classify import normalize
    db=tmp_path/'synthetic.sqlite';store=Store(db)
    brands={'Grenade':[r'\bgrenade\b'],'Quest':[r'\bquest\b']}
    domains={'official':[],'retailers':[]}
    run=store.start('test-fixture',{'brands':brands,'domains':domains})
    query={'id':'q001','query':'test-only protein bars','category':'Category discovery','branded':False,'language':'en','priority':1,'purchase_intent':3,'canada_relevance':5}
    store.search(run,query,'ok',raw={'synthetic':True})
    store.result(run,'q001',normalize({'title':'Quest test review','url':'https://example.test/review','snippet':'Test-only Quest comparison'},1,brands,domains))
    store.page(run,'https://example.test/review','fetch','ok',{'excerpt':'Synthetic test fixture only','brands':['Quest'],'candidate_brands':['Example Brand']},'{"synthetic":true}')
    store.finish(run,'complete')
    store.execute('INSERT INTO requests(run_id,kind,timestamp,status,cost,error) VALUES(?,?,?,?,?,?)',(run,'search','2026-01-01T00:00:00+00:00',200,None,None))
    monkeypatch.setenv('AUDIT_DB',str(db))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    for page in ['Executive Overview','Keyword Explorer','Competitor Intelligence','Technical & GEO Audit','Action Plan']:
        app.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not app.exception,page


def test_connection_button_shows_key_result(tmp_path,monkeypatch):
    monkeypatch.setenv('AUDIT_DB',str(tmp_path/'connection.sqlite'))
    monkeypatch.setattr('grenade.connection.check_key',lambda:{'authenticated':True,'message':'Test key accepted; Search untested.'})
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    next(button for button in app.button if button.label=='Check DeepSeek connection').click().run(timeout=30)
    assert not app.exception
    assert any('Test key accepted' in item.value for item in app.success)


def test_unconfigured_service_disables_audit_even_with_key(tmp_path,monkeypatch):
    monkeypatch.setenv('AUDIT_DB',str(tmp_path/'blocked.sqlite'))
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-test-key')
    missing=tmp_path/'unconfigured.json'
    missing.write_text('{"verified":false}')
    monkeypatch.setenv('API_CONTRACT',str(missing))
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    assert not app.exception
    assert next(button for button in app.button if button.label=='Start audit').disabled
    assert any('Search/Fetch is not configured' in item.value for item in app.warning)
    import sqlite3
    with sqlite3.connect(tmp_path/'blocked.sqlite') as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==0


def test_service_test_button_checks_both_apis(tmp_path,monkeypatch):
    monkeypatch.setenv('AUDIT_DB',str(tmp_path/'probe.sqlite'))
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-test-key')
    calls=[]
    class FakeClient:
        def __init__(self,*a,**k):pass
        def search(self,*a):
            calls.append('search')
            return ([{'title':'Grenade bars test','url':'https://example.test/bar'}],{'synthetic':True},'2026-01-01T00:00:00+00:00',False)
        def fetch(self,*a):
            calls.append('fetch')
            return ('# Test bar',{'title':'Test bar'},'2026-01-01T00:00:00+00:00',False)
    monkeypatch.setattr('grenade.runner.Client',FakeClient)
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    next(button for button in app.button if button.label=='Test Search & Fetch').click().run(timeout=30)
    assert not app.exception
    assert calls==['search','fetch']
    assert any('Search and Fetch both succeeded' in item.value for item in app.success)
    assert any('not the acquisition baseline' in item.value for item in app.info)
