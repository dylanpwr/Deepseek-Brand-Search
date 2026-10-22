import json, os
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from grenade.storage import Store
from grenade.analysis import frames,visibility,grouped_visibility,gaps,fetched_pages,compare,WEIGHTS
from grenade.runner import load_queries,ROOT,plan,run_audit

load_dotenv()
st.set_page_config(page_title='Grenade | Search Intelligence',page_icon='🟢',layout='wide')
st.markdown("""<style>.stApp {background:#101414} h1,h2,h3 {letter-spacing:-.04em} [data-testid="stMetric"] {background:#1b2421;padding:18px;border-radius:12px;border-top:3px solid #b6ef48} a {color:#b6ef48}</style>""",unsafe_allow_html=True)
st.caption('GRENADE / CANADA · SEARCH INTELLIGENCE')
st.title('Find the visibility. Follow the evidence.')
st.caption('DeepSeek result order · Canadian query intent · GEO diagnostic heuristics')
store=Store(os.getenv('AUDIT_DB','data/audits.sqlite'))
queries=load_queries(ROOT/'config/queries.csv')
brands=json.loads((ROOT/'config/brands.json').read_text());domains=json.loads((ROOT/'config/domains.json').read_text())
page=st.sidebar.radio('Workspace',['Executive Overview','Keyword Explorer','Competitor Intelligence','Technical & GEO Audit','Action Plan'])
with st.sidebar.expander('Run an audit'):
    limit=st.number_input('Query limit',1,len(queries),10)
    fetch_limit=st.number_input('Maximum Fetch calls',0,100,5)
    refresh=st.checkbox('Fresh weekly measurement (bypass cache)',value=True)
    st.caption('Prices unknown unless configured. Retries count toward MAX_REQUESTS. Technical HTTP calls are separate.')
    if st.button('Start audit',type='primary'):
        try:
            contract=json.loads(Path(os.getenv('API_CONTRACT',str(ROOT/'config/api_contract.json'))).read_text())
            manifest,fingerprint=plan(ROOT/'config/queries.csv',contract,brands,domains,limit,20,fetch_limit,5)
            with st.spinner('Collecting evidence…'):
                rid,error=run_audit(store,manifest,fingerprint,refresh)
            if error:st.error(error)
            else:st.success(f'Run {rid} recorded')
        except (ValueError,OSError) as e:st.error(str(e))
runs=store.rows('SELECT * FROM runs ORDER BY id DESC')
if not runs:
    st.info('No audit data yet. Visibility is not measured. Configure the verified API contract and credentials, then start the 10-query audit.')
    a,b,c=st.columns(3)
    a.metric('Queries ready',len(queries));b.metric('Non-Grenade queries',sum(not q['branded'] for q in queries));c.metric('Successful live searches','Not measured')
    st.subheader(page)
    if page=='Keyword Explorer':st.dataframe(pd.DataFrame(queries),hide_index=True,use_container_width=True)
    elif page=='Action Plan':
        st.write('No evidence-ranked recommendations yet. First establish the baseline, verify official-domain ownership and Canadian distribution, then validate gaps against fetched pages.')
    elif page=='Technical & GEO Audit':
        st.write('No official-domain audit yet. Candidate domains must be validated before their pages contribute findings. GEO readiness is a diagnostic heuristic, not a measurement of AI recommendations.')
    else:
        counts=pd.DataFrame(queries).groupby('category').size().reset_index(name='Queries')
        st.plotly_chart(px.bar(counts,x='category',y='Queries',color='category',title='Configured research coverage'),use_container_width=True)
    st.stop()
