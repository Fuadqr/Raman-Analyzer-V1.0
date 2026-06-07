
from __future__ import annotations

import os
import argparse
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scipy.signal import savgol_filter
from scipy import sparse
from scipy.sparse.linalg import spsolve
from BaselineRemoval import BaselineRemoval

try:
    from joblib import Parallel, delayed
    import joblib
    _HAVE_JOBLIB = True
except Exception:
    joblib = None
    _HAVE_JOBLIB = False

try:
    from tqdm.auto import tqdm
    _HAVE_TQDM = True
except Exception:
    tqdm = None
    _HAVE_TQDM = False


def _tqdm_is_on(cfg=None):
    if cfg is None:
        enabled = TQDM_ENABLED
    else:
        enabled = bool(cfg.get("tqdm_enabled", TQDM_ENABLED))
    return bool(enabled and _HAVE_TQDM)


def _iter_progress(iterable, desc, total=None, cfg=None):
    if not _tqdm_is_on(cfg):
        return iterable
    return tqdm(iterable, desc=desc, total=total, file=sys.stdout,
                dynamic_ncols=True, leave=True)


def _make_pbar(desc, total, cfg=None):
    if not _tqdm_is_on(cfg):
        return None
    return tqdm(desc=desc, total=total, file=sys.stdout,
                dynamic_ncols=True, leave=True)


@contextmanager
def tqdm_joblib(tqdm_object):
    if tqdm_object is None or joblib is None:
        yield tqdm_object
        return

    class TqdmBatchCompletionCallback(joblib.parallel.BatchCompletionCallBack):
        def __call__(self, *args, **kwargs):
            tqdm_object.update(n=self.batch_size)
            return super().__call__(*args, **kwargs)

    old_callback = joblib.parallel.BatchCompletionCallBack
    joblib.parallel.BatchCompletionCallBack = TqdmBatchCompletionCallback
    try:
        yield tqdm_object
    finally:
        joblib.parallel.BatchCompletionCallBack = old_callback
        tqdm_object.close()

# ============================================================
# CONFIG  (edit these only)
# ============================================================

INPUT_DIR  =r"INPUT_FOLDER_HERE"
OUTPUT_DIR = r"OUTPUT_FOLDER_HERE"

#Baseline method
# Full control (unlike the GUI, which is locked to ZhangFit):
#   'ZhangFit'  - adaptive iteratively-reweighted penalised least squares
#   'ModPoly'   - modified polynomial fit
#   'IModPoly'  - improved modified polynomial fit
#   'ALS'       - asymmetric least squares (sparse implementation below)
METHOD = "ZhangFit"

# ZhangFit params — engine default is lambda=50 (the GUI / engine value).
# (The Document-1 notebook used 100; set ZHANG_LAMBDA=100 to reproduce it.)
ZHANG_LAMBDA      = 50
ZHANG_PORDER      = 3
ZHANG_REPITITION  = 100

# ModPoly / IModPoly params
POLY_DEGREE = 3
ITERS       = 100
CONV_THRESH = 0.001

# ALS params
LAM_ALS = 10000
P_ALS   = 0.001

#Savitzky-Golay smoothing
# 'resolution_aware' - engine behaviour: physical width (cm^-1) - odd window
#                       from the median spacing (SG_TARGET_WIDTH_CM).
# 'fixed'            - Document-1 behaviour: a fixed odd window of SG_FIXED_WINDOW.
SG_MODE            = "resolution_aware"
SG_TARGET_WIDTH_CM = 18.0   # used in resolution_aware mode
SG_POLY_ORDER      = 3
SG_FIXED_WINDOW    = 21     # used in fixed mode
SG_FIXED_POLY      = 3      # used in fixed mode

#SNR windows
SNR_SIG_MIN   = 500.0
SNR_SIG_MAX   = 1800.0
SNR_NOISE_MIN = 1850.0
SNR_NOISE_MAX = 1950.0
SNR_THRESHOLD = 10.0

#SNR classification
SNR_MIN_SIGNAL_POINTS = 5
SNR_MIN_NOISE_POINTS  = 5
SNR_NOISE_FLOOR_VALUE = 1e-4   # on the [0, 1] normalised scale
SNR_CAP               = 1000.0

#Output toggles
SAVE_PLOTS         = True
PLOTS_ONLY_LOW_SNR = False
TQDM_ENABLED       = True      # True - show proper tqdm progress bars for each step
N_WORKERS          = None      # None - os.cpu_count()

#Plot style
PLOT_DISPLAY_MIN = None        # x-axis min for plots; None - spectrum minimum
PLOT_DISPLAY_MAX = None        # x-axis max for plots; None - spectrum maximum

SUPPORTED_EXTS = {".csv", ".xlsx", ".txt"}


# PLOT STYLE
from matplotlib import rcParams

