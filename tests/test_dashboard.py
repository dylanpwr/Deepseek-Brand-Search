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