run=st.sidebar.selectbox('Search run',[r['id'] for r in runs],format_func=lambda x:f'#{x} · '+next(r['started'][:16]+' UTC · '+r['status'] for r in runs if r['id']==x))
record=next(r for r in runs if r['id']==run)
manifest=json.loads(record['manifest']);brands=manifest['brands'];domains=manifest['domains']
q,r=frames(store,run);official_validated=any(x.get('brand')=='Grenade' and x.get('evidence_url') and x.get('evidence_note') for x in domains.get('official',[]))
metrics=visibility(q,r,official_validated=official_validated)
st.caption(f'Run #{run} · {record["status"]} · fingerprint {record["fingerprint"][:12]} · timestamps stored in UTC')
st.warning('Coverage describes this API and query set. It is not Google rank, traffic, search volume, or direct AI recommendation visibility.')
if not metrics['successful_queries']:
    st.info('This run has no successful searches. No visibility conclusions are supported.')
    st.dataframe(q if not q.empty else pd.DataFrame([{'status':record['status'],'next_step':'Verify documented API contract and configure API key'}]),use_container_width=True)
    st.stop()
if not official_validated:st.info('Official-domain ownership scope is unverified. Official coverage is not measured; third-party mentions can still be analyzed.')
ops=gaps(store,run,brands,domains)

def show_results(data):
    if data.empty:st.info('No returned results in this selection.');return
    display=data.copy();display['brands']=display.brands.apply(', '.join)
    st.dataframe(display,hide_index=True,use_container_width=True,column_config={'url':st.column_config.LinkColumn('Ranking page')})

if page=='Executive Overview':
    cols=st.columns(4)
    for col,name,key in zip(cols,['Mention coverage · Top 20','Official coverage · Top 20','Mention coverage · Top 3','Successful queries'],['mentions_top20_pct','official_top20_pct','mentions_top3_pct','successful_queries']):
        value=metrics[key];col.metric(name,f'{value}%' if key.endswith('pct') and value is not None else ('Not measured' if value is None else str(value)))
    st.caption(f'Failed queries excluded: {metrics["failed_queries"]}. Average best position when present: {metrics["mentions_avg_best_position"]}. Official domains require ownership evidence in the run manifest.')
    grouping=grouped_visibility(q,r,brands,'branded',official_validated=official_validated);grouping['Query type']=grouping.branded.map({0:'No Grenade in query',1:'Grenade in query'})
    st.plotly_chart(px.bar(grouping[grouping.brand=='Grenade'],x='Query type',y='mentions_top20_pct',range_y=[0,100],title='Branded versus non-branded query coverage'),use_container_width=True)
    if not r.empty:
        shares=r.explode('brands').dropna(subset=['brands']).groupby('brands').size().reset_index(name='Result-brand appearances')
        st.plotly_chart(px.bar(shares,x='brands',y='Result-brand appearances',title='Competitive result mentions (one result can mention several brands)'),use_container_width=True)
    st.subheader('Highest-priority opportunities')
    st.dataframe(pd.DataFrame(ops).drop(columns=['evidence','factors','distribution_evidence'],errors='ignore').head(10),use_container_width=True,hide_index=True)
    comparable=[x for x in runs if x['id']!=run and x['fingerprint']==record['fingerprint']]
    if comparable:
        baseline=min(comparable,key=lambda x:x['id'])
        st.write('Comparison to earliest matching baseline')
        st.json(compare(store,run,baseline['id']))
    else:st.caption('No comparable baseline yet. Weekly runs must use the same query set and parameters.')
    req=pd.DataFrame(store.rows('SELECT * FROM requests WHERE run_id=?',(run,)))
    if not req.empty:
        st.write(f'API attempts: {len(req)} · Cost estimate: '+(f"{req.cost.sum():.4f} (configured currency)" if req.cost.notna().all() else 'Unknown: pricing not fully configured'))
    st.caption('Cached result observation times appear in Keyword Explorer; cache hits are not fresh measurements.')
