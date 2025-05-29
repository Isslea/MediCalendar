import csv
import subprocess

with open('./mediApp/params.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, start=1):
        run_flag = row.get('run', '').strip().lower()
        if run_flag != 'yes':
            print(f"⏭️ Skipping row {i}: run='{row.get('run')}', region={row.get('region')}")
            continue

        cmd = [
            'docker', 'run', '--rm',
            '--env-file=./mediApp/.env',
            'mediczuwacz',
            'find-appointment',
            '-r 202',
            '-s', row['service_id'],
            '-d', row['doctor_id']
        ]
        
        print(f"▶️ Running row {i}: region={row['region']}, service={row['service_id']}, doctor={row['doctor_id']}")
        subprocess.run(cmd, check=True)
