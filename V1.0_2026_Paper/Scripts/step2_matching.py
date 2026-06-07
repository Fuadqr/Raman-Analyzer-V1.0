from __future__ import annotations

import os
import re
import sys
import argparse
import textwrap

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

from scipy.signal import find_peaks
from scipy.interpolate import interp1d
from scipy.stats import pearsonr

try:
    from tqdm import tqdm
    _TQDM_AVAILABLE = True
except ImportError:
    tqdm = None
    _TQDM_AVAILABLE = False


UNKNOWN_FOLDER = r"UNKNOWN_PARQUET_FOLDER_HERE"
KNOWN_ROOT     = r"REFERENCE_LIBRARY_ROOT_HERE"
OUTPUT_EXCEL   = r"match_report.xlsx"

# PLOTTING 
# True  = save the same 3-panel best-match PNG plots as the single-spectrum script.
#         Plots are automatically sorted into Over_Threshold and Below_Threshold folders.
# False = Excel report only; no plot files are written.
PLOT_ENABLED = True
OUTPUT_PLOT_DIR = os.path.join(os.path.dirname(OUTPUT_EXCEL), "best_match_plots")
OVER_THRESHOLD_FOLDER = "Over_Threshold"
BELOW_THRESHOLD_FOLDER = "Below_Threshold"

TQDM_ENABLED = True


def _progress(iterable, desc=None, total=None, unit="it", enabled=True):
    if enabled and _TQDM_AVAILABLE:
        return tqdm(
            iterable,
            desc=desc,
            total=total,
            unit=unit,
            file=sys.stdout,
            dynamic_ncols=True,
            leave=True,
            ascii=True,
            mininterval=0.2,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )
    return iterable


#Analysis window (user-selected: 500-3500)
RANGE_MIN = 500
RANGE_MAX = 3500

#Scoring (engine values) 
THRESHOLD       = 70
PEAK_TOLERANCE  = 10.0
NUM_TOP_PEAKS   = 7
PEAK_WEIGHT     = 0.40
PEARSON_WEIGHT  = 0.60

#Peak detection (engine values) 
PEAK_PROMINENCE        = 0.05
PEAK_MIN_HEIGHT        = 0.05
MIN_PEAK_SEPARATION_CM = 20.0

#Shared correlation grid (engine values) 
SHARED_GRID_SPACING_CM = 1.0
SHARED_GRID_MIN_POINTS = 200
SHARED_GRID_MAX_POINTS = 4000

#Confidence ladder (engine values) 
STRONG_MARGIN             = 10.0
CLOSE_TWIN_MARGIN         = 10.0
STRONG_CUTOFF_CAP         = 95.0
GAP_MIN                   = 10.0
CHEMISTRY_OVERRIDE_CUTOFF = 90.0
BIG_GAP_OVERRIDE_CUTOFF   = 20.0

# Optional exclude range, e.g. [(0, 0)] disables. Use [(lo, hi)] to drop peaks.
EXCLUDE_RANGES = None

# Emit extra sheets (Summary / Class_Long / File_Long) in the workbook.
DETAILED_OUTPUT = False


TIER_A_AGGREGATE = "Tier_A_all"
TIER_B_AGGREGATE = "Tier_B_all"
TIER_C_FOLDER    = "Tier_C"
LEGACY_TIER1_FOLDER = "Tier1_Strong"
LEGACY_TIER2_FOLDER = "Tier2_Moderate"
LEGACY_TIER3_FOLDER = "Tier3_Singletons"
LEGACY_TIER4_FOLDER = "Tier4_Excluded"
HIGH_CONF_NAME = "High_Confidence"
LOW_CONF_NAME  = "Low_Confidence"


rcParams["font.family"]    = "serif"
rcParams["font.serif"]     = ["Times New Roman", "DejaVu Serif"]
rcParams["font.size"]      = 16
rcParams["axes.linewidth"] = 1.1
rcParams["axes.labelsize"] = 18
rcParams["axes.titlesize"] = 18
rcParams["xtick.labelsize"] = 15
rcParams["ytick.labelsize"] = 15
rcParams["xtick.direction"] = "in"
rcParams["ytick.direction"] = "in"
rcParams["xtick.major.size"] = 6
rcParams["ytick.major.size"] = 6
rcParams["xtick.major.width"] = 1.1
rcParams["ytick.major.width"] = 1.1
rcParams["legend.frameon"] = False
rcParams["legend.fontsize"] = 14

FAMILY_DISPLAY_FOR_PLOT = {
    "PLASTIC":    "POLYMER",
    "NONPLASTIC": "NONPOLYMER",
    "UNKNOWN":    "UNKNOWN",
}


def _display_family_for_plot(f):
    if f is None:
        return "UNKNOWN"
    return FAMILY_DISPLAY_FOR_PLOT.get(str(f), str(f))


_TIER_AB_PATTERN = re.compile(r"^Tier_([AB])\.(\d+)$")


def _classify_tier_folder(folder_name):
    if folder_name == TIER_C_FOLDER:
        return ("C", "C")
    m = _TIER_AB_PATTERN.match(folder_name)
    if m:
        return (m.group(1), f"{m.group(1)}.{m.group(2)}")
    return None


def _display_material_family(family):
    raw = "" if family is None else str(family)
    n = raw.upper().replace("-", "").replace("_", "").replace(" ", "")
    if n == "PLASTIC":
        return "Polymer"
    if n == "NONPLASTIC":
        return "Non-polymers"
    return raw


def _family_from_library_folder(folder_name):
    raw = "" if folder_name is None else str(folder_name)
    n = raw.upper().replace("-", "").replace("_", "").replace(" ", "")
    if n in ("POLYMER", "POLYMERS", "PLASTIC", "PLASTICS"):
        return "PLASTIC"
    if n in ("NONPOLYMER", "NONPOLYMERS", "NONPLASTIC", "NONPLASTICS"):
        return "NONPLASTIC"
    return None


