"""Analyze saved emergent Gemini worldlines without calling an API."""
from __future__ import annotations
import argparse,collections,json
from pathlib import Path


def _turn_signature(turn:dict)->dict:
    responses=turn["country_responses"]
    return {
        "event":turn["snapshot"]["event"],
        "event_origin":turn["snapshot"].get("event_origin"),
        "responses":{c:responses[c]["response_id"] for c in sorted(responses)},
        "actions":{c:responses[c]["action"]["action_id"] for c in sorted(responses)},
        "damage_after":turn["executed_state"]["reconstruction"]["after"],
        "homeostasis":turn["research_metrics"]["global_homeostasis"],
        "sovereignty":turn["research_metrics"]["national_sovereignty"],
    }


def analyze(data:dict)->dict:
    runs=data.get("runs",())
    if len(runs)<2:raise ValueError("emergence comparison requires at least two runs")
    paths=[]
    for row in runs:
        details=row.get("details",row)
        turns=details["turns"]
        paths.append({"run":details.get("run",row.get("run_id")),"seed":details.get("seed",row.get("seed")),
                      "turns":[_turn_signature(t) for t in turns]})
    first_divergence=None
    width=min(len(p["turns"]) for p in paths)
    for i in range(width):
        signatures={json.dumps({"responses":p["turns"][i]["responses"],"actions":p["turns"][i]["actions"]},sort_keys=True,ensure_ascii=False) for p in paths}
        if len(signatures)>1:
            first_divergence=i+1;break
    event_counts=collections.Counter(t["event"] for p in paths for t in p["turns"][1:])
    action_counts=collections.Counter(a for p in paths for t in p["turns"] for a in t["actions"].values())
    run_count=len(paths)
    recurrent=sorted(({"event":e,"occurrences":n} for e,n in event_counts.items() if n>=run_count),key=lambda x:(-x["occurrences"],x["event"]))
    rare=sorted(({"event":e,"occurrences":n} for e,n in event_counts.items() if n==1),key=lambda x:x["event"])
    outcomes=[]
    for p in paths:
        last=p["turns"][-1]
        outcomes.append({"run":p["run"],"seed":p["seed"],"final_damage":last["damage_after"],
                         "final_homeostasis":last["homeostasis"],"final_sovereignty":last["sovereignty"],
                         "event_path":[t["event"] for t in p["turns"]]})
    return {"research_mode":"emergent-worldlines","run_count":run_count,
            "first_behavioral_divergence_turn":first_divergence,
            "recurrent_derived_events":recurrent,"single_occurrence_derived_events":rare,
            "action_frequency":dict(sorted(action_counts.items())),"worldline_outcomes":outcomes}


def main():
    p=argparse.ArgumentParser();p.add_argument("result",type=Path);p.add_argument("--output",type=Path)
    a=p.parse_args();data=json.loads(a.result.read_text(encoding="utf-8"));result=analyze(data)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        if a.output.exists():raise SystemExit("output exists; refusing to overwrite")
        a.output.write_text(text+"\n",encoding="utf-8")
    else:print(text)
if __name__=="__main__":main()