rcParams["font.family"]       = "serif"
rcParams["font.serif"]        = ["Times New Roman", "DejaVu Serif"]
rcParams["font.size"]         = 16
rcParams["axes.linewidth"]    = 1.1
rcParams["axes.labelsize"]    = 18
rcParams["axes.titlesize"]    = 18
rcParams["xtick.labelsize"]   = 15
rcParams["ytick.labelsize"]   = 15
rcParams["xtick.direction"]   = "in"
rcParams["ytick.direction"]   = "in"
rcParams["xtick.major.size"]  = 6
rcParams["ytick.major.size"]  = 6
rcParams["xtick.major.width"] = 1.1
rcParams["ytick.major.width"] = 1.1
rcParams["legend.frameon"]    = False
rcParams["legend.fontsize"]   = 14

COLOR_RAW       = "#7a7a7a"
COLOR_BASELINE  = "#3a8f5a"
COLOR_CORRECTED = "#1f4f8b"
COLOR_SMOOTHED  = "#1f3f72"
COLOR_SIGNAL    = "#9ec5e8"
COLOR_NOISE     = "#b03030"
COLOR_PEAK      = "#1f3f72"



# BASELINE METHODS
def baseline_als(y, lam, p, niter=10):
    """Asymmetric Least Squares baseline (sparse, no dense LxL allocation).
    Ported from the Document-1 notebook."""
    y = np.asarray(y, dtype=float)
    L = len(y)
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(L - 2, L), format="csc")
    DtD = lam * (D.T @ D)
    w = np.ones(L)
    z = y
    for _ in range(niter):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + DtD
        z = spsolve(Z, w * y)
        w = p * (y > z) + (1 - p) * (y < z)
    return z


def compute_baseline_corrected(intensity, method, cfg):
    """Return the baseline-corrected spectrum for the chosen method.
    'baseline' is recovered as intensity - corrected downstream."""
    if method == "ALS":
        baseline = baseline_als(intensity, cfg["lam_als"], cfg["p_als"])
        return intensity - baseline

    baseObj = BaselineRemoval(intensity)
    if method == "ModPoly":
        return baseObj.ModPoly(cfg["poly_degree"], cfg["iters"], cfg["conv_thresh"])
    if method == "IModPoly":
        return baseObj.IModPoly(cfg["poly_degree"], cfg["iters"], cfg["conv_thresh"])
    if method == "ZhangFit":
        return baseObj.ZhangFit(lambda_=cfg["zhang_lambda"],
                                porder=cfg["zhang_porder"],
                                repitition=cfg["zhang_repitition"])
    raise ValueError(f"Unknown baseline method: {method!r}")