elif page=='Keyword Explorer':
    categories=st.multiselect('Intent',sorted(q.category.unique()),default=sorted(q.category.unique()))
    filtered=q[q.category.isin(categories)]
    st.dataframe(filtered.drop(columns=['raw'],errors='ignore'),use_container_width=True,hide_index=True)
    if not filtered.empty:
        qid=st.selectbox('Query',filtered.query_id,format_func=lambda x:filtered[filtered.query_id==x]['query'].iloc[0])
        selected=r[r.query_id==qid] if not r.empty else r;show_results(selected)
        history=[]
        for prior in runs:
            if prior['fingerprint']!=record['fingerprint']:continue
            hq,hr=frames(store,prior['id'])
            if hq.empty:continue
            hq=hq[(hq.query_id==qid)&(hq.status=='ok')]
            if hq.empty:continue
            hr=hr[(hr.query_id==qid)&hr.brands.apply(lambda x:'Grenade' in x)] if not hr.empty else hr
            history.append({'timestamp':hq.observed_at.iloc[0],'best_position':int(hr['rank'].min()) if not hr.empty else None,'run':prior['id']})
        st.caption('Absent results are missing points, never rank 21. Failed queries excluded. Only matching run fingerprints included.')
        if history:
            chart=px.line(pd.DataFrame(history).sort_values('timestamp'),x='timestamp',y='best_position',markers=True,title='Historical best Grenade mention position')
            chart.update_yaxes(autorange='reversed');st.plotly_chart(chart,use_container_width=True)
            st.dataframe(pd.DataFrame(history),hide_index=True)
        comp=grouped_visibility(filtered,r[r.query_id.isin(filtered.query_id)] if not r.empty else r,brands,official_validated=official_validated)
        st.dataframe(comp,use_container_width=True,hide_index=True)
    st.download_button('Export returned results CSV',r.to_csv(index=False),'results.csv')
elif page=='Competitor Intelligence':
    comp=grouped_visibility(q,r,brands,official_validated=official_validated)
    st.plotly_chart(px.bar(comp,x='category',y='mentions_top20_pct',color='brand',barmode='group',range_y=[0,100],title='Competitor query coverage by intent'),use_container_width=True)
    if not r.empty:
        dom=r.groupby(['domain','classification']).size().reset_index(name='Result slots').sort_values('Result slots',ascending=False)
        st.dataframe(dom,use_container_width=True,hide_index=True)
        st.subheader('Publishers and retailers')
        show_results(r[r.classification.isin(['Review','Comparison / guide','Retailer'])])
        st.subheader('Content themes in returned titles (exploratory)')
        themes=r.title.str.lower().str.extractall(r'\b(protein|chocolate|sugar|taste|review|comparaison|buy|best|barres)\b')[0].value_counts().rename_axis('Theme').reset_index(name='Occurrences')
        st.dataframe(themes,hide_index=True)
    candidates=[]
    for p in fetched_pages(store,run):
        for brand in p['evidence'].get('candidate_brands',[]):candidates.append({'candidate':brand,'source':p['url']})
    st.subheader('Additional brand candidates — human validation required')
    st.dataframe(pd.DataFrame(candidates),hide_index=True)
    st.caption('Add validated brands and regex aliases in config/brands.json; changed detection rules start a new comparable series.')
elif page=='Technical & GEO Audit':
    pages=[p for p in fetched_pages(store,run) if p['kind']=='technical']
    if not pages:st.info('No technical evidence: validate official-domain ownership in config/domains.json and run an audit.')
    for p in pages:
        with st.expander(p['url']+' · '+p['status']):
            st.json(p['evidence'])
    st.caption('HTTP source inspection cannot prove rendered schema absence, index exclusion, ranking causes or AI citation probability. Cross-source product fact consistency requires SKU-level review.')
elif page=='Action Plan':
    st.caption('Transparent score = 20 × weighted sum of 0–5 factors. Distribution unknown receives 1/5; scores estimate priority, not revenue.')
    st.json(WEIGHTS)
    st.dataframe(pd.DataFrame(ops).drop(columns=['evidence','factors','distribution_evidence'],errors='ignore'),use_container_width=True,hide_index=True)
    for o in ops[:30]:
        with st.expander(f'{o["priority_score"]}/100 · {o["query"]}'):
            st.write(o['recommendation']);st.json(o)
    st.download_button('Export action evidence JSON',json.dumps(ops,ensure_ascii=False,indent=2),'action-plan.json')
    st.subheader('Imported first-party data')
    imports=store.rows('SELECT id,source,timestamp FROM imports ORDER BY id DESC');st.dataframe(pd.DataFrame(imports),hide_index=True)
    st.caption('Use python -m grenade.runner import-data to store GSC, Ads or retailer CSVs. They remain separate until matching periods, geography and query semantics are validated.')
