#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.signal import savgol_filter, find_peaks
import ipywidgets as widgets
from IPython.display import display
from BaselineRemoval import BaselineRemoval  # Assuming you have a baseline removal library

# Function to estimate baseline using ALS
def baseline_als(y, lam, p, niter=10):
    L = len(y)
    D = sparse.csc_matrix(np.diff(np.eye(L), 2))
    w = np.ones(L)
    for i in range(niter):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + lam * D.dot(D.transpose())
        z = spsolve(Z, w*y)
        w = p * (y > z) + (1-p) * (y < z)
    return z

# Function to process and plot the data for all methods
def process_and_plot(data,method, poly_degree, iters, conv_thresh, lambda_zhang, porder, repitition, lam_als, p_als,
                     window_length, poly_order,
                     peak_prominence, peak_distance, peak_width):
    plt.figure(figsize=(20,12))
    #plt.plot(data['Wave'], data['Intensity'], label='Original Data', color='grey')

    if method == 'ALS':
        baseline = data['Intensity'].values-baseline_als(data['Intensity'].values, lam_als, p_als)
        # For ALS, plot only the estimated baseline
        #plt.plot(data['Wave'], baseline, 'r--', label='Estimated Baseline (ALS)', linewidth=2)
    else:
        baseObj = BaselineRemoval(data['Intensity'].values)
        if method == 'ModPoly':
            baseline = baseObj.ModPoly(poly_degree, iters, conv_thresh)
        elif method == 'IModPoly':
            baseline = baseObj.IModPoly(poly_degree, iters, conv_thresh)
        elif method == 'ZhangFit':
            baseline = baseObj.ZhangFit(lambda_=lambda_zhang, porder=porder, repitition=repitition)
            
        
    
    smoothed_output = savgol_filter(baseline, window_length, poly_order)

    # Peak finding
    peaks, properties = find_peaks(
        smoothed_output, 
        prominence=peak_prominence, 
        distance=peak_distance, 
        width=peak_width
    )

    # Collecting Peak Values
    
    peak_wavelengths = data['Wave'].iloc[peaks].values
    peak_intensities = smoothed_output[peaks]

    # Create a Pandas DataFrame for the peak data
    peak_data = {
        'Raman shift [1/cm]': peak_wavelengths,
        'intensity': peak_intensities
    }
    peak_df = pd.DataFrame(peak_data)
    
    
    corrected_intensity = data['Intensity'].values - baseline
    
    half_line = '-' * 40
    stars = '*' * 40
    print(stars)
    print("These graphs are based on these values:")
    print(stars)
    print(f"method: {method}")
    print(half_line)
    print("Parameters for ModPoly and IModPoly:")
    print(f"poly_degree: {poly_degree}")
    print(f"iters: {iters}")
    print(f"conv_thresh: {conv_thresh}")
    print(half_line)
    print("Parameters for Zhang Method:")
    print(f"lambda_zhang: {lambda_zhang}")
    print(f"porder: {porder}")
    print(f"repitition: {repitition}")
    print(half_line)
    print("Parameters for ALS Method:")
    print(f"lam_als: {lam_als}")
    print(f"p_als: {p_als}")
    print(half_line)
    print("Parameters for Smoothing:")
    print(f"window_length: {window_length}")
    print(f"poly_order: {poly_order}")
    print(half_line)
    print("Parameters for Peak Picking:")
    print(half_line)
    print(f"peak_prominence: {peak_prominence}")
    print(f"peak_distance: {peak_distance}")
    print(f"peak_width: {peak_width}")
    print(stars)
    
        # For other methods, plot both the estimated baseline and corrected intensity
    plt.figure(figsize=(12, 12))

    # Plot the first set of data
    plt.subplot(2, 1, 1)
    plt.plot(data['Wave'], data['Intensity'], label='Original Data', color='grey')
    plt.plot(data['Wave'], corrected_intensity, 'g--', label='Baseline')
    plt.plot(data['Wave'], baseline, color='blue', label='Original Data - Baseline', linewidth=1)
    #plt.plot(data['Wave'], smoothed_output, 'b--', label='Smoothed Data', linewidth=2)
    #plt.plot(peak_wavelengths, peak_intensities, "x", color='red', label='Peaks', markersize=10, linewidth=10)

    plt.legend(fontsize=20)
    plt.tick_params(axis='both', which='major', labelsize=15)
    #plt.xlabel('Raman Shift', fontsize=20)
    plt.ylabel('Intensity', fontsize=20)
    plt.title(f'Spectrum Analysis using {method} Method', fontsize=20)

    # Plot the second set of data beneath the first one
    plt.subplot(2, 1, 2)
    plt.plot(data['Wave'], smoothed_output, 'b--', label='Smoothed Data', linewidth=2)
    plt.plot(peak_wavelengths, peak_intensities, "x", color='red', label='Peaks', markersize=10, linewidth=10)

    plt.legend(fontsize=20)
    plt.tick_params(axis='both', which='major', labelsize=15)
    plt.xlabel('Raman Shift', fontsize=20)
    plt.ylabel('Intensity', fontsize=20)

    plt.tight_layout()
    plt.show()

