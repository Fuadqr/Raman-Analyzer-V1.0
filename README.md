# Raman-Analyzer-V1.0
# Code Overview

The new Python code provides a comprehensive set of functionalities for Raman spectroscopy data analysis:

## 1. Baseline Removal
The user has the flexibility to choose from four baseline removal methods:

a. **Asymmetric Least Squares (ALS)**
   - Developed by P. Eilers and H. Boelens (2005).
   - Source: [StackOverflow - Python Baseline Correction Library]

b. **BaselineRemoval Package**
   - Developed by Md Azimul Haque (2022).
   - Implements three methods:
     - **Modpoly:** Modified multi-polynomial fit by Lieber & Mahadevan-Jansen (2003).
     - **IModPoly:** Improved ModPoly by Zhao (2007).
     - **ZhangFit:** Adaptive iteratively reweighted penalized least squares by Zhi-Min Zhang (2010).
   - Source: [PyPI – BaselineRemoval]

## 2. Smoothing
The code offers smoothing using the Savitzky-Golay filter, commonly used for noisy data. Users can specify:
   - The length of the smoothing window.
   - The order of the polynomial used for fitting the data within the window.
   - Implementation available in the SciPy library.
   - Source: [SciPy - savgol_filter]

## 3. Peak Picking
The code includes a peak-picking algorithm to identify local maxima in the signal. Users can customize:
   - The minimum peak height.
   - The minimum horizontal peak spacing.
   - The minimum peak width.
   - Implementation available in the SciPy library.
   - Source: [SciPy - find_peaks]

## 4. Plotting (Optional)
The code provides an optional plotting feature for data visualization.

## 5. Determine the Type of an Unknown Polymer
The code enables users to determine the type of an unknown polymer by comparing the Raman shift values. Users can specify:
   - The absolute difference between the peaks of the unknown polymer and the values in a polymer library.
   - The percentage of closeness or similarity, which can be highlighted based on this difference.

This Python code offers a versatile toolbox for Raman spectroscopy data analysis, with various customization options for baseline removal, smoothing, peak picking, and polymer identification.

---
