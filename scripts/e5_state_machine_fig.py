"""E5/#148: the overnight batch pipeline's transition function, drawn.

Nodes and edges came from ytk.batch while it existed; the pipeline retired in
#197 P2, so STATES is frozen here as the historical record the figure drew.

    uv run --with matplotlib python scripts/e5_state_machine_fig.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_field_audits import figure, footer, save, stamp
from plot_assets import BLUE, CYAN, GOLD, MARGIN, MUTED, RED, TEXT

# ytk.batch was removed in #197 P2; the machine as it stood:
STATES = ("captured", "submitted", "enriched", "filed", "skipped")


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    plt.style.use("dark_background")

    fig, top = figure(
        15,
        7.2,
        6,
        "e5 · state machine",
        "The overnight pipeline's transition function — advance as far as possible, never lose an item",
        "one ledger entry per url  ·  every transition idempotent and crash-safe  ·  "
        "a failure is a recorded state plus a reason, retried the next night",
    )
    ax = fig.add_axes([MARGIN, 0.16, 1 - 2 * MARGIN, top - 0.20])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 34)
    ax.axis("off")

    # main chain: captured -> submitted -> enriched -> filed; skipped hangs below
    chain = [s for s in STATES if s != "skipped"]
    xs = {name: 6 + i * 26 for i, name in enumerate(chain)}
    y_main = 22
    box_w, box_h = 14, 6

    def node(x: float, y: float, label: str, color: str) -> None:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                box_w,
                box_h,
                boxstyle="round,pad=0.6,rounding_size=1.4",
                facecolor="#000000",
                edgecolor=color,
                linewidth=1.6,
            )
        )
        ax.text(
            x + box_w / 2,
            y + box_h / 2,
            label,
            color=TEXT,
            fontsize=12.5,
            ha="center",
            va="center",
        )

    def arrow(p0, p1, color, style="-", rad=0.0, lw=1.5):
        ax.add_patch(
            FancyArrowPatch(
                p0,
                p1,
                arrowstyle="-|>",
                mutation_scale=15,
                linestyle=style,
                color=color,
                linewidth=lw,
                connectionstyle=f"arc3,rad={rad}",
            )
        )

    terminal = {"filed": GOLD, "skipped": MUTED}
    for name in chain:
        node(xs[name], y_main, name, terminal.get(name, BLUE))
    node(xs["captured"], 6, "skipped", MUTED)

    # forward transitions (the happy path), labeled with what advances them
    forward = [
        (
            "captured",
            "submitted",
            "stage_submit\nfetch meta + transcript,\none batches.create per night",
        ),
        ("submitted", "enriched", "stage_poll\nbatch ended -> result\nby custom_id, JSON stored"),
        (
            "enriched",
            "filed",
            "stage_file\nguards: chroma · memory · idle\nthen write_note + upsert",
        ),
    ]
    for a, b, label in forward:
        arrow((xs[a] + box_w + 0.8, y_main + box_h / 2), (xs[b] - 0.8, y_main + box_h / 2), BLUE)
        ax.text(
            (xs[a] + xs[b] + box_w) / 2,
            y_main + box_h + 1.2,
            label,
            color=CYAN,
            fontsize=8.6,
            ha="center",
            va="bottom",
        )

    # failure edges: recorded reason, attempts += 1, retried next night
    arrow(
        (xs["submitted"] + box_w / 2, y_main - 0.8),
        (xs["captured"] + box_w / 2 + 3, y_main - 0.8),
        RED,
        style="--",
        rad=0.35,
    )
    ax.text(
        xs["submitted"] + box_w / 2,
        y_main - 8.6,
        "errored / expired result\nerror kept, attempts += 1",
        color=RED,
        fontsize=8.4,
        ha="center",
    )
    arrow(
        (xs["captured"] - 2.0, y_main + 1.2),
        (xs["captured"] - 2.0, y_main + box_h - 1.2),
        RED,
        style="--",
        rad=-1.6,
    )
    ax.text(
        xs["captured"] - 3.4,
        y_main + box_h / 2,
        "fetch failed:\nstays captured,\nreason recorded",
        color=RED,
        fontsize=8.0,
        ha="right",
        va="center",
    )
    arrow(
        (xs["enriched"] + box_w / 2, y_main - 0.8),
        (xs["enriched"] + box_w / 2, y_main - 4.6),
        RED,
        style="--",
    )
    ax.text(
        xs["enriched"] + box_w / 2,
        y_main - 8.6,
        "filer failed: stays enriched,\nothers keep filing\n(guard failure skips the whole run)",
        color=RED,
        fontsize=8.4,
        ha="center",
    )
    # terminal filter rejection
    arrow(
        (xs["captured"] + box_w / 2 - 3, y_main - 0.8),
        (xs["captured"] + box_w / 2 - 3, 6 + box_h + 0.8),
        MUTED,
        style="--",
    )
    ax.text(
        xs["captured"] - 1.5,
        (y_main + 6) / 2 + 1.5,
        "FilteredOut:\nterminal,\nnever retried",
        color=MUTED,
        fontsize=8.4,
        ha="right",
        va="center",
    )

    footer(
        fig,
        f"{stamp()}  ·  ytk/batch.py — an item is never deleted before reaching filed; the "
        f"sidecar ledger (~/.ytk/batch_ledger.json) keeps pipeline state out of the pending "
        f"queue #163 is reworking. Enrichment runs on the existing claude-haiku-4-5 prompt via "
        f"the Message Batches API (50% price); the file stage reuses the synchronous path's "
        f"write_note + upsert, so the retrieval gate is untouched by construction.",
    )
    save(fig, "e5-state-machine.png")


if __name__ == "__main__":
    main()
