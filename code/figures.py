"""Generate journal figures (vector PDF) for the subagent-specification study.

Palette: Okabe-Ito subset #0072B2 / #D55E00 / #CC79A7, validated colourblind-safe
(all checks pass: lightness band, chroma floor, CVD separation, normal-vision floor,
contrast vs surface). Every series is also directly labelled, so identity is never
carried by colour alone, and all figures remain readable in greyscale print.
"""
import json, re, collections, math, random, statistics as st, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import parsing, stats   # same normaliser, schema set and bootstrap as analyze.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

random.seed(20260823)
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT/"data"
OUT  = ROOT/"paper"; OUT.mkdir(parents=True, exist_ok=True)   # flat: no figures/ sub-folder

BLUE, VERM, PINK = "#0072B2", "#D55E00", "#CC79A7"
INK, MUTED, GRID = "#1a1a1a", "#666666", "#d9d9d9"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9.5,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": "#555555", "axes.linewidth": 0.6,
    "xtick.color": "#555555", "ytick.color": "#555555",
    "text.color": INK, "axes.labelcolor": INK,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})

def save(fig,name):
    fig.savefig(OUT/(name+".pdf"))

def despine(ax, keep=("left","bottom")):
    for s in ("top","right","left","bottom"):
        ax.spines[s].set_visible(s in keep)

# ---------------- data ----------------
def renorm(v):
    if v is None: return None
    if isinstance(v, list): items=[str(x).strip() for x in v]
    elif isinstance(v, str):
        s=v.strip()
        if not s: return []
        if s in ("*","all"): return ["*"]
        items=[x.strip() for x in s.split(",")] if "," in s else re.findall(r'[A-Za-z_][\w.-]*\([^)]*\)|\S+', s)
    else: items=[str(v)]
    return [x for x in items if x]
def bt(t):
    m=re.match(r'^([A-Za-z_][\w.-]*)\s*\(', t); return m.group(1) if m else t

VOCAB=json.load(open(DATA/"tool_vocab.json")); VALID=set(VOCAB["valid"])
def tool_ok(t):
    b=bt(t); return b in VALID or b.startswith("mcp__") or t.startswith("mcp__") or b=="*"

RAW=[json.loads(l) for l in __import__("gzip").open(DATA/"agents.jsonl.gz","rt")]
for a in RAW:
    if "tools_raw" in a: a["tools"]=renorm(a.get("tools_raw"))
SPEC=[a for a in RAW if not a.get("fm_error") and a.get("name") and a.get("description")]
byrepo=collections.defaultdict(list)
for a in SPEC: byrepo[a["repo"]].append(a)
expl=lambda a: a.get("tools") not in (None,["*"]) and bool(a.get("tools"))
FILEWRITE={"Write","Edit","NotebookEdit"}

STRICT=[("reviewer",r'(^|[-_ ])(code[-_ ]?)?review(er)?([-_ ]|$)|(^|[-_ ])auditor([-_ ]|$)'),
 ("security",r'(^|[-_ ])(security|appsec|pentest(er)?|vulnerability)([-_ ]|$)'),
 ("docs",r'(^|[-_ ])(doc|docs|documentation)([-_ ]|$)|technical[-_ ]?writer|doc[-_ ]?writer'),
 ("tester",r'(^|[-_ ])(test(er)?|qa|test[-_ ]?writer|test[-_ ]?runner|test[-_ ]?automator)([-_ ]|$)'),
 ("implementer",r'(^|[-_ ])(implementer|developer|coder|builder)([-_ ]|$)'),
 ("debugger",r'(^|[-_ ])(debugger|bug[-_ ]?fixer|fixer|troubleshooter)([-_ ]|$)'),
 ("architect",r'(^|[-_ ])architect([-_ ]|$)'),
 ("planner",r'(^|[-_ ])(planner|orchestrator|coordinator)([-_ ]|$)')]
def srole(a):
    n=str(a.get("name") or "").lower().replace("_","-")
    h=[r for r,p in STRICT if re.search(p,n)]
    return h[0] if len(h)==1 else None
for a in SPEC: a["_r"]=srole(a)

def boot(vals):
    return stats.bootstrap_ci(list(vals))   # percentile bootstrap over repositories, as in the text
def repo_rate(pred, denom, repos=None):
    ps=[]
    for r in (repos or byrepo):
        recs=[a for a in byrepo[r] if denom(a)]
        if recs: ps.append(sum(1 for a in recs if pred(a))/len(recs))
    if not ps: return None
    lo,hi=boot(ps); return st.mean(ps), lo, hi, len(ps)

