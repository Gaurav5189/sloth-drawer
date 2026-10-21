import json, re, urllib.request, time, sys

PAGE = """DuraMax 900 Series Air Purifier -- User Manual (Model DX-900P)
Section 4.2 Filter Maintenance

The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.
Replace the Pre-Carbon filter sooner if the FILTER LIFE indicator flashes
red or after 720 hours of continuous operation, whichever occurs first.

Note: Do not wash the Pre-Carbon filter. Washing it will damage the carbon
layer and reduce filtration performance.

The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.
The carbon filter (Part No. DX-CF30) should be replaced every 3 months.
Wipe the exterior with a dry cloth every 2 weeks. Do not use solvents."""

def norm(s): return re.sub(r"\s+", " ", s).strip().lower()

def expand_quote(page, quote):
    """Deterministic: model POINTS, code QUOTES.
    Locate the model's quote fragment in the page and expand it to the
    enclosing sentence(s). Returns (sentence, ok)."""
    q = norm(quote)
    p = norm(page)
    i = p.find(q)
    if i == -1:
        # try without trailing punctuation
        q2 = q.rstrip(" .,:;")
        i = p.find(q2)
        if i == -1: return None, False
    # expand to sentence boundaries
    start = max(p.rfind(".", 0, i), p.rfind("\n", 0, i))
    # find end: the first sentence end after the fragment
    j = i + len(q)
    end = p.find(".", j)
    if end == -1: end = len(p) - 1
    sent = p[start+1:end+1].strip() if start >= 0 else p[i:end+1].strip()
    # merge continuation lines (sentence wrapped across newlines)
    return sent, True

def months_from_text(t):
    t = norm(t)
    m = re.search(r"every\s+(\d+)\s+(month|year|week|day)", t)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return {("month"):n, ("year"):n*12, ("week"):round(n/4.345,2), ("day"):round(n/30.44,2)}[u]
    m = re.search(r"(\d+)\s*(?:-|to)?\s*(\d+)\s+(month|year)", t)
    if m: return round((int(m.group(1))+int(m.group(2)))/2 * (12 if m.group(2)=="year" else 1), 2)
    m = re.search(r"(\d+)\s+months?", t)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s+years?", t)
    if m: return int(m.group(1))*12
    return None

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
- section: the section heading it came from.

EXCERPT:
"""+PAGE

def run(model):
    body=json.dumps({"model":model,"prompt":P,"stream":False,"format":SCHEMA,
        "options":{"temperature":0,"num_ctx":4096}}).encode()
    t0=time.time()
    d=json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://localhost:11434/api/generate",body,{"Content-Type":"application/json"}),timeout=900).read())
    el=time.time()-t0
    raw=d.get("response","")
    print(f"\n=== {model}  {el:.1f}s  {d.get('eval_count')} out tok  {d.get('eval_count')/el:.1f} tok/s")
    try: j=json.loads(raw)
    except Exception as e:
        print("  JSON FAIL:", str(e)[:90], raw[:200]); return
    print("  model said:", json.dumps(j)[:220])
    sent, ok = expand_quote(PAGE, j.get("quote",""))
    print("  quote in page? ", ok)
    print("  CODE-EXPANDED citation:", (sent or "n/a")[:150])
    code_m = months_from_text(sent or "")
    model_m = j.get("interval_months")
    print(f"  model months={model_m}  code months={code_m}  AGREE={code_m==model_m}")
    print("  VERDICT:", "PASS (code confirms)" if (ok and code_m is not None and code_m==model_m) else "REJECT/REPAIR")

for m in sys.argv[1:]: run(m)