def _read_raw_table(file_path: str):
    """Delimited read with no header/type assumptions. Returns str DataFrame."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".xlsx":
        return pd.read_excel(file_path, header=None, dtype=str)

    import re
    from io import StringIO

    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ln for ln in fh.readlines() if not ln.lstrip().startswith("#")]
    if not lines:
        raise ValueError(f"Empty file: {file_path}")
    text_buf = "".join(lines)

    candidates = []
    for sep in (",", "\t", ";", r"\s+"):
        if sep == r"\s+":
            splitter = lambda ln: re.split(r"\s+", ln.strip()) if ln.strip() else []
        else:
            splitter = lambda ln: ln.rstrip("\n").rstrip("\r").split(sep)
        max_cols = 0
        for ln in lines:
            w = len(splitter(ln))
            if w > max_cols:
                max_cols = w
        if max_cols < 2:
            continue
        try:
            df = pd.read_csv(
                StringIO(text_buf), sep=sep, header=None,
                names=list(range(max_cols)), dtype=str,
                engine="python" if sep == r"\s+" else "c",
                skip_blank_lines=False, on_bad_lines="skip",
            )
        except Exception:
            continue
        if df.shape[0] == 0 or df.shape[1] < 2:
            continue

        numeric_rows = 0
        for i in range(min(len(df), 200)):
            n = 0
            for v in df.iloc[i].values:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                try:
                    if np.isfinite(float(s)):
                        n += 1
                except (ValueError, TypeError):
                    pass
                if n >= 2:
                    break
            if n >= 2:
                numeric_rows += 1
        candidates.append((numeric_rows, df.shape[1], df))

    if not candidates:
        raise ValueError(f"Could not parse: {file_path}")
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _looks_like_header_row(values):
    keywords = ("raman", "shift", "intensity", "wave", "wavenumber",
                "cm-1", "1/cm", "counts", "cps")
    for v in values:
        if v is None:
            continue
        s = str(v).strip().lower()
        if s and any(k in s for k in keywords):
            return True
    return False


def _row_numeric_count(values):
    n = 0
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        try:
            if np.isfinite(float(s)):
                n += 1
        except (ValueError, TypeError):
            pass
    return n


def load_data(file_path: str):
    """Robust loader for messy Raman exports. Returns ascending, deduped
    DataFrame with columns ['Wave', 'Intensity']."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported format: {ext}")

    # Fast path: a previously-exported intermediate with Wave + Smoothed.
    try:
        quick = (pd.read_excel(file_path, nrows=5) if ext == ".xlsx"
                 else pd.read_csv(file_path, nrows=5))
        if "Wave" in quick.columns and "Smoothed" in quick.columns:
            full = (pd.read_excel(file_path) if ext == ".xlsx"
                    else pd.read_csv(file_path))
            out = full[["Wave", "Smoothed"]].copy()
            out.columns = ["Wave", "Intensity"]
            out["Wave"] = pd.to_numeric(out["Wave"], errors="coerce")
            out["Intensity"] = pd.to_numeric(out["Intensity"], errors="coerce")
            out = out.dropna()
            if len(out) == 0:
                raise ValueError("No valid numeric data")
            out = out.sort_values("Wave", kind="mergesort").reset_index(drop=True)
            return out.drop_duplicates(subset="Wave", keep="first").reset_index(drop=True)
    except Exception:
        pass

    raw = _read_raw_table(file_path)

    def _col_is_empty(col):
        for v in col:
            if v is None:
                continue
            if isinstance(v, float) and np.isnan(v):
                continue
            if str(v).strip() == "":
                continue
            return False
        return True

    keep_cols = [c for c in raw.columns if not _col_is_empty(raw[c])]
    if len(keep_cols) < 2:
        raise ValueError(f"Fewer than 2 non-empty columns in: {file_path}")
    raw = raw[keep_cols].reset_index(drop=True)

    data_start = None
    for i in range(len(raw)):
        if _row_numeric_count(raw.iloc[i].values) >= 2:
            data_start = i
            break
    if data_start is None:
        raise ValueError(f"No numeric data rows found in: {file_path}")

    header_row = None
    if data_start > 0:
        cand = raw.iloc[data_start - 1].values
        if _looks_like_header_row(cand):
            header_row = cand

    data_block = raw.iloc[data_start:].reset_index(drop=True)
    numeric = data_block.apply(lambda c: pd.to_numeric(c, errors="coerce"))
    finite_counts = numeric.notna().sum()
    valid_cols = [c for c in numeric.columns if finite_counts[c] > 0]
    if len(valid_cols) < 2:
        raise ValueError(f"Fewer than 2 numeric columns in: {file_path}")
    numeric = numeric[valid_cols]

    ranked = sorted(valid_cols,
                    key=lambda c: (-int(finite_counts[c]), valid_cols.index(c)))
    wave_col, int_col = ranked[0], ranked[1]

    if header_row is not None:
        header_map = {}
        for pos, col_name in enumerate(raw.columns):
            if pos < len(header_row):
                header_map[col_name] = str(header_row[pos]).strip().lower()
        wave_kw = ("raman", "shift", "wave", "cm-1", "1/cm", "wavenumber")
        int_kw = ("intensity", "counts", "cps")
        wave_cand = int_cand = None
        for c in valid_cols:
            h = header_map.get(c, "")
            if wave_cand is None and any(k in h for k in wave_kw):
                wave_cand = c
            if int_cand is None and any(k in h for k in int_kw):
                int_cand = c
        if wave_cand is not None and int_cand is not None and wave_cand != int_cand:
            wave_col, int_col = wave_cand, int_cand

    out = pd.DataFrame({
        "Wave": numeric[wave_col].values,
        "Intensity": numeric[int_col].values,
    }).dropna(subset=["Wave", "Intensity"]).reset_index(drop=True)
    if len(out) == 0:
        raise ValueError(f"No numeric data rows found in: {file_path}")

    out = out.sort_values("Wave", kind="mergesort").reset_index(drop=True)
    out = out.drop_duplicates(subset="Wave", keep="first").reset_index(drop=True)
    return out



# RESOLUTION-AWARE SAVITZKY-GOLAY
def sg_window_length(wavenumbers, target_width_cm, poly_order):
    """Physical smoothing width (cm^-1) - valid odd SG window from median spacing."""
    wn = np.asarray(wavenumbers, dtype=float)
    if len(wn) < 5:
        n = len(wn)
        if n < 3:
            return n
        return n if n % 2 == 1 else n - 1

    diffs = np.diff(wn)
    diffs = diffs[np.isfinite(diffs)]
    diffs = diffs[np.abs(diffs) > 0]
    if len(diffs) == 0:
        wl = poly_order + 2
        return wl + 1 if wl % 2 == 0 else wl

    dx = float(np.median(np.abs(diffs)))
    wl = int(round(target_width_cm / dx))
    if wl % 2 == 0:
        wl += 1

    min_valid = poly_order + 2
    if min_valid % 2 == 0:
        min_valid += 1
    wl = max(wl, min_valid)

    max_valid = len(wn) if len(wn) % 2 == 1 else len(wn) - 1
    wl = min(wl, max_valid)

    if wl <= poly_order:
        wl = poly_order + 2
        if wl % 2 == 0:
            wl += 1
        if wl > max_valid:
            wl = max_valid
    if wl < 3 and len(wn) >= 3:
        wl = 3
    return int(wl)


def sg_smooth_resolution_aware(y, wavenumbers, target_width_cm, poly_order):
    """Returns (smoothed, window_length_used). On failure: (copy_of_y, nan)."""
    y = np.asarray(y, dtype=float)
    wn = np.asarray(wavenumbers, dtype=float)
    n = len(y)
    if n < 5:
        return y.copy(), float("nan")
    wl = sg_window_length(wn, target_width_cm, poly_order)
    po = int(poly_order)
    if wl is None or wl <= po or wl < 3 or wl > n:
        return y.copy(), float("nan")
    try:
        return savgol_filter(y, wl, po), float(wl)
    except Exception:
        return y.copy(), float("nan")


