#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import pandas as pd
import numpy as np
import xlsxwriter

def analyze_and_save_data_V2(input_excel_path, peaks_excel_path, output_excel_path, highlight_threshold, atol):
    try:
       
        # Input the peaks data
        kn_poly_data = pd.read_excel(peaks_excel_path)

        # Clean the peaks data
        kn_poly_data_clean = kn_poly_data.fillna(0).drop('Name', axis=1)
        poly_type = kn_poly_data_clean.iloc[0, :]

        # Open the input Excel file and get the list of sheet names
        xls = pd.ExcelFile(input_excel_path)
        sheet_names = xls.sheet_names

        # Create a Pandas Excel writer using XlsxWriter
        with pd.ExcelWriter(output_excel_path, engine='xlsxwriter') as writer:
            for sheet_name in sheet_names:
                
                # Load the datasets for the current sheet only
                unkn_poly_data = pd.read_excel(input_excel_path, sheet_name=sheet_name, names=['Raman shift', 'Intensity', 'FWHM'], header=None)

                # The input data
                data = unkn_poly_data

                # Selects the data and creates an end value so no data is skipped || Liam
                data_filler = pd.DataFrame([['Spectrum:', 'Filler']], columns=['Raman shift', 'Intensity'])
                data = pd.concat([data, data_filler])

                # Get the name || Liam
                data = data[data['Raman shift'] != 'Raman shift [1/cm]']
                data.index = data.Intensity
                file_names = data[data['Raman shift'] == 'Spectrum:']['Intensity']

                results = []
                for current_file, next_file in zip(file_names, file_names[1:]):
                    data_subset = data.loc[current_file:next_file]
                    data_subset = data_subset.iloc[:-2]
                    partial_results = []
                    # Iterate over Raman shift values in the subset
                    for raman_shift in list(data_subset['Raman shift'].iloc[2:]):
                        # Check if there is a close match in peaks_data_clean using isclose
                        is_close = np.isclose(kn_poly_data_clean, b=raman_shift, atol=atol).any(axis=0)
                        partial_results.append(is_close)

                    # Calculate the percentage of True values and append to results
                    percentage = (np.count_nonzero(np.vstack(partial_results), axis=0) / poly_type) * 100
                    results.append(percentage)

                # Create a DataFrame from the results
                result_df = pd.DataFrame(results).T
                result_df.columns = list(file_names[:-1])
                
                result_df.index.name = "Name"

                # Find the polymer(s) with the highest percentage for each column and apply threshold filter
                max_percentage_poly = result_df.idxmax(axis=0)
                max_percentage_values = result_df.max(axis=0)
                threshold_met = max_percentage_values >= highlight_threshold
                max_percentage_poly_filtered = max_percentage_poly.where(threshold_met, '')

                # Add a new row at the bottom of the DataFrame with the names of the polymer(s)
                result_df.loc['Poly type'] = max_percentage_poly_filtered

                # Write the result_df to the current sheet in the output Excel file
                result_df.to_excel(writer, sheet_name=sheet_name, index=True, float_format="%.2f")

                # Get the xlsxwriter workbook and worksheet objects for formatting
                workbook = writer.book
                worksheet = writer.sheets[sheet_name]

                # Define the format to use for cells with values greater than the threshold
                format_high = workbook.add_format({'bg_color': 'yellow', 'font_color': 'red'})

                # Apply conditional formatting to the desired cells
                worksheet.conditional_format('B2:XFD1000', {'type': 'cell',
                                                          'criteria': '>',
                                                          'value': highlight_threshold,
                                                          'format': format_high})

                print(f"Sheet '{sheet_name}' analysis and Excel file creation completed!")

        print("All sheets processed and saved to your output Excel file.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

