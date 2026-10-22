import re
from urllib.parse import urlparse

def domain(url):
    return (urlparse(url).hostname or '').lower().removeprefix('www.')

def matches(host,root):
    root=root.lower().removeprefix('www.').rstrip('.')
    return bool(root) and (host==root or host.endswith('.'+root))

def mentions(text,brands):
    return [brand for brand,patterns in brands.items() if any(re.search(p,text,re.I) for p in patterns)]

def official(host,config):
    for entry in config.get('official',[]):
        if entry.get('evidence_url') and entry.get('evidence_note') and matches(host,entry['domain']): return entry['brand']
    return None

def classify(row,config):
    host=domain(row['url']);text=' '.join(str(row.get(k) or '') for k in ('title','snippet','summary','url'))
    owned=official(host,config)
    if owned: return 'Official brand',owned
    if any(matches(host,x) for x in config.get('retailers',[])): return 'Retailer',None
    if re.search(r'\breview|\bavis\b|\btest\b',text,re.I): return 'Review',None
    if re.search(r'\bbest\b|meilleur|compar|\bvs\b|buying guide',text,re.I): return 'Comparison / guide',None
    return 'Other / unclassified',None

def normalize(row,rank,brands,config):
    classification,owned=classify(row,config)
    text=' '.join(str(row.get(k) or '') for k in ('title','snippet','summary'))
    detected=mentions(text,brands)
    if owned and owned not in detected: detected.append(owned)
    return {'rank':rank,'title':row.get('title') or '', 'url':row['url'], 'domain':domain(row['url']),
        'snippet':row.get('snippet') or '', 'summary':row.get('summary') or '',
        'rerank_score':row.get('rerank_score'), 'authority_tier':row.get('authority_tier') or 'Unknown / not supplied',
        'publication_date':row.get('publication_date'), 'brands':detected,'official_brand':owned,
        'classification':classification}

def discovered_candidates(text,known):
    # Suggestions require human validation; never automatically counted as brands.
    candidates=set(re.findall(r'\b([A-Z][A-Za-z0-9-]+(?: [A-Z][A-Za-z0-9-]+){0,2}) (?:protein bars?|Protein Bars?)\b',text))
    return sorted(c for c in candidates if c.lower() not in {b.lower() for b in known})
