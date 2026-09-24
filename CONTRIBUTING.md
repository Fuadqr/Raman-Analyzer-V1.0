# Contributing Spectra to the Raman Analyzer Reference Library

The Raman Analyzer reference library is designed to grow. Contributions of new
Raman spectra are welcome, particularly for:

- polymer classes currently represented by a single spectrum (Tier C)
- copolymers and polymer blends
- environmentally weathered and aged microplastics
- polymer classes not yet present in the library
- non-polymer materials commonly co-occurring in microplastic samples
  (minerals, natural fibres, biological material)

To preserve the integrity of the library, spectra are not added automatically.
Every submission passes the same quality control and tier assignment as the
original compilation.

---

## 1. How to submit

**Option A - GitHub (preferred)**

1. Open an issue using the "Spectrum contribution" template, or
2. Open a pull request adding your spectra under `contributions/<your-name-or-institution>/`.

**Option B - Email**

Send your spectra and metadata to the corresponding author:
f.y.m.alqrinawi@bham.ac.uk

---

## 2. File format

Each spectrum must be a separate file in one of the following formats:

| Format | Extension |
|---|---|
| Comma-separated | `.csv` |
| Excel | `.xlsx` |
| Tab-delimited text | `.txt` |

Each file must contain **two columns**:

| Column 1 | Column 2 |
|---|---|
| Raman shift (cm<sup>-1</sup>) | Intensity |

Notes:

- Submit **raw spectra** where possible. If the spectra have already been
  baseline-corrected or smoothed, state this in the metadata so that
  double-processing is avoided.
- Do not truncate spectra. The wider the spectral range, the more useful the
  reference (the default matching window is 500 to 3500 cm<sup>-1</sup>).
- One file per spectrum. Do not merge multiple spectra into one file.
- Use a consistent file-naming scheme, for example
  `PE_HDPE_pristine_001.csv`.

---

## 3. Required metadata

Submit a single `metadata.csv` covering all contributed spectra, with one row
per file. The following fields are required:

| Field | Description | Example |
|---|---|---|
| `filename` | File name of the spectrum | `PE_HDPE_pristine_001.csv` |
| `polymer` | Polymer class or material | `HDPE` |
| `identity_verified_by` | How the identity was confirmed | `supplier-grade reference material` |
| `sample_origin` | Pristine, weathered, or environmental | `environmental (marine surface water)` |
| `instrument` | Make and model | `Renishaw inVia Qontor` |
| `laser_wavelength_nm` | Excitation wavelength | `785` |
| `grating` | Grating used, if known | `1200 l/mm` |
| `objective` | Objective used, if known | `50x` |
| `laser_power_mW` | Power at the sample, if known | `30` |
| `acquisition_time_s` | Accumulation time, if known | `10` |
| `preprocessing` | Any processing already applied | `none` |
| `contributor` | Name and affiliation for credit | `X, University of Y` |
| `licence` | Licence under which the spectra are released | `CC-BY 4.0` |
| `reference` | Publication or DOI, if applicable | `10.1021/xxxxx` |
| `notes` | Anything else relevant | `pigmented, blue fragment` |

A template is provided in `contributions/metadata_template.csv`.

**Licensing.** Only submit spectra you have the right to release. By
contributing, you confirm that the spectra may be redistributed as part of the
reference library under the stated licence. If no licence is stated, CC-BY 4.0
is assumed.

---

## 4. What happens to a submission

1. **Preprocessing.** Baseline correction (adaptive iteratively reweighted
   penalised least squares) and Savitzky-Golay smoothing, unless the spectra
   were already processed by the contributor.
2. **Quality screening.** The signal-to-noise ratio is computed for each
   spectrum. Spectra with SNR below 5, and spectra for which SNR cannot be
   computed, are not added to the library.
3. **Tier assignment.** Each accepted spectrum is compared with the existing
   spectra of the same polymer class and assigned to Tier A, B, or C according
   to how many in-class spectra it agrees with at r >= 0.90. Where a class
   contains more than one internally consistent group, sub-tiers are preserved
   (A.1, A.2, and so on).
4. **Release.** Accepted spectra are added to the versioned library release,
   credited to the contributor in the library metadata, and distributed to
   users through the built-in library updater in the GUI.

Submissions that do not pass quality screening are reported back to the
contributor with the reason, so they can be resubmitted after remeasurement if
desired.

---

## 5. Reporting bugs and requesting features

For software issues unrelated to spectra, please open a GitHub issue including:

- the Raman Analyzer version
- your operating system
- the steps needed to reproduce the problem
- the log output shown in the application, where relevant

---

## 6. Citation

If you use the Raman Analyzer or its reference library, please cite:

> Alqrinawi, F., Kelleher, L., Haverson, L., Schneidewind, U., Comer-Warner, S.,
> Lynch, I., Krause, S. The Raman Analyzer: an open-source framework for
> reproducible Raman identification of microplastic polymers. (under review)

Contributors of spectra are credited in the library metadata and in the release
notes of the library version in which their spectra first appear.
