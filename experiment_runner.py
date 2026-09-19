#!/usr/bin/env python3
"""HOMEOSTASIS SECURITY の低コスト比較実験ランナー。

集計・dry-run は Gemini API を呼ばない。実験は ``run`` サブコマンドに加え、
確認入力が通った場合だけ開始する。
"""

from __future__ import annotations

import argparse
import csv
from getpass import getpass
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
MAX_RUNS = 2
REACTION_CONFIG_FILE = "reaction_axis_config.json"
METRICS = (
    "actual_threat_level",
    "perceived_threat_a",
    "perceived_threat_b",
    "perceived_minus_actual_a",
    "perceived_minus_actual_b",
    "escalation_pressure",
    "recovery_capacity",
)

CONDITIONS: dict[str, dict[str, Any]] = {
    "A": {
        "label": "慎重外交型×慎重外交型 / 国際法ON / Hotline ON",
        "profile": "cautious",
        "law": True,
        "hotline": True,
        "filename": "result_cautious_law_hotline_run{run}.json",
        "legacy": r"simulation_result_cautious_cautious_law_hotline_run(\d+)(?:_previous_20260830T105924)?\.json",
    },
    "B": {
        "label": "強硬型×強硬型 / 国際法ON / Hotline ON",
        "profile": "hardliner",
        "law": True,
        "hotline": True,
        "filename": "result_hardliner_law_hotline_run{run}.json",
    },
    "C": {
        "label": "慎重外交型×慎重外交型 / 国際法OFF / Hotline ON",
        "profile": "cautious",
        "law": False,
        "hotline": True,
        "filename": "result_cautious_no_law_hotline_run{run}.json",
    },
    "D": {
        "label": "慎重外交型×慎重外交型 / 国際法ON / Hotline OFF",
        "profile": "cautious",
        "law": True,
        "hotline": False,
        "filename": "result_cautious_law_no_hotline_run{run}.json",
        "legacy": r"simulation_result_cautious_cautious_law_no_hotline_run(\d+)\.json",
    },
    "E": {
        "label": "強硬型×強硬型 / 国際法OFF / Hotline OFF",
        "profile": "hardliner",
        "law": False,
        "hotline": False,
        "filename": "result_hardliner_no_law_no_hotline_run{run}.json",
    },
    "F": {
        "label": "強硬型×強硬型 / 国際法OFF / Hotline ON",
        "profile": "hardliner",
        "law": False,
        "hotline": True,
        "filename": "result_hardliner_no_law_hotline_run{run}.json",
    },
    "G": {
        "label": "強硬型×強硬型 / 国際法ON / Hotline OFF",
        "profile": "hardliner",
        "law": True,
        "hotline": False,
        "filename": "result_hardliner_law_no_hotline_run{run}.json",
    },
    "H": {
        "label": "慎重外交型×慎重外交型 / 国際法OFF / Hotline OFF",
        "profile_a": "cautious", "profile_b": "cautious",
        "law": False, "hotline": False,
        "filename": "result_cautious_no_law_no_hotline_run{run}.json",
    },
    "I": {
        "label": "強硬型×慎重外交型 / 国際法ON / Hotline ON",
        "profile_a": "hardliner", "profile_b": "cautious",
        "law": True, "hotline": True,
        "filename": "result_hardliner_cautious_law_hotline_run{run}.json",
    },
    "J": {
        "label": "強硬型×慎重外交型 / 国際法ON / Hotline OFF",
        "profile_a": "hardliner", "profile_b": "cautious",
        "law": True, "hotline": False,
        "filename": "result_hardliner_cautious_law_no_hotline_run{run}.json",
    },
    "K": {
        "label": "強硬型×慎重外交型 / 国際法OFF / Hotline ON",
        "profile_a": "hardliner", "profile_b": "cautious",
        "law": False, "hotline": True,
        "filename": "result_hardliner_cautious_no_law_hotline_run{run}.json",
    },
    "L": {
        "label": "強硬型×慎重外交型 / 国際法OFF / Hotline OFF",
        "profile_a": "hardliner", "profile_b": "cautious",
        "law": False, "hotline": False,
        "filename": "result_hardliner_cautious_no_law_no_hotline_run{run}.json",
    },
    "M": {
        "label": "慎重外交型×強硬型 / 国際法ON / Hotline ON",
        "profile_a": "cautious", "profile_b": "hardliner",
        "law": True, "hotline": True,
        "filename": "result_cautious_hardliner_law_hotline_run{run}.json",
    },
    "N": {
        "label": "慎重外交型×強硬型 / 国際法ON / Hotline OFF",
        "profile_a": "cautious", "profile_b": "hardliner",
        "law": True, "hotline": False,
        "filename": "result_cautious_hardliner_law_no_hotline_run{run}.json",
    },
    "O": {
        "label": "慎重外交型×強硬型 / 国際法OFF / Hotline ON",
        "profile_a": "cautious", "profile_b": "hardliner",
        "law": False, "hotline": True,
        "filename": "result_cautious_hardliner_no_law_hotline_run{run}.json",
    },
    "P": {
        "label": "慎重外交型×強硬型 / 国際法OFF / Hotline OFF",
        "profile_a": "cautious", "profile_b": "hardliner",
        "law": False, "hotline": False,
        "filename": "result_cautious_hardliner_no_law_no_hotline_run{run}.json",
    },
}


