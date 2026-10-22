import socket
import pytest
from grenade.technical import parse_html,findings,geo,safe_url,audit_site

HTML="""<html lang="en-CA"><head><title>Test bar</title><meta name="description" content="Canadian protein bar"><link rel="canonical" href="/products/bar"><meta name="robots" content="noindex"><link rel="alternate" hreflang="fr-CA" href="/fr/bar"><script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Test","offers":{"@type":"Offer","priceCurrency":"CAD","availability":"https://schema.org/InStock"}},{"@type":"Organization","name":"Test"}]}</script></head><body><h1>Test bar</h1><h2>Canada comparison</h2><a href="/collection">Bars</a></body></html>"""

def test_metadata_graph_schema_and_geo():
    p=parse_html('https://example.test/products/bar',HTML,{'X-Robots-Tag':'noarchive'})
    assert p['canonical']=='https://example.test/products/bar'
    assert len(p['products'])==1 and len(p['offers'])==1 and len(p['organizations'])==1
    assert p['hreflang'][0]['lang']=='fr-CA'
    assert p['x_robots_tag']=='noarchive' and p['html_lang']=='en-CA'
    assert any('noindex' in x['finding'] for x in findings(p))
    assert 0<=geo(p)['score']<=100
    assert 'Diagnostic heuristic' in geo(p)['label']

def test_private_urls_blocked(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',80))])
    with pytest.raises(ValueError,match='Non-public'):safe_url('http://localhost/')
    for url in ['file:///etc/passwd','https://user:pass@example.test','https://example.test:9000']:
        with pytest.raises(ValueError):safe_url(url)

def test_robots_respected():
    calls=[]
    def request(url):
        calls.append(url)
        return 200,'User-agent: *\nDisallow: /',{},url
    p=audit_site('https://example.test/products/bar',request=request)
    assert p['status']=='robots_disallowed' and len(calls)==1
    assert 'page' not in p

def test_inaccessible_is_not_a_confirmed_issue():
    def request(url):return 403,'Blocked',{},url
    p=audit_site('https://example.test/products/bar',request=request)
    assert p['status']=='robots_inaccessible' and 'findings' not in p

def test_sitemap_and_page_audit():
    def request(url):
        body='User-agent: *\nAllow: /\nSitemap: https://example.test/map.xml' if url.endswith('robots.txt') else '<urlset><url><loc>https://example.test/products/bar</loc></url></urlset>' if url.endswith('.xml') else HTML
        return 200,body,{},url
    p=audit_site('https://example.test/products/bar',request=request)
    assert p['status']=='ok' and p['resources'][1]['loc_count']==1
