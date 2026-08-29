import json
import matplotlib.pyplot as plt

with open("contrast_scores.json", encoding="utf-8") as f:
    data = json.load(f)

metrics = [
    ("misperception", "Misperception Risk", "Misperception Risk / 誤認リスク"),
    ("trust", "Trust", "Trust / 信頼度"),
    ("tension", "Tension Level", "Tension Level / 緊張レベル"),
    ("resilience", "Resilience", "Resilience / 回復力"),
]

hotline = data["conditions"]["hotline"]
no_hotline = data["conditions"]["no_hotline"]
turns = [x["turn"] for x in hotline]

for key, en_label, panel_title in metrics:
    h = [x[key] for x in hotline]
    n = [x[key] for x in no_hotline]

    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#07111f")
    ax.set_facecolor("#0b1526")

    ax.plot(
        turns, h,
        marker="o", linewidth=2.4, markersize=6,
        color="#67e8ff", label="HOTLINE"
    )
    ax.plot(
        turns, n,
        marker="o", linewidth=2.4, markersize=6,
        color="#ff79dc", label="NO HOTLINE"
    )

    ax.set_xticks(turns)
    ax.set_ylim(0, 5)
    ax.set_xlabel("TURN", color="#d9f6ff")
    ax.set_ylabel(en_label, color="#d9f6ff")
    ax.set_title(f"{en_label}: HOTLINE vs NO HOTLINE", color="#f5fbff", pad=12)

    ax.tick_params(colors="#cfefff")
    for spine in ax.spines.values():
        spine.set_color("#2a4d66")

    ax.grid(True, alpha=0.18, color="#8ed8ff")
    leg = ax.legend(frameon=True)
    leg.get_frame().set_facecolor("#0f1c2e")
    leg.get_frame().set_edgecolor("#2a4d66")
    for t in leg.get_texts():
        t.set_color("#e8fbff")

    plt.tight_layout()
    plt.savefig(f"contrast_{key}.png", dpi=180, facecolor=fig.get_facecolor())
    plt.close()

print("ダーク版の比較グラフ4枚を再生成しました")
