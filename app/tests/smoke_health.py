"""Rzeczywisty start Streamlit i HTTP 200, zakończenie własnego procesu."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
import httpx

APP = Path(__file__).resolve().parent.parent


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, DATA_DIR=os.getenv('DATA_DIR',str(APP.parent/'exercises'/'dane')), STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    (APP/'logs').mkdir(exist_ok=True)
    log = APP/'logs'/'health-startup.log'
    process = None
    try:
        with log.open('w',encoding='utf-8') as output:
            process = subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.headless','true',
                                        '--server.address','127.0.0.1','--server.port',str(port)],cwd=APP,env=env,stdout=output,stderr=subprocess.STDOUT)
            deadline = time.monotonic()+45
            with httpx.Client(timeout=2,trust_env=False) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f'Streamlit zakończył pracę: {process.returncode}; zobacz {log}')
                    try:
                        response = client.get(f'http://127.0.0.1:{port}/_stcore/health')
                        if response.status_code == 200:
                            result = {'health_status':200,'health_body':response.text,'port':port,'data':env['DATA_DIR'], 'python':sys.version.split()[0]}
                            (APP/'logs'/'health-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                            print(json.dumps(result,ensure_ascii=False))
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(.4)
            raise RuntimeError('Brak HTTP 200 na health w ciągu 45 s')
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)

if __name__ == '__main__':
    main()
