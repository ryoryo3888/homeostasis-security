from dataclasses import dataclass, field
from getpass import getpass
from typing import Dict, List
import json
import time

from google import genai


MODEL_NAME = "gemini-3.6-flash"
TURN_COUNT = 5
USE_GEMINI = True


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


def call_gemini(
    client: genai.Client,
    country_a: Agent,
    country_b: Agent,
    world_state: str,
) -> str:
    prompt = f"""
あなたは2つの架空国家を動かすシミュレーションエンジンです。

重要:
A国とB国は独立したAgentです。
それぞれ、自国が知っている情報だけを使って判断してください。
相手国の内部的な判断理由や非公開情報を使ってはいけません。

====================
A国
====================
{country_a.context()}

====================
B国
====================
{country_b.context()}

====================
両国が観測できる現在の世界状況
====================
{world_state}

A国とB国それぞれについて、
次に取る行動を1つだけ決めてください。

必ず次の形式で答えてください。
行動と理由は必ず両方とも空欄にせず、具体的な文章で書いてください。
ただし、判断の根拠・リスク評価・相手の意図の推測・次の展開への備えは省略せず、思考の深さを保ってください。文章を自然で読みやすく、人が現状に意識を持てるように表現してください。
=== A国 ===
行動:
理由:

=== B国 ===
行動:
理由:
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

            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print(
                    "\nGeminiの利用制限に到達しました。"
                    "60秒待って自動再試行します..."
                )
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
            combined_response = call_gemini(
                client=client,
                country_a=country_a,
                country_b=country_b,
                world_state=world_state,
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
        action_a = action_a or decision_a.replace("行動：", "行動:").split("行動:", 1)[-1].split("理由:", 1)[0].strip()
        action_b = action_b or decision_b.replace("行動：", "行動:").split("行動:", 1)[-1].split("理由:", 1)[0].strip()
        print("\n=== A国の判断 ===")
        print(decision_a)

        print("\n=== B国の判断 ===")
        print(decision_b)

        results.append(
            {
                "turn": turn,
                "world_state": world_state,
                "country_a": {
                    "action": action_a,
                    "reason": reason_a,
                },
                "country_b": {
                    "action": action_b,
                    "reason": reason_b,
                },
            }
        )

        world_state = (
            f"A国は「{action_a}」という行動を取りました。"
            f"B国は「{action_b}」という行動を取りました。"
            "両国間で武力衝突はまだ発生していません。"
            "各国は相手国の行動を観測できますが、"
            "その行動を選んだ内部的な理由までは知りません。"
        )

    output_data = {
        "mode": "gemini" if USE_GEMINI else "development",
        "turn_count": TURN_COUNT,
        "results": results,
    }

    with open("simulation_result.json", "w", encoding="utf-8") as f:
        json.dump(
            output_data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n====================")
    print("SIMULATION END")
    print("====================")

    print("\nsimulation_result.json を保存しました。")


if __name__ == "__main__":
    main()