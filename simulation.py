from dataclasses import dataclass, field
from getpass import getpass
from typing import Dict, List, Optional
import json
import hashlib
import os
from pathlib import Path
import random
import tempfile
import time

from google import genai
from google.genai import types
from model_response_json import load_response_object
from response_receipts import ResponseReceipts
from provider_retry import retryable_provider_status


MODEL_NAME = "gemini-3.6-flash"
TURN_COUNT = 8
USE_GEMINI = True

# 対照実験の条件
# "hotline" = A国/B国が直接確認できる緊急通信路あり
# "no_hotline" = 公開情報と観測できる行動のみ
EXPERIMENT_CONDITION = "no_hotline"


@dataclass(frozen=True)
class LeaderProfile:
    name: str
    threat_sensitivity: float
    risk_tolerance: float
    trust_bias: float
    legal_restraint: float
    prestige_orientation: float

    def context(self) -> str:
        return "\n".join(
            [
                f"- profile_name: {self.name}",
                f"- threat_sensitivity: {self.threat_sensitivity:.2f}",
                f"- risk_tolerance: {self.risk_tolerance:.2f}",
                f"- trust_bias: {self.trust_bias:.2f}",
                f"- legal_restraint: {self.legal_restraint:.2f}",
                f"- prestige_orientation: {self.prestige_orientation:.2f}",
            ]
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "threat_sensitivity": self.threat_sensitivity,
            "risk_tolerance": self.risk_tolerance,
            "trust_bias": self.trust_bias,
            "legal_restraint": self.legal_restraint,
            "prestige_orientation": self.prestige_orientation,
        }


@dataclass(frozen=True)
class InternationalLaw:
    enabled: bool
    principles: tuple[str, ...]

    def context(self) -> str:
        if not self.enabled:
            return "この実験条件では、共通の国際法制度は存在しません。"

        principles_text = "\n".join(f"- {item}" for item in self.principles)
        return (
            "以下は世界に存在する制度的制約です。行動を技術的に禁止するものではありませんが、"
            "違反には法的・外交的・評判上の帰結が生じ得ます。\n"
            f"{principles_text}"
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "principles": list(self.principles),
        }


@dataclass(frozen=True)
class ExternalEvent:
    event_id: str
    title: str
    observable_description: str
    base_threat_level: int
    information_reliability: float
    hidden_context: str

    def public_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "observable_description": self.observable_description,
            "information_reliability": self.information_reliability,
        }


CAUTIOUS_DIPLOMAT = LeaderProfile(
    name="慎重外交型",
    threat_sensitivity=0.45,
    risk_tolerance=0.30,
    trust_bias=0.60,
    legal_restraint=0.85,
    prestige_orientation=0.35,
)

SECURITY_HARDLINER = LeaderProfile(
    name="安全保障強硬型",
    threat_sensitivity=0.80,
    risk_tolerance=0.65,
    trust_bias=0.25,
    legal_restraint=0.55,
    prestige_orientation=0.80,
)

INTERNATIONAL_LAW = InternationalLaw(
    enabled=True,
    principles=(
        "武力による威嚇および武力行使は原則として禁止される。",
        "国際紛争は平和的手段で解決する義務がある。",
        "国家の主権および領土保全は尊重される。",
        "武力攻撃が発生した場合、必要性と比例性を満たす自衛権を行使できる。",
        "戦闘時は民間人保護、区別、比例性、予防措置が求められる。",
    ),
)

