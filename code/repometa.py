"""Fetch repository metadata for the spec-bearing repositories: stars, fork status, age, activity.
Needed for (a) engineered-project filtering, (b) stratified reporting, (c) threats to validity.

Requires the GitHub CLI (`gh auth login`). Reads ../data/agents.jsonl.gz and appends to
../data/repometa.jsonl (resumable); the archived snapshot ships it gzipped.
"""
import json, subprocess, pathlib, sys, concurrent.futures as cf
B=pathlib.Path(__file__).resolve().parent; DATA=B.parent/"data"; OUT=DATA/"repometa.jsonl"
sys.path.insert(0, str(B)); import parsing
spec_repos={r["repo"] for r in parsing.iter_jsonl(DATA/"agents.jsonl.gz") if parsing.is_specification(r)}
done=set()
if OUT.exists():
    for l in open(OUT):
        try: done.add(json.loads(l)["repo"])
        except: pass
todo=sorted(spec_repos-done)
print(f"repos needing metadata: {len(todo)}", flush=True)
def get(repo):
    p=subprocess.run(["gh","api",f"repos/{repo}","--jq",
        '{repo:.full_name,stars:.stargazers_count,forks:.forks_count,is_fork:.fork,archived:.archived,'
        'created:.created_at,pushed:.pushed_at,size:.size,lang:.language,'
        'open_issues:.open_issues_count,has_wiki:.has_wiki,license:(.license.key // null),'
        'subscribers:.subscribers_count,topics:(.topics|length)}'],
        capture_output=True,text=True,timeout=60)
    if p.returncode!=0: return None
    try: return json.loads(p.stdout)
    except: return None
n=0
with open(OUT,"a") as f, cf.ThreadPoolExecutor(6) as ex:
    for r in ex.map(get, todo):
        if r: f.write(json.dumps(r)+"\n"); n+=1
        if n%100==0: f.flush(); print(f"  {n}", flush=True)
print("done",n)