def condition_for_file(path: Path) -> tuple[str, int] | None:
    """管理対象のファイル名から条件とrun番号を返す。バックアップは除外する。"""
    for code, spec in CONDITIONS.items():
        canonical = re.escape(spec["filename"]).replace(r"\{run\}", r"(\d+)")
        match = re.fullmatch(canonical, path.name)
        if not match and spec.get("legacy"):
            match = re.fullmatch(spec["legacy"], path.name)
        if match:
            return code, int(match.group(1))
    return None


def discover_runs(directory: Path) -> dict[str, list[tuple[int, Path]]]:
    found: dict[str, list[tuple[int, Path]]] = {code: [] for code in CONDITIONS}
    for path in directory.glob("*.json"):
        identified = condition_for_file(path)
        if identified:
            code, run_number = identified
            found[code].append((run_number, path))
    for items in found.values():
        items.sort(key=lambda item: (item[0], item[1].name))
    return found


def output_path(directory: Path, condition: str, run_number: int) -> Path:
    return directory / CONDITIONS[condition]["filename"].format(run=run_number)


def next_run_number(existing: Iterable[tuple[int, Path]]) -> int:
    used = {number for number, _ in existing}
    number = 1
    while number in used:
        number += 1
    return number


def print_plan(directory: Path, condition: str | None = None) -> None:
    found = discover_runs(directory)
    print("DRY-RUN: Gemini APIは呼びません。ファイルも変更しません。")
    codes = (condition,) if condition else CONDITIONS.keys()
    for code in codes:
        items = found[code]
        names = ", ".join(path.name for _, path in items) or "なし"
        status = "上限到達" if len(items) >= MAX_RUNS else "実行可能"
        print(f"{code}: {CONDITIONS[code]['label']}")
        print(f"  検出済み: {len(items)}run ({names})")
        print(f"  状態: {status}")
        if len(items) < MAX_RUNS:
            number = next_run_number(items)
            print(f"  次の出力: {output_path(directory, code, number).name}")


def validate_result(data: dict[str, Any], condition: str) -> None:
    spec = CONDITIONS[condition]
    if data.get("mode") != "gemini":
        raise ValueError("modeがgeminiではありません。")
    if data.get("turn_count") != 8 or len(data.get("results", [])) != 8:
        raise ValueError("8TURNの完全な結果ではありません。")
    if bool(data.get("international_law", {}).get("enabled")) != spec["law"]:
        raise ValueError("国際法条件が一致しません。")
    for country, profile_key in (
        ("country_a", spec.get("profile_a", spec.get("profile"))),
        ("country_b", spec.get("profile_b", spec.get("profile"))),
    ):
        expected_profile = "慎重外交型" if profile_key == "cautious" else "安全保障強硬型"
        actual = data.get("agents", {}).get(country, {}).get("leader_profile", {}).get("name")
        if actual != expected_profile:
            raise ValueError(f"{country}のLeaderProfileが条件と一致しません。")
    expected_communication = "hotline" if spec["hotline"] else "no_hotline"
    if data.get("experiment_condition") != expected_communication:
        raise ValueError("Hotline条件が一致しません。")