EXTERNAL_EVENTS = (
    ExternalEvent(
        event_id="border_exercise",
        title="国境付近で軍事演習を検知",
        observable_description="両国の国境付近で小規模な軍事演習が確認された。目的は公表されていない。",
        base_threat_level=30,
        information_reliability=0.90,
        hidden_context="演習は定例訓練だが、事前通知が遅れている。",
    ),
    ExternalEvent(
        event_id="unit_deviation",
        title="部隊が予定区域を逸脱",
        observable_description="演習参加部隊の一部が予定区域を外れ、国境方向へ移動したとの観測がある。",
        base_threat_level=48,
        information_reliability=0.80,
        hidden_context="航法上の混乱による逸脱だが、現場部隊はまだ修正命令を受領していない。",
    ),
    ExternalEvent(
        event_id="unidentified_aircraft_report",
        title="所属不明機接近の未確認情報",
        observable_description="SNS上で、所属不明の航空機が国境付近へ接近したという情報が拡散している。公的確認はない。",
        base_threat_level=22,
        information_reliability=0.35,
        hidden_context="民間航空機を軍用機と誤認した可能性が高い。",
    ),
    ExternalEvent(
        event_id="communication_outage",
        title="国境地域で通信障害",
        observable_description="国境地域の通信網に断続的な障害が発生し、現場報告と外交連絡の一部が遅延している。",
        base_threat_level=38,
        information_reliability=0.95,
        hidden_context="設備障害が主因で、意図的な妨害を示す証拠はない。",
    ),
    ExternalEvent(
        event_id="civilian_injury",
        title="国境付近で民間人負傷",
        observable_description="国境付近で民間人が負傷した。原因と責任主体はまだ確定していない。",
        base_threat_level=58,
        information_reliability=0.75,
        hidden_context="演習区域外に落下した破片が原因だが、どちらの装備由来かは未確定である。",
    ),
    ExternalEvent(
        event_id="third_country_statement",
        title="第三国が抑制を要求",
        observable_description="第三国政府が両国へ抑制と事実調査を求める声明を発表した。",
        base_threat_level=42,
        information_reliability=1.00,
        hidden_context="第三国は軍事介入を予定しておらず、外交的沈静化を優先している。",
    ),
    ExternalEvent(
        event_id="exercise_end_notice",
        title="演習終了通知",
        observable_description="演習部隊を通常配置へ戻す予定だという公式通知が公表された。撤収完了は未確認である。",
        base_threat_level=24,
        information_reliability=0.85,
        hidden_context="撤収命令は実際に発出済みだが、完了には時間を要する。",
    ),
    ExternalEvent(
        event_id="delayed_explanation",
        title="遅延していた説明が到着",
        observable_description="演習計画と部隊逸脱に関する詳細説明が通常の外交ルートで到着した。内容の検証は継続中である。",
        base_threat_level=18,
        information_reliability=0.90,
        hidden_context="説明内容は概ね事実と一致しているが、一部記録が欠落している。",
    ),
)


@dataclass
class Agent:
    name: str
    goal: str
    relationships: Dict[str, str]
    leader_profile: LeaderProfile
    national_interests: List[str]
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

        interests_text = "\n".join(f"- {item}" for item in self.national_interests)

        return f"""
国家名: {self.name}

国家目標:
{self.goal}

国家利益:
{interests_text}

リーダー特性（0.0〜1.0の判断傾向であり、行動を固定する規則ではない）:
{self.leader_profile.context()}

他国との関係:
{relationships_text}

これまでの記憶:
{memory_text}
""".strip()


def generate_content_with_retry(client: genai.Client, *, response_recorder=None, **kwargs):
    max_attempts = 3
    unavailable_retries = 0
    rate_limit_retries = 0

    for attempt in range(max_attempts):
        try:
            response = client.models.generate_content(**kwargs)
        except Exception as error:
            error_text = str(error)
            error_code = retryable_provider_status(error)

            if "GenerateRequestsPerDayPerProjectPerModel" in error_text:
                print("Geminiの日次上限に到達しました。本日は再試行しても通らないため停止します。")
                raise

            if error_code == 503:
                if unavailable_retries >= 2 or attempt == max_attempts - 1:
                    raise
                base_delay = 30 * (2 ** unavailable_retries)
                unavailable_retries += 1
                wait_seconds = base_delay + random.uniform(0, 3)
                print(
                    f"Gemini 503: 約{base_delay}秒待って再試行します "
                    f"({unavailable_retries}/2)"
                )
                time.sleep(wait_seconds)
                continue

            if error_code == 429:
                if rate_limit_retries >= 1 or attempt == max_attempts - 1:
                    raise
                rate_limit_retries += 1
                print("Geminiの一時的な利用制限です。60秒待って1回だけ再試行します...")
                time.sleep(60)
                continue

            raise

        # Persistence is outside provider retry handling. A storage failure
        # after receiving a decision must never request another decision.
        if response_recorder is not None:
            response_recorder(response, kwargs, attempt + 1)
        return response

    raise RuntimeError("Gemini APIの最大試行回数に到達しました。")


