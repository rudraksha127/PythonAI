#!/usr/bin/env python3
"""
Fast Code Statistics Script
A lightweight version that quickly counts lines in Python files.
"""

import os
import glob
from pathlib import Path
from collections import defaultdict
import time


def count_lines(filepath):
    """Count lines in a file using efficient method."""
    try:
        with open(filepath, 'rb') as f:
            return sum(1 for _ in f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return 0


def fast_code_stats(root_dir, output_file="fast_code_stats.txt"):
    """Fast analysis of Python files."""
    print("Fast Code Statistics Analysis")
    print("=" * 50)
    
    start_time = time.time()
    
    # Find all Python files
    python_files = glob.glob(os.path.join(root_dir, '**', '*.py'), recursive=True)
    
    print(f"Found {len(python_files):,} Python files")
    print(f"Analyzing...")
    
    # Collect statistics
    total_files = 0
    total_lines = 0
    dir_stats = defaultdict(lambda: {'files': 0, 'lines': 0})
    
    for filepath in python_files:
        try:
            lines = count_lines(filepath)
            total_files += 1
            total_lines += lines
            
            # Directory stats
            file_dir = os.path.dirname(filepath)
            dir_stats[file_dir]['files'] += 1
            dir_stats[file_dir]['lines'] += lines
            
        except Exception as e:
            print(f"Error: {e}")
    
    elapsed = time.time() - start_time
    
    # Generate simple report
    report = []
    report.append("FAST CODE STATISTICS REPORT")
    report.append("=" * 50)
    report.append(f"Total Files: {total_files:,}")
    report.append(f"Total Lines: {total_lines:,}")
    report.append(f"Time: {elapsed:.2f}s")
    report.append(f"Avg/File: {total_lines/total_files:.1f}")
    report.append("-" * 50)
    
    # Top directories
    report.append("\nTop Directories by Lines:")
    for dir_path, stats in sorted(dir_stats.items(), 
                                  key=lambda x: x[1]['lines'], 
                                  reverse=True)[:10]:
        rel_path = os.path.relpath(dir_path, root_dir)
        report.append(f"  {rel_path}: {stats['lines']:,} lines ({stats['files']} files)")
    
    # Write report
    with open(output_file, 'w') as f:
        f.write('\n'.join(report))
    
    print(f"\nDone! {total_files:,} files, {total_lines:,} lines")
    print(f"Report: {output_file}")
    
    return {
        'files': total_files,
        'lines': total_lines,
        'time': elapsed,
        'report': output_file
    }


if __name__ == "__main__":
    script_dir = Path(__file__).parent
    stats = fast_code_stats(str(script_dir))
    
    print("\nQuick Stats:")
    print(f"  Files: {stats['files']:,}")
    print(f"  Lines: {stats['lines']:,}")
    print(f"  Time: {stats['time']:.2f}s")