# ============ FIG 1 — concentration ============
cnt=sorted((len(v) for v in byrepo.values()), reverse=True)
tot=sum(cnt); n=len(cnt)
cum=[]; s=0
for i,c in enumerate(cnt,1): s+=c; cum.append((i/n, s/tot))
fig,ax=plt.subplots(figsize=(3.3,2.5))
ax.plot([0,1],[0,1], color=MUTED, lw=0.7, ls=(0,(3,3)), zorder=1)
ax.plot([0]+[x for x,_ in cum], [0]+[y for _,y in cum], color=BLUE, lw=1.6, zorder=3)
i10=int(0.10*n)-1
ax.plot([cum[i10][0]],[cum[i10][1]], "o", ms=4.5, color=VERM, zorder=4)
ax.annotate(f"top 10% of repositories\nhold {100*cum[i10][1]:.0f}% of specifications",
            xy=(cum[i10][0],cum[i10][1]), xytext=(0.30,0.42), fontsize=7.5, color=INK,
            arrowprops=dict(arrowstyle="-", lw=0.6, color=VERM))
ax.text(0.62,0.55,"equal contribution", fontsize=7, color=MUTED, rotation=31, ha="center")
ax.set_xlabel("repositories, ranked by number of specifications")
ax.set_ylabel("cumulative share of specifications")
ax.xaxis.set_major_formatter(PercentFormatter(1.0)); ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlim(0,1); ax.set_ylim(0,1); ax.grid(axis="y", color=GRID, lw=0.5); ax.set_axisbelow(True)
despine(ax); save(fig,"fig1_concentration"); plt.close(fig)

# ============ FIG 2 — team size CCDF ============
sizes=sorted(len(v) for v in byrepo.values())
xs=sorted(set(sizes)); ys=[sum(1 for s_ in sizes if s_>=x)/len(sizes) for x in xs]
fig,ax=plt.subplots(figsize=(3.3,2.5))
ax.step(xs, ys, where="post", color=BLUE, lw=1.6)
med=st.median(sizes)
ax.axvline(med, color=VERM, lw=0.9, ls=(0,(3,2)))
ax.annotate(f"median {med:.0f}", xy=(med,0.5), xytext=(med*1.6,0.62), fontsize=7.5, color=VERM)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("specifications per repository"); ax.set_ylabel("P(X $\\geq$ x)")
ax.grid(color=GRID, lw=0.5, which="both"); ax.set_axisbelow(True); despine(ax)
save(fig,"fig2_teamsize"); plt.close(fig)

# ============ FIG 3 — role x privilege (unconditional; omission = full pool) ============
PRIM = FILEWRITE | {"Bash","PowerShell"}
def cap(a, ws):
    t=a.get("tools")
    if t is None or t==["*"]: return True      # omitting tools: inherits the FULL pool
    return bool({bt(x) for x in t} & ws)
rows=[]
for r,_p in STRICT:
    g=[a for a in SPEC if a["_r"]==r]
    if len(g)<40: continue
    fw=repo_rate(lambda a: cap(a,FILEWRITE), lambda a,_r=r: a["_r"]==_r)
    pr=repo_rate(lambda a: cap(a,PRIM),      lambda a,_r=r: a["_r"]==_r)
    if fw and pr: rows.append((r,len(g),fw,pr))
rows.sort(key=lambda x: x[2][0])
fig,ax=plt.subplots(figsize=(6.6,3.1))
y=range(len(rows))
for i,(r,ns,fw,pr) in enumerate(rows):
    ax.plot([fw[1],fw[2]],[i,i], color=BLUE, lw=1.1, alpha=.55, solid_capstyle="butt")
    ax.plot([pr[1],pr[2]],[i,i], color=VERM, lw=1.1, alpha=.55, solid_capstyle="butt")
    ax.plot([fw[0],pr[0]],[i,i], color="#999999", lw=0.7, zorder=2)
    ax.plot([fw[0]],[i], "o", ms=5.5, color=BLUE, zorder=3)
    ax.plot([pr[0]],[i], "D", ms=4.8, color=VERM, zorder=3)
floor=math.floor(100*min(pr[0] for _r,_n,_fw,pr in rows))/100   # lowest write-or-shell point estimate
ax.axvline(floor, color="#444444", lw=0.7, ls=(0,(4,3)), zorder=1)
ax.text(floor+0.002, len(rows)-0.42, f"no role class falls below {100*floor:.0f}%", fontsize=7.2, color="#444444")
ax.set_yticks(list(y)); ax.set_yticklabels([f"{r}  (n={ns})" for r,ns,_f,_p in rows])
ax.set_xlim(0,1.02); ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("repository-weighted share of specifications with the capability (95% bootstrap CI)")
ax.plot([],[], "o", color=BLUE, label="can write files (Write/Edit/NotebookEdit)")
ax.plot([],[], "D", color=VERM, label="can write files or run shell")
ax.legend(loc="upper center", bbox_to_anchor=(0.5,1.16), ncol=2,
          frameon=False, handletextpad=.4, columnspacing=1.6)