def call_agent(
    client: genai.Client,
    agent: Agent,
    world_state: str,
    communication_context: str,
    international_law: InternationalLaw,
    response_recorder=None,
) -> str:
    prompt = f"""
あなたは架空国家 {agent.name} の意思決定Agentです。

あなたは自国について与えられた情報と、観測可能な世界状況だけを使って判断します。
相手国の内部意図、非公開情報、内部の判断理由、非公開の記憶は見えません。

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

====================
国際法上の制度的環境
====================
{international_law.context()}

自国の利益、法的制約、安全保障リスク、観測情報、過去の経験、リーダー特性を踏まえ、
次に自国が取る行動を自由に1つだけ決めてください。
外交、静観、監視、制裁、軍事展開、威嚇、防衛、攻撃、国際機関への提起など、
行動の種類は限定されません。特定の結末へ向かう必要もありません。

必ず次の形式で答えてください。

現在認識:
懸念:
行動:
理由:

現在認識と懸念は、あなた自身が実際に持った認識だけを書いてください。
理由には、観測情報、国家利益、リーダー特性、法的制約のうち、実際に判断へ影響したものを自然な文章で含めてください。
""".strip()

    response = generate_content_with_retry(
        client,
        response_recorder=response_recorder,
        model=MODEL_NAME,
        contents=prompt,
    )
    decision = response.text
    parse_agent_decision(decision)
    return decision.strip()


EVALUATION_FIELDS = (
    "actual_threat_level",
    "perceived_threat_a",
    "perceived_threat_b",
    "immune_response_strength_a",
    "immune_response_strength_b",
    "legal_alignment_a",
    "legal_alignment_b",
    "escalation_pressure",
    "clarification_quality",
    "trust_signal",
    "recovery_capacity",
)


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(float(value)))))


def parse_evaluator_response(response_text: str) -> dict:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    parsed = load_response_object(cleaned)
    missing = [field_name for field_name in EVALUATION_FIELDS if field_name not in parsed]
    if missing:
        raise ValueError(f"Evaluatorの必須項目が不足しています: {', '.join(missing)}")

    for field_name in EVALUATION_FIELDS:
        value = parsed[field_name]
        if type(value) not in (int, float) or not 0 <= value <= 100 or value != int(value):
            raise ValueError(f"Evaluatorの{field_name}は0〜100の整数が必要です。値を補正せず停止します。")
    return {
        field_name: int(parsed[field_name])
        for field_name in EVALUATION_FIELDS
    }


