import json, time, urllib.request, sys

MANUAL = """DuraMax 900 Series Air Purifier -- User Manual (Model DX-900P)
Section 4.2 Filter Maintenance

The Pre-Carbon filter (Part No. DX-CF14) must be replaced every 2 months.
Replace the Pre-Carbon filter sooner if the FILTER LIFE indicator flashes
red or after 720 hours of continuous operation, whichever occurs first.

To replace the Pre-Carbon filter:
 1. Unplug the unit from the wall outlet.
 2. Remove the front panel by pressing the two release tabs.
 3. Pull the Pre-Carbon filter (DX-CF14) out of the housing.
 4. Remove the plastic wrapper from the new filter. Do not remove the
    carbon dust mesh.
 5. Slide the new filter into the housing until it clicks.

Note: Do not wash the Pre-Carbon filter. Washing it will damage the carbon
layer and reduce filtration performance.

The HEPA filter (Part No. DX-HF22) should be replaced every 12 months.
The carbon filter (Part No. DX-CF30) should be replaced every 3 months.
Wipe the exterior with a dry cloth every 2 weeks. Do not use solvents."""

ARRAY_SCHEMA = {
 "type":"object","properties":{
  "device_name":{"type":"string"},
  "intervals":{"type":"array","items":{"type":"object","properties":{
     "task":{"type":"string"},"interval_months":{"type":"number"},
     "quote":{"type":"string"},"page":{"type":"string"}},
   "required":["task","interval_months","quote","page"]}}},
 "required":["device_name","intervals"]}

ONE_SCHEMA = {
 "type":"object","properties":{
  "has_interval":{"type":"boolean"},
  "task":{"type":"string"},
  "interval_months":{"type":"number"},
  "quote":{"type":"string"}},
 "required":["has_interval","task","interval_months","quote"]}

P_ARRAY = """Extract every maintenance task and its replacement interval from this manual excerpt.

Rules:
- interval_months is a number of months. Convert days/weeks to months (30 days = 1 month, 12 months = 1 year).
- quote must be copied VERBATIM from the text and must contain the interval.
- page must be the section heading the task was found under.
- There are AT LEAST THREE tasks with intervals in this excerpt. Do not return an empty list.

MANUAL:
""" + MANUAL

P_ONE = """Read this manual excerpt and answer ONE question about it.

Question: Does this excerpt state how often ONE specific maintenance task must be done?

Rules:
- If the excerpt states an interval, set has_interval to true.
- task = the short name of the task (e.g. "Pre-Carbon filter replacement").
- interval_months = the interval in months as a number. Convert: 30 days = 1 month, 4 weeks = 1 month, 12 months = 1 year. If no interval, use 0.
- quote = the exact sentence from the excerpt that states the interval, copied word for word. If there is no interval, use an empty string.

EXCERPT:
""" + MANUAL

def call(model, prompt, fmt):
    body = json.dumps({"model":model,"prompt":prompt,"stream":False,"format":fmt,
        "options":{"temperature":0,"num_ctx":4096}}).encode()
    t0=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate",body,{"Content-Type":"application/json"}),timeout=900)
        d=json.loads(r.read())
    except Exception as e:
        return {"err":str(e)}
    el=time.time()-t0
    return {"s":round(el,1),"out_tok":d.get("eval_count",0),"in_tok":d.get("prompt_eval_count",0),
            "tps":round(d.get("eval_count",0)/el,1) if el else 0,"raw":d.get("response","")}

def score_array(raw, expect):
    try: j=json.loads(raw)
    except Exception as e: return {"parse":"FAIL","detail":str(e)[:80],"raw":raw[:200]}
    iv=j.get("intervals",[]); ok=0; wrong=[]
    for it in iv:
        q=(it.get("quote") or "").strip().lower(); m=it.get("interval_months") or 0
        if q and q[:35] in MANUAL.lower() and m>0: ok+=1
        else: wrong.append(it)
    return {"device_name":j.get("device_name"),"n":len(iv),"quote_valid":ok,"wrong":wrong,"raw":raw[:300]}

def score_one(raw):
    try: j=json.loads(raw)
    except Exception as e: return {"parse":"FAIL","detail":str(e)[:80],"raw":raw[:200]}
    q=(j.get("quote") or "").strip().lower(); m=j.get("interval_months") or 0
    valid = bool(q) and q[:35] in MANUAL.lower() and m>0
    return {"has":j.get("has_interval"),"task":j.get("task"),"months":m,"quote_ok":valid,"raw":raw[:300]}

for model in sys.argv[1:]:
    print("#"*25, model)
    a=call(model,P_ARRAY,ARRAY_SCHEMA); print("A array-schema  ", {k:v for k,v in a.items() if k!="raw"}); print("   ",score_array(a.get("raw",""),None))
    b=call(model,P_ONE,ONE_SCHEMA);    print("B one-at-a-time ", {k:v for k,v in b.items() if k!="raw"}); print("   ",score_one(b.get("raw","")))
    c=call(model,P_ARRAY,"json");      print("C plain-json    ", {k:v for k,v in c.items() if k!="raw"}); print("   ",score_array(c.get("raw",""),None))
    print("-"*70)