def sanitize_fixed_window(window_length, poly_order, n_points):
    """Coerce (window, poly) into something savgol_filter accepts. Returns the
    sanitised odd window length, or None if no valid config exists."""
    if n_points < 3:
        return None
    wl = int(window_length)
    po = int(poly_order)
    if wl % 2 == 0:
        wl += 1
    min_valid = po + 2
    if min_valid % 2 == 0:
        min_valid += 1
    if wl < min_valid:
        wl = min_valid
    max_valid = n_points if n_points % 2 == 1 else n_points - 1
    if wl > max_valid:
        wl = max_valid
    if wl < 3 or wl <= po:
        return None
    return wl


def sg_smooth(y, wavenumbers, cfg):
    """Dispatch SG smoothing on cfg['sg_mode']. Returns (smoothed, window_used)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 5:
        return y.copy(), float("nan")

    if cfg["sg_mode"] == "fixed":
        wl = sanitize_fixed_window(cfg["sg_fixed_window"], cfg["sg_fixed_poly"], n)
        po = int(cfg["sg_fixed_poly"])
        if wl is None:
            return y.copy(), float("nan")
        try:
            return savgol_filter(y, wl, po), float(wl)
        except Exception:
            return y.copy(), float("nan")

    # default: resolution_aware
    return sg_smooth_resolution_aware(
        y, wavenumbers, cfg["sg_target_width_cm"], cfg["sg_poly_order"])



# RANGE-AWARE SNR 
def inline_snr(wavenumbers, corrected, smoothed,
               sig_min, sig_max, noise_min, noise_max):
    wn = np.asarray(wavenumbers, dtype=float)
    sm = np.asarray(smoothed, dtype=float)
    co = np.asarray(corrected, dtype=float)

    sig_mask = (wn >= sig_min) & (wn <= sig_max)
    n_mask = (wn >= noise_min) & (wn <= noise_max)
    if (int(sig_mask.sum()) < SNR_MIN_SIGNAL_POINTS
            or int(n_mask.sum()) < SNR_MIN_NOISE_POINTS):
        return float("nan")

    s_min = float(np.nanmin(sm))
    s_max = float(np.nanmax(sm))
    rng = s_max - s_min
    if not np.isfinite(rng) or rng <= 0:
        return float("nan")

    if abs(s_min) < 1e-6 and abs(s_max - 1.0) < 1e-6:
        sm_n = sm.copy()
        co_n = co.copy()
    else:
        sm_n = (sm - s_min) / rng
        co_n = (co - s_min) / rng

    signal_peak = float(np.max(sm_n[sig_mask]))
    region = co_n[n_mask]
    noise_val = float(np.sqrt(np.mean((region - region.mean()) ** 2)))
    if not np.isfinite(noise_val):
        return float("nan")

    if noise_val < SNR_NOISE_FLOOR_VALUE:
        snr = signal_peak / SNR_NOISE_FLOOR_VALUE
        return float(min(snr, SNR_CAP))
    return float(signal_peak / noise_val)


def discover_input_files(input_root):
    records = []
    for root, _, files in os.walk(input_root):
        for f in files:
            if os.path.splitext(f)[1].lower() not in SUPPORTED_EXTS:
                continue
            rel_dir = os.path.relpath(root, input_root)
            rel_dir = "" if rel_dir == "." else rel_dir
            records.append({"input_path": os.path.join(root, f),
                            "rel_dir": rel_dir, "file_name": f})
    return sorted(records, key=lambda x: (x["rel_dir"], x["file_name"]))



# Files Processing
def process_one(rec, output_root, cfg):
    file_path = rec["input_path"]
    rel_dir = rec["rel_dir"]
    try:
        data = load_data(file_path)
        intensity = data["Intensity"].values.astype(float)
        wavenumbers = data["Wave"].values.astype(float)

        corrected = compute_baseline_corrected(intensity, cfg["method"], cfg)
        baseline = intensity - corrected

        smoothed, _wl = sg_smooth(corrected, wavenumbers, cfg)

        snr_val = inline_snr(
            wavenumbers, corrected, smoothed,
            cfg["sig_min"], cfg["sig_max"],
            cfg["noise_min"], cfg["noise_max"],
        )
        snr_finite = bool(np.isfinite(snr_val))
        snr_flag = ("UNMEASURABLE" if not snr_finite
                    else ("LOW" if snr_val < cfg["snr_threshold"] else "OK"))

        out_dir = os.path.join(output_root, rel_dir) if rel_dir else output_root
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(file_path))[0]
        parquet_path = os.path.join(out_dir, f"{base}_bs+sm.parquet")

        processed = pd.DataFrame({
            "Wave": wavenumbers,
            "Original_Intensity": intensity,
            "Baseline": baseline,
            "Baseline_Corrected": corrected,
            "Smoothed": smoothed,
            "SNR": (round(float(snr_val), 2) if snr_finite else np.nan),
            "SNR_Flag": snr_flag,
            "SNR_Threshold": float(cfg["snr_threshold"]),
        })
        processed.to_parquet(parquet_path, index=False)

        return (True, {
            "File": os.path.basename(file_path),
            "Relative_Folder": rel_dir if rel_dir else "[ROOT]",
            "Output_Parquet": parquet_path,
            "SNR": snr_val,
            "SNR_Flag": snr_flag,
            "Low_SNR_Flag": bool(snr_flag == "LOW"),
        })
    except Exception as e:
        return (False, {
            "File": os.path.basename(file_path),
            "Relative_Folder": rel_dir if rel_dir else "[ROOT]",
            "Error": str(e),
        })



# Diagnostic plots
def _snr_components(wavenumbers, corrected, smoothed, cfg):
    """Recompute normalised signal-peak and noise from stored arrays so the
    SNR panel can show the breakdown. Mirrors inline_snr's normalisation."""
    wn = np.asarray(wavenumbers, dtype=float)
    sm = np.asarray(smoothed, dtype=float)
    co = np.asarray(corrected, dtype=float)
    sig_mask = (wn >= cfg["sig_min"]) & (wn <= cfg["sig_max"])
    n_mask = (wn >= cfg["noise_min"]) & (wn <= cfg["noise_max"])
    if int(sig_mask.sum()) < 1 or int(n_mask.sum()) < 1:
        return np.nan, np.nan
    s_min, s_max = float(np.nanmin(sm)), float(np.nanmax(sm))
    rng = s_max - s_min
    if not np.isfinite(rng) or rng <= 0:
        return np.nan, np.nan
    if abs(s_min) < 1e-6 and abs(s_max - 1.0) < 1e-6:
        sm_n, co_n = sm.copy(), co.copy()
    else:
        sm_n = (sm - s_min) / rng
        co_n = (co - s_min) / rng
    signal_peak = float(np.max(sm_n[sig_mask]))
    region = co_n[n_mask]
    noise_val = float(np.sqrt(np.mean((region - region.mean()) ** 2)))
    return signal_peak, noise_val