def run_experiment(args: argparse.Namespace) -> None:
    directory = args.output_dir.resolve()
    existing = discover_runs(directory)[args.condition]
    if len(existing) >= MAX_RUNS and not args.allow_over_limit:
        raise SystemExit(
            f"条件{args.condition}は既に{len(existing)}runあります。"
            "2run上限のため停止しました。超過実行には --allow-over-limit が必要です。"
        )
    run_number = next_run_number(existing)
    destination = output_path(directory, args.condition, run_number)
    if destination.exists():
        raise SystemExit(f"出力先が存在するため停止しました: {destination.name}")

    print("警告: この操作はGemini APIを呼びます。")
    print("1runは8TURNで、通常24回（2 Agent + 1 Evaluator × 8）のAPI呼び出しです。")
    print(f"条件: {args.condition} - {CONDITIONS[args.condition]['label']}")
    print(f"seed: {args.seed}（記録し、対応可能な生成設定にも渡します）")
    print(f"保存先: {destination.name}")
    if args.yes:
        confirmed = "YES"
    else:
        confirmed = input("実行する場合だけ YES と入力してください: ").strip()
    if confirmed != "YES":
        raise SystemExit("キャンセルしました。Gemini APIは呼んでいません。")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = getpass("Gemini API Key（画面には表示されません）: ").strip()
    if not api_key:
        raise SystemExit("APIキーがないため停止しました。Gemini APIは呼んでいません。")

    # APIをimportするのは、明示確認を終えた後だけ。
    import simulation

    spec = CONDITIONS[args.condition]
    original = {
        "cwd": Path.cwd(),
        "profile": simulation.SECURITY_HARDLINER,
        "law": simulation.INTERNATIONAL_LAW,
        "condition": simulation.EXPERIMENT_CONDITION,
        "turn_count": simulation.TURN_COUNT,
        "use_gemini": simulation.USE_GEMINI,
        "getpass": simulation.getpass,
        "generator": simulation.generate_content_with_retry,
        "agent": simulation.Agent,
    }
    profile_for = lambda key: simulation.CAUTIOUS_DIPLOMAT if key == "cautious" else original["profile"]
    profile_a = profile_for(spec.get("profile_a", spec.get("profile")))
    profile_b = profile_for(spec.get("profile_b", spec.get("profile")))
    law = simulation.InternationalLaw(
        enabled=spec["law"], principles=original["law"].principles
    )
    base_generator = original["generator"]

    def seeded_generator(client: Any, **kwargs: Any) -> Any:
        config = dict(kwargs.get("config") or {})
        config["seed"] = args.seed
        kwargs["config"] = config
        return base_generator(client, **kwargs)

    def configured_agent(*agent_args: Any, **agent_kwargs: Any) -> Any:
        name = agent_kwargs.get("name", agent_args[0] if agent_args else None)
        agent_kwargs["leader_profile"] = profile_a if name == "A国" else profile_b
        return original["agent"](*agent_args, **agent_kwargs)

    try:
        with tempfile.TemporaryDirectory(prefix=".experiment-", dir=directory) as temp_name:
            temp_dir = Path(temp_name)
            os.chdir(temp_dir)
            random.seed(args.seed)
            simulation.SECURITY_HARDLINER = profile_a
            simulation.Agent = configured_agent
            simulation.INTERNATIONAL_LAW = law
            simulation.EXPERIMENT_CONDITION = "hotline" if spec["hotline"] else "no_hotline"
            simulation.TURN_COUNT = 8
            simulation.USE_GEMINI = True
            simulation.getpass = lambda _prompt: api_key
            simulation.generate_content_with_retry = seeded_generator
            # Keep response evidence outside the disposable staging directory,
            # including when generation, validation or publication fails.
            simulation.main(receipt_output=destination, receipt_run=run_number)
            generated = temp_dir / f"simulation_result_independent_agents_{simulation.EXPERIMENT_CONDITION}.json"
            data = json.loads(generated.read_text(encoding="utf-8"))
            validate_result(data, args.condition)
            data["experiment_metadata"] = {
                "condition_code": args.condition,
                "condition_label": spec["label"],
                "run_number": run_number,
                "seed": args.seed,
                "seed_note": "Python乱数とGemini生成設定へ指定。API側の完全再現を保証するものではありません。",
            }
            staged = temp_dir / "validated-result.json"
            staged.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.link(staged, destination)
    finally:
        os.chdir(original["cwd"])
        simulation.SECURITY_HARDLINER = original["profile"]
        simulation.INTERNATIONAL_LAW = original["law"]
        simulation.EXPERIMENT_CONDITION = original["condition"]
        simulation.TURN_COUNT = original["turn_count"]
        simulation.USE_GEMINI = original["use_gemini"]
        simulation.getpass = original["getpass"]
        simulation.generate_content_with_retry = original["generator"]
        simulation.Agent = original["agent"]
    print(f"完了: {destination.name}")


def observations(data: dict[str, Any]) -> list[dict[str, float]]:
    rows = []
    for turn in data.get("results", []):
        evaluation = turn.get("evaluation", {})
        required = (
            "actual_threat_level", "perceived_threat_a", "perceived_threat_b",
            "escalation_pressure", "recovery_capacity",
        )
        if not all(isinstance(evaluation.get(key), (int, float)) for key in required):
            raise ValueError(f"TURN {turn.get('turn')} のevaluationが不完全です。")
        actual = float(evaluation["actual_threat_level"])
        rows.append({
            "actual_threat_level": actual,
            "perceived_threat_a": float(evaluation["perceived_threat_a"]),
            "perceived_threat_b": float(evaluation["perceived_threat_b"]),
            "perceived_minus_actual_a": float(evaluation["perceived_threat_a"]) - actual,
            "perceived_minus_actual_b": float(evaluation["perceived_threat_b"]) - actual,
            "escalation_pressure": float(evaluation["escalation_pressure"]),
            "recovery_capacity": float(evaluation["recovery_capacity"]),
        })
    return rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def population_stddev(values: list[float]) -> float:
    center = mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def load_reaction_config(directory: Path) -> dict[str, Any]:
    path = directory / REACTION_CONFIG_FILE
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"反応評価設定を読み込めません: {path.name}: {error}") from error
    tolerance = config.get("adaptive_tolerance")
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
        raise ValueError("adaptive_toleranceは0〜100の数値で指定してください。")
    if not 0 <= float(tolerance) <= 100:
        raise ValueError("adaptive_toleranceは0〜100の範囲で指定してください。")
    labels = config.get("labels", {})
    if not all(isinstance(labels.get(key), str) for key in ("overreaction", "adaptive", "underreaction")):
        raise ValueError("反応分類のlabelsが不足しています。")
    return config


def classify_reaction(gap: float, tolerance: float) -> str:
    if gap > tolerance:
        return "overreaction"
    if gap < -tolerance:
        return "underreaction"
    return "adaptive"


def reaction_observations(
    data: dict[str, Any], tolerance: float, run_name: str
) -> list[dict[str, Any]]:
    rows = []
    for turn in data.get("results", []):
        evaluation = turn.get("evaluation", {})
        actual = evaluation.get("actual_threat_level")
        if not isinstance(actual, (int, float)):
            raise ValueError(f"TURN {turn.get('turn')} の推定脅威が不正です。")
        for country, suffix in (("country_a", "a"), ("country_b", "b")):
            response = evaluation.get(f"immune_response_strength_{suffix}")
            if not isinstance(response, (int, float)):
                raise ValueError(f"TURN {turn.get('turn')} の{country}反応強度が不正です。")
            gap = float(response) - float(actual)
            rows.append({
                "run": run_name,
                "turn": turn.get("turn"),
                "country": country,
                "estimated_threat": float(actual),
                "response_strength": float(response),
                "reaction_gap": gap,
                "adaptive_fit": max(0.0, min(100.0, 100.0 - abs(gap))),
                "classification": classify_reaction(gap, tolerance),
            })
    return rows


