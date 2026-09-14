"""HOMEOSTASIS SECURITY v2 Gemini Agent experiment engine.

The browser dashboard never imports or calls this module. A real API call is
possible only through the explicit CLI entry point at the bottom of this file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import random
import tempfile
import time
from typing import Any, Callable


MODEL_NAME = "gemini-3.6-flash"
TURN_COUNT = 5
RESEARCH_QUESTION = "国家主権を維持したまま、地球規模の恒常性は成立するのか？"

SOURCE_EVENT = {
    "origin": "v1 二国間の恒常性シミュレーション／第3ターン",
    "event": "A国のミサイルがB国の民間農地へ着弾",
    "lost_annual_rice_capacity_tons": 8000,
    "recovery_turns": 4,
}

INITIAL_WORLD_STATE = {
    "food": 82,
    "energy": 79,
    "economy": 81,
    "environment": 76,
    "international_trust": 72,
    "conflict_load": 24,
    "national_sovereignty": 88,
}

COUNTRY_ACTIONS = {
    "A": ("攻撃継続", "停戦", "補償", "制裁への反発", "外交交渉"),
    "B": ("軍事報復", "農地復旧", "食料輸入", "援助要請", "停戦交渉"),
    "C": ("輸入政策変更", "援助参加", "中立維持", "制裁参加", "自国優先"),
}
COORDINATOR_PROPOSALS = ("食料援助", "仲裁", "制裁提案", "資源再配分", "緊急協定提案")
PROPOSAL_RESPONSES = ("受け入れる", "拒否する", "条件付きで応じる")
EVALUATOR_FIELDS = (
    "food",
    "energy",
    "economy",
    "environment",
    "international_trust",
    "conflict_load",
    "sovereignty_pressure",
)


@dataclass(frozen=True)
class AgentSpec:
    code: str
    role: str
    interests: tuple[str, ...]
    actions: tuple[str, ...]

    def private_context(self) -> str:
        interests = "\n".join(f"- {item}" for item in self.interests)
        actions = "、".join(self.actions)
        return f"役割: {self.role}\n国家利益:\n{interests}\n選択可能な行動: {actions}"


AGENTS = {
    "A": AgentSpec(
        "A",
        "事件を発生させた国家",
        ("国家安全保障", "国際的立場", "自国民の保護"),
        COUNTRY_ACTIONS["A"],
    ),
    "B": AgentSpec(
        "B",
        "農地への直接被害を受けた国家",
        ("食料供給", "民間人保護", "領土と主権"),
        COUNTRY_ACTIONS["B"],
    ),
    "C": AgentSpec(
        "C",
        "食料価格・経済への二次的影響を受ける第三国",
        ("国内物価", "供給安定", "外交的自律性"),
        COUNTRY_ACTIONS["C"],
    ),
}


def clamp_score(value: Any) -> int:
    """Round a numeric value and constrain it to the public 0..100 scale."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid score")
    return max(0, min(100, int(round(float(value)))))


def calculate_global_homeostasis(world_state: dict[str, Any]) -> int:
    """Calculate global homeostasis from all six global indicators.

    Formula:
      mean(food, energy, economy, environment, international_trust)
      - 0.40 * conflict_load

    Conflict is a burden, while the other five indicators sustain recovery.
    The result is rounded and constrained to 0..100.
    """
    sustaining = sum(
        world_state[key]
        for key in ("food", "energy", "economy", "environment", "international_trust")
    ) / 5
    return clamp_score(sustaining - 0.40 * world_state["conflict_load"])


def generate_content_with_retry(
    client: Any,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    jitter_fn: Callable[[float, float], float] = random.uniform,
    **kwargs: Any,
) -> Any:
    """Call Gemini with bounded retries while leaving SDK retries disabled."""
    max_attempts = 3
    unavailable_retries = 0
    rate_limit_retries = 0
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as error:
            text = str(error)
            code = getattr(error, "code", None)
            status = getattr(error, "status", None)
            if "GenerateRequestsPerDayPerProjectPerModel" in text:
                raise
            unavailable = code == 503 or status == "UNAVAILABLE" or ("503" in text and "UNAVAILABLE" in text)
            if unavailable:
                if unavailable_retries >= 2 or attempt == max_attempts - 1:
                    raise
                delay = 30 * (2**unavailable_retries) + jitter_fn(0, 3)
                unavailable_retries += 1
                sleep_fn(delay)
                continue
            if "429" in text or "RESOURCE_EXHAUSTED" in text:
                if rate_limit_retries >= 1 or attempt == max_attempts - 1:
                    raise
                rate_limit_retries += 1
                sleep_fn(60)
                continue
            raise
    raise RuntimeError("Gemini API retry limit reached")


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("response does not contain a JSON object")
        cleaned = cleaned[start : end + 1]
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("response JSON must be an object")
    return value


