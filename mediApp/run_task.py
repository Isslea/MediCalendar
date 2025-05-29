import csv
import subprocess

with open('./mediApp/params.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
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
