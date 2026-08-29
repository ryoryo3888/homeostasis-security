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
        relationships_text = "\n".join(
            f"- {country}: {status}"
            for country, status in self.relationships.items()
        )

        memory_text = (
            "\n".join(f"- {item}" for item in self.memory)
            if self.memory
            else "- まだ記憶はありません。"
        )

        return f"""
国家名: {self.name}

最優先目標:
{self.goal}

他国との関係:
{relationships_text}

これまでの記憶:
{memory_text}
""".strip()


def call_agent(
    client: genai.Client,
    agent: Agent,
    world_state: str,
    communication_context: str,
) -> str:
    prompt = f"""
あなたは架空国家 {agent.name} の意思決定Agentです。

重要:
あなたは自国について与えられた情報と、
両国から観測可能な世界状況だけを使って判断してください。

相手国の本当の目的・内部の判断理由・非公開情報・記憶は見えません。
分からないことは推測として扱い、事実と混同しないでください。
相手の行動には複数の可能な意図があることを考慮してください。

====================
あなた自身の状態
====================
{agent.context()}

====================
現在観測できる世界状況
====================
{world_state}

====================
利用可能な通信環境
====================
{communication_context}

通信手段が存在する場合も、相手の本音が自動的に分かるわけではありません。
必要なら、その通信手段を使って相手へ確認する行動を選ぶことができます。

次に自国が取る行動を1つだけ決めてください。

必ず次の形式で答えてください。

現在認識:
懸念:
行動:
理由:

理由には、
・現在何を観測しているか
・相手の意図をどう推測しているか
・どんな誤認リスクがあるか
・なぜその行動を選ぶのか
・次に何が起こる可能性があるか
を自然な文章で含めてください。
""".strip()

    while True:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            error_text = str(e)

            if "GenerateRequestsPerDayPerProjectPerModel" in error_text:
                print("Geminiの日次上限に到達しました。本日は再試行しても通らないため停止します。")
                raise

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("Geminiの一時的な利用制限です。60秒待って1回だけ再試行します...")
                time.sleep(60)
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                )
                return response.text.strip()

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
    """Geminiを使わず、両国が実際に生成した判断内容から状態指標を算出する。"""

    text = " ".join([
        world_state,
        action_a, reason_a, belief_a,
        action_b, reason_b, belief_b,
    ])

    hostile_words = [
        "攻撃", "武力", "威嚇", "報復", "軍事行動", "動員",
        "封鎖", "最後通牒", "敵対", "エスカレーション",
    ]
    cooperative_words = [
        "対話", "協議", "外交", "ホットライン", "説明", "合意",
        "透明性", "信頼", "緩和", "情報共有", "確認",
    ]
    clarification_words = [
        "意図確認", "事実照会", "監視", "観測", "検証",
        "誤認", "確認", "説明を求め", "透明性",
    ]
    uncertainty_words = [
        "未確認", "不明", "可能性", "推測", "警戒",
        "疑念", "懸念", "リスク",
    ]

    hostile = sum(text.count(w) for w in hostile_words)
    cooperative = sum(text.count(w) for w in cooperative_words)
    clarification = sum(text.count(w) for w in clarification_words)
    uncertainty = sum(text.count(w) for w in uncertainty_words)

    def clamp(v):
        return max(0, min(100, int(round(v))))

    tension = clamp(
        45
        + hostile * 7
        + uncertainty * 2
        - cooperative * 3
        - clarification * 2
    )

    misperception_risk = clamp(
        40
        + uncertainty * 4
        + hostile * 2
        - clarification * 6
        - cooperative * 2
    )

    trust = clamp(
        45
        + cooperative * 4
        + clarification * 3
        - hostile * 5
        - uncertainty
    )

    resilience = clamp(
        60
        + cooperative * 3
        + clarification * 2
        - hostile * 3
    )

    homeostasis = clamp(
        (
            (100 - tension)
            + (100 - misperception_risk)
            + trust
            + resilience
        ) / 4
    )

    if homeostasis >= 70:
        overall_impact = "対話・確認・情報共有が機能し、システムは安定方向へ向かっています。"
    elif homeostasis >= 50:
        overall_impact = "緊張要因を残しながらも、外交的な調整によって一定の均衡が維持されています。"
    else:
        overall_impact = "不確実性や警戒が強く、相互作用による不安定化リスクが高まっています。"

    return {
        "homeostasis": homeostasis,
        "tension": tension,
        "misperception_risk": misperception_risk,
        "trust": trust,
        "resilience": resilience,
        "overall_impact": overall_impact,
    }


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


def _extract_section(decision: str, heading: str, stop_headings: tuple[str, ...]) -> str:
    lines = [
        line.strip().replace("**", "").replace("：", ":")
        for line in decision.splitlines()
    ]

    for i, line in enumerate(lines):
        if line.startswith(heading + ":"):
            first = line.split(":", 1)[1].strip()
            parts = [first] if first else []

            for following in lines[i + 1:]:
                if any(following.startswith(h + ":") for h in stop_headings):
                    break
                if following:
                    parts.append(following)

            return " ".join(parts).strip()

    return ""


def extract_action(decision: str) -> str:
    value = _extract_section(
        decision,
        "行動",
        ("現在認識", "理由"),
    )
    return value or decision.splitlines()[0].strip()


def extract_concern(decision: str) -> str:
    return _extract_section(
        decision,
        "懸念",
        ("行動", "理由"),
    )


def extract_concern(decision: str) -> str:
    return _extract_section(
        decision,
        "懸念",
        ("行動", "理由"),
    )


def extract_reason(decision: str) -> str:
    return _extract_section(
        decision,
        "理由",
        ("現在認識", "行動"),
    )


def extract_belief(decision: str) -> str:
    value = _extract_section(
        decision,
        "現在認識",
        ("行動", "理由"),
    )
    return value or "相手国の意図は未確認"


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
        name="A国",
        goal="国家の安全と主権を守りながら、不要な武力衝突を避けること。",
        relationships={
            "B国": "中立",
        },
    )

    country_b = Agent(
        name="B国",
        goal="国家の安全と主権を守りながら、自国に対する脅威を早期に察知すること。",
        relationships={
            "A国": "中立",
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
        concern_a = extract_concern(decision_a)
        concern_b = extract_concern(decision_b)
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
            "concern": concern_a,
                    "belief": belief_a,
                },
                "country_b": {
                    "action": action_b,
                    "reason": reason_b,
            "concern": concern_b,
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
