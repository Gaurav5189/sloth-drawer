import json, re, time, urllib.request, sys
PAGE = """DuraMax 900 Series Air Purifier -- User Manual (Model DX-900P)

Section 4.2 Filter Maintenance
The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.
Replace the Pre-Carbon filter sooner if the FILTER LIFE indicator flashes
red or after 720 hours of continuous operation, whichever occurs first.
Note: Do not wash the Pre-Carbon filter. Washing it will damage the carbon
layer and reduce filtration performance.
The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.
The carbon filter (Part No. DX-CF30) should be replaced every 3 months.

Section 4.3 Exterior Care
Wipe the exterior with a dry cloth every 2 weeks. Do not use solvents.
Replace the Pre-Motor filter (Part No. DX-PF07) every 90 days.
The front panel may be cleaned with a mild detergent solution."""

TRUTH = [("Pre-Carbon filter","2",2),("HEPA filter","12",12),("carbon filter","3",3),
         ("Pre-Motor filter","90 days",3)]
SCHEMA={"type":"object","properties":{
 "has_interval":{"type":"boolean"},"task":{"type":"string"},
 "interval_months":{"type":"number"},"quote":{"type":"string"},
 "section":{"type":"string"}},"required":["has_interval","task","interval_months","quote","section"]}
P="""Read this manual excerpt and answer ONE question about it.

Question: Does this excerpt state how often ONE specific maintenance task must be done?

Rules:
- has_interval: true if the excerpt states an interval for some task.
- task: short name of that task (e.g. "Pre-Carbon filter replacement").
- interval_months: the interval in months as a number (30 days = 1 month, 4 weeks = 1 month, 12 months = 1 year). Use 0 if none.
- quote: the exact words from the excerpt that state the interval, copied word for word. Short is fine.
- section: the section heading it came under.

EXCERPT:
"""+PAGE

def norm(s): return re.sub(r"\s+"," ",s).strip().lower()
def expand(page, quote):
    q=norm(quote); p=norm(page); i=p.find(q)
    if i==-1:
        q2=q.rstrip(" .,:;"); i=p.find(q2)
        if i==-1: return None,False
    st=max(p.rfind(".",0,i), p.rfind("\n",0,i))
    j=i+len(q); en=p.find(".",j); en=len(p)-1 if en==-1 else en
    return (p[st+1:en+1].strip() if st>=0 else p[i:en+1].strip()), True
def months_of(t):
    t=norm(t)
    m=re.search(r"every\s+(\d+)\s+(month|year|week|day)",t)
    if m:
        n,u=int(m.group(1)),m.group(2)
        return {("month"):n,("year"):n*12,("week"):round(n/4.345,2),("day"):round(n/30.44,2)}[u]
    m=re.search(r"(\d+)\s*months?",t)
    if m: return int(m.group(1))
    m=re.search(r"(\d+)\s*years?",t)
    if m: return int(m.group(1))*12
    return None
def verify(j, page):
    sent,ok=expand(page, j.get("quote",""))
    if not ok: return "REJECT(quote not in page)",None,None
    cm=months_of(sent or "")
    if cm is None: return "REJECT(no interval in cited sentence)",cm,None
    mm=j.get("interval_months")
    if mm!=cm: return f"REPAIR(model said {mm}, code says {cm})",cm,cm
    return "PASS",cm,cm

def run(model):
    body=json.dumps({"model":model,"prompt":P,"stream":False,"format":SCHEMA,
        "options":{"temperature":0,"num_ctx":4096}}).encode()
    t0=time.time()
    d=json.loads(urllib.request.urlopen(urllib.request.Request(
      "http://localhost:11434/api/generate",body,{"Content-Type":"application/json"}),timeout=900).read())
    el=time.time()-t0
    try: j=json.loads(d.get("response",""))
    except Exception as e: j={}
    verdict, cm, _ = verify(j, PAGE)
    print(f"--- {model}: {el:.1f}s  {d.get('eval_count')}tok  {d.get('eval_count')/el:.1f}tok/s")
    print(f"    task={j.get('task')!r} months={j.get('interval_months')} section={j.get('section')!r}")
    print(f"    VERDICT: {verdict}")
    return el

print("=== ONE-FACT-PER-CALL: does it find the right interval in a multi-interval page? ===")
for m in sys.argv[1:]: run(m)

print("\n=== REJECTION / REPAIR PATH (simulated bad model output) ===")
bad = [
 ("hallucinated quote", {"has_interval":True,"task":"Replace filter","interval_months":2,"quote":"The Pre-Carbon filter must be replaced every 6 months.","section":"4.2"}),
 ("real quote, wrong months", {"has_interval":True,"task":"Replace filter","interval_months":3,"quote":"The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.","section":"4.2"}),
 ("cites a non-interval sentence", {"has_interval":True,"task":"Replace filter","interval_months":9,"quote":"Note: Do not wash the Pre-Carbon filter.","section":"4.2"}),
]
for name,j in bad:
    v,cm,_=verify(j,PAGE)
    print(f"  {name:32s} -> {v}")

print("\n=== GROUND TRUTH: intervals that exist in the page ===")
for t,q,m in TRUTH: print(f"  {t}: {q} -> {m} months")
