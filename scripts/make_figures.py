#!/usr/bin/env python3
"""
Standalone figure generation for the MSR 2027 manuscript.

    python make_figures_standalone.py [ROOT] [--outdir DIR]

ROOT defaults to /content/drive/MyDrive/peltzman on Colab, ./peltzman otherwise.
Reads from ROOT/results, writes PDF + PNG + 400 dpi JPG to ROOT/figures.

Inputs (each figure is skipped with a message if its input is absent):
    results/results_multiplicity.csv              -> fig1_coefficients
    results/event_study.csv                       -> fig2_event_studies
    results/nb8_armb3_path_o5_self_merge_rate.csv -> fig3_placebo_path

Design notes
    Identity never depends on hue alone. Significance is carried by marker
    fill as well as colour; the placebo and the real treatment differ in line
    style and marker shape as well as hue. Both figures therefore survive
    greyscale printing and colour-vision deficiency.
    Single axis throughout, recessive grid and spines, thin marks.
"""
import os, sys, argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# --- palette -----------------------------------------------------------
INK   = "#1A1A1A"   # text and axis ink
ACC   = "#0F5F58"   # the treatment / significant
ALT   = "#B45309"   # the placebo / contrast series
NULL  = "#8A8A8A"   # not significant
GRID  = "#D9D9D9"
BAND  = "#E8E8E8"
MDE_SD = 0.0251     # detectable effect for the primary outcome, in SD

# Set these before %run if you need non-default paths in a notebook.
ROOT_OVERRIDE   = None
OUTDIR_OVERRIDE = None

# On Colab, zip the figures and hand them to the browser when the run ends.
DOWNLOAD = True

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.edgecolor": INK, "axes.linewidth": 0.6,
    "xtick.color": INK, "ytick.color": INK, "text.color": INK,
    "axes.labelcolor": INK, "legend.frameon": False,
    "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})

LABELS = {
    "o3_review_coverage": "Review coverage",
    "o1_reviewers_per_pr": "Reviewers per PR",
    "o2b_reviews_per_pr": "Reviews per PR",
    "o2_comments_per_pr": "Comments per PR",
    "o3b_changes_req_rate": "Changes-requested rate",
    "o4_churn_per_merged": "Change size",
    "o5_self_merge_rate": "Self-merge rate",
    "o6_direct_push_share": "Direct-push share",
}
FACETS = [
    ("BREADTH",   ["o3_review_coverage", "o1_reviewers_per_pr", "o2b_reviews_per_pr"]),
    ("DEPTH",     ["o2_comments_per_pr", "o3b_changes_req_rate", "o4_churn_per_merged"]),
    ("AUTHORITY", ["o5_self_merge_rate", "o6_direct_push_share"]),
]


def tidy(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color=GRID, lw=0.4, zorder=0)
    ax.set_axisbelow(True)


def save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    for ext, kw in (("pdf", {}), ("png", {"dpi": 300}), ("jpg", {"dpi": 400})):
        fig.savefig(os.path.join(outdir, f"{name}.{ext}"), **kw)
    plt.close(fig)
    print(f"  wrote {name}.pdf / .png / .jpg")


# --- Figure 1: coefficient plot ----------------------------------------
def fig_coefficients(res_dir, outdir):
    p = os.path.join(res_dir, "results_multiplicity.csv")
    if not os.path.exists(p):
        print("  skip fig1: missing results_multiplicity.csv"); return
    d = pd.read_csv(p)
    d = d[d["treatment"].astype(str).str.startswith("A_")].set_index("outcome")

    rows, ylab, group_at = [], [], []
    y = 0
    for facet, outs in FACETS:
        group_at.append((y + 0.6, facet))
        for o in outs:
            if o not in d.index: continue
            r = d.loc[o]
            sd = float(r["outcome_sd"])
            rows.append((y, float(r["att_in_sd"]), float(r["cs_se"]) / sd,
                         float(r["p_bh"]) < 0.05))
            ylab.append(LABELS.get(o, o)); y -= 1
        y -= 0.5

    fig, ax = plt.subplots(figsize=(3.45, 3.1))
    ax.axvspan(-MDE_SD, MDE_SD, color=BAND, zorder=0)
    ax.axvline(0, color=INK, lw=0.6, zorder=1)

    for yy, att, se, sig in rows:
        col = ACC if sig else NULL
        ax.errorbar(att, yy, xerr=1.96 * se, fmt="none",
                    ecolor=col, elinewidth=1.1, capsize=0, zorder=2)
        ax.plot(att, yy, marker="o" if sig else "o", ms=4.5,
                mfc=col if sig else "white", mec=col, mew=1.1, zorder=3,
                linestyle="none")

    ax.set_yticks([r[0] for r in rows]); ax.set_yticklabels(ylab)
    for yy, name in group_at:
        ax.text(ax.get_xlim()[0], yy, name, fontsize=6.5, style="italic",
                color=INK, va="center", ha="left")
    ax.set_xlabel("ATT (outcome standard deviations)")
    tidy(ax); ax.grid(axis="y", visible=False)

    handles = [
        Line2D([], [], marker="o", ms=4.5, mfc=ACC, mec=ACC, ls="-",
               color=ACC, lw=1.1, label="survives BH correction"),
        Line2D([], [], marker="o", ms=4.5, mfc="white", mec=NULL, ls="-",
               color=NULL, lw=1.1, label="null"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.30),
              ncol=2, handletextpad=0.4, columnspacing=1.2)
    ax.text(0.5, 1.02, "detectable effect", transform=ax.transAxes,
            fontsize=6.5, color="#6B6B6B", ha="center")
    save(fig, outdir, "fig1_coefficients")


