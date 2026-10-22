import pytest
from grenade.storage import Store

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'test.sqlite')

@pytest.fixture
def contract():
    # Synthetic transport fixture. This is NOT a claimed DeepSeek API schema.
    return {'verified':True,'verified_at':'test-only','documentation_sha256':'test-only',
      'auth':{'header':'Authorization','prefix':'Bearer '},'max_results':20,'max_rpm':100000,
      'retry_statuses':[429,500,502,503],'retry_after_header':'Retry-After',
      'search':{'url':'https://api.example.test/search','method':'POST','payload':{},
        'query_field':'q','limit_field':'n','results_path':'items','fields':{'title':'title','url':'url','snippet':'snippet'}},
      'fetch':{'url':'https://api.example.test/fetch','method':'POST','payload':{},'url_field':'url','content_path':'content'}}

@pytest.fixture
def query():
    return {'id':'q1','query':'best protein bars Canada','category':'Category discovery','branded':False,
      'language':'en','priority':1,'purchase_intent':3,'canada_relevance':5}