def discover_known_files(known_root):
    records = []
    if not os.path.isdir(known_root):
        raise FileNotFoundError(f"Known root not found: {known_root}")

    legacy_v61_map = {LEGACY_TIER1_FOLDER: "A", LEGACY_TIER2_FOLDER: "B",
                      LEGACY_TIER3_FOLDER: "C"}
    legacy_hl_map = {HIGH_CONF_NAME: "A", LOW_CONF_NAME: "C"}

    for top_level in sorted(os.listdir(known_root)):
        top_dir = os.path.join(known_root, top_level)
        if not os.path.isdir(top_dir):
            continue
        for class_name in sorted(os.listdir(top_dir)):
            class_dir = os.path.join(top_dir, class_name)
            if not os.path.isdir(class_dir):
                continue
            folder_family = _family_from_library_folder(top_level)

            new_abc_dirs = []
            has_aggregate = False
            for child in sorted(os.listdir(class_dir)):
                child_path = os.path.join(class_dir, child)
                if not os.path.isdir(child_path):
                    continue
                if child in (TIER_A_AGGREGATE, TIER_B_AGGREGATE):
                    has_aggregate = True
                    continue
                classified = _classify_tier_folder(child)
                if classified is not None:
                    bt, sub = classified
                    new_abc_dirs.append((bt, sub, child_path))

            legacy_v61_dirs = {
                label: os.path.join(class_dir, name)
                for name, label in legacy_v61_map.items()
                if os.path.isdir(os.path.join(class_dir, name))
            }
            legacy_hl_dirs = {
                label: os.path.join(class_dir, name)
                for name, label in legacy_hl_map.items()
                if os.path.isdir(os.path.join(class_dir, name))
            }
            has_tier4 = os.path.isdir(os.path.join(class_dir, LEGACY_TIER4_FOLDER))

            use_new = bool(new_abc_dirs) or has_aggregate
            use_v61 = (not use_new) and bool(legacy_v61_dirs)
            use_hl  = (not use_new) and (not use_v61) and bool(legacy_hl_dirs)

            is_plastic = use_new or use_v61 or use_hl or has_tier4
            material_family = folder_family or ("PLASTIC" if is_plastic else "NONPLASTIC")

            def _emit(fp, f, tier, subgroup):
                stem = f.replace("_bs+sm.parquet", "").replace(".parquet", "")
                fid = f"{material_family}__{class_name}__{subgroup}__{stem}"
                records.append({
                    "file_id": fid, "material_family": material_family,
                    "class_label": class_name, "tier": tier,
                    "tier_subgroup": subgroup, "top_level": top_level,
                    "file_name": f, "file_stem": stem, "file_path": fp,
                })

            if use_new:
                for bt, sub, tier_dir in new_abc_dirs:
                    for rroot, _, files in os.walk(tier_dir):
                        for f in files:
                            if f.endswith(".parquet"):
                                _emit(os.path.join(rroot, f), f, bt, sub)
            elif use_v61 or use_hl:
                src = legacy_v61_dirs if use_v61 else legacy_hl_dirs
                for tier_label, tier_dir in src.items():
                    for rroot, _, files in os.walk(tier_dir):
                        for f in files:
                            if f.endswith(".parquet"):
                                _emit(os.path.join(rroot, f), f, tier_label, tier_label)
            elif not is_plastic:
                # Untiered class folder (tier=None signals UNTIERED branch)
                for rroot, _, files in os.walk(class_dir):
                    for f in files:
                        if f.endswith(".parquet"):
                            stem = f.replace("_bs+sm.parquet", "").replace(".parquet", "")
                            records.append({
                                "file_id": f"{material_family}__{class_name}__UNTIERED__{stem}",
                                "material_family": material_family,
                                "class_label": class_name, "tier": None,
                                "tier_subgroup": None, "top_level": top_level,
                                "file_name": f, "file_stem": stem,
                                "file_path": os.path.join(rroot, f),
                            })

    fam_order = {"PLASTIC": 0, "NONPLASTIC": 1}
    tier_order = {"A": 0, "B": 1, "C": 2}

    # Fallback (B): one-level layout — known_root/<class>/*.parquet
    if not records:
        for class_name in sorted(os.listdir(known_root)):
            class_dir = os.path.join(known_root, class_name)
            if not os.path.isdir(class_dir):
                continue
            direct = sorted(f for f in os.listdir(class_dir)
                            if f.endswith(".parquet")
                            and os.path.isfile(os.path.join(class_dir, f)))
            for f in direct:
                stem = f.replace("_bs+sm.parquet", "").replace(".parquet", "")
                records.append({
                    "file_id": f"NONPLASTIC__{class_name}__UNTIERED__{stem}",
                    "material_family": "NONPLASTIC", "class_label": class_name,
                    "tier": None, "tier_subgroup": None, "top_level": "",
                    "file_name": f, "file_stem": stem,
                    "file_path": os.path.join(class_dir, f),
                })

    if not records:
        flat = sorted(f for f in os.listdir(known_root)
                      if f.endswith(".parquet")
                      and os.path.isfile(os.path.join(known_root, f)))
        if flat:
            class_name = os.path.basename(os.path.normpath(known_root)) or "Reference"
            for f in flat:
                stem = f.replace("_bs+sm.parquet", "").replace(".parquet", "")
                records.append({
                    "file_id": f"FLAT__{class_name}__UNTIERED__{stem}",
                    "material_family": "NONPLASTIC", "class_label": class_name,
                    "tier": None, "tier_subgroup": None, "top_level": "",
                    "file_name": f, "file_stem": stem,
                    "file_path": os.path.join(known_root, f),
                })

    return sorted(records, key=lambda x: (
        fam_order.get(x["material_family"], 99),
        x["class_label"],
        tier_order.get(x["tier"], 98) if x["tier"] is not None else 98,
        x["tier_subgroup"] if x["tier_subgroup"] is not None else "",
        x["file_name"],
    ))


def discover_unknown_files(unknown_root):
    records = []
    for rroot, _, files in os.walk(unknown_root):
        for f in files:
            if not f.endswith(".parquet"):
                continue
            stem = f.replace("_bs+sm.parquet", "").replace(".parquet", "")
            records.append({"file_id": stem, "file_name": f,
                            "file_stem": stem,
                            "file_path": os.path.join(rroot, f)})
    return sorted(records, key=lambda x: x["file_name"])


def compute_grid_points(range_min, range_max):
    span = float(range_max) - float(range_min)
    if span <= 0:
        raise ValueError("range_max must be > range_min")
    n = int(round(span / float(SHARED_GRID_SPACING_CM)))
    return max(SHARED_GRID_MIN_POINTS, min(SHARED_GRID_MAX_POINTS, n))


def build_shared_grid(range_min, range_max):
    n = compute_grid_points(range_min, range_max)
    return np.linspace(range_min, np.nextafter(range_max, range_min), n)


def interpolate_to_grid(subset_df, grid):
    if subset_df is None or len(subset_df) < 2:
        return None
    try:
        f = interp1d(subset_df["Wave"].values, subset_df["Normalized"].values,
                     kind="linear", bounds_error=False, fill_value=np.nan)
        return f(grid)
    except Exception:
        return None


def read_snr_from_parquet(df):
    if "SNR" not in df.columns or len(df["SNR"]) == 0:
        return float("nan")
    try:
        v = float(df["SNR"].iloc[0])
    except (TypeError, ValueError):
        return float("nan")
    return v if np.isfinite(v) else float("nan")


