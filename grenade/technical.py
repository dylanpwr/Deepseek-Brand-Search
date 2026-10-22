import ipaddress, json, socket, re
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from .classify import domain, mentions

USER_AGENT='GrenadeVisibilityAudit/1.0'

def safe_url(url):
    p=urlparse(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('Only public HTTP(S) URLs on standard ports are permitted')
    addresses=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('Non-public destination blocked')
    return url

def get_public(url,session=None):
    session=session or requests.Session()
    for _ in range(5):
        safe_url(url)
        response=session.get(url,timeout=25,allow_redirects=False,stream=True,headers={'User-Agent':USER_AGENT})
        if response.status_code in (301,302,303,307,308):
            url=urljoin(url,response.headers['Location']);response.close();continue
        chunks=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>3_000_000: response.close();raise ValueError('Page exceeds 3 MB limit')
            chunks.append(chunk)
        body=b''.join(chunks).decode(response.encoding or 'utf-8',errors='replace');response.close()
        return response.status_code,body,dict(response.headers),url
    raise ValueError('Too many redirects')

def nodes(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from nodes(v)
    elif isinstance(value,list):
        for v in value: yield from nodes(v)

def parse_html(url,html,headers=None):
    soup=BeautifulSoup(html,'html.parser');headers={k.lower():v for k,v in (headers or {}).items()}
    def meta(name):
        item=soup.find('meta',attrs={'name':re.compile('^'+re.escape(name)+'$',re.I)})
        return item.get('content') if item else None
    canonical=soup.find('link',rel='canonical');schemas=[];invalid=0
    for script in soup.find_all('script',type='application/ld+json'):
        try: schemas.extend(nodes(json.loads(script.string or script.get_text())))
        except (ValueError,TypeError): invalid+=1
    def typed(n,t):
        value=n.get('@type',[]);return t in (value if isinstance(value,list) else [value])
    products=[x for x in schemas if typed(x,'Product')]
    organizations=[x for x in schemas if typed(x,'Organization')]
    offers=[x for x in schemas if typed(x,'Offer') or typed(x,'AggregateOffer') or 'availability' in x]
    for tag in soup(['script','style','nav','footer']): tag.decompose()
    text=soup.get_text(' ',strip=True)
    langs=[{'lang':x.get('hreflang'),'url':urljoin(url,x.get('href',''))} for x in soup.find_all('link',hreflang=True)]
    return {'url':url,'title':soup.title.get_text(strip=True) if soup.title else None,
        'meta_description':meta('description'),'canonical':urljoin(url,canonical['href']) if canonical and canonical.get('href') else None,
        'robots':meta('robots'),'googlebot':meta('googlebot'),'x_robots_tag':headers.get('x-robots-tag'),
        'h1':[x.get_text(' ',strip=True) for x in soup.find_all('h1')],
        'headings':[x.get_text(' ',strip=True) for x in soup.find_all(['h2','h3'])],
        'word_count':len(text.split()),'products':products,'organizations':organizations,'offers':offers,
        'invalid_jsonld':invalid,'hreflang':langs,'html_lang':soup.html.get('lang') if soup.html else None,
        'internal_links':sorted(set(urljoin(url,a['href']) for a in soup.find_all('a',href=True) if domain(urljoin(url,a['href']))==domain(url))),
        'canadian_signals':sorted(set(re.findall(r'\b(?:Canada|Canadian|CAD|Québec)\b',text,re.I))),
        'text':text[:100000], 'scope':'Raw HTTP HTML only; no JavaScript rendering'}

def findings(page):
    url=page['url'];out=[]
    for field,label in [('title','Title'),('meta_description','Meta description'),('canonical','Canonical')]:
        if not page.get(field): out.append({'url':url,'finding':label+' not observed in returned HTML','confidence':'High for returned HTML; index impact unknown','class':'Technical discoverability issues'})
    robots=' '.join(str(page.get(k) or '') for k in ('robots','googlebot','x_robots_tag'))
    if re.search(r'\bnoindex\b',robots,re.I):
        out.append({'url':url,'finding':'noindex directive observed: '+robots,'confidence':'High; intended behavior needs review','class':'Technical discoverability issues'})
    if not page['h1']: out.append({'url':url,'finding':'H1 not observed in returned HTML','confidence':'High for returned HTML','class':'Poor topical coverage'})
    if not page['products'] and re.search(r'/products?/',url):
        out.append({'url':url,'finding':'Product JSON-LD not observed; other schema formats and rendered markup untested','confidence':'Medium','class':'Inadequate structured product information'})
    return out

def geo(page):
    # Page-level proxy signals only; consistency across products/retailers needs human evidence.
    text=page.get('text','')
    checks={
      'Structured product facts':bool(page['products']),
      'Brand organization entity':bool(page['organizations']),
      'Offer / availability metadata':bool(page['offers']),
      'Extractable description':bool(page['meta_description'] and page['h1'] and page['word_count']>=150),
      'Canadian information':bool(page['canadian_signals']),
      'Language identification':bool(page['html_lang']),
      'Comparison-friendly explanation':bool(re.search(r'compar|versus|difference|why choose',text,re.I)),
    }
    return {'score':round(100*sum(checks.values())/len(checks)), 'checks':checks,
       'label':'Diagnostic heuristic for inspected page; not AI recommendation probability',
       'confidence':'Low to medium: extractability proxies only',
       'not_measured':['Cross-source SKU fact consistency','Third-party citation quality','Brand entity consistency across domains','Actual ChatGPT, Perplexity or AI Overview recommendations']}

def audit_site(url,request=get_public):
    base=f'{urlparse(url).scheme}://{urlparse(url).netloc}'
    robots_url=base+'/robots.txt';resources=[]
    try:
        code,body,headers,final=request(robots_url)
        resources.append({'url':robots_url,'status':code,'body':body[:100000]})
        robot=None
        if code==200:
            robot=RobotFileParser();robot.parse(body.splitlines())
            if not robot.can_fetch(USER_AGENT,url):
                return {'url':url,'status':'robots_disallowed','resources':resources,'note':'Page not fetched; no conclusion about indexing'}
        elif code in (401,403) or code>=500:
            return {'url':url,'status':'robots_inaccessible','resources':resources,'note':'Conservative crawl skip; indexing unknown'}
        sitemaps=re.findall(r'^Sitemap:\s*(\S+)',body,re.M|re.I) if code==200 else []
        for sitemap in (sitemaps or [base+'/sitemap.xml'])[:3]:
            try:
                sc,sb,sh,sf=request(sitemap)
                xml=BeautifulSoup(sb,'xml') if False else BeautifulSoup(sb,'html.parser')
                resources.append({'url':sitemap,'status':sc,'body':sb[:100000],
                    'loc_count':len(xml.find_all('loc')),'note':'Sitemap resource accessibility only; no index-coverage inference'})
            except Exception as e: resources.append({'url':sitemap,'error':type(e).__name__})
        code,body,headers,final=request(url)
        if code!=200: return {'url':url,'status':'inaccessible','http_status':code,'resources':resources}
        page=parse_html(final,body,headers)
        return {'url':url,'status':'ok','page':page,'findings':findings(page),'geo':geo(page),'resources':resources,'raw_html':body}
    except (requests.RequestException,ValueError,OSError) as e:
        return {'url':url,'status':'inaccessible','error':type(e).__name__,'resources':resources,'note':'Missing evidence, not a confirmed SEO defect'}