def _save_fig(fig, out_base, cfg):
    """Save PNG only. PDF export has been removed completely."""
    fig.savefig(out_base + ".png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_preprocessing(wn, intensity, baseline, corrected, smoothed,
                        stem, method, dmin, dmax, out_base, cfg):
    fig, (ax_top, ax_bot) = plt.subplots(
        nrows=2, ncols=1, figsize=(13.5, 12.5),
        gridspec_kw={"height_ratios": [1.0, 1.0], "hspace": 0.50})
    fig.subplots_adjust(left=0.085, right=0.97, top=0.92, bottom=0.07)

    ax_top.plot(wn, intensity, color=COLOR_RAW, lw=1.0, alpha=0.9,
                label="Raw spectrum")
    ax_top.plot(wn, baseline, color=COLOR_BASELINE, lw=1.6, ls="--",
                label="Baseline")
    ax_top.plot(wn, corrected, color=COLOR_CORRECTED, lw=1.2, alpha=0.95,
                label="Raw spectrum \u2212 baseline")
    ax_top.set_title(f"Spectrum analysis using {method} method",
                     pad=58, fontsize=18, fontweight="bold")
    ax_top.set_xlabel("Raman shift (cm$^{-1}$)", fontsize=18, labelpad=10)
    ax_top.set_ylabel("Intensity", fontsize=18, labelpad=10)
    ax_top.set_xlim(dmin, dmax)
    ax_top.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb", alpha=0.6)
    ax_top.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=3,
                  fontsize=13, framealpha=0.0, handletextpad=0.6,
                  columnspacing=1.5, borderaxespad=0.0)
    for s in ("top", "right"):
        ax_top.spines[s].set_visible(False)

    ax_bot.plot(wn, smoothed, color=COLOR_SMOOTHED, lw=1.6, ls="--",
                label="Smoothed data")
    ax_bot.set_title("Smoothing using Savitzky\u2013Golay filter",
                     pad=58, fontsize=18, fontweight="bold")
    ax_bot.set_xlabel("Raman shift (cm$^{-1}$)", fontsize=18, labelpad=10)
    ax_bot.set_ylabel("Intensity", fontsize=18, labelpad=10)
    ax_bot.set_xlim(dmin, dmax)
    ax_bot.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb", alpha=0.6)
    ax_bot.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=1,
                  fontsize=13, framealpha=0.0, handletextpad=0.6,
                  borderaxespad=0.0)
    for s in ("top", "right"):
        ax_bot.spines[s].set_visible(False)

    _save_fig(fig, out_base, cfg)


