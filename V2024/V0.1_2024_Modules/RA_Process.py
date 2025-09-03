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
from BaselineRemoval import BaselineRemoval  
import os
from openpyxl import Workbook
from openpyxl.styles import Alignment, NamedStyle
from openpyxl.utils.dataframe import dataframe_to_rows


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
def process_and_plot(file_path,method, poly_degree, iters, conv_thresh, lambda_zhang, porder, repitition, lam_als, p_als,
                     window_length, poly_order,
                     peak_prominence, peak_distance, peak_width, ws):
    
    try:
        # Reading the data
        data = pd.read_csv(file_path, names=['Wave', 'Intensity'], comment='#')
        print(f"Data from {file_path}:")  # Debugging print statement
        print(data.head())  # Print the first few rows of the data
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

            # Smoothing
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
                'Intensity': peak_intensities
            }
            peak_df = pd.DataFrame(peak_data)

            # Sort peak data by Raman shift (ascending)
            peak_df.sort_values(by='Raman shift [1/cm]', ascending=True, inplace=True)

            # Create a named style for numeric formatting
            numeric_style = NamedStyle(name='numeric')
            numeric_style.number_format = '0.00'

            # Write headers with alignment
            ws.append(['Spectrum:', os.path.splitext(os.path.basename(file_path))[0]])
            ws.append(['', ''])
            ws.append(['', ''])
            ws.append(['Raman shift [1/cm]', 'Intensity'])

            # Write peak data with formatting, skipping the header
            for row in dataframe_to_rows(peak_df, index=False, header=False):
                ws.append([round(row[0], 2), round(row[1], 2)])
            ws.append(['', ''])
    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def process_files_in_folder(folder_path, output_excel_file, method, poly_degree, iters, conv_thresh, lambda_zhang, porder, repitition, lam_als, p_als,
                            window_length, poly_order, peak_prominence, peak_distance, peak_width):
    # Create a new Excel workbook
    wb = Workbook()
    ws = wb.active

    print(f"Checking all files in {folder_path}")  # Debugging print statement
    files_processed = 0  # Counter for files processed
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            print(f"Processing file: {file_path}")  # Debugging print statement
            try:
                # Call process_and_plot function for each file with 'ws' parameter
                process_and_plot(file_path=file_path,
                                 method=method,
                                 poly_degree=poly_degree,
                                 iters=iters,
                                 conv_thresh=conv_thresh,
                                 lambda_zhang=lambda_zhang,
                                 porder=porder,
                                 repitition=repitition,
                                 lam_als=lam_als,
                                 p_als=p_als,
                                 window_length=window_length,
                                 poly_order=poly_order,
                                 peak_prominence=peak_prominence,
                                 peak_distance=peak_distance,
                                 peak_width=peak_width,
                                 ws=ws)
                files_processed += 1
            except Exception as e:
                print(f"Failed to process {file_path}: {e}")

    # Create a named style for numeric formatting
    numeric_style = NamedStyle(name='numeric')
    numeric_style.number_format = '0.00'
    # Apply the numeric style to the cells in the data section
    for row in ws.iter_rows(min_row=3, min_col=2, max_col=2):
        for cell in row:
            cell.style = numeric_style

    # Save the Excel file
    wb.save(output_excel_file)
    print(f"Peak data saved to {output_excel_file}")