def select_representative_peaks(positions, intensities, num_peaks, min_sep_cm):
    if len(positions) == 0:
        return np.array([]), np.array([])
    order = np.argsort(intensities)[::-1]
    sel_p, sel_i = [], []
    for idx in order:
        p = float(positions[idx])
        if all(abs(p - sp) >= min_sep_cm for sp in sel_p):
            sel_p.append(p)
            sel_i.append(float(intensities[idx]))
        if len(sel_p) >= num_peaks:
            break
    sp = np.array(sel_p, dtype=float)
    si = np.array(sel_i, dtype=float)
    o = np.argsort(sp)
    return sp[o], si[o]


def find_top_peaks(df, range_min, range_max, num_peaks, exclude_ranges, grid):
    snr = read_snr_from_parquet(df)

    subset = df[(df["Wave"] >= range_min) & (df["Wave"] <= range_max)].copy()
    if len(subset) < 2:
        return None, None, np.array([]), np.array([]), 0, None, snr

    s_min, s_max = subset["Smoothed"].min(), subset["Smoothed"].max()
    subset["Normalized"] = ((subset["Smoothed"] - s_min) / (s_max - s_min)
                            if s_max != s_min else 0.0)

    interp_vals = interpolate_to_grid(subset, grid) if grid is not None else None

    # peak range == corr range here (engine passes the same min/max for both)
    sub_p = subset[(subset["Wave"] >= range_min) & (subset["Wave"] <= range_max)].copy()
    if len(sub_p) < 2:
        return subset, None, np.array([]), np.array([]), 0, interp_vals, snr

    waves = sub_p["Wave"].values
    norms = sub_p["Normalized"].values
    avg_spacing = (waves[-1] - waves[0]) / (len(waves) - 1) if len(waves) > 1 else 1.0
    distance = max(5, int(round(MIN_PEAK_SEPARATION_CM / avg_spacing)))

    peaks, _ = find_peaks(norms, distance=distance,
                          prominence=PEAK_PROMINENCE, height=PEAK_MIN_HEIGHT)
    if len(peaks) == 0:
        return subset, None, np.array([]), np.array([]), 0, interp_vals, snr

    pos = waves[peaks]
    ints = norms[peaks]
    if exclude_ranges:
        for r_min, r_max in exclude_ranges:
            keep = (pos < r_min) | (pos > r_max)
            pos, ints = pos[keep], ints[keep]
    if len(pos) == 0:
        return subset, None, np.array([]), np.array([]), 0, interp_vals, snr

    pos, ints = select_representative_peaks(pos, ints, num_peaks, MIN_PEAK_SEPARATION_CM)
    return subset, None, pos, ints, len(pos), interp_vals, snr


def interp_safe(result, G):
    iv = result[5] if result else None
    if iv is None:
        return np.zeros(G, dtype=float)
    arr = np.asarray(iv, dtype=float)
    arr[np.isnan(arr)] = 0.0
    return arr


def result_snr(result):
    if result is None or len(result) < 7:
        return float("nan")
    try:
        v = float(result[6])
    except (TypeError, ValueError):
        return float("nan")
    return v if np.isfinite(v) else float("nan")


def pearson_matrix(U_mat, K_mat):
    U_c = U_mat - U_mat.mean(axis=1, keepdims=True)
    K_c = K_mat - K_mat.mean(axis=1, keepdims=True)
    U_n = np.linalg.norm(U_c, axis=1, keepdims=True)
    K_n = np.linalg.norm(K_c, axis=1, keepdims=True)
    U_n[U_n == 0] = 1.0
    K_n[K_n == 0] = 1.0
    return np.clip((U_c / U_n) @ (K_c / K_n).T, 0.0, 1.0)


def assess_confidence(best_score, gap, best_tier, threshold,
                      second_score, second_class,
                      chemistry_override_cutoff, big_gap_override_cutoff):
    strong_cutoff = min(threshold + STRONG_MARGIN, STRONG_CUTOFF_CAP)
    close_twin_cutoff = min(threshold + CLOSE_TWIN_MARGIN, STRONG_CUTOFF_CAP - 5)

    if best_tier is None:
        has_second_u = second_score is not None and second_class is not None
        if best_score < threshold:
            return {"label": "REJECTED",
                    "note": (f"untiered reference; score {best_score:.2f}% is below "
                             f"the {threshold:.0f}% threshold"),
                    "flags": ["UNTIERED_REF"], "score_band": "REJECTED",
                    "gap_quality": "N/A", "reference_support": "UNTIERED",
                    "strong_signals_count": 0,
                    "near_twin_class": None, "near_twin_score": None}
        parts = ["untiered reference; only similarity score evaluated",
                 f"score {best_score:.2f}% (>= {threshold:.0f}% threshold)"]
        if has_second_u:
            parts.append(f"2nd-best class {second_class} at {second_score:.2f}% "
                         f"(gap {gap:.2f}%)")
        else:
            parts.append("no competing 2nd class")
        parts.append("verdict UNTIERED_MATCH (no tier-based confidence)")
        return {"label": "UNTIERED_MATCH", "note": "; ".join(parts),
                "flags": ["UNTIERED_REF"], "score_band": "N/A",
                "gap_quality": "N/A", "reference_support": "UNTIERED",
                "strong_signals_count": 0,
                "near_twin_class": None, "near_twin_score": None}

    if best_score < threshold:
        is_multi = best_tier in ("A", "B", "Tier1", "Tier2", "High")
        return {"label": "REJECTED",
                "note": f"best-class score {best_score:.2f}% is below the "
                        f"{threshold:.0f}% threshold",
                "flags": [], "score_band": "REJECTED", "gap_quality": "N/A",
                "reference_support": "MULTI_SPECTRUM" if is_multi else "SINGLETON",
                "strong_signals_count": 0,
                "near_twin_class": None, "near_twin_score": None}

    if best_score >= chemistry_override_cutoff:
        score_band = "CHEMISTRY_CERTAIN"
    elif best_score >= strong_cutoff:
        score_band = "STRONG"
    else:
        score_band = "ACCEPTABLE"

    has_second = second_score is not None and second_class is not None
    if has_second and gap >= big_gap_override_cutoff:
        gap_quality = "BIG_GAP"
    elif has_second and gap >= GAP_MIN:
        gap_quality = "CLEAN_WIN"
    elif has_second and second_score >= close_twin_cutoff:
        gap_quality = "CLOSE_TWIN"
    elif has_second:
        gap_quality = "WEAK_WIN"
    else:
        gap_quality = "NO_SECOND"

    is_multi = best_tier in ("A", "B", "Tier1", "Tier2", "High")
    reference_support = "MULTI_SPECTRUM" if is_multi else "SINGLETON"

    sig_chem = best_score >= chemistry_override_cutoff
    sig_gap = (has_second and gap >= big_gap_override_cutoff) or (not has_second)
    sig_ref = is_multi
    n_strong = int(sig_chem) + int(sig_gap) + int(sig_ref)
    label = "HIGH" if n_strong >= 2 else ("MEDIUM" if n_strong == 1 else "LOW")

    flags = []
    near_twin_class = near_twin_score = None
    if sig_chem:
        flags.append("CHEMISTRY_CERTAIN")
    if has_second and sig_gap:
        flags.append("BIG_GAP")
    if not has_second:
        flags.append("NO_SECOND")
    flags.append("MULTI_SPECTRUM_REF" if is_multi else "SINGLETON_REF")
    if has_second and gap_quality == "CLOSE_TWIN":
        flags.append("CLOSE_TWIN")
        near_twin_class, near_twin_score = second_class, second_score
    elif has_second and gap_quality == "WEAK_WIN":
        flags.append("WEAK_GAP")

    parts = [f"score {best_score:.2f}% "
             f"(1 point if >= {chemistry_override_cutoff:.0f}%, otherwise 0) - {int(sig_chem)}"]
    if not has_second:
        parts.append(f"no competing 2nd class "
                     f"(1 point by default when no 2nd class exists) - {int(sig_gap)}")
    else:
        parts.append(f"gap to 2nd-best class {gap:.2f}% "
                     f"(2nd: {second_class} at {second_score:.2f}%) "
                     f"(1 point if >= {big_gap_override_cutoff:.0f}%, otherwise 0) - {int(sig_gap)}")
    parts.append(f"reference is Tier {best_tier} "
                 f"(1 point if Tier A or Tier B, otherwise 0) - {int(sig_ref)}")
    parts.append(f"total {n_strong}/3 - {label}")

    return {"label": label, "note": "; ".join(parts), "flags": flags,
            "score_band": score_band, "gap_quality": gap_quality,
            "reference_support": reference_support,
            "strong_signals_count": n_strong,
            "near_twin_class": near_twin_class, "near_twin_score": near_twin_score}


