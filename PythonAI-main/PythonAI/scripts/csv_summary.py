#!/usr/bin/env python3
"""
CSV Summary Statistics Generator

This script reads a CSV file and prints comprehensive summary statistics
for each column, automatically detecting column types and providing
appropriate statistics.

Usage:
    python scripts/csv_summary.py <csv_file_path>

Example:
    python scripts/csv_summary.py data/sample.csv
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd


def print_section_header(title: str, level: int = 1) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"{' ' * 10}{title.upper()}")
    print(f"{'=' * 80}\n")


def print_numeric_stats(df: pd.DataFrame, col: str) -> None:
    """Print statistics for numeric columns."""
    stats = df[col].describe(percentiles=[0.25, 0.5, 0.75])
    null_count = df[col].isna().sum()
    null_pct = (null_count / len(df)) * 100
    unique_count = df[col].nunique()

    print_section_header(f"Numeric Column: {col}")
    print(f"{'Count:':<20} {len(df[col]):>10}")
    print(f"{'Null Values:':<20} {null_count:>10} ({null_pct:.2f}%)")
    print(f"{'Unique Values:':<20} {unique_count:>10}")
    print(f"{'Mean:':<20} {stats['mean']:>10.4f}")
    print(f"{'Std Dev:':<20} {stats['std']:>10.4f}")
    print(f"{'Min:':<20} {stats['min']:>10.4f}")
    print(f"{'25th Percentile:':<20} {stats['25%']:>10.4f}")
    print(f"{'Median (50th):':<20} {stats['50%']:>10.4f}")
    print(f"{'75th Percentile:':<20} {stats['75%']:>10.4f}")
    print(f"{'Max:':<20} {stats['max']:>10.4f}")


def print_categorical_stats(df: pd.DataFrame, col: str) -> None:
    """Print statistics for categorical/text columns."""
    null_count = df[col].isna().sum()
    null_pct = (null_count / len(df)) * 100
    unique_count = df[col].nunique()

    # Get top 10 most frequent values
    top_values = df[col].value_counts().head(10)

    print_section_header(f"Categorical Column: {col}")
    print(f"{'Count:':<20} {len(df[col]):>10}")
    print(f"{'Null Values:':<20} {null_count:>10} ({null_pct:.2f}%)")
    print(f"{'Unique Values:':<20} {unique_count:>10}")

    if not top_values.empty:
        print("\nTop 10 Most Frequent Values:")
        print("-" * 40)
        for value, count in top_values.items():
            pct = (count / len(df)) * 100
            print(f"  {str(value):<30} {count:>10} ({pct:.2f}%)")


def print_boolean_stats(df: pd.DataFrame, col: str) -> None:
    """Print statistics for boolean columns."""
    null_count = df[col].isna().sum()
    null_pct = (null_count / len(df)) * 100
    true_count = df[col].sum()
    false_count = len(df) - true_count - null_count

    print_section_header(f"Boolean Column: {col}")
    print(f"{'Count:':<20} {len(df[col]):>10}")
    print(f"{'Null Values:':<20} {null_count:>10} ({null_pct:.2f}%)")
    print(f"{'True Values:':<20} {true_count:>10} ({true_count / len(df) * 100:.2f}%)")
    print(f"{'False Values:':<20} {false_count:>10} ({false_count / len(df) * 100:.2f}%)")


def print_datetime_stats(df: pd.DataFrame, col: str) -> None:
    """Print statistics for datetime columns."""
    null_count = df[col].isna().sum()
    null_pct = (null_count / len(df)) * 100

    # Convert to datetime if not already
    if not pd.api.types.is_datetime64_any_dtype(df[col]):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    non_null = df[col].dropna()

    print_section_header(f"Datetime Column: {col}")
    print(f"{'Count:':<20} {len(df[col]):>10}")
    print(f"{'Null Values:':<20} {null_count:>10} ({null_pct:.2f}%)")
    print(f"{'Earliest Date:':<20} {non_null.min():>25}")
    print(f"{'Latest Date:':<20} {non_null.max():>25}")
    print(f"{'Date Range:':<20} {non_null.max() - non_null.min()}")


def generate_csv_summary(file_path: Path) -> None:
    """
    Generate and print summary statistics for a CSV file.

    Args:
        file_path: Path to the CSV file
    """
    try:
        # Read CSV file
        df = pd.read_csv(file_path)

        if df.empty:
            print(f"Error: The file '{file_path}' is empty.")
            return

        print_section_header(f"CSV Summary Statistics: {file_path.name}")
        print(f"{'File Path:':<20} {file_path.resolve()}")
        print(f"{'Total Rows:':<20} {len(df):>10}")
        print(f"{'Total Columns:':<20} {len(df.columns):>10}")
        print(f"{'File Size:':<20} {file_path.stat().st_size / 1024:.2f} KB")
        print(f"{'Last Modified:':<20} {datetime.fromtimestamp(file_path.stat().st_mtime)}")

        # Analyze each column
        for col in df.columns:
            col_type = df[col].dtype

            # Determine column type
            if pd.api.types.is_numeric_dtype(col_type):
                print_numeric_stats(df, col)
            elif pd.api.types.is_bool_dtype(col_type):
                print_boolean_stats(df, col)
            elif pd.api.types.is_datetime64_any_dtype(col_type):
                print_datetime_stats(df, col)
            else:
                # Treat as categorical/text
                print_categorical_stats(df, col)

    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print(f"Error: The file '{file_path}' is empty or could not be parsed.")
        sys.exit(1)
    except pd.errors.ParserError:
        print(f"Error: Could not parse '{file_path}' as a CSV file.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: An unexpected error occurred: {str(e)}")
        sys.exit(1)


def main():
    """Parse command line arguments and generate summary."""
    parser = argparse.ArgumentParser(
        description="Generate summary statistics for CSV files.", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("file_path", type=Path, help="Path to the CSV file")

    args = parser.parse_args()

    # Validate file exists
    if not args.file_path.exists():
        print(f"Error: File not found: {args.file_path}")
        sys.exit(1)

    # Validate it's a file
    if not args.file_path.is_file():
        print(f"Error: '{args.file_path}' is not a file.")
        sys.exit(1)

    # Generate summary
    generate_csv_summary(args.file_path)


if __name__ == "__main__":
    main()
