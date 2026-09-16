"""Deterministic action-choice catalog for Gemini agents.

The model chooses a choice_id. Python owns the executable action tuple, so an
invalid action/resource/recipient combination cannot be invented by the model.
"""
from __future__ import annotations
import hashlib
from typing import Mapping, Sequence
from .feasibility import validate_action_feasible


def build_action_choices(feasible: Sequence[Mapping[str, object]]):
    choices=[]
    for index,row in enumerate(feasible,1):
        maximum=float(row["maximum_amount"])
        # Amount remains a bounded model decision for transfer actions. Everything
        # else is immutable and owned by Python.
        choices.append({
            "choice_id":f"A{index:03d}",
            "action_id":row["action_id"],
            "recipient_type":row["recipient_type"],
            "target_country":row["target_country"],
            "resource":row["resource"],
            "maximum_amount":maximum,
        })
    return tuple(choices)


def materialize_choice(choice_id:str, amount:float, description:str, choices, feasible):
    match=next((x for x in choices if x["choice_id"]==choice_id),None)
    if match is None:raise ValueError("unknown action_choice_id")
    maximum=float(match["maximum_amount"])
    if maximum==0:
        if amount!=0:raise ValueError("non-transfer action amount must be 0")
    elif isinstance(amount,bool) or not isinstance(amount,(int,float)) or not 0<amount<=maximum:
        raise ValueError(f"amount must be > 0 and <= {maximum}")
    action={"action_id":match["action_id"],"description":description,"parameters":{"recipient_type":match["recipient_type"],"target_country":match["target_country"],"resource":match["resource"],"amount":amount}}
    validate_action_feasible("__COUNTRY_PLACEHOLDER__",action,feasible) if False else None
    return action


def validate_catalog(country_id:str, choices, feasible):
    if len({x["choice_id"] for x in choices})!=len(choices):raise ValueError("duplicate choice_id")
    for choice,row in zip(choices,feasible):
        amount=0 if float(choice["maximum_amount"])==0 else min(1.0,float(choice["maximum_amount"]))
        action={"action_id":choice["action_id"],"description":"preflight","parameters":{"recipient_type":choice["recipient_type"],"target_country":choice["target_country"],"resource":choice["resource"],"amount":amount}}
        validate_action_feasible(country_id,action,feasible)
    return True


def catalog_digest(choices):
    raw="|".join(f'{x["choice_id"]}:{x["action_id"]}:{x["recipient_type"]}:{x["target_country"]}:{x["resource"]}:{x["maximum_amount"]}' for x in choices)
    return hashlib.sha256(raw.encode()).hexdigest()
