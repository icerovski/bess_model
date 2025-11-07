import pandas as pd
import sys
import itertools

def clean_data(filepath="data/inputs.csv"):
    """
    Loads and cleans the CSV file.
    - Strips whitespace from column names and key string columns.
    - Converts all numeric columns (const + years) to numeric types,
      handling commas, dashes, and stray characters.
    """
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

    # 1. Clean column names
    df.columns = df.columns.str.strip()

    # 2. Identify year columns
    year_cols = [col for col in df.columns if col.startswith('20')]
    if not year_cols:
        print("Error: No year columns found (e.g., '2026', '2027', ...)")
        sys.exit(1)

    # 3. Clean key text columns
    key_cols = ['scenario', 'category', 'parameter']
    for col in key_cols:
        if col in df.columns:
            # Handle potential float/NaN values in scenario/category cols
            df[col] = df[col].astype(str).str.strip()

    # 4. Clean all numeric columns
    num_cols = ['const'] + year_cols
    for col in num_cols:
        if col in df.columns:
            # Convert to string, remove commas, handle non-numeric dashes/blanks
            df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            df[col] = df[col].str.replace('-', 'NaN', regex=False).str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 5. Drop any rows that are *completely* empty
    df.dropna(how='all', inplace=True)
    
    # 6. Set the multi-index for easy lookup
    try:
        df = df.set_index(['scenario', 'category', 'parameter'])
    except KeyError:
        print("Error: CSV must contain 'scenario', 'category', and 'parameter' columns.")
        sys.exit(1)
        
    return df, year_cols

def get_combined_inputs(base_inputs_df, common_name, base_rev_name, trader_cogs_name):
    """
    Creates a single, combined DataFrame for a specific scenario combination.
    It overlays inputs in three levels:
    1. common
    2. base_revenue (e.g., 'base')
    3. trader_cogs (e.g., 'vitol')
    """
    try:
        common_inputs = base_inputs_df.loc[common_name]
    except KeyError:
        print(f"Error: '{common_name}' scenario not found in CSV.")
        sys.exit(1)
    
    inputs_to_combine = [common_inputs]

    try:
        base_rev_inputs = base_inputs_df.loc[base_rev_name]
        inputs_to_combine.append(base_rev_inputs)
    except KeyError:
        print(f"Warning: Base revenue scenario '{base_rev_name}' not found. Using 'common' only.")
        base_rev_inputs = pd.DataFrame(index=common_inputs.index, columns=common_inputs.columns)
        
    try:
        trader_cogs_inputs = base_inputs_df.loc[trader_cogs_name]
        inputs_to_combine.append(trader_cogs_inputs)
    except KeyError:
        print(f"Warning: Trader COGS scenario '{trader_cogs_name}' not found. Using 'common' only.")
        trader_cogs_inputs = pd.DataFrame(index=common_inputs.index, columns=common_inputs.columns)

    # Combine in order: Start with common, patch with base_rev, then patch with trader_cogs
    # Concatenate all found DataFrames. This stacks them vertically.
    combined = pd.concat(inputs_to_combine)
    
    # De-duplicate the index (category, parameter), keeping the *last* occurrence.
    # This ensures trader_cogs > base_rev > common priority.
    combined = combined[~combined.index.duplicated(keep='last')]
    
    return combined

def get_series(inputs_df, category, parameter, year_cols):
    """
    Safely retrieves a time series from the inputs DataFrame.
    - If param is not found, returns a series of zeros.
    - If 'const' has a value, it broadcasts that value across all years.
    - Otherwise, it returns the time series from the year columns.
    """
    try:
        row = inputs_df.loc[(category, parameter)]
    except KeyError:
        # Not found, return a series of zeros
        print(f"Warning: Parameter '{parameter}' in category '{category}' not found. Using 0.")
        return pd.Series([0] * len(year_cols), index=year_cols, name=parameter)

    const_val = row['const']
    
    if pd.notna(const_val):
        # Broadcast constant value
        return pd.Series([const_val] * len(year_cols), index=year_cols, name=parameter)
    else:
        # Return the time series from year columns, filling any gaps with 0
        return row[year_cols].fillna(0).rename(parameter)

def calculate_ebitda(inputs_df, year_cols):
    """
    Calculates EBITDA based on the new logic:
    EBITDA = Base Gross Margin - (Base Gross Margin * Trader COGS Percent)
    """
    
    # --- 1. Get Base Gross Margin ---
    # This comes from the 'base_revenue' scenario (e.g., 'base_1' or 'base_2')
    base_gross_margin = get_series(inputs_df, "net_revenue", "Total gross margin (base)", year_cols)

    # --- 2. Get Trader COGS ---
    # This comes from the 'trader_cogs' scenario (e.g., 'trader_1', 'trader_2', ...)
    trader_cogs_percent = get_series(inputs_df, "trader_cogs", "trader_cogs_percent", year_cols)
    
    # --- 3. Calculate Trader COGS Cost ---
    trader_cogs_cost = base_gross_margin * trader_cogs_percent

    # --- 4. Calculate EBITDA ---
    # Per logic: EBITDA = Base Gross Margin - Trader COGS Cost
    # (Assuming no other operating costs are specified in this file)
    ebitda = base_gross_margin - trader_cogs_cost

    # --- 5. Assemble Final Report ---
    report = pd.DataFrame(index=year_cols)
    report['Base Gross Margin'] = base_gross_margin
    report['Trader COGS Cost'] = trader_cogs_cost
    report['EBITDA'] = ebitda
    
    return report

# --- Main execution ---
if __name__ == "__main__":
    
    # 1. Load and clean data
    base_inputs_df, year_cols = clean_data()
    
    # 2. Define scenario combinations
    base_revenue_scenarios = ['base', 'low']
    trader_cogs_scenarios = ['vitol', 'gen-i', 'met']
    
    # Create all 6 combinations (e.g., ('base_1', 'trader_1'))
    scenario_combinations = list(itertools.product(base_revenue_scenarios, trader_cogs_scenarios))
    
    # 3. Dictionary to store results
    all_ebitda_series = {}

    print("Running EBITDA calculations for 6 scenario combinations...")

    # 4. Loop, calculate, and store results
    for (base_rev, trader_cogs) in scenario_combinations:
        
        scenario_name = f"{base_rev} + {trader_cogs}"
        print(f"\n--- Calculating Scenario: {scenario_name} ---")
        
        # Get the specific inputs for this combination
        combined_inputs = get_combined_inputs(base_inputs_df, 'common', base_rev, trader_cogs)
        
        # Calculate the full P&L
        report_df = calculate_ebitda(combined_inputs, year_cols)
        
        # Store results
        all_ebitda_series[scenario_name] = report_df['EBITDA']
        
        # Print the detailed report for this scenario
        print(report_df.to_markdown(floatfmt=",.0f"))

    # 5. Create and print the final comparison table
    print("\n" + "="*80)
    print(" " * 25 + "Final EBITDA Comparison (in EUR)")
    print("="*80)
    
    final_comparison_df = pd.DataFrame(all_ebitda_series)
    final_comparison_df.index.name = "Year"
    
    # Print a nicely formatted summary table
    print(final_comparison_df.to_markdown(floatfmt=",.0f"))

    # Print a summary of totals
    print("\n--- Total EBITDA over projection period ---")
    print(final_comparison_df.sum().to_markdown(headers=["Scenario", "Total EBITDA"], floatfmt=",.0f"))