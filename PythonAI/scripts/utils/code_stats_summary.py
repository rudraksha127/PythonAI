#!/usr/bin/env python3
"""
Code Statistics Summary Script
This script analyzes Python files in the codebase and generates a summary report
including total lines of code, file counts, and statistics by directory.
"""

import os
import glob
from pathlib import Path
from collections import defaultdict
import time


def count_lines_in_file(filepath):
    """Count the number of lines in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return 0


def analyze_python_files(root_dir, output_file="code_stats_report.txt"):
    """
    Analyze all Python files in the directory tree and generate a summary report.
    
    Args:
        root_dir: Root directory to search for Python files
        output_file: Name of the output report file
    """
    print(f"Starting code analysis in: {root_dir}")
    print(f"This may take a moment for large codebases...")
    print()
    
    # Initialize statistics
    total_files = 0
    total_lines = 0
    files_by_dir = defaultdict(list)
    dir_stats = defaultdict(lambda: {'files': 0, 'lines': 0})
    
    start_time = time.time()
    
    # Search for all Python files
    python_files = list(glob.glob(os.path.join(root_dir, '**', '*.py'), recursive=True))
    
    print(f"Found {len(python_files)} Python files to analyze...")
    print()
    
    # Analyze each file
    for i, filepath in enumerate(python_files, 1):
        try:
            # Get relative path for cleaner output
            rel_path = os.path.relpath(filepath, root_dir)
            
            # Count lines
            lines = count_lines_in_file(filepath)
            
            # Update statistics
            total_files += 1
            total_lines += lines
            
            # Track by directory
            file_dir = os.path.dirname(filepath)
            files_by_dir[file_dir].append({
                'path': rel_path,
                'lines': lines
            })
            
            dir_stats[file_dir]['files'] += 1
            dir_stats[file_dir]['lines'] += lines
            
            # Progress feedback
            if i % 100 == 0:
                print(f"Processed {i}/{len(python_files)} files...")
                
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    elapsed_time = time.time() - start_time
    
    # Generate report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("PYTHON CODE STATISTICS SUMMARY REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Root Directory: {root_dir}")
    report_lines.append(f"Total Processing Time: {elapsed_time:.2f} seconds")
    report_lines.append("-" * 80)
    report_lines.append(f"Total Python Files: {total_files:,}")
    report_lines.append(f"Total Lines of Code: {total_lines:,}")
    report_lines.append(f"Average Lines per File: {total_lines/total_files:.1f}")
    report_lines.append("=" * 80)
    report_lines.append()
    
    # Directory-level statistics
    report_lines.append("DIRECTORY-LEVEL STATISTICS")
    report_lines.append("=" * 80)
    
    # Sort directories by lines of code (descending)
    sorted_dirs = sorted(dir_stats.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    for dir_path, stats in sorted_dirs:
        rel_dir = os.path.relpath(dir_path, root_dir)
        report_lines.append(f"\nDirectory: {rel_dir}")
        report_lines.append(f"  Files: {stats['files']:,}")
        report_lines.append(f"  Lines: {stats['lines']:,}")
        report_lines.append(f"  Avg per file: {stats['lines']/stats['files']:.1f}")
    
    report_lines.append("\n" + "=" * 80)
    report_lines.append("TOP 20 LARGEST FILES")
    report_lines.append("=" * 80)
    
    # Find top 20 largest files
    all_files = []
    for dir_path, files in files_by_dir.items():
        for file_info in files:
            all_files.append(file_info)
    
    # Sort by lines (descending)
    sorted_files = sorted(all_files, key=lambda x: x['lines'], reverse=True)[:20]
    
    for i, file_info in enumerate(sorted_files, 1):
        report_lines.append(f"{i:2d}. {file_info['lines']:6,} lines - {file_info['path']}")
    
    # Write report to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"\nAnalysis complete!")
    print(f"Total files analyzed: {total_files:,}")
    print(f"Total lines of code: {total_lines:,}")
    print(f"Report saved to: {output_file}")
    print(f"\nTop 5 directories by lines of code:")
    for i, (dir_path, stats) in enumerate(sorted_dirs[:5], 1):
        rel_dir = os.path.relpath(dir_path, root_dir)
        print(f"  {i}. {rel_dir}: {stats['lines']:,} lines in {stats['files']} files")
    
    return {
        'total_files': total_files,
        'total_lines': total_lines,
        'files_by_dir': files_by_dir,
        'dir_stats': dir_stats,
        'report_file': output_file,
        'processing_time': elapsed_time
    }


def print_quick_summary(stats):
    """Print a quick summary of the statistics."""
    print("\n" + "=" * 60)
    print("QUICK SUMMARY")
    print("=" * 60)
    print(f"Total Python Files: {stats['total_files']:,}")
    print(f"Total Lines of Code: {stats['total_lines']:,}")
    print(f"Avg Lines per File: {stats['total_lines']/stats['total_files']:.1f}")
    print(f"Report: {stats['report_file']}")
    print("=" * 60)


if __name__ == "__main__":
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    
    # Run the analysis
    stats = analyze_python_files(
        root_dir=str(script_dir),
        output_file="code_stats_report.txt"
    )
    
    # Print quick summary
    print_quick_summary(stats)