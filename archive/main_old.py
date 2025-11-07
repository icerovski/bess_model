import pandas as pd
from dataclasses import dataclass, field
from typing import Union, List

@dataclass
class Parameter:
    df_name: pd.DataFrame 
    param_name: str

    # --- Calculated (Derived) Fields ---
    # 'init=False' means this field is NOT provided when creating
    # an instance. It will be created in __post_init__.
    raw_data: pd.Series = field(init=False)

    def __post_init__(self):
        """
        This special method runs *after* the auto-generated
        __init__ sets self.df_name and self.param_name.
        """
        # Your calculation logic is moved here, using 'self.'
        self.raw_data = self.df_name.loc[self.param_name].dropna()

    # This property was removed as it conflicts with the
    # input field 'param_name'. You can just access 'self.param_name'.
    
    @property
    def param_unit(self) -> str:
        """Pull the unit of the parameter."""
        # Properties should only take 'self' and use 'self.'
        return self.raw_data['unit']
    
    @property
    def param_values(self) -> Union[float, List[float]]:
        """
        Pull the numeric values of the parameter.
        Returns a single float if one value, else a list.
        """
        return self.raw_data.drop('unit').astype(float)
        

def calculate_sales_projection_v2(input_csv_path: str, output_csv_path: str) -> pd.Series:
    """
    Calculates an annual sales projection based on parameters in a CSV file.
    
    The input CSV must be in the "wide" format:
    - Column 1: 'parameter' (index)
    - Column 2: 'unit'
    - Columns 3-N: The actual years of the projection (e.g., '2025', '2026', ...)
    
    Required parameters:
    - 'last_year_sales': The starting sales value (float).
    - 'growth_factor': The growth rate(s).
        - If one value is provided, it's used for all years.
        - If a series is provided, it must match the timeline.
    """
    
    # 1. Read the input CSV, using the 'parameter' column as the index
    try:
        params_df = pd.read_csv(input_csv_path, index_col='parameter')
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_csv_path}")
        return
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # 2. Get the projection timeline directly from the CSV headers
    # We convert them to strings to ensure consistent matching
    # The columns will now be ['unit', '2025', '2026', ...]
    # all_columns = list(params_df.columns)

    # We slice the list to get only the years (excluding the 'unit' column)
    projection_years = list(params_df.columns.drop('unit')) 
    projection_length = len(projection_years)

    print(f"Detected projection timeline: {projection_years[0]} to {projection_years[-1]} ({projection_length} years)")

    # 3. Extract global parameters
    # A) last_year_sales
    try:
        last_year_sales = Parameter(params_df, 'last_year_sales')
        print(f"Growth Rates Series:\n {last_year_sales.param_values} for all {projection_length} years.")
    except KeyError as e:
        print(f"Error: Missing required parameter: {e}")
        return
    except ValueError:
        print("Error: 'last_year_sales' has an invalid value.")
        return

    # B) growth_factor
    try:
        growth_series = Parameter(params_df, 'growth_factor')
        print(f"Base Sales:\n {growth_series.raw_data}")
    except KeyError:
        print("Error: Missing required parameter: 'growth_factor'")
        return

    # 4. Perform the sales calculation
    sales_projection = []
    current_sales = last_year_sales

    for year in projection_years:
        # Get the growth rate for this specific year
        growth_rate = growth_factors[year]
        
        # Calculate the new sales
        current_sales = current_sales * (1 + growth_rate)
        sales_projection.append(current_sales)

    # 6. Create the final pandas Series
    # The index is now the explicit years from your CSV
    sales_series = pd.Series(
        sales_projection, 
        index=pd.Index(projection_years, name='year'),
        name='projected_sales'
    )
    
    # 7. Save the series to the output CSV
    try:
        sales_series.to_csv(output_csv_path)
        print(f"\nSuccessfully calculated projection and saved to {output_csv_path}")
    except Exception as e:
        print(f"Error saving output file: {e}")
        
    return sales_series

# --- --- --- --- ---
#  RUN THE SCRIPT
# --- --- --- --- ---

def main():
    print("Hello from bess-model!")

    # Run the calculation
    projection = calculate_sales_projection_v2(
        input_csv_path="data/inputs.csv" , 
        output_csv_path="output/output_sales.csv"
    )

    # Display the result
    if projection is not None:
        print("\n--- Resulting Sales Projection ---")
        print(projection.to_string(float_format="%.2f"))

if __name__ == "__main__":
    main()