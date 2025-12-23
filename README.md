# Raman-Analyzer-V1.0
# Code Overview

**Raman Analyzer** is an **open-source Python tool** (with an optional **Windows-based GUI**) designed for **automated, high-throughput analysis of Raman spectroscopy data**, with a particular focus on **microplastic (MP) polymer identification**.  
The tool integrates **established spectral pre-processing techniques** with a **dual-algorithm matching framework** that combines **peak-based matching** and **full-spectrum correlation analysis**, enabling **robust, reproducible, and dataset-adaptive polymer identification**.

## 1. Spectral Pre-processing

To account for variability in Raman signal quality and fluorescence interference, Raman Analyzer provides user-configurable pre-processing workflows, including baseline correction and spectral smoothing.

**a. Baseline Removal**

Four baseline correction methods are implemented, allowing users to select the most suitable approach for their dataset:

-Asymmetric Least Squares (ALS) Based on Eilers & Boelens (2005).

-BaselineRemoval Package by Md Azimul Haque (2022), implementing:

   -- ModPoly - Modified multi-polynomial fitting 
   
   
   -- IModPoly - Improved ModPoly 
   
   
   -- ZhangFit - Adaptive iteratively reweighted penalized least squares 


**b. Spectral Smoothing**

Noise reduction and signal-to-noise ratio (SNR) enhancement are performed using the Savitzky-Golay filter (SciPy implementation). Users can define:

-Smoothing window length (in cm⁻¹)

-Polynomial order

-This step is essential for improving peak detection and correlation accuracy, particularly for low-intensity or coloured particles.


## 2. Spectral Normalization and Exclusion Ranges

-After pre-processing, spectra are min–max normalized over a user-defined spectral range (typically 800-1800 cm⁻¹, the MPs fingerprint region).

-Optional exclusion ranges can be specified to remove Instrumental artefacts or Fluorescence-related features (e.g. Nile Red interference around 1488 cm⁻¹)


## 3. Dual-Algorithm Polymer Matching Framework

Polymer identification is performed using a combined similarity scores:

**a. Peak-Based Matching**

-Local maxima are detected using scipy.signal.find_peaks

-A user-defined number of the most prominent peaks is selected

-Peak positions are matched against a reference library using a configurable tolerance (typically ±10 cm⁻¹)

-A Peak Matching Score quantifies the fraction of characteristic peaks shared between unknown and reference spectra

**b. Full-Spectrum Correlation**

-Normalized spectra are interpolated onto a common Raman shift grid

-Pearson correlation coefficients are computed across the full spectral range

-Correlation values are scaled to a 0-100 Correlation Score (CS)

**c. Combined Similarity Score**

The final Hit Quality Index (HQI) is computed as a weighted combination of PMS and CS, with user-defined weighting factors. Validation results demonstrate that combining peak matching with full-spectrum correlation substantially improves identification accuracy and reduces false or dual matches compared to peak-only approaches.

## 4. Reference Spectral Library

-Raman Analyzer includes a reference library of 254 Raman spectra, consisting of: In-house curated spectra and another Open-source libraries (SLoPP and SLoPP-E)

-The library covers 14 polymer types and common non-polymer classes, supporting both pristine and environmentally relevant microplastic samples.


## 5. Batch Processing and Output

-Supports CSV, TXT, and Excel spectral input formats

-Enables automated batch analysis of large spectral datasets using consistent parameter settings

-Outputs results in structured spreadsheet formats for rapid interpretation and reporting

-Optional plotting functionality for visual inspection of spectras, detected peaks, and matching results

## 6. Graphical User Interface (GUI)

A Windows-based GUI is provided to make Raman Analyzer accessible to users without programming experience. The GUI supports:

-Parameter configuration

-Batch processing

-Automated result export

After downloading the GUI from the GitHub repository (RamanAnalyzer_v1.0.exe) 
The first step is to prepare the spectral data by downloading both the reference library (containing known spectra) and your unknown spectra (you can test with the validation spectra from GitHub or any spectra of unknown polymers you wish to analyse).

**In Step 1**, the user will be asked to process the reference library and unknown spectra folders one at a time by uploading each folder separately, for each one, the user needs to specify a different output directory. This pre-processing is essential step ensures that baseline correction and smoothing are applied to both datasets.

**In Step 2**, the user needs to load the processed folders from Step 1 for the comparison analysis. The user needs to select the unknown polymers folder and the known polymers folder, then specify the location where the actual output Excel file will be saved. Optionally, the user can also choose a location to save the generated comparison plots.

During this step, the user can chose several analysis parameters including Range Min/Max to define the Raman shift range for analysis (in cm⁻¹), Peak Tolerance for peak matching, Number of Top Peaks to prioritize in the comparison, and Similarity Threshold which is the percentage threshold for highlighting matches (polymers achieving this similarity percentage or higher will be highlighted in yellow in the output Excel file). Additionally, the user must configure Peak Weight and Pearson Weight, ensuring these two values sum to exactly 1.0 before the analysis can begin.
Additional options are available if the user wishes to customize the analysis further, including Exclusion Range to not include specific regions from the analysis, Generate Plots to create visual comparisons, and Save Peak Data to export detailed peak information.


---
# **! Important for python code users !**
### **Before running the code, make sure to have the following Python libraries installed:**
---
- [`numpy`](https://pypi.org/project/numpy/): Import as `np`. Usually installed with `pip install numpy`.
- [`pandas`](https://pypi.org/project/pandas/): Import as `pd`. Usually installed with `pip install pandas`.
- [`matplotlib`](https://pypi.org/project/matplotlib/): Specifically, `matplotlib.pyplot`, import as `plt`. Usually installed with `pip install matplotlib`.
- [`scipy`](https://pypi.org/project/scipy/): Includes `sparse`, `sparse.linalg` (as `spsolve`), and `signal` (as `savgol_filter`, `find_peaks`). Usually installed with `pip install scipy`.
- [`ipywidgets`](https://pypi.org/project/ipywidgets/): Import as `widgets`. Usually installed with `pip install ipywidgets`.
- [`IPython`](https://pypi.org/project/ipython/): Specifically, `IPython.display`, import as `display`. Usually installed with `pip install ipython`.
- [`BaselineRemoval`](https://pypi.org/project/BaselineRemoval/): For baseline removal algorithms. Usually installed with `pip install BaselineRemoval`.
- [`openpyxl`](https://pypi.org/project/openpyxl/): Import as `Workbook`, `NamedStyle`, and use `utils.dataframe` (as `dataframe_to_rows`). Usually installed with `pip install openpyxl`.
- [`xlsxwriter`](https://pypi.org/project/XlsxWriter/): For writing files in the XLSX file format. Usually installed with `pip install XlsxWriter`.

---
