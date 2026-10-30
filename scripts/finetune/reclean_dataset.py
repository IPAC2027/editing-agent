"""Re-clean an existing dataset folder with the current rules (no papers needed)."""
import json, importlib.util, hashlib, random, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("pd","scripts/finetune/prepare_dataset.py"); pd=importlib.util.module_from_spec(spec); spec.loader.exec_module(pd)
from jacow_formatter import check_rewrite
src, dst = Path(sys.argv[1]), Path(sys.argv[2]); dst.mkdir(parents=True, exist_ok=True)
files={n:(dst/f"{n}.jsonl").open("w",encoding="utf-8") for n in ("train","eval","test","rejected")}
counts={k:0 for k in ("rows_read","latex_left","style_fixed","rejected","corrections","duplicates","unchanged_available","unchanged_kept","train","eval","test")}
seen=set(); unchanged=[]; rng=random.Random(7)
def split_for(row):
    if row.get("_split")=="test": return "test"
    b=int(hashlib.sha256(row["paper"].encode()).hexdigest(),16)%1000
    return "eval" if b<100 else "train"
for name in ("train","eval","test","rejected"):
    path=src/f"{name}.jsonl"
    if not path.exists(): continue
    for line in path.open(encoding="utf-8"):
        r=json.loads(line); counts["rows_read"]+=1
        u=r["messages"][1]["content"]; raw=u.split("Reference:\n",1)[1].split("\n\nVerified",1)[0]
        rec=json.loads(u.split("JACoW):\n",1)[1]) if "Verified" in u else {}
        editor=r.get("editor_original") or r["messages"][2]["content"]
        raw, editor = pd.latex_to_text(raw), pd.latex_to_text(editor)
        base={k:r[k] for k in ("conference","paper","label","source") if k in r}
        if name=="test": base["_split"]="test"
        if pd.has_latex(raw) or pd.has_latex(editor):
            counts["latex_left"]+=1; counts["rejected"]+=1
            files["rejected"].write(json.dumps({**base,"reason":"LaTeX left after conversion","messages":pd.messages(raw,None,editor)},ensure_ascii=False)+"\n"); continue
        final, notes = pd.style_fix(editor)
        if final is None:
            counts["rejected"]+=1
            files["rejected"].write(json.dumps({**base,"reason":"style: "+notes[-1],"messages":pd.messages(raw,None,editor)},ensure_ascii=False)+"\n"); continue
        counts["style_fixed"]+=bool(notes)
        fp=hashlib.sha256((pd.normal(raw)+"\0"+pd.normal(final)).encode()).hexdigest()
        if fp in seen: counts["duplicates"]+=1; continue
        seen.add(fp)
        row={**base,"style_fixes":notes,"editor_original":editor if notes else None}
        if raw==final:
            counts["unchanged_available"]+=1
            unchanged.append({**row,"reason":"unchanged","messages":pd.messages(raw,None,final)}); continue
        removable=[x for x in pd._URL.findall(raw) if x not in final] if rec.get("doi") and str(rec["doi"]).lower() in final.lower() else []
        v=check_rewrite(raw, final, allowed_additions=[str(x) for x in rec.values()], allowed_removals=removable,
                        allowed_substitutions=pd.journal_substitutions(raw, final, str(rec.get("journal",""))))
        row["messages"]=pd.messages(raw, rec or None, final)
        if not v.ok:
            counts["rejected"]+=1
            files["rejected"].write(json.dumps({**row,"reason":"editor changed information: "+"; ".join(v.problems)[:200]},ensure_ascii=False)+"\n"); continue
        row["reason"]="formatting"; s=split_for(row); row.pop("_split",None)
        files[s].write(json.dumps(row,ensure_ascii=False)+"\n"); counts[s]+=1; counts["corrections"]+=1
limit=int(counts["corrections"]*0.15/0.85); rng.shuffle(unchanged)
for row in unchanged[:limit]:
    s=split_for(row); row.pop("_split",None)
    files[s].write(json.dumps(row,ensure_ascii=False)+"\n"); counts[s]+=1; counts["unchanged_kept"]+=1
for f in files.values(): f.close()
(dst/"summary.json").write_text(json.dumps(counts,indent=1),encoding="utf-8"); print(json.dumps(counts,indent=1))