def _plot_snr(wn, corrected, smoothed, snr, stem, dmin, dmax, out_base, cfg):
    sig_peak_n, noise_n = _snr_components(wn, corrected, smoothed, cfg)
    thr = cfg["snr_threshold"]
    if not np.isfinite(snr):
        verdict, vcolor, snr_text = "UNMEASURABLE", "#666666", "SNR = NaN  (unmeasurable)"
    elif snr < thr:
        verdict, vcolor, snr_text = f"FAIL  (SNR < {thr:g})", "#b03030", f"SNR = {snr:.1f}"
    else:
        verdict, vcolor, snr_text = f"PASS  (SNR \u2265 {thr:g})", "#1b7a3e", f"SNR = {snr:.1f}"

    fig, ax = plt.subplots(figsize=(13.5, 7.5))
    fig.subplots_adjust(left=0.085, right=0.97, top=0.80, bottom=0.13)

    s_lo, s_hi = cfg["sig_min"], cfg["sig_max"]
    n_lo, n_hi = cfg["noise_min"], cfg["noise_max"]
    ax.axvspan(s_lo, s_hi, alpha=0.30, color=COLOR_SIGNAL,
               label=f"Signal window [{s_lo:.0f}\u2013{s_hi:.0f}] cm$^{{-1}}$", zorder=1)
    ax.axvspan(n_lo, n_hi, alpha=0.22, color=COLOR_NOISE,
               label=f"Noise window [{n_lo:.0f}\u2013{n_hi:.0f}] cm$^{{-1}}$  (flat_region)",
               zorder=1)
    ax.plot(wn, smoothed, color=COLOR_SMOOTHED, lw=1.5,
            label="Smoothed spectrum", zorder=3)

    sig_mask = (wn >= s_lo) & (wn <= s_hi)
    if int(sig_mask.sum()) > 0:
        idx = int(np.argmax(smoothed[sig_mask]))
        peak_w = float(wn[sig_mask][idx]); peak_y = float(smoothed[sig_mask][idx])
        ax.axvline(peak_w, color=COLOR_PEAK, lw=1.0, ls="--", alpha=0.65, zorder=2,
                   label=f"Peak @ {peak_w:.0f} cm$^{{-1}}$")
        ax.scatter([peak_w], [peak_y], color=COLOR_PEAK, s=70, zorder=4,
                   edgecolor="white", lw=0.9)

    ax.set_title(f"SNR diagnostic  |  {snr_text}  \u2014  {verdict}",
                 pad=58, fontsize=18, fontweight="bold", color=vcolor)
    ax.set_xlabel("Raman shift (cm$^{-1}$)", fontsize=18, labelpad=10)
    ax.set_ylabel("Intensity", fontsize=18, labelpad=10)
    # Always keep the noise window visible even if it sits outside the display.
    xlo = min(dmin, s_lo, n_lo); xhi = max(dmax, s_hi, n_hi)
    pad = 0.02 * (xhi - xlo)
    ax.set_xlim(xlo - pad, xhi + pad)
    ax.grid(True, linestyle=":", linewidth=0.6, color="#bbbbbb", alpha=0.6)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=4,
              fontsize=13, framealpha=0.0, handletextpad=0.6,
              columnspacing=1.5, borderaxespad=0.0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    if np.isfinite(snr):
        sig_str = f"{sig_peak_n:.3f}" if np.isfinite(sig_peak_n) else "NaN"
        noise_str = f"{noise_n:.4f}" if np.isfinite(noise_n) else "NaN"
        info = (f"signal peak (normalised) = {sig_str}\n"
                f"noise (flat_region, normalised) = {noise_str}\n"
                f"SNR = signal / noise = {snr:.1f}")
        ax.text(0.985, 0.04, info, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=12, family="monospace", color="#222222",
                bbox=dict(facecolor="white", edgecolor="#888888",
                          linewidth=0.6, pad=6.0, alpha=0.92), zorder=5)

    _save_fig(fig, out_base, cfg)


def plot_one(row, cfg):
    try:
        df = pd.read_parquet(row["Output_Parquet"])
        wn = df["Wave"].values
        intensity = df["Original_Intensity"].values
        baseline = df["Baseline"].values
        corrected = df["Baseline_Corrected"].values
        smoothed = df["Smoothed"].values
        snr = row["SNR"]

        stem = os.path.splitext(os.path.basename(row["Output_Parquet"]))[0]
        if stem.endswith("_bs+sm"):
            stem = stem[:-6]

        # Single consolidated plots root, mirroring any input subfolders to
        # avoid filename collisions.
        plot_dir = os.path.join(cfg["output_dir"], "plots")
        rel = row["Relative_Folder"]
        if rel and rel != "[ROOT]":
            plot_dir = os.path.join(plot_dir, rel)
        os.makedirs(plot_dir, exist_ok=True)

        dmin = cfg["plot_display_min"] if cfg["plot_display_min"] is not None else float(np.min(wn))
        dmax = cfg["plot_display_max"] if cfg["plot_display_max"] is not None else float(np.max(wn))

        _plot_preprocessing(wn, intensity, baseline, corrected, smoothed,
                            stem, cfg["method"], dmin, dmax,
                            os.path.join(plot_dir, f"{stem}_preprocessing"), cfg)
        _plot_snr(wn, corrected, smoothed, snr, stem, dmin, dmax,
                  os.path.join(plot_dir, f"{stem}_snr"), cfg)

        return (True, row["Output_Parquet"])
    except Exception as e:
        return (False, {"Parquet": row["Output_Parquet"], "Error": str(e)})