def summarize_reactions(
    rows: list[dict[str, Any]], run_groups: list[list[dict[str, Any]]]
) -> dict[str, Any]:
    count = len(rows)
    result: dict[str, Any] = {"observation_count": count}
    for classification in ("overreaction", "adaptive", "underreaction"):
        classified = sum(row["classification"] == classification for row in rows)
        rates = [
            100.0 * sum(row["classification"] == classification for row in group) / len(group)
            for group in run_groups if group
        ]
        result[f"{classification}_count"] = classified
        result[f"{classification}_rate"] = round(100.0 * classified / count, 3) if count else None
        result[f"{classification}_rate_run_stddev"] = (
            round(population_stddev(rates), 3) if len(rates) >= 2 else None
        )
    for metric in ("reaction_gap", "adaptive_fit"):
        values = [float(row[metric]) for row in rows]
        run_means = [mean([float(row[metric]) for row in group]) for group in run_groups if group]
        result[f"mean_{metric}"] = round(mean(values), 3) if values else None
        result[f"{metric}_stddev"] = round(population_stddev(values), 3) if values else None
        result[f"{metric}_run_mean_stddev"] = (
            round(population_stddev(run_means), 3) if len(run_means) >= 2 else None
        )
    return result


def discover_valid_results(directory: Path) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    """内容からA〜Eを判定し、同一resultsを1runとして返す。"""
    found: dict[str, list[tuple[Path, dict[str, Any]]]] = {
        code: [] for code in CONDITIONS
    }
    profiles = {
        "慎重外交型": "cautious",
        "安全保障強硬型": "hardliner",
    }
    mapping = {
        ("cautious", "cautious", True, True): "A",
        ("hardliner", "hardliner", True, True): "B",
        ("cautious", "cautious", False, True): "C",
        ("cautious", "cautious", True, False): "D",
        ("hardliner", "hardliner", False, False): "E",
        ("hardliner", "hardliner", False, True): "F",
        ("hardliner", "hardliner", True, False): "G",
        ("cautious", "cautious", False, False): "H",
        ("hardliner", "cautious", True, True): "I",
        ("hardliner", "cautious", True, False): "J",
        ("hardliner", "cautious", False, True): "K",
        ("hardliner", "cautious", False, False): "L",
        ("cautious", "hardliner", True, True): "M",
        ("cautious", "hardliner", True, False): "N",
        ("cautious", "hardliner", False, True): "O",
        ("cautious", "hardliner", False, False): "P",
    }
    candidates = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names = [
                data.get("agents", {}).get(country, {}).get("leader_profile", {}).get("name")
                for country in ("country_a", "country_b")
            ]
            profile_a, profile_b = (profiles.get(name) for name in names)
            law = data.get("international_law", {}).get("enabled")
            communication = data.get("experiment_condition")
            hotline = True if communication == "hotline" else False if communication == "no_hotline" else None
            code = mapping.get((profile_a, profile_b, law, hotline))
            if not code:
                continue
            validate_result(data, code)
            result_key = json.dumps(
                data["results"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
            explicit_run = condition_for_file(path) is not None or "run" in path.stem
            candidates.append((code, not explicit_run, path.name, path, data, result_key))
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
    seen: set[str] = set()
    for code, _, _, path, data, result_key in sorted(candidates):
        if result_key in seen:
            continue
        seen.add(result_key)
        found[code].append((path, data))
    return found


def aggregate(directory: Path) -> list[dict[str, Any]]:
    found = discover_valid_results(directory)
    reaction_config = load_reaction_config(directory)
    tolerance = float(reaction_config["adaptive_tolerance"])
    summaries = []
    for code, spec in CONDITIONS.items():
        all_rows: list[dict[str, float]] = []
        run_rows: list[list[dict[str, float]]] = []
        reaction_rows: list[dict[str, Any]] = []
        reaction_run_rows: list[list[dict[str, Any]]] = []
        used_files = []
        errors = []
        seeds = []
        for path, data in found[code]:
            try:
                observed = observations(data)
                all_rows.extend(observed)
                run_rows.append(observed)
                reactions = reaction_observations(data, tolerance, path.name)
                reaction_rows.extend(reactions)
                reaction_run_rows.append(reactions)
                used_files.append(path.name)
                seeds.append(data.get("experiment_metadata", {}).get("seed"))
            except ValueError as error:
                errors.append(f"{path.name}: {error}")
        row: dict[str, Any] = {
            "condition": code,
            "label": spec["label"],
            "run_count": len(used_files),
            "observation_count": len(all_rows),
            "files": used_files,
            "seeds": seeds,
            "seed_recorded_count": sum(seed is not None for seed in seeds),
            "seed_missing_count": sum(seed is None for seed in seeds),
            "errors": errors,
        }
        for metric in METRICS:
            values = [item[metric] for item in all_rows]
            run_means = [mean([item[metric] for item in items]) for items in run_rows]
            row[f"{metric}_mean"] = round(mean(values), 3) if values else None
            row[f"{metric}_stddev"] = round(population_stddev(values), 3) if values else None
            row[f"{metric}_run_mean_stddev"] = (
                round(population_stddev(run_means), 3)
                if len(run_means) >= 2
                else None
            )
        country_summaries = {}
        for country in ("country_a", "country_b"):
            country_rows = [item for item in reaction_rows if item["country"] == country]
            country_runs = [
                [item for item in items if item["country"] == country]
                for items in reaction_run_rows
            ]
            country_summaries[country] = summarize_reactions(country_rows, country_runs)
        run_summaries = []
        for items in reaction_run_rows:
            run_summary = summarize_reactions(items, [items])
            run_summary["run"] = items[0]["run"] if items else None
            run_summaries.append(run_summary)
        row["reaction_axis"] = {
            "overall": summarize_reactions(reaction_rows, reaction_run_rows),
            "country_a": country_summaries["country_a"],
            "country_b": country_summaries["country_b"],
            "runs": run_summaries,
            "observations": reaction_rows,
        }
        summaries.append(row)
    return summaries


def write_summary(directory: Path, *, write_html: bool = True) -> None:
    reaction_config = load_reaction_config(directory)
    summaries = aggregate(directory)
    json_path = directory / "summary.json"
    csv_path = directory / "summary.csv"
    html_path = directory / "dashboard_experiments.html"
    json_payload = {
        "method": "内容からA〜Pを判定した全8TURN Gemini結果を使用。同一resultsは重複除外。stddevは全TURNの母標準偏差、run_mean_stddevはrun平均間の母標準偏差",
        "api_used": False,
        "metric_definitions": {
            "actual_threat_level": "推定脅威（Evaluator estimate）。絶対的な真実ではない。",
            "reaction_gap": "Agent反応強度 - 推定脅威",
            "adaptive_fit": "max(0, 100 - abs(reaction_gap))",
        },
        "reaction_axis_config": reaction_config,
        "conditions": summaries,
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = [
        "condition", "label", "run_count", "observation_count",
        "seed_recorded_count", "seed_missing_count", "seeds", "files",
    ]
    fields += [
        f"{metric}_{suffix}"
        for metric in METRICS
        for suffix in ("mean", "stddev", "run_mean_stddev")
    ]
    for scope in ("overall", "country_a", "country_b"):
        fields += [
            f"reaction_{scope}_{name}"
            for name in (
                "overreaction_rate", "adaptive_rate", "underreaction_rate",
                "mean_reaction_gap", "reaction_gap_stddev",
                "reaction_gap_run_mean_stddev", "mean_adaptive_fit",
                "adaptive_fit_stddev", "adaptive_fit_run_mean_stddev",
            )
        ]
    csv_rows = []
    for summary in summaries:
        flattened = dict(summary)
        for scope in ("overall", "country_a", "country_b"):
            for name, value in summary["reaction_axis"][scope].items():
                flattened[f"reaction_{scope}_{name}"] = value
        csv_rows.append(flattened)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)
    if write_html:
        write_dashboard(html_path, summaries, reaction_config)
    print("集計完了（Gemini APIは呼んでいません）:")
    print(f"- {csv_path.name}")
    print(f"- {json_path.name}")
    if write_html:
        print(f"- {html_path.name}")


def write_dashboard(
    path: Path, summaries: list[dict[str, Any]], reaction_config: dict[str, Any]
) -> None:
    embedded = json.dumps(summaries, ensure_ascii=False).replace("</", "<\\/")
    config_embedded = json.dumps(reaction_config, ensure_ascii=False).replace("</", "<\\/")
    html = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HOMEOSTASIS SECURITY 7条件比較実験</title>
<style>
:root{color-scheme:dark;--bg:#07111d;--panel:#101f2f;--panel2:#14293c;--line:#28445f;--text:#e8f2fa;--muted:#9eb2c4;--accent:#67e8f9;--warn:#fbbf24}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#132d43,var(--bg) 55%);color:var(--text);font:15px/1.55 system-ui,sans-serif}
main{max-width:1280px;margin:auto;padding:32px 20px 60px}h1{margin:0;font-size:clamp(24px,4vw,40px)}.note{color:var(--muted);margin:8px 0 24px}.eyebrow{color:var(--accent);letter-spacing:.12em;text-transform:uppercase;font-size:12px}.lead{font-size:18px;max-width:900px}.concept{background:linear-gradient(135deg,#12334a,#102334);border-left:4px solid var(--accent);padding:18px 20px;border-radius:12px;margin:22px 0}.concept strong{color:#a5f3fc}.limitations{border:1px solid #755b20;background:#2b2415;padding:14px 18px;border-radius:12px;margin:18px 0 26px}.limitations summary{cursor:pointer;color:#fde68a;font-weight:700}.limitations ul{columns:2;margin-bottom:0}.definitions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}.definition{background:var(--panel2);border-radius:10px;padding:14px;border-top:4px solid}.definition h3{margin:0 0 5px}.definition p{margin:0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px}.card{background:rgba(16,31,47,.94);border:1px solid var(--line);border-radius:14px;padding:18px;overflow:auto}
h2{font-size:18px;margin:0 0 12px}.chart{min-height:265px}svg{width:100%;height:250px}.axis{stroke:#53718b;stroke-width:1}.bar{opacity:.9}.empty{color:var(--muted);padding:80px 0;text-align:center}.section-title{margin:34px 0 8px}.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);margin:6px 0 12px}.swatch{display:inline-block;width:12px;height:12px;margin-right:5px;border-radius:2px}.wide{grid-column:1/-1}select{background:#0b1927;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:5px 8px}.condition-key{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:7px;font-size:13px;color:var(--muted)}.finding{border-left:3px solid var(--accent)}.finding strong{display:block;color:var(--text);margin-bottom:4px}.contrast-value{font-size:21px;color:var(--accent);font-weight:700}.small{font-size:12px;color:var(--muted)}
table{border-collapse:collapse;width:100%;min-width:900px}th,td{border-bottom:1px solid var(--line);padding:8px;text-align:right}th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--panel)}
</style></head><body><main><div class="eyebrow">HOMEOSTASIS SECURITY / LOCAL ANALYSIS</div><h1>脅威と反応の適合性</h1><p class="lead">A〜Gの条件を比較し、国家の反応がEvaluatorによる推定脅威に対して強すぎるか、釣り合っているか、弱すぎるかを確認します。</p>
<div class="concept"><strong>恒常性の中心概念</strong><br>HOMEOSTASIS SECURITYは「低緊張＝良い」とは評価しません。高い脅威に必要な防衛反応を取ることも適応です。ここでの恒常性とは、<strong>脅威に対する反応の適合</strong>と、緊張後に回復できる能力を意味します。</div>
<details class="limitations" open><summary>研究上の限界（常に確認してください）</summary><ul><li>推定脅威と反応強度はEvaluatorに依存します。</li><li>各条件のrun数はまだ少数です。</li><li>A・D・Eなど古いrunにはseed記録がありません。</li><li>適応範囲±<span id="toleranceText"></span>は初期設定です。</li><li>実世界の国家行動で検証済みではありません。</li></ul></details>
<div class="definitions"><article class="definition" style="border-color:#fb7185"><h3>過剰反応</h3><p>反応強度が推定脅威を許容幅より上回る状態。必要以上の展開や威嚇の可能性を示します。</p></article><article class="definition" style="border-color:#34d399"><h3>適応反応</h3><p>反応強度が推定脅威と概ね釣り合う状態。高脅威への強い防衛も含みます。</p></article><article class="definition" style="border-color:#60a5fa"><h3>過少反応</h3><p>反応強度が推定脅威を許容幅より下回る状態。必要な警戒や防衛の不足を示します。</p></article></div>
<h2 class="section-title">観測された傾向</h2><section class="grid"><article class="card finding"><strong>強硬型の過剰反応傾向</strong>Eでは過剰反応が87.5%でした。B・F・Gでも慎重外交型より高い割合が観測されています。</article><article class="card finding"><strong>国際法とHotlineによる改善方向</strong>強硬型の対照比較では、制度がある側でエスカレーション圧の低下と回復力の上昇が観測されました。</article><article class="card finding"><strong>慎重外交型の過少反応</strong>Dでは過少反応が16.7%あり、慎重さが常に適応的とは限らない可能性が見えています。</article></section>
<h2 class="section-title">条件と制度効果</h2><div class="condition-key" id="conditionKey"></div><section class="grid" id="institutionContrasts" style="margin-top:14px"></section>
<h2 class="section-title">反応分類と適合度</h2><p class="note">「推定脅威（Evaluator estimate）」は絶対的な真実ではありません。reaction_gap＝反応強度−推定脅威、adaptive_fit＝100−|reaction_gap|（最低0）です。</p>
<div class="legend"><span><i class="swatch" style="background:#fb7185"></i>過剰反応</span><span><i class="swatch" style="background:#34d399"></i>適応反応</span><span><i class="swatch" style="background:#60a5fa"></i>過少反応</span></div>
<section class="grid"><article class="card wide"><h2>条件別 反応分類割合</h2><div id="reactionStack"></div></article><article class="card"><h2>reaction_gap分布</h2><div id="gapDistribution"></div></article><article class="card"><h2>run別 adaptive_fit</h2><div id="runFit"></div></article><article class="card wide"><h2>TURNごとの推定脅威と反応強度</h2><label>条件 <select id="turnCondition"></select></label><div id="turnSeries"></div></article><article class="card wide"><h2>反応適合性 集計</h2><div id="reactionTable"></div></article></section>
<h2 class="section-title">既存の安全保障指標</h2><section id="charts" class="grid"></section><section class="card" style="margin-top:18px"><h2>平均・TURN標準偏差・run間標準偏差</h2><div id="table"></div></section>
<script>const rows=__DATA__;const reactionConfig=__CONFIG__;
const metrics=[['actual_threat_level','推定脅威（Evaluator estimate）'],['perceived_threat_a','A国認知脅威'],['perceived_threat_b','B国認知脅威'],['perceived_minus_actual_a','A国 認知−推定'],['perceived_minus_actual_b','B国 認知−推定'],['escalation_pressure','エスカレーション圧力'],['recovery_capacity','回復能力']];
const colors=['#60a5fa','#f97316','#34d399','#c084fc','#facc15','#fb7185','#22d3ee'];
document.querySelector('#toleranceText').textContent=reactionConfig.adaptive_tolerance;
document.querySelector('#conditionKey').innerHTML=rows.map(r=>`<span><strong style="color:${colors['ABCDEFG'.indexOf(r.condition)]}">${r.condition}</strong> ${r.label}（${r.run_count}run・seed ${r.seed_recorded_count}/${r.run_count}）</span>`).join('');
const byCode=Object.fromEntries(rows.map(r=>[r.condition,r]));
const contrasts=[
  ['国際法ON：Hotline ON','B','F','強硬型でB（法ON）とF（法OFF）を比較'],
  ['国際法ON：Hotline OFF','G','E','強硬型でG（法ON）とE（法OFF）を比較'],
  ['Hotline ON：国際法ON','B','G','強硬型でB（Hotline ON）とG（OFF）を比較'],
  ['Hotline ON：国際法OFF','F','E','強硬型でF（Hotline ON）とE（OFF）を比較']
];
document.querySelector('#institutionContrasts').innerHTML=contrasts.map(([title,on,off,desc])=>{const a=byCode[on],b=byCode[off],esc=a.escalation_pressure_mean-b.escalation_pressure_mean,rec=a.recovery_capacity_mean-b.recovery_capacity_mean,fit=a.reaction_axis.overall.mean_adaptive_fit-b.reaction_axis.overall.mean_adaptive_fit;return `<article class="card"><h2>${title}</h2><div class="small">${desc}</div><p><span class="contrast-value">${esc.toFixed(1)}</span> エスカレーション圧差<br><span class="contrast-value">${rec>=0?'+':''}${rec.toFixed(1)}</span> 回復力差<br><span class="contrast-value">${fit>=0?'+':''}${fit.toFixed(1)}</span> adaptive_fit差</p><div class="small">差は制度あり側−なし側。負の圧力差・正の回復力差が改善方向。観測された傾向であり、因果効果の確定値ではありません。</div></article>`}).join('');
function chart(key,title){const available=rows.filter(r=>r[key+'_mean']!==null);let body='<div class="empty">データなし</div>';if(available.length){const vals=available.map(r=>r[key+'_mean']);const min=Math.min(0,...vals),max=Math.max(1,...vals);const span=max-min;body='<svg viewBox="0 0 520 340" role="img" aria-label="'+title+'">'+available.map((r,i)=>{const w=420* Math.abs(r[key+'_mean'])/Math.max(Math.abs(min),Math.abs(max));const y=18+i*44;return `<text x="5" y="${y+19}" fill="#e8f2fa">${r.condition}</text><rect class="bar" x="42" y="${y}" width="${w}" height="25" rx="4" fill="${colors['ABCDEFG'.indexOf(r.condition)]}"/><text x="${Math.min(480,48+w)}" y="${y+18}" fill="#e8f2fa">${r[key+'_mean'].toFixed(1)}</text>`}).join('')+'</svg>'}return `<article class="card chart"><h2>${title}</h2>${body}</article>`}
document.querySelector('#charts').innerHTML=metrics.map(m=>chart(m[0],m[1])).join('');
const fmt=v=>v===null?'—':Number(v).toFixed(2);document.querySelector('#table').innerHTML='<table><thead><tr><th>条件</th><th>run</th><th>seed記録</th>'+metrics.map(m=>`<th>${m[1]}<br>平均 / σTURN / σrun</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>`<tr><td>${r.condition}</td><td>${r.run_count}</td><td>${r.seed_recorded_count}/${r.run_count}</td>${metrics.map(m=>`<td>${fmt(r[m[0]+'_mean'])} / ${fmt(r[m[0]+'_stddev'])} / ${fmt(r[m[0]+'_run_mean_stddev'])}</td>`).join('')}</tr>`).join('')+'</tbody></table>';
const reactionColors={overreaction:'#fb7185',adaptive:'#34d399',underreaction:'#60a5fa'};
const reactionNames=reactionConfig.labels;
function reactionStack(){const keys=['overreaction','adaptive','underreaction'];return '<svg viewBox="0 0 700 340" aria-label="過剰・適応・過少反応割合">'+rows.map((r,i)=>{const o=r.reaction_axis.overall;let x=80;const y=18+i*44;const seg=keys.map(k=>{const v=o[k+'_rate']||0,w=v*5.5,start=x;x+=w;return `<rect x="${start}" y="${y}" width="${w}" height="27" fill="${reactionColors[k]}"><title>${r.condition} ${reactionNames[k]} ${v.toFixed(1)}%</title></rect>${w>52?`<text x="${start+w/2}" y="${y+19}" text-anchor="middle" fill="#07111d" font-size="12">${reactionNames[k]} ${v.toFixed(0)}%</text>`:''}`}).join('');return `<text x="12" y="${y+19}" fill="#e8f2fa">${r.condition}</text>${seg}`}).join('')+'</svg>'}document.querySelector('#reactionStack').innerHTML=reactionStack();
function gapPlot(){const all=rows.flatMap(r=>r.reaction_axis.observations.map(o=>({...o,condition:r.condition})));const scale=v=>300+Math.max(-100,Math.min(100,v))*2.5;return `<svg viewBox="0 0 600 350" aria-label="reaction gap分布"><rect x="${scale(-reactionConfig.adaptive_tolerance)}" y="10" width="${scale(reactionConfig.adaptive_tolerance)-scale(-reactionConfig.adaptive_tolerance)}" height="310" fill="#34d399" opacity=".12"/><line x1="300" y1="10" x2="300" y2="325" stroke="#e8f2fa"/><text x="305" y="338" fill="#9eb2c4">0（反応強度＝推定脅威）</text>${all.map((o,i)=>{const y=25+'ABCDEFG'.indexOf(o.condition)*43+(i%2)*8;return `<circle cx="${scale(o.reaction_gap)}" cy="${y}" r="3" fill="${reactionColors[o.classification]}" opacity=".65"><title>${o.condition} ${o.run} TURN${o.turn} ${o.country}: ${reactionNames[o.classification]} gap ${o.reaction_gap}</title></circle>`}).join('')}${rows.map((r,i)=>`<text x="8" y="${31+i*43}" fill="#e8f2fa">${r.condition}</text>`).join('')}</svg>`}document.querySelector('#gapDistribution').innerHTML=gapPlot();
function runFit(){const all=rows.flatMap(r=>r.reaction_axis.runs.map((x,i)=>({condition:r.condition,index:i+1,value:x.mean_adaptive_fit})));return '<svg viewBox="0 0 600 350" aria-label="run別adaptive fit">'+all.map((x,i)=>{const y=12+i*20,w=x.value*4.7;return `<text x="4" y="${y+13}" fill="#e8f2fa" font-size="11">${x.condition}-${x.index}</text><rect x="45" y="${y}" width="${w}" height="14" fill="${colors['ABCDEFG'.indexOf(x.condition)]}"/><text x="${Math.min(565,50+w)}" y="${y+12}" fill="#e8f2fa" font-size="11">${x.value.toFixed(1)}</text>`}).join('')+'</svg>'}document.querySelector('#runFit').innerHTML=runFit();
const selector=document.querySelector('#turnCondition');selector.innerHTML=rows.map(r=>`<option>${r.condition}</option>`).join('');selector.value='E';function renderTurns(){const r=rows.find(x=>x.condition===selector.value),obs=r.reaction_axis.observations;const points=[];for(let t=1;t<=8;t++){const a=obs.filter(x=>x.turn===t&&x.country==='country_a'),b=obs.filter(x=>x.turn===t&&x.country==='country_b');const avg=(xs,k)=>xs.reduce((s,x)=>s+x[k],0)/xs.length;points.push({turn:t,threat:avg(a,'estimated_threat'),a:avg(a,'response_strength'),b:avg(b,'response_strength')})}const x=t=>45+(t-1)*70,y=v=>235-v*2.05,path=k=>points.map((p,i)=>(i?'L':'M')+x(p.turn)+','+y(p[k])).join(' ');document.querySelector('#turnSeries').innerHTML=`<svg viewBox="0 0 580 270" aria-label="推定脅威と反応強度のTURN推移"><line x1="40" y1="235" x2="550" y2="235" stroke="#53718b"/>${points.map(p=>`<text x="${x(p.turn)}" y="255" text-anchor="middle" fill="#9eb2c4">${p.turn}</text>`).join('')}<path d="${path('threat')}" fill="none" stroke="#facc15" stroke-width="3"/><path d="${path('a')}" fill="none" stroke="#fb7185" stroke-width="2"/><path d="${path('b')}" fill="none" stroke="#60a5fa" stroke-width="2"/><text x="45" y="15" fill="#facc15">推定脅威</text><text x="145" y="15" fill="#fb7185">A国反応</text><text x="235" y="15" fill="#60a5fa">B国反応</text></svg>`}selector.addEventListener('change',renderTurns);renderTurns();
document.querySelector('#reactionTable').innerHTML='<table><thead><tr><th>条件・範囲</th><th>過剰反応</th><th>適応反応</th><th>過少反応</th><th>平均gap</th><th>平均adaptive_fit</th><th>gap σrun</th><th>fit σrun</th></tr></thead><tbody>'+rows.flatMap(r=>['overall','country_a','country_b'].map(scope=>{const o=r.reaction_axis[scope],name=scope==='overall'?'全体':scope==='country_a'?'A国':'B国';return `<tr><td>${r.condition} ${name}</td><td>${fmt(o.overreaction_rate)}% 過剰</td><td>${fmt(o.adaptive_rate)}% 適応</td><td>${fmt(o.underreaction_rate)}% 過少</td><td>${fmt(o.mean_reaction_gap)}</td><td>${fmt(o.mean_adaptive_fit)}</td><td>${fmt(o.reaction_gap_run_mean_stddev)}</td><td>${fmt(o.adaptive_fit_run_mean_stddev)}</td></tr>`})).join('')+'</tbody></table>';
</script></main></body></html>""".replace("__DATA__", embedded).replace("__CONFIG__", config_embedded)
    path.write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="7条件の手動実験・集計（デフォルトはAPIなしdry-run）")
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command")
    dry = sub.add_parser("dry-run", help="APIなしで実行予定と既存runを確認")
    dry.add_argument("--condition", choices=CONDITIONS)
    run = sub.add_parser("run", help="確認後に1runだけGemini API実験を実行")
    run.add_argument("--condition", choices=CONDITIONS, required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--allow-over-limit", action="store_true")
    run.add_argument("--yes", action="store_true", help="対話確認を省略（APIを呼ぶため慎重に使用）")
    sub.add_parser("aggregate", help="APIなしでsummaryと比較HTMLを生成")
    sub.add_parser("aggregate-summary", help="APIなしでsummary.csv/jsonだけを生成")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.command in (None, "dry-run"):
        print_plan(args.output_dir.resolve(), getattr(args, "condition", None))
    elif args.command == "run":
        run_experiment(args)
    elif args.command == "aggregate":
        write_summary(args.output_dir.resolve())
    elif args.command == "aggregate-summary":
        write_summary(args.output_dir.resolve(), write_html=False)


if __name__ == "__main__":
    main()
