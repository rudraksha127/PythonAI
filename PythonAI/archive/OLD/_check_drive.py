import os, sys, pathlib
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ag = 'D:/PythonAI_Data/anti_gravity_data'
print(f'D: drive exists: {os.path.isdir("D:/")}')
print(f'D:/PythonAI_Data exists: {os.path.isdir("D:/PythonAI_Data")}')
print(f'anti_gravity_data exists: {os.path.isdir(ag)}')

if os.path.isdir(ag):
    p = pathlib.Path(ag)
    dirs = sorted([x.name for x in p.iterdir() if x.is_dir()])
    print(f'\nTop directories ({len(dirs)}):')
    for d in dirs:
        subfiles = list(p.glob(f'{d}/**/*'))
        n = sum(1 for f in subfiles if f.is_file())
        sz = sum(f.stat().st_size for f in subfiles if f.is_file()) / 1e6
        print(f'  {d:30s} {n:5d} files, {sz:7.1f} MB')
    
    all_files = list(p.rglob('*'))
    total_f = sum(1 for f in all_files if f.is_file())
    total_s = sum(f.stat().st_size for f in all_files if f.is_file())
    print(f'\nTotal: {total_f} files, {total_s/1e9:.2f} GB')
else:
    print('anti_gravity_data directory not found yet')
