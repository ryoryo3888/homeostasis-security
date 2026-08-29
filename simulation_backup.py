from dataclasses import dataclass, field
from getpass import getpass
from typing import Dict, List

from google import genai


MODEL_NAME = "gemini-3.5-flash"


@dataclass
class Agent:
    name: str
    goal: str
    relationships: Dict[str, str]
    memory: List[str] = field(default_factory=list)

    def build_prompt(self, world_state: str) -> str:
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
あなたは架空国家「{self.name}」の政府です。

【最優先目標】
{self.goal}

【他国との関係】
{relationships_text}

【自国のこれまでの記憶】
{memory_text}

【現在知ることができる世界状況】
{world_state}

あなた自身が現在知っている情報だけを使って判断してください。
他国の内部事情や、他国の判断理由、人間の予測結果を
推測で補わないでください。

現在の状況を踏まえて、
次に取る行動を1つだけ決めてください。

次の形式で短く答えてください。

行動:
理由:
""".strip()

    def decide(self, client: genai.Client, world_state: str) -> str:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=self.build_prompt(world_state),
        )

        decision = response.text.strip()
        self.memory.append(decision)

        return decision


def extract_action(decision: str) -> str:
    for line in decision.splitlines():
        line = line.strip()

        if line.startswith("行動:"):
            return line.replace("行動:", "", 1).strip()

        if line.startswith("行動："):
            return line.replace("行動：", "", 1).strip()

    return decision.splitlines()[0].strip()


def main():
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

    # -------------------------
    # TURN 1
    # -------------------------

    world_state_1 = (
        "現在は平時です。"
        "A国とB国の間には軍事衝突はなく、外交関係は中立です。"
        "ただし、両国の国境付近で小規模な軍事演習が確認されました。"
    )

    decision_a_1 = country_a.decide(
        client=client,
        world_state=world_state_1,
    )

    decision_b_1 = country_b.decide(
        client=client,
        world_state=world_state_1,
    )

    action_a_1 = extract_action(decision_a_1)
    action_b_1 = extract_action(decision_b_1)

    # 両国の「実際の行動」だけを次の世界へ反映する。
    # 判断理由や内部思考は相手国には見せない。
    world_state_2 = (
        f"A国は「{action_a_1}」という行動を取りました。"
        f"B国は「{action_b_1}」という行動を取りました。"
        "両国間で武力衝突はまだ発生していません。"
        "各国は相手国の行動を観測できますが、"
        "その行動を選んだ内部的な理由までは知りません。"
    )

    # -------------------------
    # TURN 2
    # -------------------------

    decision_a_2 = country_a.decide(
        client=client,
        world_state=world_state_2,
    )

    decision_b_2 = country_b.decide(
        client=client,
        world_state=world_state_2,
    )

    print("\n====================")
    print("TURN 1")
    print("====================")

    print("\n=== 世界状況 ===")
    print(world_state_1)

    print("\n=== A国の判断 ===")
    print(decision_a_1)

    print("\n=== B国の判断 ===")
    print(decision_b_1)

    print("\n====================")
    print("TURN 2")
    print("====================")

    print("\n=== 更新された世界状況 ===")
    print(world_state_2)

    print("\n=== A国の判断 ===")
    print(decision_a_2)

    print("\n=== B国の判断 ===")
    print(decision_b_2)

    print("\n=== A国の記憶 ===")
    for item in country_a.memory:
        print(f"- {item}")

    print("\n=== B国の記憶 ===")
    for item in country_b.memory:
        print(f"- {item}")


if __name__ == "__main__":
    main()