def _format_snr(value):
    if value is None:
        return "--"
    try:
        return f"{value:.1f}" if np.isfinite(value) else "--"
    except Exception:
        return "--"


def _safe_plot_filename(name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip()
    return safe or "unknown"


def _annotate_peaks_staggered(ax, positions, intensities, color,
                              max_peaks_to_annotate):
    if len(positions) == 0 or len(positions) > max_peaks_to_annotate:
        return
    order = np.argsort(positions)
    for i, idx in enumerate(order):
        p = positions[idx]
        y = intensities[idx]
        dy, va = (12, "bottom") if i % 2 == 0 else (-14, "top")
        ax.annotate(f"{p:.1f}", xy=(p, y), xytext=(0, dy),
                    textcoords="offset points",
                    ha="center", va=va, fontsize=12,
                    color=color, fontweight="bold", clip_on=True)


def plot_best_match(unknown_result, known_result,
                    unknown_name, best_family, best_class, best_file_name,
                    best_tier, similarity_score,
                    peak_tolerance, num_top_peaks,
                    corr_range_min, corr_range_max,
                    peak_weight, pearson_weight,
                    threshold, output_path,
                    confidence_label, confidence_note,
                    second_class, second_family, second_score, gap,
                    ambiguity_flags, near_twin_class, near_twin_score,
                    strong_signals_count, reference_support,
                    unknown_snr, known_snr,
                    exclude_ranges, best_tier_subgroup):

    unknown_subset = unknown_result[0]
    unknown_pos    = unknown_result[2]
    unknown_int    = unknown_result[3]
    known_subset   = known_result[0]
    known_pos      = known_result[2]
    known_int      = known_result[3]

    if unknown_subset is None or known_subset is None:
        print("Cannot plot: missing spectrum subset.")
        return

    # Peak / Pearson sub-scores recomputed for the bar panel.
    if len(unknown_pos) > 0 and len(known_pos) > 0:
        d = np.abs(unknown_pos[:, None] - known_pos)
        m = int(np.sum(np.any(d <= peak_tolerance, axis=1)))
        denom = max(len(unknown_pos), len(known_pos), m)
        peak_score = (m / denom) * 100 if denom > 0 else 0.0
    else:
        peak_score = 0.0

    xmin = max(unknown_subset["Wave"].min(), known_subset["Wave"].min())
    xmax = min(unknown_subset["Wave"].max(), known_subset["Wave"].max())
    pearson_score = 0.0
    if xmax > xmin:
        try:
            f1 = interp1d(unknown_subset["Wave"], unknown_subset["Normalized"],
                          kind="linear", bounds_error=True)
            f2 = interp1d(known_subset["Wave"], known_subset["Normalized"],
                          kind="linear", bounds_error=True)
            x_c = np.linspace(xmin, np.nextafter(xmax, xmin), 1000)
            corr, _ = pearsonr(f1(x_c), f2(x_c))
            pearson_score = max(corr, 0.0) * 100
        except Exception:
            pearson_score = 0.0

    is_untiered = (best_tier is None) or (reference_support == "UNTIERED")


    fig = plt.figure(figsize=(16.5, 15.0))
    gs = GridSpec(nrows=3, ncols=1, figure=fig,
                  height_ratios=[4.0, 2.4, 2.6],
                  hspace=0.55,
                  left=0.075, right=0.97, top=0.91, bottom=0.06)
    ax1     = fig.add_subplot(gs[0, 0])
    ax_info = fig.add_subplot(gs[1, 0])
    ax2     = fig.add_subplot(gs[2, 0])


    ax1.plot(unknown_subset["Wave"], unknown_subset["Normalized"],
             label=f"Unknown: {unknown_name}", lw=1.8, alpha=0.85,
             color="#1f4f8b")
    ax1.plot(known_subset["Wave"], known_subset["Normalized"],
             label=f"Best file: {best_file_name}", lw=1.8, alpha=0.85,
             color="#b03030")

    if len(unknown_pos) > 0:
        ax1.scatter(unknown_pos, unknown_int,
                    color="#1f4f8b", marker="x", s=70, lw=2.0,
                    label="Unknown peaks", zorder=5)
    if len(known_pos) > 0:
        ax1.scatter(known_pos, known_int,
                    color="#b03030", marker="o", s=55,
                    edgecolor="white", lw=0.8,
                    label="Known peaks", zorder=5)

    if exclude_ranges:
        for i, (r_min, r_max) in enumerate(exclude_ranges):
            if r_max > r_min:
                ax1.axvspan(r_min, r_max, alpha=0.15, color="grey",
                            label="Excluded region" if i == 0 else None)

    for i, p in enumerate(known_pos):
        lbl = f"±{peak_tolerance} cm$^{{-1}}$ tolerance" if i == 0 else None
        ax1.axvline(p - peak_tolerance, color="#b03030", lw=0.6, ls="--",
                    alpha=0.35, label=lbl)
        ax1.axvline(p + peak_tolerance, color="#b03030", lw=0.6, ls="--",
                    alpha=0.35)

    if is_untiered:
        tier_display = "untiered"
    elif best_tier:
        tier_display = best_tier
    else:
        tier_display = "untiered"

    family_display = _display_family_for_plot(best_family)

    ax1.set_title(
        f"{unknown_name} vs class '{best_class}'\n"
        f"Family: {family_display}  |  Tier: {tier_display}  |  "
        f"Best file: {best_file_name}  |  "
        f"Similarity: {similarity_score:.2f}%"
        + (f"  |  Confidence: {confidence_label}" if confidence_label else ""),
        pad=70, fontsize=18, fontweight="bold")
    ax1.set_xlabel("Raman shift (cm$^{-1}$)", fontsize=18, labelpad=10)
    ax1.set_ylabel("Normalised intensity", fontsize=18, labelpad=10)
    ax1.set_xlim(corr_range_min, corr_range_max)
    ax1.set_ylim(-0.05, 1.30)
    ax1.tick_params(axis="both", labelsize=15)
    ax1.grid(True, axis="both", linestyle=":", linewidth=0.6,
             color="#bbbbbb", alpha=0.6)
    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005),
               ncol=5, fontsize=13, framealpha=0.0,
               handletextpad=0.5, columnspacing=1.5,
               borderaxespad=0.0)
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)

    _annotate_peaks_staggered(ax1, unknown_pos, unknown_int,
                              color="#1f4f8b",
                              max_peaks_to_annotate=num_top_peaks)
    _annotate_peaks_staggered(ax1, known_pos, known_int,
                              color="#b03030",
                              max_peaks_to_annotate=num_top_peaks)

    #MIDDLE PANEL
    ax_info.axis("off")
    n_u = len(unknown_result[2]) if unknown_result[2] is not None else 0
    n_k = len(known_result[2])   if known_result[2]   is not None else 0

    left_rows = [
        ("Peaks",       f"unknown={n_u}, known={n_k}"),
        ("Best class",  f"{best_class}  ({family_display})"),
        ("Best tier",   f"{tier_display}  ({reference_support or '-'})"),
        ("Best score",  f"{similarity_score:.2f}%"),
    ]
    if second_class is not None:
        sf = f" ({_display_family_for_plot(second_family)})" if second_family else ""
        left_rows.append(("2nd class", f"{second_class}{sf}  ({second_score:.2f}%)"))
        if gap is not None:
            left_rows.append(("Gap to 2nd", f"{gap:.2f}%"))
    if near_twin_class and near_twin_score is not None:
        left_rows.append(("Near-twin", f"{near_twin_class} ({near_twin_score:.2f}%)"))
    left_rows.append(("Unknown SNR", _format_snr(unknown_snr)))
    left_rows.append(("Known SNR",   _format_snr(known_snr)))
    if is_untiered:
        left_rows.append(("Strong signals", "N/A (untiered)"))
    elif strong_signals_count is not None:
        left_rows.append(("Strong signals", f"{strong_signals_count}/3"))
    if ambiguity_flags:
        left_rows.append(("Flags", ", ".join(ambiguity_flags)))

    label_w = max(len(lbl) for lbl, _ in left_rows)
    left_body = "\n".join(f"{lbl.ljust(label_w)} : {val}" for lbl, val in left_rows)

    right_body = ""
    if is_untiered:
        verdict = "UNTIERED_MATCH" if similarity_score >= threshold else "REJECTED"
        rel = ">=" if similarity_score >= threshold else "<"
        right_body = (
            "No tiers found - similarity-only comparison.\n\n"
            "Reference library has no tier metadata for this class,\n"
            "so the three-axis confidence rule does not apply.\n\n"
            "Verdict is based on the similarity score alone:\n"
            f"  score {similarity_score:.2f}% {rel} {threshold:.0f}% = {verdict}"
        )
    elif confidence_note:
        wrapped = []
        for p in [s.strip() for s in confidence_note.split(";") if s.strip()]:
            chunks = textwrap.wrap(p, width=58) or [p]
            wrapped.append(chunks[0])
            wrapped.extend("  " + c for c in chunks[1:])
        right_body = "\n".join(wrapped)

    header_y = 0.95
    ax_info.text(0.25, header_y, "Match details",
                 transform=ax_info.transAxes,
                 ha="center", va="center", fontsize=17, fontweight="bold",
                 color="#222222",
                 bbox=dict(facecolor="white", edgecolor="none", pad=4.0),
                 zorder=4)
    ax_info.add_line(Line2D([0.05, 0.45], [header_y, header_y],
                            transform=ax_info.transAxes,
                            color="#222222", linestyle=":", linewidth=1.4,
                            zorder=3))
    ax_info.text(0.05, 0.85, left_body,
                 transform=ax_info.transAxes,
                 ha="left", va="top", fontsize=14,
                 family="monospace", color="#222222",
                 linespacing=1.45, zorder=3)

    right_header = ("Confidence reasoning  (untiered: similarity-only)"
                    if is_untiered else "Confidence reasoning")
    ax_info.text(0.75, header_y, right_header,
                 transform=ax_info.transAxes,
                 ha="center", va="center", fontsize=17, fontweight="bold",
                 color="#222222",
                 bbox=dict(facecolor="white", edgecolor="none", pad=4.0),
                 zorder=4)
    ax_info.add_line(Line2D([0.55, 0.95], [header_y, header_y],
                            transform=ax_info.transAxes,
                            color="#222222", linestyle=":", linewidth=1.4,
                            zorder=3))
    ax_info.text(0.55, 0.85, right_body,
                 transform=ax_info.transAxes,
                 ha="left", va="top", fontsize=14,
                 family="monospace", color="#222222",
                 linespacing=1.45, zorder=3)

    #BOTTOM PANEL
    metrics = ["Peak match", "Full-spectrum corr.", "Total similarity"]
    scores  = [peak_score, pearson_score, similarity_score]
    weights = [peak_weight * 100, pearson_weight * 100, 100]

    bar_colors = ["#9ec5e8", "#3a78b8", "#1f3f72"]

    bars = ax2.bar(metrics, scores, color=bar_colors, alpha=0.92,
                   edgecolor="#1a2a44", linewidth=0.8)
    ax2.axhline(y=threshold, color="#b03030", linestyle="--", lw=1.4,
                alpha=0.85, label=f"{threshold}% threshold")
    ax2.legend(loc="upper right", fontsize=14, framealpha=0.9,
               edgecolor="#888888")
    for i, v in enumerate(scores):
        ax2.text(i, v + 2, f"{v:.2f}%\n(w={weights[i]:.0f}%)",
                 ha="center", va="bottom", fontsize=15)
    ax2.set_ylabel("Score (%)", fontsize=18, labelpad=10)
    ax2.set_title("Similarity metrics", pad=12, fontsize=18, fontweight="bold")
    ax2.set_ylim(0, 122)
    ax2.tick_params(axis="x", labelsize=15)
    ax2.tick_params(axis="y", labelsize=14)
    ax2.grid(axis="y", alpha=0.3, linestyle=":", linewidth=0.6)
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)
    _ = bars  # keep reference; no further styling

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def analyze_folders(cfg):
    unknown_folder = cfg["unknown_folder"]
    known_root     = cfg["known_root"]
    output_file    = cfg["output_file"]
    threshold      = cfg["threshold"]
    peak_tolerance = cfg["peak_tolerance"]
    num_top_peaks  = cfg["num_top_peaks"]
    range_min      = cfg["range_min"]
    range_max      = cfg["range_max"]
    exclude_ranges = cfg["exclude_ranges"]
    detailed       = cfg["detailed_output"]
    chem_cut       = cfg["chemistry_override_cutoff"]
    biggap_cut     = cfg["big_gap_override_cutoff"]
    plot_enabled   = bool(cfg["plot_enabled"])
    plot_dir       = cfg["plot_dir"]
    tqdm_enabled   = bool(cfg["tqdm_enabled"])

    total_w = cfg["peak_weight"] + cfg["pearson_weight"]
    peak_weight = cfg["peak_weight"] / total_w
    pearson_weight = cfg["pearson_weight"] / total_w

    print("=" * 60)
    print("SCRIPT VERSION: PNG_ONLY_THRESHOLD_FOLDERS_TQDM_STDOUT")
    print(f"PLOTTING: {'ON' if plot_enabled else 'OFF'}")
    if plot_enabled:
        over_dir = os.path.join(plot_dir, OVER_THRESHOLD_FOLDER)
        below_dir = os.path.join(plot_dir, BELOW_THRESHOLD_FOLDER)
        os.makedirs(over_dir, exist_ok=True)
        os.makedirs(below_dir, exist_ok=True)
        print("Plot format        - PNG only")
        print(f"Plot base folder   - {plot_dir}")
        print(f"Over threshold     - {over_dir}")
        print(f"Below threshold    - {below_dir}")
    else:
        over_dir = below_dir = None
        print("No PNG plots will be written; Excel report only.")
    print(f"TQDM PROGRESS: {'ON' if (tqdm_enabled and _TQDM_AVAILABLE) else 'OFF'}")
    if tqdm_enabled and not _TQDM_AVAILABLE:
        print("tqdm is not installed. Install it with: pip install tqdm")
    print("=" * 60)

    print("Discovering reference library ...")
    known_records = discover_known_files(known_root)
    unknown_records = discover_unknown_files(unknown_folder)
    if not unknown_records:
        print("ERROR: no .parquet files in unknown folder"); return None
    if not known_records:
        print("ERROR: no .parquet files under reference library root"); return None

    class_labels = sorted({r["class_label"] for r in known_records})
    families = sorted({_display_material_family(r["material_family"]) for r in known_records})
    print(f"Found {len(unknown_records)} unknowns, {len(known_records)} knowns "
          f"({len(class_labels)} classes)")
    print(f"Material families: {families}")
    print(f"Analysis range: {range_min}-{range_max} cm-1 | "
          f"weights peak={peak_weight:.2f} pearson={pearson_weight:.2f} | "
          f"threshold {threshold}")

    grid = build_shared_grid(range_min, range_max)
    G = len(grid)

    #Precompute peaks/interp for every spectrum
    print("Precomputing spectra & peaks ...")
    known_pre, unknown_pre, skipped = {}, {}, []

    def _precompute(rec):
        df = pd.read_parquet(rec["file_path"])
        return find_top_peaks(df, range_min, range_max, num_top_peaks,
                              exclude_ranges, grid)

    for rec in _progress(known_records, desc="Precompute known", unit="file", enabled=tqdm_enabled):
        try:
            known_pre[rec["file_id"]] = {"meta": rec, "result": _precompute(rec)}
        except Exception as e:
            skipped.append((rec["file_path"], str(e)))
    for rec in _progress(unknown_records, desc="Precompute unknown", unit="file", enabled=tqdm_enabled):
        try:
            unknown_pre[rec["file_id"]] = {"meta": rec, "result": _precompute(rec)}
        except Exception as e:
            skipped.append((rec["file_path"], str(e)))
    if skipped:
        print(f"  {len(skipped)} file(s) skipped during precompute")

    u_ids = list(unknown_pre.keys())
    k_ids = list(known_pre.keys())
    if not u_ids or not k_ids:
        print("ERROR: nothing usable after precompute"); return None

    #Pearson matrix
    print("Computing Pearson correlation matrix ...")
    U_mat = np.vstack([
        interp_safe(unknown_pre[u]["result"], G)
        for u in _progress(u_ids, desc="Build unknown matrix", unit="unknown", enabled=tqdm_enabled)
    ])
    K_mat = np.vstack([
        interp_safe(known_pre[k]["result"], G)
        for k in _progress(k_ids, desc="Build known matrix", unit="file", enabled=tqdm_enabled)
    ])
    R = pearson_matrix(U_mat, K_mat) * 100.0

    #File-level pair scoring
    print("Scoring file-level pairs ...")
    rows = []
    score_pbar = None
    if tqdm_enabled and _TQDM_AVAILABLE:
        score_pbar = tqdm(
            total=len(u_ids) * len(k_ids),
            desc="Score file pairs",
            unit="pair",
            file=sys.stdout,
            dynamic_ncols=True,
            leave=True,
            ascii=True,
            mininterval=0.2,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )
    try:
        for ui, u_id in enumerate(u_ids):
            u_result = unknown_pre[u_id]["result"]
            u_peaks = u_result[2] if (u_result is not None and u_result[2] is not None) else np.array([])
            for ki, k_id in enumerate(k_ids):
                k_meta = known_pre[k_id]["meta"]
                k_result = known_pre[k_id]["result"]
                k_peaks = k_result[2] if (k_result is not None and k_result[2] is not None) else np.array([])
                if len(u_peaks) > 0 and len(k_peaks) > 0:
                    dists = np.abs(u_peaks[:, None] - k_peaks)
                    matched = int(np.sum(np.any(dists <= peak_tolerance, axis=1)))
                    denom = max(len(u_peaks), len(k_peaks), matched)
                    peak_score = (matched / denom) * 100
                else:
                    peak_score = 0.0
                final_score = peak_weight * peak_score + pearson_weight * float(R[ui, ki])
                _tier = k_meta["tier"]
                _sub = k_meta.get("tier_subgroup", _tier)
                rows.append({
                    "Known Class": k_meta["class_label"],
                    "Material Family": _display_material_family(k_meta["material_family"]),
                    "Tier": _tier if _tier is not None else "",
                    "Tier Subgroup": _sub if _sub is not None else "",
                    "Known File ID": k_id,
                    "Known File": k_meta["file_stem"],
                    "Unknown ID": u_id,
                    "Unknown File": unknown_pre[u_id]["meta"]["file_stem"],
                    "Peak Score (%)": float(peak_score),
                    "Pearson Score (%)": float(R[ui, ki]),
                    "Similarity (%)": float(final_score),
                })
                if score_pbar is not None:
                    score_pbar.update(1)
    finally:
        if score_pbar is not None:
            score_pbar.close()
    results_df = pd.DataFrame(rows)

    print("Building per-unknown summaries ...")
    class_level_rows, summaries = [], []
    results_by_unknown = dict(tuple(results_df.groupby("Unknown ID", sort=False)))

    for u_id in _progress(u_ids, desc="Summaries and PNG plots", unit="unknown", enabled=tqdm_enabled):
        sub = results_by_unknown.get(u_id)
        if sub is None or sub.empty:
            continue

        best_row = sub.sort_values("Similarity (%)", ascending=False).iloc[0]
        best_class = best_row["Known Class"]
        best_family = best_row["Material Family"]
        _tier_raw = best_row["Tier"]
        best_tier = _tier_raw if _tier_raw not in (None, "", "nan") else None
        best_file_id = best_row["Known File ID"]
        best_file_name = best_row["Known File"]
        best_score = float(best_row["Similarity (%)"])

        class_best = (sub.sort_values("Similarity (%)", ascending=False)
                         .groupby(["Known Class", "Material Family"], as_index=False).first()
                         .sort_values("Similarity (%)", ascending=False)
                         .reset_index(drop=True))

        others = class_best[class_best["Known Class"] != best_class]
        if len(others) > 0:
            srow = others.iloc[0]
            second_class = srow["Known Class"]
            second_family = srow["Material Family"]
            second_score = float(srow["Similarity (%)"])
        else:
            second_class = second_family = None
            second_score = 0.0
        gap = best_score - second_score if second_class else best_score

        conf = assess_confidence(
            best_score=best_score, gap=gap, best_tier=best_tier,
            threshold=threshold,
            second_score=second_score if second_class else None,
            second_class=second_class,
            chemistry_override_cutoff=chem_cut,
            big_gap_override_cutoff=biggap_cut,
        )
        confidence = conf["label"]
        flag_str = ", ".join(conf["flags"]) if conf["flags"] else ""
        final_class = "" if confidence == "REJECTED" else best_class
        final_family = "" if confidence == "REJECTED" else best_family

        u_res = unknown_pre[u_id]["result"]
        u_n_peaks = u_res[4] if (u_res is not None and u_res[4] is not None) else 0
        unknown_snr = result_snr(u_res)
        known_snr = result_snr(known_pre[best_file_id]["result"]
                               if best_file_id in known_pre else None)

        summaries.append({
            "Unknown File": unknown_pre[u_id]["meta"]["file_stem"],
            "Unknown Peak Count": u_n_peaks,
            "Best Family": final_family,
            "Best Class": final_class,
            "Best Tier": best_tier,
            "Reference Support": conf["reference_support"],
            "Best File": best_file_name,
            "Best Score (%)": best_score,
            "Second Class": second_class or "",
            "Second Family": second_family or "",
            "Second Score (%)": second_score,
            "Gap (%)": gap,
            "Score Band": conf["score_band"],
            "Gap Quality": conf["gap_quality"],
            "Strong Signals Count": conf["strong_signals_count"],
            "Match Flags": flag_str,
            "Near-Twin Class": conf["near_twin_class"] or "",
            "Near-Twin Score (%)": (conf["near_twin_score"]
                                    if conf["near_twin_score"] is not None else ""),
            "Unknown SNR": unknown_snr if np.isfinite(unknown_snr) else np.nan,
            "Known SNR": known_snr if np.isfinite(known_snr) else np.nan,
            "Confidence": confidence,
            "Confidence Note": conf["note"],
        })

        if plot_enabled:
            try:
                unknown_name = unknown_pre[u_id]["meta"]["file_stem"]
                target_plot_dir = over_dir if best_score >= threshold else below_dir
                out_png = os.path.join(
                    target_plot_dir, f"{_safe_plot_filename(unknown_name)}__best_match.png"
                )
                plot_best_match(
                    unknown_result=u_res,
                    known_result=(known_pre[best_file_id]["result"]
                                  if best_file_id in known_pre else None),
                    unknown_name=unknown_name,
                    best_family=best_family,
                    best_class=best_class,
                    best_file_name=best_file_name,
                    best_tier=best_tier,
                    similarity_score=best_score,
                    peak_tolerance=peak_tolerance,
                    num_top_peaks=num_top_peaks,
                    corr_range_min=range_min,
                    corr_range_max=range_max,
                    peak_weight=peak_weight,
                    pearson_weight=pearson_weight,
                    threshold=threshold,
                    output_path=out_png,
                    confidence_label=confidence,
                    confidence_note=conf["note"],
                    second_class=second_class,
                    second_family=second_family,
                    second_score=(second_score if second_class else None),
                    gap=gap,
                    ambiguity_flags=conf["flags"],
                    near_twin_class=conf["near_twin_class"],
                    near_twin_score=conf["near_twin_score"],
                    strong_signals_count=conf["strong_signals_count"],
                    reference_support=conf["reference_support"],
                    unknown_snr=unknown_snr,
                    known_snr=known_snr,
                    exclude_ranges=exclude_ranges,
                    best_tier_subgroup=(best_row.get("Tier Subgroup", best_tier)
                                        if hasattr(best_row, "get") else best_tier),
                )
            except Exception as e:
                print(f"  plot skipped for {u_id}: {e}")

        for _, r in class_best.iterrows():
            class_level_rows.append({
                "Unknown File": unknown_pre[u_id]["meta"]["file_stem"],
                "Known Class": r["Known Class"],
                "Known Family": r["Material Family"],
                "Best File Inside Class": r["Known File"],
                "Best Tier Inside Class": r["Tier"],
                "Class Score (%)": float(r["Similarity (%)"]),
            })

    class_level_df = pd.DataFrame(class_level_rows)
    summary_df = pd.DataFrame(summaries)

    #Excel report
    print("Writing Excel report ...")
    _write_excel(output_file, class_level_df, summary_df, results_df,
                 threshold, detailed)

    n_match = int((summary_df["Best Score (%)"] >= threshold).sum()) if not summary_df.empty else 0
    print("=" * 60)
    print(f"Done: {len(u_ids)} unknowns processed, {n_match} matched at >= {threshold}%")
    if skipped:
        print(f"Skipped ({len(skipped)}):")
        for fp, err in skipped:
            print(f"  x {fp} - {err}")
    print(f"Report - {output_file}")
    if plot_enabled:
        print(f"PNG plots over threshold  - {over_dir}")
        print(f"PNG plots below threshold - {below_dir}")
    return summary_df


