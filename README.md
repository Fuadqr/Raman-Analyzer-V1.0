# Raman-Analyzer-V1.0
# Code Overview
![Before Image](/ReadmeIMG/Before.png)
![After Image](/ReadmeIMG/After.png)


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
The code enables users to determine the type of an unknown polymer by comparing the peaks values. Users can specify:
   - The absolute difference between the peaks of the unknown polymer and the values in a polymer library.
   - The percentage of closeness or similarity, which can be highlighted based on this difference.

This Python code offers a versatile toolbox for Raman spectroscopy data analysis, with various customization options for baseline removal, smoothing, peak picking, and polymer identification.

---
# **! Important !**
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
