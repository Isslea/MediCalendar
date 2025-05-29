import csv
import subprocess

with open('./mediApp/params.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['run'].strip().lower() != 'yes':
            print(f"⏭️ Skipping row: {row['name']}")
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
        print("Running:", " ".join(cmd))
        subprocess.run(cmd, check=True)