def _write_excel(output_file, class_level_df, summary_df, results_df,
                 threshold, detailed):
    pivot_class = (class_level_df.pivot(index="Known Class", columns="Unknown File",
                                        values="Class Score (%)")
                   if not class_level_df.empty else pd.DataFrame())

    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        if not pivot_class.empty:
            column_order = list(pivot_class.columns)

            best_row_s = pd.Series(
                {r["Unknown File"]: r["Best Class"] for _, r in summary_df.iterrows()},
                name="Best Class")

            def _snr_excel(val):
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    return ""
                return v if np.isfinite(v) else ""

            snr_unknown_s = pd.Series(
                {r["Unknown File"]: _snr_excel(r.get("Unknown SNR", np.nan))
                 for _, r in summary_df.iterrows()}, name="SNR Unknown")
            snr_known_s = pd.Series(
                {r["Unknown File"]: _snr_excel(r.get("Known SNR", np.nan))
                 for _, r in summary_df.iterrows()}, name="SNR Known")

            summary_rows = pd.concat([
                best_row_s.to_frame().T,
                snr_unknown_s.to_frame().T,
                snr_known_s.to_frame().T,
            ]).reindex(columns=column_order)

            final_matrix = pd.concat([pivot_class, summary_rows])
            final_matrix.to_excel(writer, sheet_name="Class_Results")

            wb = writer.book
            ws = writer.sheets["Class_Results"]
            pct_fmt = wb.add_format({"num_format": "0.00"})
            hi_fmt = wb.add_format({"num_format": "0.00", "bold": True, "bg_color": "#FFF2CC"})
            snr_fmt = wb.add_format({"num_format": "0.0", "italic": True})
            text_fmt = wb.add_format({})

            n_rows = final_matrix.shape[0]
            n_cols = final_matrix.shape[1]
            n_class_rows = n_rows - 3   # three summary rows at the bottom

            for r_excel in range(1, n_rows + 1):
                df_row = r_excel - 1
                for c in range(1, n_cols + 1):
                    val = final_matrix.iloc[df_row, c - 1]
                    if df_row < n_class_rows:
                        if pd.notna(val) and isinstance(val, (int, float)):
                            ws.write(r_excel, c, val, hi_fmt if val >= threshold else pct_fmt)
                    else:
                        label = final_matrix.index[df_row]
                        if label == "Best Class":
                            ws.write(r_excel, c, val if pd.notna(val) else "", text_fmt)
                        else:
                            if isinstance(val, (int, float)) and pd.notna(val):
                                ws.write_number(r_excel, c, float(val), snr_fmt)
                            else:
                                ws.write(r_excel, c, "", snr_fmt)

        if detailed:
            if not summary_df.empty:
                summary_df.to_excel(writer, sheet_name="Summary", index=False)
            if not class_level_df.empty:
                class_level_df.to_excel(writer, sheet_name="Class_Long", index=False)
            if not results_df.empty:
                results_df.to_excel(writer, sheet_name="File_Long", index=False)


