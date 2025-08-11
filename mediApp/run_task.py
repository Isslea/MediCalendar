import subprocess
import os
file_path = 'shared/doctor_data.json'
os.makedirs(os.path.dirname(file_path), exist_ok=True)
shared_path = os.path.abspath('./shared').replace('\\', '/')
cmd = [
    'docker', 'run', '--rm',
    '--env-file=./mediApp/.env',
    '-v', f'{shared_path}:/app/shared',
    'mediczuwacz',
    'find-appointment'
]
subprocess.run(cmd, check=True)