def call_evaluator(
    client: genai.Client,
    event: ExternalEvent,
    world_state_before: str,
    action_a: str,
    reason_a: str,
    belief_a: str,
    action_b: str,
    reason_b: str,
    belief_b: str,
    international_law: InternationalLaw,
    response_recorder=None,
) -> dict:
    prompt = f"""
あなたは国家間相互作用を観測する中立Evaluatorです。
平和か、善い世界か、好ましい政策かを採点してはいけません。
文章中の特定単語の出現回数でも採点してはいけません。

観測状況、外部イベントの実態、両国の認識と行動の意味的関係だけを評価し、
指定された11項目を0〜100の整数で返してください。
以下の行動はAgentの選択・宣言です。実行、通信の送受信、交渉の成立を確認した記録ではありません。
行動に関する採点は宣言内容についての推定であり、実現済みの世界状態とは扱わないでください。

評価原則:
- actual_threat_level: 外部イベントの実態と両国の今回行動が生む、現時点の客観的危険度。
- perceived_threat_a/b: 各国が判断時に認識していた脅威度。
- immune_response_strength_a/b: 警戒、制裁、展開、威嚇、防衛、攻撃等を含む国家反応の強度。外交的行動も強度0とは限らない。
- legal_alignment_a/b: 行動が提示された国際法上どの程度正当化可能か。武力行使でも必要性・比例性を満たす自衛なら高くできる。
- escalation_pressure: 両行動の組合せが次の相互反応を増幅させる圧力。
- clarification_quality: 今回行動によって事実関係を識別できる度合い。外交という語だけで加点しない。
- trust_signal: 今回観測された行動が相互信頼へ与える信号。50を中立とする。
- recovery_capacity: 損傷や緊張が生じた後も制度・通信・運用を回復できる能力。

攻撃という語だけで減点せず、実際の脅威との必要性・比例性を見ること。
平和的な表現でも、重大な脅威を放置する反応なら低い免疫反応として評価すること。

外部イベント（公開情報）:
{event.observable_description}

外部イベントの評価用実態（Agentには非公開）:
- base_threat_level: {event.base_threat_level}
- information_reliability: {event.information_reliability}
- hidden_context: {event.hidden_context}

行動前の観測可能状況:
{world_state_before}

A国:
- 現在認識: {belief_a}
- 行動: {action_a}
- 理由: {reason_a}

B国:
- 現在認識: {belief_b}
- 行動: {action_b}
- 理由: {reason_b}

国際法:
{international_law.context()}

説明文や総合的な善悪評価は返さず、次のJSONオブジェクトだけを返してください:
{{
  "actual_threat_level": 0,
  "perceived_threat_a": 0,
  "perceived_threat_b": 0,
  "immune_response_strength_a": 0,
  "immune_response_strength_b": 0,
  "legal_alignment_a": 0,
  "legal_alignment_b": 0,
  "escalation_pressure": 0,
  "clarification_quality": 0,
  "trust_signal": 50,
  "recovery_capacity": 0
}}
""".strip()

    response = generate_content_with_retry(
        client,
        response_recorder=response_recorder,
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return parse_evaluator_response(response.text)


def _bounded_update(previous: int, target: float, max_delta: int = 15) -> int:
    target_score = clamp_score(target)
    delta = max(-max_delta, min(max_delta, target_score - previous))
    return clamp_score(previous + delta)


def calculate_metrics(evaluation: dict, previous_metrics: Optional[dict] = None) -> dict:
    """Evaluatorの事実寄り成分から、公開指標を決定的に計算する。"""
    actual = clamp_score(evaluation["actual_threat_level"])
    perceived_a = clamp_score(evaluation["perceived_threat_a"])
    perceived_b = clamp_score(evaluation["perceived_threat_b"])
    immune_a = clamp_score(evaluation["immune_response_strength_a"])
    immune_b = clamp_score(evaluation["immune_response_strength_b"])
    legal_a = clamp_score(evaluation["legal_alignment_a"])
    legal_b = clamp_score(evaluation["legal_alignment_b"])

    overreaction_a = max(0, immune_a - actual)
    overreaction_b = max(0, immune_b - actual)
    underreaction_a = max(0, actual - immune_a)
    underreaction_b = max(0, actual - immune_b)
    response_fit_a = clamp_score(100 - abs(immune_a - actual))
    response_fit_b = clamp_score(100 - abs(immune_b - actual))
    response_fit = clamp_score((response_fit_a + response_fit_b) / 2)
    misperception_risk = clamp_score(
        (abs(perceived_a - actual) + abs(perceived_b - actual)) / 2
    )
    legal_alignment = clamp_score((legal_a + legal_b) / 2)
    immune_response_strength = clamp_score((immune_a + immune_b) / 2)
    overreaction = clamp_score((overreaction_a + overreaction_b) / 2)
    underreaction = clamp_score((underreaction_a + underreaction_b) / 2)

    previous_tension = (previous_metrics or {}).get("tension", 45)
    previous_trust = (previous_metrics or {}).get("trust", 50)
    previous_resilience = (previous_metrics or {}).get("resilience", 60)

    tension_target = (
        evaluation["escalation_pressure"] * 0.45
        + max(immune_a, immune_b) * 0.30
        + ((perceived_a + perceived_b) / 2) * 0.25
    )
    trust_target = (
        (100 - misperception_risk) * 0.55
        + evaluation["clarification_quality"] * 0.25
        + evaluation["trust_signal"] * 0.20
    )
    resilience_target = (
        response_fit * 0.40
        + evaluation["recovery_capacity"] * 0.25
        + legal_alignment * 0.20
        + evaluation["clarification_quality"] * 0.15
    )

    tension = _bounded_update(previous_tension, tension_target)
    trust = _bounded_update(previous_trust, trust_target)
    resilience = _bounded_update(previous_resilience, resilience_target)
    homeostasis = clamp_score(
        response_fit * 0.25
        + (100 - misperception_risk) * 0.20
        + trust * 0.15
        + legal_alignment * 0.15
        + resilience * 0.15
        + (100 - tension) * 0.10
    )

    if overreaction > underreaction + 10:
        overall_impact = "実際の脅威水準に比べ、国家の免疫反応が過剰な状態です。"
    elif underreaction > overreaction + 10:
        overall_impact = "実際の脅威水準に比べ、国家の免疫反応が不足している状態です。"
    else:
        overall_impact = "実際の脅威水準と国家の免疫反応は概ね釣り合っています。"

    return {
        "homeostasis": homeostasis,
        "tension": tension,
        "misperception_risk": misperception_risk,
        "trust": trust,
        "resilience": resilience,
        "overall_impact": overall_impact,
        "threat_level": actual,
        "immune_response_strength": immune_response_strength,
        "immune_response_strength_a": immune_a,
        "immune_response_strength_b": immune_b,
        "overreaction": overreaction,
        "overreaction_a": overreaction_a,
        "overreaction_b": overreaction_b,
        "underreaction": underreaction,
        "underreaction_a": underreaction_a,
        "underreaction_b": underreaction_b,
        "response_fit": response_fit,
        "response_fit_a": response_fit_a,
        "response_fit_b": response_fit_b,
        "legal_alignment": legal_alignment,
        "legal_alignment_a": legal_a,
        "legal_alignment_b": legal_b,
    }



def metric_provenance(previous_metrics: Optional[dict], *, live_evaluator: bool) -> dict:
    """Describe the existing calculation; do not alter scores or Agent inputs."""
    previous = previous_metrics or {}
    return {
        "evaluation_source": "model_evaluator_estimates" if live_evaluator else "synthetic_fixture",
        "metric_source": "calculate_metrics(evaluation, previous_metrics)",
        "direct_world_measurement": False,
        "history_dependent_fields": ["tension", "trust", "resilience", "homeostasis"],
        "bounded_update_fields": ["tension", "trust", "resilience"],
        "previous_values_used": {
            "tension": previous.get("tension", 45),
            "trust": previous.get("trust", 50),
            "resilience": previous.get("resilience", 60),
        },
        "previous_values_source": "previous_turn_metrics" if previous_metrics else "implementation_initial_values",
        "bounded_update_max_delta": 15,
        "interpretation": "指標の履歴依存には実装の前値・変化幅制限が含まれる。Agentから創発した履歴依存の証明ではない。",
    }


def evaluate_metrics(
    client: genai.Client,
    event: ExternalEvent,
    world_state_before: str,
    action_a: str,
    reason_a: str,
    belief_a: str,
    action_b: str,
    reason_b: str,
    belief_b: str,
    international_law: InternationalLaw,
    previous_metrics: Optional[dict] = None,
    response_recorder=None,
) -> tuple[dict, dict]:
    evaluation = call_evaluator(
        client=client,
        event=event,
        world_state_before=world_state_before,
        action_a=action_a,
        reason_a=reason_a,
        belief_a=belief_a,
        action_b=action_b,
        reason_b=reason_b,
        belief_b=belief_b,
        international_law=international_law,
        response_recorder=response_recorder,
    )
    return calculate_metrics(evaluation, previous_metrics), evaluation


def mock_decisions(turn: int) -> str:
    scenarios = {
        1: (
            "外交ルートを通じてB国へ軍事演習の事実確認と説明を求める。",
            "不要な誤解を避けながら、相手国の意図を確認するため。",
            "国境付近の警戒監視体制と情報収集を強化する。",
            "脅威を早期に察知しつつ、直接的な軍事衝突を避けるため。",
        ),
        2: (
            "通常の外交ルートでB国へ部隊逸脱の説明を求める。",
            "直接通信路がない条件で事実関係を確認するため。",
            "A国からの照会に対し、軍事演習は侵攻目的ではないと説明する。",
            "不要な緊張を抑え、自国の安全と主権を維持するため。",
        ),
        3: (
            "国境監視を維持しつつ、通常外交ルートで追加情報を照会する。",
            "未確認情報と観測事実を区別するため。",
            "通常外交ルートで航空機情報の共同確認を提案する。",
            "公的確認のない情報だけで対応を決めないため。",
        ),
        4: (
            "通信障害下でも利用できる既存外交経路を確認する。",
            "連絡遅延による判断上の不確実性へ対応するため。",
            "復旧状況を公開し、通常外交による連絡を継続する。",
            "通信障害が意図的な行動と解釈される可能性を抑えるため。",
        ),
        5: (
            "警戒水準を平時レベルへ段階的に戻す。",
            "対話と情報共有によって直近の脅威が低下したため。",
            "情報収集活動を通常レベルへ戻し、外交協議を継続する。",
            "緊張緩和を維持しつつ、必要な監視能力を残すため。",
        ),
        6: (
            "第三国声明を検討しつつ、現在の警戒態勢を維持する。",
            "外部の要求と自国の安全保障上の必要を比較するため。",
            "第三国へ事実関係を説明し、国境監視を継続する。",
            "外交的孤立を避けながら状況を把握するため。",
        ),
        7: (
            "演習終了通知の履行状況を監視する。",
            "通知だけでなく実際の撤収を確認する必要があるため。",
            "部隊の通常配置への移行を公表する。",
            "自国の意図を示しつつ防衛能力を維持するため。",
        ),
        8: (
            "到着した説明を検証し、今後の対応を再評価する。",
            "説明と観測事実の一致度を確認するため。",
            "追加資料を提示し、通常の外交ルートで回答を求める。",
            "残る不一致を整理して国家利益を守るため。",
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


def mock_evaluation(event: ExternalEvent, turn: int) -> dict:
    """APIなしの配線確認専用。研究結果としては使用しない。"""
    actual = clamp_score(event.base_threat_level + (turn % 3 - 1) * 4)
    return {
        "actual_threat_level": actual,
        "perceived_threat_a": clamp_score(actual + 8),
        "perceived_threat_b": clamp_score(actual - 5),
        "immune_response_strength_a": clamp_score(actual + 12),
        "immune_response_strength_b": clamp_score(actual - 8),
        "legal_alignment_a": 75,
        "legal_alignment_b": 78,
        "escalation_pressure": clamp_score(45 + turn * 2),
        "clarification_quality": clamp_score(35 + turn * 4),
        "trust_signal": clamp_score(48 + turn),
        "recovery_capacity": 62,
    }


def split_decisions(response_text: str):
    if "=== B国 ===" not in response_text:
        raise ValueError("B国の回答を分離できませんでした。")

    a_part, b_part = response_text.split("=== B国 ===", 1)

    a_part = a_part.replace("=== A国 ===", "", 1).strip()
    b_part = b_part.strip()

    return a_part, b_part


def _extract_section(decision: str, heading: str, stop_headings: tuple[str, ...]) -> str:
    if not isinstance(decision, str):
        raise ValueError("Agent回答がテキストではありません。判断を補完せず停止します。")
    lines = [
        line.strip().replace("**", "").replace("：", ":")
        for line in decision.splitlines()
    ]

    matches = [i for i, line in enumerate(lines) if line.startswith(heading + ":")]
    if len(matches) != 1:
        raise ValueError(f"Agent回答の「{heading}」が欠落または重複しています。判断を補完せず停止します。")
    i = matches[0]
    first = lines[i].split(":", 1)[1].strip()
    parts = [first] if first else []
    for following in lines[i + 1:]:
        if any(following.startswith(h + ":") for h in stop_headings):
            break
        if following:
            parts.append(following)
    if not parts:
        raise ValueError(f"Agent回答の「{heading}」が空です。判断を補完せず停止します。")
    return " ".join(parts).strip()


def extract_action(decision: str) -> str:
    return _extract_section(
        decision,
        "行動",
        ("現在認識", "懸念", "理由"),
    )


def extract_concern(decision: str) -> str:
    return _extract_section(
        decision,
        "懸念",
        ("現在認識", "行動", "理由"),
    )


def extract_reason(decision: str) -> str:
    return _extract_section(
        decision,
        "理由",
        ("現在認識", "懸念", "行動"),
    )


def extract_belief(decision: str) -> str:
    return _extract_section(
        decision,
        "現在認識",
        ("懸念", "行動", "理由"),
    )


def parse_agent_decision(decision: str) -> dict[str, str]:
    """Read the four requested sections without inventing missing Agent content."""
    return {
        "action": extract_action(decision),
        "reason": extract_reason(decision),
        "concern": extract_concern(decision),
        "belief": extract_belief(decision),
    }


def build_world_state(action_a: str, action_b: str) -> str:
    return (
        f"A国Agentは行動として「{action_a}」を選択した。"
        f"B国Agentは行動として「{action_b}」を選択した。"
        "これはAgentの行動選択の記録であり、実行結果や相手国への到達を確認した記録ではない。"
        "ただし、相手がその行動を選んだ内部的な意図や判断理由は直接観測できない。"
    )


def build_turn_state(previous_world_state: str, event: ExternalEvent) -> str:
    return (
        f"前TURNまでの記録（行動選択と実現結果は別）:\n{previous_world_state}\n\n"
        f"今回の外部イベント:\n{event.observable_description}\n"
        f"情報の公的な信頼度: {int(round(event.information_reliability * 100))}%"
    )


def save_result_exclusive(destination: Path, data: dict) -> None:
    """Publish a complete JSON file only if no result already owns the name."""
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"既存の結果を上書きせず停止します: {destination}")
    fd, staged = tempfile.mkstemp(prefix=".simulation-result-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, destination)
    finally:
        os.unlink(staged)


def main(*, receipt_output=None, receipt_run=1):
    output_file = (f"simulation_result_independent_agents_{EXPERIMENT_CONDITION}.json"
                   if USE_GEMINI else "simulation_result_development.json")
    if os.path.lexists(output_file):
        raise FileExistsError(f"既存の結果を上書きせず停止します: {output_file}")
    client = None
    received_responses = []

    if USE_GEMINI:
        if type(receipt_run) is not int or receipt_run < 1:
            raise ValueError("receipt_run must be a positive integer")
        receipts = ResponseReceipts.for_output(receipt_output or output_file)
        receipts.prepare()
        api_key = getpass("Gemini API Key: ")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def recorder(turn, actor, role):
        def preserve(response, request, attempt):
            identity = {
                "run": receipt_run, "turn": turn, "agent_id": actor, "agent_type": role,
                "model": request["model"], "schema_version": 2, "attempt": attempt,
                "snapshot_id": f"v1-run-{receipt_run}-turn-{turn}",
                "observation_digest": hashlib.sha256(json.dumps(
                    request, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(),
            }
            reference = receipts.record(identity, response)
            received_responses.append({**identity, "response_receipt": reference})
        return preserve

    country_a = Agent(
        name="A国",
        goal="国家の安全、主権、国民の生命、国際的立場を守ること。",
        relationships={
            "B国": "中立",
        },
        leader_profile=CAUTIOUS_DIPLOMAT,
        national_interests=[
            "領土と主権の維持",
            "国民および国境地域の安全",
            "防衛能力と国際的信用の維持",
        ],
    )

    country_b = Agent(
        name="B国",
        goal="国家の安全、主権、国民の生命、経済的安定を守ること。",
        relationships={
            "A国": "中立",
        },
        leader_profile=CAUTIOUS_DIPLOMAT,
        national_interests=[
            "領土と主権の維持",
            "国民および国境地域の安全",
            "経済活動と外交関係の安定",
        ],
    )

    world_state = (
        "現在は平時です。"
        "A国とB国の間には軍事衝突はなく、外交関係は中立です。"
        "両国は相手国の現在の内部意図を知りません。"
    )

    results = []
    previous_metrics = None

    print(
        "\n実行モード:",
        "Gemini AI" if USE_GEMINI else "開発モード（APIなし）",
    )

    for turn in range(1, TURN_COUNT + 1):
        event = EXTERNAL_EVENTS[turn - 1]
        world_state_before = build_turn_state(world_state, event)

        print("\n====================")
        print(f"TURN {turn}")
        print("====================")

        print("\n=== 世界状況 ===")
        print(world_state_before)

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
                world_state=world_state_before,
                communication_context=communication_context,
                international_law=INTERNATIONAL_LAW,
                response_recorder=recorder(turn, country_a.name, "country"),
            )

            print("\nB国Agentが判断中...")
            decision_b = call_agent(
                client=client,
                agent=country_b,
                world_state=world_state_before,
                communication_context=communication_context,
                international_law=INTERNATIONAL_LAW,
                response_recorder=recorder(turn, country_b.name, "country"),
            )
        else:
            combined_response = mock_decisions(turn)
            decision_a, decision_b = split_decisions(combined_response)

        parsed_a = parse_agent_decision(decision_a)
        parsed_b = parse_agent_decision(decision_b)
        country_a.memory.append(decision_a)
        country_b.memory.append(decision_b)

        action_a, action_b = parsed_a["action"], parsed_b["action"]
        reason_a, reason_b = parsed_a["reason"], parsed_b["reason"]
        concern_a, concern_b = parsed_a["concern"], parsed_b["concern"]
        belief_a, belief_b = parsed_a["belief"], parsed_b["belief"]
        print("\n=== A国の判断 ===")
        print(decision_a)
    
        print("\n=== B国の判断 ===")
        print(decision_b)
    
        world_state = build_world_state(action_a, action_b)

        if USE_GEMINI:
            metrics, evaluation = evaluate_metrics(
                client=client,
                event=event,
                world_state_before=world_state_before,
                action_a=action_a,
                reason_a=reason_a,
                belief_a=belief_a,
                action_b=action_b,
                reason_b=reason_b,
                belief_b=belief_b,
                international_law=INTERNATIONAL_LAW,
                previous_metrics=previous_metrics,
                response_recorder=recorder(turn, "evaluator", "evaluator"),
            )
        else:
            evaluation = mock_evaluation(event, turn)
            metrics = calculate_metrics(evaluation, previous_metrics)

        provenance = metric_provenance(previous_metrics, live_evaluator=USE_GEMINI)
        previous_metrics = metrics
    
        results.append(
            {
                "turn": turn,
                "world_state_before": world_state_before,
                "world_state": world_state,
                "external_event": event.public_dict(),
                "evaluation": evaluation,
                "metrics": metrics,
                "metric_provenance": provenance,
                "country_a": {
                    "action": action_a,
                    "action_status": "declared",
                    "realization_status": "unverified",
                    "reason": reason_a,
                    "concern": concern_a,
                    "belief": belief_a,
                },
                "country_b": {
                    "action": action_b,
                    "action_status": "declared",
                    "realization_status": "unverified",
                    "reason": reason_b,
                    "concern": concern_b,
                    "belief": belief_b,
                },
            }
        )


    output_data = {
        "schema_version": 2,
        "mode": "gemini" if USE_GEMINI else "development",
        "experiment_condition": EXPERIMENT_CONDITION,
        "turn_count": TURN_COUNT,
        "model": MODEL_NAME,
        "international_law": INTERNATIONAL_LAW.to_dict(),
        "agents": {
            "country_a": {
                "name": country_a.name,
                "leader_profile": country_a.leader_profile.to_dict(),
                "national_interests": country_a.national_interests,
            },
            "country_b": {
                "name": country_b.name,
                "leader_profile": country_b.leader_profile.to_dict(),
                "national_interests": country_b.national_interests,
            },
        },
        "results": results,
    }

    if USE_GEMINI:
        output_data["response_receipts"] = received_responses
    save_result_exclusive(Path(output_file), output_data)

    print("\n====================")
    print("SIMULATION END")
    print("====================")

    print(f"\n{output_file} を保存しました。")


if __name__ == "__main__":
    main()