def build_cfg(args):
    ex = EXCLUDE_RANGES
    if args.exclude_min is not None and args.exclude_max is not None \
            and args.exclude_max > args.exclude_min > 0:
        ex = [(float(args.exclude_min), float(args.exclude_max))]
    return {
        "unknown_folder": args.unknown,
        "known_root": args.known,
        "output_file": args.output,
        "threshold": args.threshold,
        "peak_tolerance": args.peak_tolerance,
        "num_top_peaks": args.num_peaks,
        "range_min": args.range_min, "range_max": args.range_max,
        "peak_weight": args.peak_weight, "pearson_weight": args.pearson_weight,
        "chemistry_override_cutoff": CHEMISTRY_OVERRIDE_CUTOFF,
        "big_gap_override_cutoff": BIG_GAP_OVERRIDE_CUTOFF,
        "exclude_ranges": ex,
        "detailed_output": args.detailed,
        "plot_enabled": args.plot_enabled,
        "plot_dir": args.plot_dir,
        "tqdm_enabled": args.tqdm_enabled,
    }


def main():
    ap = argparse.ArgumentParser(description="Step 2 Raman matching.")
    ap.add_argument("--unknown", default=UNKNOWN_FOLDER)
    ap.add_argument("--known", default=KNOWN_ROOT)
    ap.add_argument("--output", default=OUTPUT_EXCEL)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--peak-tolerance", type=float, default=PEAK_TOLERANCE, dest="peak_tolerance")
    ap.add_argument("--num-peaks", type=int, default=NUM_TOP_PEAKS, dest="num_peaks")
    ap.add_argument("--range-min", type=float, default=RANGE_MIN, dest="range_min")
    ap.add_argument("--range-max", type=float, default=RANGE_MAX, dest="range_max")
    ap.add_argument("--peak-weight", type=float, default=PEAK_WEIGHT, dest="peak_weight")
    ap.add_argument("--pearson-weight", type=float, default=PEARSON_WEIGHT, dest="pearson_weight")
    ap.add_argument("--exclude-min", type=float, default=None, dest="exclude_min")
    ap.add_argument("--exclude-max", type=float, default=None, dest="exclude_max")
    ap.add_argument("--detailed", action="store_true", default=DETAILED_OUTPUT)
    tqdm_group = ap.add_mutually_exclusive_group()
    tqdm_group.add_argument("--tqdm", dest="tqdm_enabled", action="store_true",
                            help="Show tqdm progress bars.")
    tqdm_group.add_argument("--no-tqdm", dest="tqdm_enabled", action="store_false",
                            help="Disable tqdm progress bars.")
    ap.set_defaults(tqdm_enabled=TQDM_ENABLED)
    plot_group = ap.add_mutually_exclusive_group()
    plot_group.add_argument("--plot", dest="plot_enabled", action="store_true",
                            help="Save best-match PNG plots for each unknown.")
    plot_group.add_argument("--no-plot", dest="plot_enabled", action="store_false",
                            help="Do not save plots; write Excel only.")
    ap.set_defaults(plot_enabled=PLOT_ENABLED)
    ap.add_argument("--plot-dir", default=OUTPUT_PLOT_DIR, dest="plot_dir",
                    help="Base folder where best-match PNG files are saved. Two subfolders are created automatically: Over_Threshold and Below_Threshold.")
    args, _ = ap.parse_known_args()
    analyze_folders(build_cfg(args))


if __name__ == "__main__":
    main()