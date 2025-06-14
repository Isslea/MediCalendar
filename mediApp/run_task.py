import csv
import subprocess
import os
file_path = 'shared/doctor_data.json'
os.makedirs(os.path.dirname(file_path), exist_ok=True)

with open('./mediApp/params.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        run_flag = row.get('run', '').strip().lower()
        if run_flag != 'yes':
            print(f"Skipping row {i}: {row.get('name')}")
            continue

        print(f"Running row {i}: {row['name']}")
        shared_path = os.path.abspath('./shared').replace('\\', '/')
        cmd = [
            'docker', 'run', '--rm',
            '--env-file=./mediApp/.env',
            '-v', f'{shared_path}:/app/shared',
            'mediczuwacz',
            'find-appointment',
            '-r 202',
            '-s', row['service_id'],
            '-d', row['doctor_id'],
            '-n telegram',
            '--stars', row['stars']
        ]
        subprocess.run(cmd, check=True)
