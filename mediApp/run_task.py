import csv
import subprocess
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, '../shared/doctor_data.json')
os.makedirs(os.path.dirname(file_path), exist_ok=True)

params_path = os.path.join(base_dir, 'params.csv')
with open(params_path) as f:
    reader = csv.DictReader(f)
    shared_path = os.path.abspath(os.path.join(base_dir, '../shared')).replace('\\', '/')
    cmd = [
        'docker', 'run', '--rm',
        '--env-file=./mediApp/.env',
        '-v', f'{shared_path}:/app/shared',
        'mediczuwacz',
        'find-appointment'
    ]
    subprocess.run(cmd, check=True)