ax.grid(axis="x", color=GRID, lw=0.5); ax.set_axisbelow(True); despine(ax)
save(fig,"fig3_role_privilege"); plt.close(fig)

# ============ FIG 4 — the mechanism (funnel) ============
insp=[a for a in SPEC if a["_r"] in {"reviewer","security","docs"} and expl(a)]
fw=lambda a: bool({bt(t) for t in a["tools"]} & FILEWRITE)
hasbash=lambda a: "Bash" in {bt(t) for t in a["tools"]}
n0=len(insp); n1=sum(1 for a in insp if not fw(a)); n2=sum(1 for a in insp if not fw(a) and hasbash(a)); n3=n1-n2
stages=[("inspection-role specifications\nwith an explicit tool list", n0, BLUE),
        ("denied file-write tools\n(developer restricts)", n1, BLUE),
        ("...but granted unrestricted Bash\n(restriction is void)", n2, VERM),
        ("genuinely read-only", n3, PINK)]
fig,ax=plt.subplots(figsize=(4.0,2.7))
for i,(lab,v,c) in enumerate(stages):
    ax.barh(i, v/n0, color=c, height=.6, zorder=3)
    ax.text(v/n0+0.015, i, f"{v}  ({100*v/n0:.1f}%)", va="center", fontsize=8, color=INK)
ax.set_yticks(range(len(stages))); ax.set_yticklabels([s[0] for s in stages], fontsize=7.6)
ax.invert_yaxis(); ax.set_xlim(0,1.28); ax.set_xticks([0,.25,.5,.75,1.0])
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.annotate(f"{100*n2/max(1,n1):.1f}% of the restricted\nspecifications", xy=(n2/n0,2), xytext=(n2/n0+0.30,2.75),
            fontsize=7.2, color=VERM, arrowprops=dict(arrowstyle="-", lw=0.6, color=VERM))
ax.set_xlabel("share of inspection-role specifications")
ax.grid(axis="x", color=GRID, lw=0.5); ax.set_axisbelow(True); despine(ax)
save(fig,"fig4_mechanism"); plt.close(fig)

# ============ FIG 5 — field population ============
FIELDS=[("model",0),("color",1),("memory",0),("maxTurns",0),("permissionMode",0),
        ("hooks",0),("disallowedTools",0),("isolation",0),("background",0)]
fr=[]
for f,cos in FIELDS:
    pred=(lambda a: bool(a.get("has_hooks"))) if f=="hooks" else (lambda a,_f=f: a.get(_f) is not None)
    r=repo_rate(pred, lambda a: True)
    if r: fr.append((f,cos,r))
fr.sort(key=lambda x: x[2][0], reverse=True)
fig,ax=plt.subplots(figsize=(3.5,2.8))
for i,(f,cos,r) in enumerate(fr):
    c=PINK if cos else BLUE
    ax.barh(i, r[0], color=c, height=.62, zorder=3)
    ax.plot([r[1],r[2]],[i,i], color=INK, lw=0.8, zorder=4)
    ax.text(max(r[0],r[2])+0.022, i, f"{100*r[0]:.1f}%", va="center", fontsize=7.5, color=INK)
ax.set_yticks(range(len(fr)))
ax.set_yticklabels([f + ("  (cosmetic)" if c else "") for f,c,_ in fr], fontsize=8)
ax.invert_yaxis(); ax.set_xlim(0,0.80); ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("repositories declaring the field (95% CI)")
ax.grid(axis="x", color=GRID, lw=0.5); ax.set_axisbelow(True); despine(ax)
save(fig,"fig5_fields"); plt.close(fig)

# ============ FIG 6 — defect forest plot ============
KNOWN=parsing.SCHEMA_FIELDS   # documented frontmatter keys, shared with analyze.py
defs=[("names an unrecognised tool", lambda a: any(not tool_ok(t) for t in a["tools"]), expl),
      ("names no recognised tool at all", lambda a: not any(tool_ok(t) for t in a["tools"]), expl),
      ("permissionMode set (inert under auto)", lambda a: a.get("permissionMode") is not None, lambda a: True),
      ("unrecognised model value",
       lambda a: not re.match(r'^(opus|sonnet|haiku|fable|inherit|claude-)', str(a.get("model")), re.I),
       lambda a: a.get("model") is not None),
      ("uses a non-schema field", lambda a: bool(set(a.get("fm_keys",[]))-KNOWN), lambda a: True)]