def run(cfg):
    input_dir = cfg["input_dir"]
    output_dir = cfg["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("SCRIPT VERSION: STEP1_PNG_ONLY_WITH_TQDM")
    print(f"PLOTTING: {'ON' if cfg['save_plots'] else 'OFF'}")
    if cfg["save_plots"]:
        print("Plot format        - PNG only")
        print(f"Plot root          - {os.path.join(output_dir, 'plots')}")
        print(f"Plots only low SNR - {'ON' if cfg['plots_only_low_snr'] else 'OFF'}")
    else:
        print("Plot output        - disabled")
    print(f"TQDM PROGRESS: {'ON' if _tqdm_is_on(cfg) else 'OFF'}")
    if cfg.get("tqdm_enabled", True) and not _HAVE_TQDM:
        print("TQDM note          - tqdm is not installed; install with: pip install tqdm")
    print("=" * 60)

    files = discover_input_files(input_dir)
    if not files:
        print(f"No supported files found in {input_dir}")
        return

    n_workers = cfg["n_workers"] or (os.cpu_count() or 4)
    total = len(files)
    print(f"Found {total} files | workers: {n_workers}")
    if cfg["method"] == "ZhangFit":
        print(f"Baseline: ZhangFit lambda={cfg['zhang_lambda']}, "
              f"porder={cfg['zhang_porder']}, reps={cfg['zhang_repitition']}")
    elif cfg["method"] in ("ModPoly", "IModPoly"):
        print(f"Baseline: {cfg['method']} degree={cfg['poly_degree']}, "
              f"iters={cfg['iters']}, conv={cfg['conv_thresh']}")
    elif cfg["method"] == "ALS":
        print(f"Baseline: ALS lam={cfg['lam_als']}, p={cfg['p_als']}")
    if cfg["sg_mode"] == "fixed":
        print(f"SG: fixed window {cfg['sg_fixed_window']}, order {cfg['sg_fixed_poly']}")
    else:
        print(f"SG: resolution-aware {cfg['sg_target_width_cm']} cm^-1, "
              f"order {cfg['sg_poly_order']}")
    print(f"Signal {cfg['sig_min']:.0f}-{cfg['sig_max']:.0f} | "
          f"Noise {cfg['noise_min']:.0f}-{cfg['noise_max']:.0f} | "
          f"threshold {cfg['snr_threshold']}")
    print("=" * 60)

    # Phase 1: process
    print("[Phase 1] Baseline + smoothing + SNR ...")
    if _HAVE_JOBLIB and n_workers != 1:
        with tqdm_joblib(_make_pbar("Phase 1 preprocessing", total, cfg)):
            results = Parallel(n_jobs=n_workers, backend="loky")(
                delayed(process_one)(rec, output_dir, cfg) for rec in files)
    else:
        results = [
            process_one(rec, output_dir, cfg)
            for rec in _iter_progress(files, "Phase 1 preprocessing", total, cfg)
        ]

    ok_rows = []
    skipped = []
    for ok, info in _iter_progress(results, "Collect process results", len(results), cfg):
        if ok:
            ok_rows.append(info)
        else:
            skipped.append(info)

    #SNR summary
    if ok_rows:
        summary_records = []
        for r in _iter_progress(ok_rows, "Build SNR summary table", len(ok_rows), cfg):
            summary_records.append({
                "File": r["File"],
                "Relative_Folder": r["Relative_Folder"],
                "SNR": (round(r["SNR"], 2) if np.isfinite(r["SNR"]) else np.nan),
                "SNR_Flag": r["SNR_Flag"],
                "Output_Parquet": r["Output_Parquet"],
            })

        snr_df = pd.DataFrame(summary_records).sort_values(
            "SNR", ascending=True, na_position="first")
        snr_csv = os.path.join(output_dir, "snr_summary.csv")
        snr_df.to_csv(snr_csv, index=False)
        n_low = int((snr_df["SNR_Flag"] == "LOW").sum())
        n_unmeas = int((snr_df["SNR_Flag"] == "UNMEASURABLE").sum())

        print("[Summary plot] SNR distribution ...")
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = [
            "tomato" if f == "LOW" else ("lightgrey" if f == "UNMEASURABLE" else "steelblue")
            for f in _iter_progress(snr_df["SNR_Flag"], "Build SNR plot colors", len(snr_df), cfg)
        ]
        ax.bar(range(len(snr_df)), snr_df["SNR"].fillna(0), color=colors)
        ax.axhline(cfg["snr_threshold"], color="red", ls="--", lw=1.5,
                   label=f"Threshold = {cfg['snr_threshold']}")
        ax.set_xlabel("File index (sorted by SNR)")
        ax.set_ylabel("SNR")
        ax.set_title(f"SNR distribution -- {n_low} low, {n_unmeas} unmeasurable")
        ax.legend()
        fig.tight_layout()
        plots_root = os.path.join(output_dir, "plots")
        os.makedirs(plots_root, exist_ok=True)
        fig.savefig(os.path.join(plots_root, "snr_distribution.png"), dpi=120)
        plt.close(fig)
        print(f"SNR summary - {snr_csv}  ({n_low} low, {n_unmeas} unmeasurable)")

    #plots
    if cfg["save_plots"] and ok_rows:
        to_plot = [
            r for r in _iter_progress(ok_rows, "Select rows to plot", len(ok_rows), cfg)
            if (not cfg["plots_only_low_snr"]) or r["Low_SNR_Flag"]
        ]
        print(f"[Phase 2] Plotting {len(to_plot)} diagnostics ...")
        if _HAVE_JOBLIB and n_workers != 1:
            with tqdm_joblib(_make_pbar("Phase 2 diagnostic PNGs", len(to_plot), cfg)):
                plot_res = Parallel(n_jobs=n_workers, backend="loky")(
                    delayed(plot_one)(r, cfg) for r in to_plot)
        else:
            plot_res = [
                plot_one(r, cfg)
                for r in _iter_progress(to_plot, "Phase 2 diagnostic PNGs", len(to_plot), cfg)
            ]

        plot_fail = []
        for ok, info in _iter_progress(plot_res, "Collect plot results", len(plot_res), cfg):
            if not ok:
                plot_fail.append(info)
        for p in plot_fail:
            print(f"  plot error: {p['Parquet']} - {p['Error']}")

    #Summary
    print("=" * 60)
    print(f"Done: {len(ok_rows)}/{total} processed")
    if skipped:
        print(f"Skipped ({len(skipped)}):")
        for s in skipped:
            print(f"  x {s['Relative_Folder']} | {s['File']} - {s['Error']}")
    print(f"Output - {output_dir}")

def build_cfg(args):
    return {
        "input_dir": args.input,
        "output_dir": args.output,
        "method": args.method,
        "zhang_lambda": args.zhang_lambda,
        "zhang_porder": ZHANG_PORDER,
        "zhang_repitition": ZHANG_REPITITION,
        "poly_degree": args.poly_degree,
        "iters": args.iters,
        "conv_thresh": args.conv_thresh,
        "lam_als": args.lam_als,
        "p_als": args.p_als,
        "sg_mode": args.sg_mode,
        "sg_target_width_cm": args.sg_width,
        "sg_poly_order": SG_POLY_ORDER,
        "sg_fixed_window": args.sg_fixed_window,
        "sg_fixed_poly": args.sg_fixed_poly,
        "sig_min": args.sig_min, "sig_max": args.sig_max,
        "noise_min": args.noise_min, "noise_max": args.noise_max,
        "snr_threshold": args.threshold,
        "save_plots": not args.no_plots,
        "plots_only_low_snr": args.plots_only_low_snr,
        "tqdm_enabled": not args.no_tqdm,
        "plot_display_min": args.display_min,
        "plot_display_max": args.display_max,
        "n_workers": args.workers,
    }


def main():
    ap = argparse.ArgumentParser(description="Step 1 Raman preprocessing (headless).")
    ap.add_argument("--input", default=INPUT_DIR)
    ap.add_argument("--output", default=OUTPUT_DIR)
    ap.add_argument("--method", default=METHOD,
                    choices=["ZhangFit", "ModPoly", "IModPoly", "ALS"])
    ap.add_argument("--zhang-lambda", type=float, default=ZHANG_LAMBDA, dest="zhang_lambda")
    ap.add_argument("--poly-degree", type=int, default=POLY_DEGREE, dest="poly_degree")
    ap.add_argument("--iters", type=int, default=ITERS)
    ap.add_argument("--conv-thresh", type=float, default=CONV_THRESH, dest="conv_thresh")
    ap.add_argument("--lam-als", type=float, default=LAM_ALS, dest="lam_als")
    ap.add_argument("--p-als", type=float, default=P_ALS, dest="p_als")
    ap.add_argument("--sg-mode", default=SG_MODE,
                    choices=["resolution_aware", "fixed"], dest="sg_mode")
    ap.add_argument("--sg-width", type=float, default=SG_TARGET_WIDTH_CM, dest="sg_width")
    ap.add_argument("--sg-fixed-window", type=int, default=SG_FIXED_WINDOW, dest="sg_fixed_window")
    ap.add_argument("--sg-fixed-poly", type=int, default=SG_FIXED_POLY, dest="sg_fixed_poly")
    ap.add_argument("--sig-min", type=float, default=SNR_SIG_MIN, dest="sig_min")
    ap.add_argument("--sig-max", type=float, default=SNR_SIG_MAX, dest="sig_max")
    ap.add_argument("--noise-min", type=float, default=SNR_NOISE_MIN, dest="noise_min")
    ap.add_argument("--noise-max", type=float, default=SNR_NOISE_MAX, dest="noise_max")
    ap.add_argument("--threshold", type=float, default=SNR_THRESHOLD)
    ap.add_argument("--workers", type=int, default=N_WORKERS)
    ap.add_argument("--no-plots", action="store_true", default=not SAVE_PLOTS)
    ap.add_argument("--plots-only-low-snr", action="store_true",
                    default=PLOTS_ONLY_LOW_SNR, dest="plots_only_low_snr")
    ap.add_argument("--no-tqdm", action="store_true", default=not TQDM_ENABLED,
                    help="Disable tqdm progress bars.")
    ap.add_argument("--display-min", type=float, default=PLOT_DISPLAY_MIN, dest="display_min")
    ap.add_argument("--display-max", type=float, default=PLOT_DISPLAY_MAX, dest="display_max")
    args, _ = ap.parse_known_args()
    run(build_cfg(args))


if __name__ == "__main__":
    main()