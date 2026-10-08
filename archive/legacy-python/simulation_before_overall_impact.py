from prompt_interface import private_value, private_text
from dataclasses import dataclass, field
from getpass import getpass
from typing import Dict, List
import json
import time

from google import genai


MODEL_NAME = "gemini-3.6-flash"
TURN_COUNT = 5
USE_GEMINI = True

# 対照実験の条件
# "hotline" = A国/B国が直接確認できる緊急通信路あり
# "no_hotline" = 公開情報と観測できる行動のみ
EXPERIMENT_CONDITION = "no_hotline"


@dataclass
class Agent:
    name: str
    goal: str
    relationships: Dict[str, str]
    memory: List[str] = field(default_factory=list)

    def context(self) -> str:
        relationships_text = private_text('context:archive/legacy-python/simulation_before_overall_impact.py:29:29').join(
            f"{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:30:12:0')}{country}{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:30:12:2')}{status}"
            for country, status in self.relationships.items()
        )

        memory_text = (
            private_text('context:archive/legacy-python/simulation_before_overall_impact.py:35:12').join(f"{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:35:22:0')}{item}" for item in self.memory)
            if self.memory
            else private_text('context:archive/legacy-python/simulation_before_overall_impact.py:37:17')
        )

        return f"{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:40:15:0')}{self.name}{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:40:15:2')}{self.goal}{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:40:15:4')}{relationships_text}{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:40:15:6')}{memory_text}{private_text('context:archive/legacy-python/simulation_before_overall_impact.py:40:15:8')}".strip()


def call_agent(
    client: genai.Client,
    agent: Agent,
    world_state: str,
    communication_context: str,
) -> str:
    prompt = f"{private_text('archive/legacy-python/simulation_before_overall_impact.py:59:13:0')}{agent.name}{private_text('archive/legacy-python/simulation_before_overall_impact.py:59:13:2')}{agent.context()}{private_text('archive/legacy-python/simulation_before_overall_impact.py:59:13:4')}{world_state}{private_text('archive/legacy-python/simulation_before_overall_impact.py:59:13:6')}{communication_context}{private_text('archive/legacy-python/simulation_before_overall_impact.py:59:13:8')}".strip()

    while True:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            error_text = str(e)

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("Geminiの利用制限に到達しました。60秒待って自動再試行します...")
                time.sleep(60)
                continue

            raise



def evaluate_metrics(
    client,
    world_state: str,
    action_a: str,
    reason_a: str,
    belief_a: str,
    action_b: str,
    reason_b: str,
    belief_b: str,
) -> dict:
    prompt = f"{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:0')}{world_state}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:2')}{action_a}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:4')}{reason_a}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:6')}{belief_a}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:8')}{action_b}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:10')}{reason_b}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:12')}{belief_b}{private_text('archive/legacy-python/simulation_before_overall_impact.py:134:13:14')}".strip()

    while True:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )

            text = response.text.strip()
            if text.startswith("```"):
                text = text.replace("```json", "", 1).replace("```", "").strip()

            metrics = json.loads(text)

            required = {
                "homeostasis",
                "tension",
                "misperception_risk",
                "trust",
                "resilience",
            }

            if set(metrics.keys()) != required:
                raise ValueError(f"指標キーが不正です: {metrics.keys()}")

            for key in required:
                value = int(metrics[key])
                if not 0 <= value <= 100:
                    raise ValueError(f"{key} が0〜100の範囲外です: {value}")
                metrics[key] = value

            return metrics

        except Exception as e:
            error_text = str(e)

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("Geminiの指標評価が利用制限に達しました。60秒待って自動再試行します...")
                time.sleep(60)
                continue

            raise


def mock_decisions(turn: int) -> str:
    scenarios = {
        1: (
            "外交ルートを通じてB国へ軍事演習の事実確認と説明を求める。",
            "不要な誤解を避けながら、相手国の意図を確認するため。",
            "国境付近の警戒監視体制と情報収集を強化する。",
            "脅威を早期に察知しつつ、直接的な軍事衝突を避けるため。",
        ),
        2: (
            "B国との緊急連絡窓口（ホットライン）の設置を提案する。",
            "偶発的な衝突や誤解を防ぐため。",
            "A国からの照会に対し、軍事演習は侵攻目的ではないと説明する。",
            "不要な緊張を抑え、自国の安全と主権を維持するため。",
        ),
        3: (
            "国境監視を維持しつつ、B国との実務協議を開始する。",
            "相互確認を増やし、緊張を段階的に下げるため。",
            "ホットライン設置に同意し、演習情報の一部共有を提案する。",
            "誤認による衝突リスクを下げるため。",
        ),
        4: (
            "B国との共同危機管理ルール作成を提案する。",
            "将来の偶発衝突を制度的に防ぐため。",
            "共同危機管理ルールの協議に参加する。",
            "安定した関係を維持しながら安全保障上の透明性を高めるため。",
        ),
        5: (
            "警戒水準を平時レベルへ段階的に戻す。",
            "対話と情報共有によって直近の脅威が低下したため。",
            "情報収集活動を通常レベルへ戻し、外交協議を継続する。",
            "緊張緩和を維持しつつ、必要な監視能力を残すため。",
        ),
    }

    a_action, a_reason, b_action, b_reason = scenarios[turn]

    return f"""
=== A国 ===
行動: {a_action}
理由: {a_reason}

=== B国 ===
行動: {b_action}
理由: {b_reason}
""".strip()


def split_decisions(response_text: str):
    if "=== B国 ===" not in response_text:
        raise ValueError("B国の回答を分離できませんでした。")

    a_part, b_part = response_text.split("=== B国 ===", 1)

    a_part = a_part.replace("=== A国 ===", "", 1).strip()
    b_part = b_part.strip()

    return a_part, b_part


