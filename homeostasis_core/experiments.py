"""Reproducible, bounded, API-free experiment orchestration."""
from __future__ import annotations
from dataclasses import dataclass
import json, os, statistics, tempfile
from pathlib import Path
from typing import Callable, Mapping
from .models import JsonModel, _freeze, _integer, _nonempty, _score

@dataclass(frozen=True)
class ExperimentPlan(JsonModel):
    scenario_id:str; seed:int; runs:int; max_runs:int=100; dry_run:bool=False; api_call_limit:int=0
    def __post_init__(self):
        _nonempty("scenario_id",self.scenario_id); _integer("seed",self.seed); _integer("runs",self.runs,minimum=1); _integer("max_runs",self.max_runs,minimum=1); _integer("api_call_limit",self.api_call_limit)
        if self.runs>self.max_runs: raise ValueError("run count exceeds configured limit")
        if not isinstance(self.dry_run,bool): raise ValueError("dry_run must be boolean")

@dataclass(frozen=True)
class ResearchResult(JsonModel):
    metadata:Mapping[str,object]; runs:tuple[Mapping[str,object],...]; summary:Mapping[str,float]
    def __post_init__(self):
        if not self.runs: raise ValueError("runs cannot be empty")
        object.__setattr__(self,"metadata",_freeze(self.metadata)); object.__setattr__(self,"runs",tuple(_freeze(r) for r in self.runs)); object.__setattr__(self,"summary",_freeze(self.summary))

def estimate_experiment(plan:ExperimentPlan)->Mapping[str,int]:
    return _freeze({"runs":plan.runs,"maximum_api_calls":plan.runs*plan.api_call_limit,"files":0 if plan.dry_run else 1})

def run_experiment(plan:ExperimentPlan, runner:Callable[[int],Mapping[str,object]], *, code_version:str, provider_type:str="deterministic", timestamp:str="1970-01-01T00:00:00Z")->ResearchResult:
    _nonempty("code_version",code_version); _nonempty("provider_type",provider_type); _nonempty("timestamp",timestamp)
    rows=[]
    for index in range(plan.runs):
        row=dict(runner(plan.seed+index)); row["run_id"]=index+1; row["seed"]=plan.seed+index
        for key in ("recovered","final_homeostasis","sovereignty_maintenance","recovery_turns"):
            if key not in row: raise ValueError(f"run result missing {key}")
        rows.append(row)
    def nums(k): return [float(r[k]) for r in rows]
    home=nums("final_homeostasis"); sov=nums("sovereignty_maintenance"); turns=nums("recovery_turns")
    summary={"average_homeostasis":statistics.fmean(home),"homeostasis_stddev":statistics.pstdev(home),"recovery_rate":100*sum(bool(r["recovered"]) for r in rows)/len(rows),"sovereignty_maintenance_rate":statistics.fmean(sov),"average_recovery_turns":statistics.fmean(turns)}
    metadata={"scenario_id":plan.scenario_id,"base_seed":plan.seed,"run_count":plan.runs,"code_version":code_version,"timestamp":timestamp,"provider_type":provider_type,"api_call_limit":plan.api_call_limit,"classification":"deterministic prototype runs"}
    return ResearchResult(metadata,tuple(rows),summary)

def save_result_atomic(result:ResearchResult,path:str|Path)->Path:
    target=Path(path)
    if os.path.lexists(target): raise FileExistsError(f"result already exists: {target}")
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=".result-",suffix=".tmp",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(result.to_dict(),stream,ensure_ascii=False,indent=2); stream.flush(); os.fsync(stream.fileno())
        # Publish exclusively: an existence check followed by replace can
        # overwrite a result created by another process between those steps.
        os.link(temp,target)
    finally:
        try: os.unlink(temp)
        except FileNotFoundError: pass
    return target