dr=[(l,repo_rate(p,d)) for l,p,d in defs]
dr=[(l,r) for l,r in dr if r]; dr.sort(key=lambda x: x[1][0])
fig,ax=plt.subplots(figsize=(4.6,2.2))
for i,(l,r) in enumerate(dr):
    ax.plot([r[1],r[2]],[i,i], color=BLUE, lw=1.2)
    ax.plot([r[0]],[i], "o", ms=5, color=BLUE, zorder=3)
    ax.text(r[2]+0.006, i, f"{100*r[0]:.1f}%", va="center", fontsize=7.5, color=INK)
ax.set_yticks(range(len(dr))); ax.set_yticklabels([l for l,_ in dr], fontsize=8)
ax.set_xlim(0,0.24); ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("repositories affected (95% bootstrap CI)")
ax.grid(axis="x", color=GRID, lw=0.5); ax.set_axisbelow(True); despine(ax)
save(fig,"fig6_defects"); plt.close(fig)

# numbers the manuscript quotes
summary=dict(
  n_files=len(RAW), n_specs=len(SPEC), n_repos=len(byrepo),
  concentration_top10=cum[i10][1], median_team=med, mean_team=sum(sizes)/len(sizes), max_team=max(sizes),
  inspection=dict(total=n0, denied_write=n1, denied_write_but_bash=n2, genuinely_readonly=n3),
  roles=[dict(role=r, n=ns, filewrite=fw[0], fw_lo=fw[1], fw_hi=fw[2],
              bash=bs[0], b_lo=bs[1], b_hi=bs[2]) for r,ns,fw,bs in rows],
  fields=[dict(field=f, cosmetic=bool(c), mean=r[0], lo=r[1], hi=r[2]) for f,c,r in fr],
  defects=[dict(defect=l, mean=r[0], lo=r[1], hi=r[2], n=r[3]) for l,r in dr],
)
json.dump(summary, open(ROOT/"data"/"figsummary.json","w"), indent=1)
print("figures written to", OUT)
for p in sorted(OUT.glob("*.pdf")): print("  ", p.name, f"{p.stat().st_size/1024:.1f} KB")
print("\nkey numbers:")
print(f"  specs {len(SPEC):,} in {len(byrepo):,} repos; top 10% of repos hold {100*cum[i10][1]:.0f}%")
print(f"  inspection specs {n0}: denied file-write {n1} ({100*n1/n0:.1f}%), "
      f"of those Bash-granted {n2} ({100*n2/max(1,n1):.1f}%), genuinely read-only {n3} ({100*n3/n0:.1f}%)")

# ============================================================================
# Figures 7-9: heatmap, governance co-occurrence, adoption over time
# ============================================================================

# ---------- FIG 7: role x tool heatmap ----------
TOOLS=["Read","Grep","Glob","WebFetch","WebSearch","Bash","Write","Edit","NotebookEdit","Task"]
roles=[r for r,_ in STRICT if sum(1 for a in SPEC if a["_r"]==r and expl(a))>=40]
M=[]
for r in roles:
    g=[a for a in SPEC if a["_r"]==r and expl(a)]
    M.append([sum(1 for a in g if t in {bt(x) for x in a["tools"]})/len(g) for t in TOOLS])
cmap=LinearSegmentedColormap.from_list("bl",["#ffffff","#cfe3f0","#7fb6d9","#2b7fb8","#0072B2"])
fig,ax=plt.subplots(figsize=(6.4,3.0))
im=ax.imshow(M,cmap=cmap,vmin=0,vmax=1,aspect="auto")
ax.set_xticks(range(len(TOOLS))); ax.set_xticklabels(TOOLS,rotation=40,ha="right")
ax.set_yticks(range(len(roles))); ax.set_yticklabels([f"{r}" for r in roles])
for i in range(len(roles)):
    for j in range(len(TOOLS)):
        v=M[i][j]
        ax.text(j,i,f"{100*v:.0f}",ha="center",va="center",fontsize=7,
                color="white" if v>0.55 else INK)
# frame the two columns that carry the argument
for j,lab in ((TOOLS.index("Bash"),"shell"),(TOOLS.index("Write"),"file write")):
    ax.add_patch(plt.Rectangle((j-0.5,-0.5),1,len(roles),fill=False,ec=VERM,lw=1.6,zorder=5))