def extract_action(decision: str) -> str:
    for line in decision.splitlines():
        line = line.strip()

        if line.startswith("行動:"):
            return line.replace("行動:", "", 1).strip()

        if line.startswith("行動："):
            return line.replace("行動：", "", 1).strip()

    return decision.splitlines()[0].strip()


def extract_reason(decision: str) -> str:
    for line in decision.splitlines():
        line = line.strip()

        if line.startswith("理由:"):
            return line.replace("理由:", "", 1).strip()

        if line.startswith("理由："):
            return line.replace("理由：", "", 1).strip()

    return ""



def extract_belief(decision: str) -> str:
    for line in decision.splitlines():
        line = line.strip()

        if line.startswith("現在認識:"):
            return line.replace("現在認識:", "", 1).strip()

        if line.startswith("現在認識："):
            return line.replace("現在認識：", "", 1).strip()

    return "相手国の意図は未確認"



def build_world_state(action_a: str, action_b: str) -> str:
    return (
        f"A国は「{action_a}」を実行した。"
        f"B国は「{action_b}」を実行した。"
        "両国は互いに相手国の行動を観測できる。"
        "ただし、相手がその行動を選んだ内部的な意図や判断理由は直接観測できない。"
    )


def main():
    client = None

    if USE_GEMINI:
        api_key = getpass("Gemini API Key: ")
        client = genai.Client(api_key=api_key)

    country_a = Agent(
        name=private_text('context:archive/legacy-python/simulation_before_overall_impact.py:253:13'),
        goal=private_text('context:archive/legacy-python/simulation_before_overall_impact.py:254:13'),
        relationships={
            private_text('context:archive/legacy-python/simulation_before_overall_impact.py:256:12'): private_text('context:archive/legacy-python/simulation_before_overall_impact.py:256:20'),
        },
    )

    country_b = Agent(
        name=private_text('context:archive/legacy-python/simulation_before_overall_impact.py:261:13'),
        goal=private_text('context:archive/legacy-python/simulation_before_overall_impact.py:262:13'),
        relationships={
            private_text('context:archive/legacy-python/simulation_before_overall_impact.py:264:12'): private_text('context:archive/legacy-python/simulation_before_overall_impact.py:264:20'),
        },
    )

    world_state = (
        "現在は平時です。"
        "A国とB国の間には軍事衝突はなく、外交関係は中立です。"
        "ただし、両国の国境付近で小規模な軍事演習が確認されました。"
    )

    results = []

    print(
        "\n実行モード:",
        "Gemini AI" if USE_GEMINI else "開発モード（APIなし）",
    )

    for turn in range(1, TURN_COUNT + 1):
        print("\n====================")
        print(f"TURN {turn}")
        print("====================")

        print("\n=== 世界状況 ===")
        print(world_state)

        if USE_GEMINI:
            if EXPERIMENT_CONDITION == "hotline":
                communication_context = (
                    "A国とB国の間には緊急連絡窓口（ホットライン）が存在します。"
                    "必要に応じて相手国へ直接説明や確認を求められます。"
                )
            else:
                communication_context = (
                    "A国とB国の間に直接確認できる緊急通信路はありません。"
                    "判断には公開情報と観測できた相手国の行動だけを利用してください。"
                )

            print("\nA国Agentが判断中...")
            decision_a = call_agent(
                client=client,
                agent=country_a,
                world_state=world_state,
                communication_context=communication_context,
            )

            print("\nB国Agentが判断中...")
            decision_b = call_agent(
                client=client,
                agent=country_b,
                world_state=world_state,
                communication_context=communication_context,
            )
        else:
            combined_response = mock_decisions(turn)
            decision_a, decision_b = split_decisions(combined_response)

        country_a.memory.append(decision_a)
        country_b.memory.append(decision_b)

        action_a = extract_action(decision_a)
        action_b = extract_action(decision_b)
        reason_a = extract_reason(decision_a)
        reason_b = extract_reason(decision_b)
        belief_a = extract_belief(decision_a)
        belief_b = extract_belief(decision_b)
        action_a = action_a or decision_a.replace("行動：", "行動:").split("行動:", 1)[-1].split("理由:", 1)[0].strip()
        action_b = action_b or decision_b.replace("行動：", "行動:").split("行動:", 1)[-1].split("理由:", 1)[0].strip()
        print("\n=== A国の判断 ===")
        print(decision_a)

        print("\n=== B国の判断 ===")
        print(decision_b)

        world_state = build_world_state(action_a, action_b)

        if USE_GEMINI:
            metrics = evaluate_metrics(
                client=client,
                world_state=world_state,
                action_a=action_a,
                reason_a=reason_a,
                belief_a=belief_a,
                action_b=action_b,
                reason_b=reason_b,
                belief_b=belief_b,
            )
        else:
            metrics = None

        results.append(
            {
                "turn": turn,
                "world_state": world_state,
                "metrics": metrics,
                "country_a": {
                    "action": action_a,
                    "reason": reason_a,
                    "belief": belief_a,
                },
                "country_b": {
                    "action": action_b,
                    "reason": reason_b,
                    "belief": belief_b,
                },
            }
        )


    output_data = {
        "mode": "gemini" if USE_GEMINI else "development",
        "turn_count": TURN_COUNT,
        "results": results,
    }

    if USE_GEMINI:
        output_file = f"simulation_result_independent_agents_{EXPERIMENT_CONDITION}.json"
    else:
        output_file = "simulation_result_development.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            output_data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n====================")
    print("SIMULATION END")
    print("====================")

    print(f"\n{output_file} を保存しました。")


if __name__ == "__main__":
    main()