def require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid text field: {key}")
    return value.strip()


def parse_coordinator_response(text: str) -> dict[str, str]:
    data = parse_json_object(text)
    proposal = require_text(data, "proposal")
    if proposal not in COORDINATOR_PROPOSALS:
        raise ValueError(f"coordinator proposal is outside allowed choices: {proposal}")
    return {"proposal": proposal, "reason": require_text(data, "reason")}


def parse_country_response(text: str, country: str) -> dict[str, str]:
    data = parse_json_object(text)
    action = require_text(data, "action")
    response = require_text(data, "proposal_response")
    if country not in AGENTS:
        raise ValueError(f"unknown country: {country}")
    if action not in AGENTS[country].actions:
        raise ValueError(f"{country} action is outside allowed choices: {action}")
    if response not in PROPOSAL_RESPONSES:
        raise ValueError(f"{country} proposal response is invalid: {response}")
    return {
        "observation": require_text(data, "observation"),
        "action": action,
        "proposal_response": response,
        "reason": require_text(data, "reason"),
    }


def parse_evaluator_response(text: str) -> dict[str, Any]:
    data = parse_json_object(text)
    missing = [key for key in EVALUATOR_FIELDS if key not in data]
    if missing:
        raise ValueError(f"Evaluator fields missing: {', '.join(missing)}")
    parsed = {key: clamp_score(data[key]) for key in EVALUATOR_FIELDS}
    parsed["assessment"] = require_text(data, "assessment")
    return parsed


def public_observation(turn: int, state: dict[str, Any], damage: int) -> dict[str, Any]:
    return {
        "turn": turn,
        "source_event": SOURCE_EVENT,
        "remaining_lost_capacity_tons": damage,
        "world_indicators": {
            key: state[key]
            for key in ("food", "energy", "economy", "environment", "international_trust", "conflict_load")
        },
    }


