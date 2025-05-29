import csv
import subprocess

with open('./mediApp/params.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        run_flag = row.get('run', '').strip().lower()
        if run_flag != 'yes':
            print(f"Skipping row {i}: {row.get('name')}")
            continue

        print(f"Running row {i}: {row['name']}")
        cmd = [
            'docker', 'run', '--rm',
            '--env-file=./mediApp/.env',
            'mediczuwacz',
            'find-appointment',
            '-r 202',
            '-s', row['service_id'],
            '-d', row['doctor_id'],
            '-n telegram'
        ]
        subprocess.run(cmd, check=True)
