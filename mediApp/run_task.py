import subprocess
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
shared_path = os.path.abspath(os.path.join(base_dir, '../shared')).replace('\\', '/')
cmd = [
    'docker', 'run', '--rm',
    '--env-file=./mediApp/.env',
    '-v', f'{shared_path}:/app/shared',
    'mediczuwacz',
    'find-appointment'
]
subprocess.run(cmd, check=True)