ax.set_title("percentage of specifications granting each tool, by declared role",fontsize=9,pad=8)
cb=fig.colorbar(im,ax=ax,fraction=0.025,pad=0.02); cb.outline.set_visible(False)
cb.set_ticks([0,0.5,1]); cb.set_ticklabels(["0%","50%","100%"])
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_xticks([x-0.5 for x in range(len(TOOLS)+1)],minor=True)
ax.set_yticks([y-0.5 for y in range(len(roles)+1)],minor=True)
ax.grid(which="minor",color="white",lw=1.4); ax.tick_params(which="minor",length=0)
save(fig,"fig7_heatmap"); plt.close(fig)

# ---------- FIG 8: governance co-occurrence ----------
T={}
for l in __import__("gzip").open(DATA/"trees.jsonl.gz","rt"):
    t=json.loads(l); T[t["repo"]]=t
withag=[t for r,t in T.items() if r in byrepo]
def has(t,rx): return any(re.search(rx,f["p"]) for f in t["cfg"])
ITEMS=[("CLAUDE.md",r'(^|/)CLAUDE\.md$',"context"),
       ("skills",r'\.claude/skills/.*\.md$',"context"),
       ("slash commands",r'\.claude/commands/.*\.md$',"context"),
       ("AGENTS.md",r'(^|/)AGENTS\.md$',"context"),
       ("CI workflow",r'\.github/workflows/',"context"),
       ("settings.json",r'\.claude/settings\.json$',"governance"),
       (".mcp.json",r'(^|/)\.mcp\.json$',"governance"),
       ("settings.local.json",r'\.claude/settings\.local\.json$',"governance")]
vals=[(lab,sum(1 for t in withag if has(t,rx))/len(withag),kind) for lab,rx,kind in ITEMS]
vals.sort(key=lambda x:x[1],reverse=True)
fig,ax=plt.subplots(figsize=(4.3,2.7))
for i,(lab,v,kind) in enumerate(vals):
    ax.barh(i,v,color=(BLUE if kind=="context" else VERM),height=.62,zorder=3)
    ax.text(v+0.012,i,f"{100*v:.1f}%",va="center",fontsize=7.6,color=INK)
ax.set_yticks(range(len(vals))); ax.set_yticklabels([v[0] for v in vals],fontsize=8)
ax.invert_yaxis(); ax.set_xlim(0,1.0); ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("share of agent-defining repositories that also ship the artifact")
from matplotlib.patches import Patch
ax.legend(handles=[Patch(facecolor=BLUE,label="instruction / context artifact"),
                   Patch(facecolor=VERM,label="governance artifact")],
          loc="lower right", frameon=False, bbox_to_anchor=(1.0,-0.02))
ax.grid(axis="x",color=GRID,lw=.5); ax.set_axisbelow(True); despine(ax)
save(fig,"fig8_cooccurrence"); plt.close(fig)

# ---------- FIG 9: adoption over time ----------
META={}
mp=DATA/"repometa.jsonl.gz"
if mp.exists():
    for l in __import__("gzip").open(mp,"rt"):
        try: m=json.loads(l); META[m["repo"]]=m
        except: pass
months=collections.Counter()
for r in byrepo:
    m=META.get(r)
    if not m or not m.get("created"): continue
    months[m["created"][:7]]+=1
if months:
    ks=sorted(months)
    ks=[k for k in ks if k>="2024-06"]
    if ks: ks=ks[:-1]   # final month is partial at collection time
    cum=[]; run=0
    for k in ks: run+=months[k]; cum.append(run)
    fig,ax=plt.subplots(figsize=(5.6,2.5))
    ax.bar(range(len(ks)),[months[k] for k in ks],color=BLUE,width=.72,zorder=3,
           label="repositories created that month")
    ax2=None
    ax.set_xticks([i for i,k in enumerate(ks) if k.endswith(("-01","-07"))])
    ax.set_xticklabels([k for k in ks if k.endswith(("-01","-07"))],rotation=45,ha="right",fontsize=7.5)
    ax.set_ylabel("agent-defining repositories\ncreated per month")
    ax.set_xlabel("repository creation month")
    ax.grid(axis="y",color=GRID,lw=.5); ax.set_axisbelow(True); despine(ax)
    ax.legend(frameon=False,loc="upper left")
    save(fig,"fig9_adoption"); plt.close(fig)
    print(f"fig9: {len(ks)} months, {sum(months[k] for k in ks)} repos dated")

print("figures 7-9 written")
for p in sorted(OUT.glob("fig[789]*.pdf")): print("  ",p.name)