def call_json(client: Any, prompt: str) -> str:
    response = generate_content_with_retry(
        client,
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return response.text


def call_coordinator(client: Any, observation: dict[str, Any]) -> dict[str, str]:
    prompt = f"""ROLE: COORDINATOR
あなたは強制権を持たない地球調整機関です。国家へ命令せず、最終判断を上書きしません。
研究問い: {RESEARCH_QUESTION}
公開観測: {json.dumps(observation, ensure_ascii=False)}
選択可能な提案: {'、'.join(COORDINATOR_PROPOSALS)}
JSONのみを返す: {{"proposal":"選択肢の1つ","reason":"公開情報に基づく理由"}}
"""
    return parse_coordinator_response(call_json(client, prompt))


def call_country(
    client: Any,
    agent: AgentSpec,
    observation: dict[str, Any],
    proposal: str,
) -> dict[str, str]:
    # This prompt contains only this country's private context plus public facts.
    # It never contains another country's private prompt, reasoning, or decision.
    prompt = f"""ROLE: COUNTRY {agent.code}
あなたは{agent.code}国の独立した意思決定Agentです。他Agentの非公開思考は見えません。
{agent.private_context()}
公開観測: {json.dumps(observation, ensure_ascii=False)}
強制力のない調整機関の提案: {proposal}
提案への回答: {'、'.join(PROPOSAL_RESPONSES)}
JSONのみを返す: {{"observation":"認識","action":"許可された行動","proposal_response":"許可された回答","reason":"理由"}}
"""
    return parse_country_response(call_json(client, prompt), agent.code)


def call_evaluator(
    client: Any,
    observation: dict[str, Any],
    proposal: dict[str, str],
    countries: dict[str, dict[str, str]],
    damage_after_actions: int,
) -> dict[str, Any]:
    # The Evaluator receives observable decisions, not private country prompts.
    public_outcomes = {
        code: {"action": result["action"], "proposal_response": result["proposal_response"]}
        for code, result in countries.items()
    }
    prompt = f"""ROLE: EVALUATOR
あなたは独立したEvaluatorです。公開された世界状態と行動結果を0〜100で評価します。
行動前観測: {json.dumps(observation, ensure_ascii=False)}
調整機関の提案: {json.dumps(proposal, ensure_ascii=False)}
公開された各国の結果: {json.dumps(public_outcomes, ensure_ascii=False)}
行動後の農地生産能力喪失: {damage_after_actions}t
必須数値: {', '.join(EVALUATOR_FIELDS)}
JSONのみを返す。必須数値に加え、"assessment"へ短い評価を書く。
"""
    return parse_evaluator_response(call_json(client, prompt))


def update_sovereignty(previous: int, evaluator: dict[str, Any], responses: dict[str, str]) -> int:
    """Update sovereignty without treating coordinator proposals as commands."""
    refusals = sum(value == "拒否する" for value in responses.values())
    conditions = sum(value == "条件付きで応じる" for value in responses.values())
    pressure_cost = evaluator["sovereignty_pressure"] / 20
    target = previous - pressure_cost + refusals + conditions * 0.5
    delta = max(-8, min(8, target - previous))
    return clamp_score(previous + delta)


def run_simulation(client: Any) -> dict[str, Any]:
    state = dict(INITIAL_WORLD_STATE)
    state["global_homeostasis"] = calculate_global_homeostasis(state)
    initial_state = dict(state)
    damage = SOURCE_EVENT["lost_annual_rice_capacity_tons"]
    turns: list[dict[str, Any]] = []

    for turn in range(1, TURN_COUNT + 1):
        # 1. Carry forward the physical damage before any new decision.
        damage_before = damage
        observation = public_observation(turn, state, damage_before)
        # 2. Each decision maker later receives only public observation plus its own context.
        # 3. The non-coercive coordinator selects a proposal independently.
        coordinator = call_coordinator(client, observation)
        # 4-5. Countries decide independently and respond to the proposal in the same call.
        countries = {
            code: call_country(client, agent, observation, coordinator["proposal"])
            for code, agent in AGENTS.items()
        }
        responses = {code: result["proposal_response"] for code, result in countries.items()}
        # 6. Integrate observable outcomes. B's restoration reduces persistent damage gradually.
        recovery = 2000 if countries["B"]["action"] == "農地復旧" and damage > 0 else 0
        damage = max(0, damage - recovery)
        # 7. A separate Evaluator scores the six global indicators.
        evaluator = call_evaluator(client, observation, coordinator, countries, damage)
        for key in ("food", "energy", "economy", "environment", "international_trust", "conflict_load"):
            state[key] = evaluator[key]
        # 8. Sovereignty and global homeostasis are deterministic calculations.
        state["national_sovereignty"] = update_sovereignty(state["national_sovereignty"], evaluator, responses)
        state["global_homeostasis"] = calculate_global_homeostasis(state)
        # 9. Record the complete public result for this turn.
        action_log = [
            f"地球調整機関: {coordinator['proposal']}",
            *(f"{code}国: {result['action']} / {result['proposal_response']}" for code, result in countries.items()),
        ]
        turns.append(
            {
                "turn": turn,
                "persistent_effects": {
                    "lost_capacity_before_actions_tons": damage_before,
                    "recovered_this_turn_tons": recovery,
                    "remaining_lost_capacity_tons": damage,
                },
                "coordinator_proposal": coordinator,
                "countries": countries,
                "proposal_responses": responses,
                "world_state": dict(state),
                "evaluator": evaluator,
                "action_log": action_log,
            }
        )

    change = state["global_homeostasis"] - initial_state["global_homeostasis"]
    return {
        "metadata": {
            "schema_version": 1,
            "engine": "homeostasis-security-v2",
            "mode": "gemini",
            "model": MODEL_NAME,
            "turn_count": TURN_COUNT,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "research_question": RESEARCH_QUESTION,
        "source_event": dict(SOURCE_EVENT),
        "initial_world_state": initial_state,
        "turns": turns,
        "final_result": {
            "outcome": "recovered" if change > 0 else "worsened" if change < 0 else "unchanged",
            "global_homeostasis_change": change,
            "remaining_lost_capacity_tons": damage,
            "national_sovereignty": state["national_sovereignty"],
            "global_homeostasis": state["global_homeostasis"],
        },
    }


def save_result(result: dict[str, Any], destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"output already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"output directory does not exist: {destination.parent}")
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def create_gemini_client(api_key: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HOMEOSTASIS SECURITY v2 Gemini Agent experiment")
    parser.add_argument("--output", type=Path, required=True, help="new JSON output path")
    parser.add_argument("--yes", action="store_true", help="skip the interactive YES confirmation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"出力先が既に存在するため停止しました: {args.output}")
    print(f"モデル: {MODEL_NAME}")
    print("5ターンで、各ターン5回（調整機関、A国、B国、C国、Evaluator）のAPI呼び出しを行います。")
    print(f"出力先: {args.output}")
    confirmed = "YES" if args.yes else input("実行する場合だけ YES と入力してください: ").strip()
    if confirmed != "YES":
        raise SystemExit("キャンセルしました。Gemini APIは呼んでいません。")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = getpass("Gemini API Key（表示されません）: ").strip()
    if not api_key:
        raise SystemExit("APIキーがないため停止しました。Gemini APIは呼んでいません。")
    result = run_simulation(create_gemini_client(api_key))
    save_result(result, args.output)
    print(f"保存しました: {args.output}")


if __name__ == "__main__":
    main()
