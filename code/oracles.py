"""O1, the acceptance oracle: for each mined repository, does the tool actually ACCEPT its
subagent specifications?  Free, deterministic, no model call: `claude -p "" --agent __probe__`
prints the agents it loaded.

Requires the Claude Code CLI on PATH (results in the paper: v2.1.233). Reads the archived corpus
from ../data/agents.jsonl.gz, re-fetches each repository's agent files from GitHub, stages them
in a temporary directory, probes, and appends one record per repository to
../data/oracle_agents.jsonl (resumable). CLAUDE_CONFIG_DIR may point at an isolated config
directory so the probe does not pick up user-level agents.
"""
import json, pathlib, re, subprocess, os, shutil, collections, concurrent.futures as cf, sys, tempfile
B=pathlib.Path(__file__).resolve().parent; DATA=B.parent/"data"
sys.path.insert(0, str(B)); import parsing
ISO=pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR", B.parent/"mainiso"))
WORK=pathlib.Path(tempfile.mkdtemp(prefix="oraclework-"))
env=dict(os.environ); env["CLAUDE_CONFIG_DIR"]=str(ISO)
RX=re.compile(r"Available agents:\s*(.+)")

def probe(cwd):
    p=subprocess.run(["claude","-p","","--agent","__probe_nonexistent__","--tools",""],
                     cwd=cwd, env=env, capture_output=True, text=True,
                     timeout=120, stdin=subprocess.DEVNULL)
    m=RX.search(p.stdout+p.stderr)
    if not m: return None
    return {x.strip() for x in m.group(1).split(",") if x.strip()}

# baseline: built-in agents present with no project agents
base=WORK/"__baseline__"; base.mkdir(exist_ok=True)
BUILTIN=probe(base)
print("built-in agents:", sorted(BUILTIN) if BUILTIN else "PROBE FAILED", flush=True)
if BUILTIN is None: sys.exit(1)

A=collections.defaultdict(list)
for r in parsing.iter_jsonl(DATA/"agents.jsonl.gz"):
    A[r["repo"]].append(r)

def run(item):
    repo, recs = item
    d=WORK/re.sub(r'[^A-Za-z0-9]+','_',repo); ad=d/".claude"/"agents"
    if ad.exists(): shutil.rmtree(d, ignore_errors=True)
    ad.mkdir(parents=True, exist_ok=True)
    for i,r in enumerate(recs):
        try:
            import urllib.request, urllib.parse
            url=f"https://raw.githubusercontent.com/{repo}/HEAD/{urllib.parse.quote(r['path'])}"
            txt=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"r"}),timeout=20).read()
            (ad/f"a{i}.md").write_bytes(txt)
        except Exception: pass
    got=probe(d)
    shutil.rmtree(d, ignore_errors=True)
    if got is None: return None
    accepted = got - BUILTIN
    declared = {str(r.get("name")).strip() for r in recs if r.get("name")}
    return {"repo":repo,"n_files":len(recs),
            "n_declared_names":len(declared),
            "n_accepted":len(accepted),
            "accepted":sorted(accepted),
            "declared":sorted(declared),
            "dropped":sorted(declared-accepted)}

# AUDIT FIX: the probe set was previously an alphabetical prefix of the corpus, which is not a
# random sample and cannot carry a binomial interval. Draw a seeded uniform random sample of
# repositories instead, stratified implicitly by taking the whole corpus as the frame.
# RANDOM SAMPLE
import random as _rnd
_rnd.seed(20260828)
items=list(A.items())
_rnd.shuffle(items)
_CAP=int(__import__("os").environ.get("ORACLE_CAP","1200"))
items=items[:_CAP]
print(f"probing a seeded RANDOM sample of {len(items)} repositories (frame: {len(A)})", flush=True)
done=set()
OUT=DATA/"oracle_agents.jsonl"
if OUT.exists():
    for l in open(OUT):
        try: done.add(json.loads(l)["repo"])
        except: pass
items=[i for i in items if i[0] not in done]
print(f"repos to probe: {len(items)}", flush=True)
n=0
with open(OUT,"a") as f, cf.ThreadPoolExecutor(8) as ex:
    for r in ex.map(run, items):
        if r: f.write(json.dumps(r)+"\n"); n+=1
        if n%100==0: f.flush(); print(f"  probed {n}", flush=True)
print("done",n)