# --- Figure 2: event studies -------------------------------------------
def fig_event_studies(res_dir, outdir):
    p = os.path.join(res_dir, "event_study.csv")
    if not os.path.exists(p):
        print("  skip fig2: missing event_study.csv"); return
    d = pd.read_csv(p)
    panels = [("o3_review_coverage", "Review coverage"),
              ("o5_self_merge_rate", "Self-merge rate"),
              ("o1_reviewers_per_pr", "Reviewers per PR")]
    panels = [(k, t) for k, t in panels if f"{k}_att" in d.columns]
    if not panels:
        print("  skip fig2: no expected columns"); return

    fig, axes = plt.subplots(1, len(panels), figsize=(7.1, 2.0), sharex=True)
    if len(panels) == 1: axes = [axes]
    for ax, (key, title) in zip(axes, panels):
        att = d[f"{key}_att"].values; se = d[f"{key}_se"].values
        t = d["event_time"].values
        ax.axhline(0, color=INK, lw=0.6, zorder=1)
        ax.axvline(0, color=NULL, lw=0.6, ls=(0, (3, 3)), zorder=1)
        ax.fill_between(t, att - 1.96 * se, att + 1.96 * se,
                        color=ACC, alpha=0.16, lw=0, zorder=2)
        ax.plot(t, att, color=ACC, lw=1.3, zorder=3)
        ax.set_title(title, pad=4)
        ax.set_xticks([-12, 0, 12, 24])
        ax.grid(axis="y", color=GRID, lw=0.4); ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("ATT")
    fig.supxlabel("months since adoption", fontsize=8, y=0.02)
    save(fig, outdir, "fig2_event_studies")


# --- Figure 3: placebo against the real treatment ----------------------
def fig_placebo(res_dir, outdir):
    p = os.path.join(res_dir, "nb8_armb3_path_o5_self_merge_rate.csv")
    if not os.path.exists(p):
        print("  skip fig3: missing nb8_armb3_path_o5_self_merge_rate.csv"); return
    d = pd.read_csv(p).sort_values("event_time")
    t = d["event_time"].values

    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    ax.axhline(0, color=INK, lw=0.6, zorder=1)
    ax.axvline(0, color=NULL, lw=0.6, ls=(0, (3, 3)), zorder=1)

    for col_a, col_s, colour, style, marker, lab in (
        ("att_real", "se_real", ACC, "-", "o", "first gating check"),
        ("att_placebo", "se_placebo", ALT, (0, (4, 2)), "s", "non-gating placebo"),
    ):
        if col_a not in d.columns: continue
        a, s = d[col_a].values, d[col_s].values
        ax.fill_between(t, a - 1.96 * s, a + 1.96 * s,
                        color=colour, alpha=0.13, lw=0, zorder=2)
        ax.plot(t, a, color=colour, lw=1.3, ls=style, zorder=3, label=lab)
        step = max(1, len(t) // 10)
        ax.plot(t[::step], a[::step], linestyle="none", marker=marker, ms=3.4,
                mfc="white", mec=colour, mew=1.0, zorder=4)

    ax.set_xticks([-12, 0, 12, 24])
    ax.set_xlabel("months since adoption"); ax.set_ylabel("ATT")
    ax.grid(axis="y", color=GRID, lw=0.4); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", handlelength=2.4)
    save(fig, outdir, "fig3_placebo_path")


def main():
    # Mount Drive if we are on Colab and it is not mounted yet.
    if not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive", force_remount=False)
        except Exception:
            pass

    for cand in ("/content/drive/MyDrive/peltzman",
                 os.path.abspath("./peltzman"),
                 os.path.abspath(".")):
        if os.path.isdir(os.path.join(cand, "results")):
            default_root = cand
            break
    else:
        default_root = "/content/drive/MyDrive/peltzman"
    # Inside a notebook, sys.argv belongs to the kernel, not to us.
    in_notebook = False
    try:
        in_notebook = get_ipython() is not None          # noqa: F821
    except NameError:
        in_notebook = False

    if in_notebook:
        root, out = ROOT_OVERRIDE or default_root, OUTDIR_OVERRIDE
    else:
        ap = argparse.ArgumentParser()
        ap.add_argument("root", nargs="?", default=default_root)
        ap.add_argument("--outdir", default=None)
        a, _unknown = ap.parse_known_args()
        root, out = a.root, a.outdir

    res_dir = os.path.join(root, "results")
    outdir = out or os.path.join(root, "figures")
    print(f"reading {res_dir}\nwriting {outdir}")
    if not os.path.isdir(res_dir):
        print(f"no results directory at {res_dir}")
        print("Set ROOT_OVERRIDE at the top of this file to the folder that "
              "contains results/, then re-run.")
        return

    fig_coefficients(res_dir, outdir)
    fig_event_studies(res_dir, outdir)
    fig_placebo(res_dir, outdir)

    made = sorted(f for f in os.listdir(outdir)) if os.path.isdir(outdir) else []
    print(f"\n{len(made)} files in {outdir}")
    for f in made:
        print("   ", f)

    if DOWNLOAD and in_notebook and made:
        import shutil
        zip_base = "/content/msr2027_figures"
        shutil.make_archive(zip_base, "zip", outdir)
        zip_path = zip_base + ".zip"
        print(f"\nzipped to {zip_path} "
              f"({os.path.getsize(zip_path)/1e6:.2f} MB)")
        try:
            from google.colab import files
            files.download(zip_path)
            print("download started; check your browser")
        except Exception as e:
            print("automatic download unavailable:", e)
            print("Open the Files pane in Colab and download", zip_path,
                  "by hand, or copy it into Drive with:")
            print("   !cp", zip_path, "/content/drive/MyDrive/")
    print("done")


if __name__ == "__main__":
    main()
