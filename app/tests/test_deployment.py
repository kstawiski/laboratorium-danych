"""Skrypt s1: rzeczywiste wykonanie powłoki, Docker zastąpiony stubem."""
from pathlib import Path
import os
import subprocess

APP = Path(__file__).resolve().parent.parent


def test_s1_publishes_target_ip_and_readonly_data(tmp_path, fixture_dir):
    binary = tmp_path/'bin'
    binary.mkdir()
    trace = tmp_path/'docker-arguments.txt'
    stub = binary/'docker'
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_TRACE"\nif [ "$1" = container ]; then exit 1; fi\nexit 0\n')
    stub.chmod(0o755)
    env = dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],DOCKER_TRACE=str(trace),DATA_DIR=str(fixture_dir))
    result = subprocess.run(['bash',str(APP/'run_docker.sh')],cwd=APP,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr
    commands = trace.read_text()
    assert 'build -t laboratorium-danych:latest' in commands
    assert '--network host' in commands
    assert 'dst=/data,readonly' in commands
    assert '--env DATA_DIR=/data' in commands
    assert 'dst=/app/cache' in commands
    assert '--env STREAMLIT_SERVER_ADDRESS=' in commands
    assert '--user ' in commands
    assert 'rm -f' not in commands


def test_s1_mounts_key_readonly_and_accepts_csv_only(tmp_path,fixture_dir):
    import shutil
    package = tmp_path/'package'
    shutil.copytree(fixture_dir,package)
    (package/'rejestr_brudny.xlsx').unlink()
    binary = tmp_path/'bin'; binary.mkdir()
    trace = tmp_path/'docker-arguments.txt'
    stub = binary/'docker'
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_TRACE"\nif [ "$1" = container ]; then exit 1; fi\nexit 0\n')
    stub.chmod(0o755)
    key = tmp_path/'fixture.key'; key.write_text('mock-only')
    env = dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],DOCKER_TRACE=str(trace),
               DATA_DIR=str(package),CACHE_DIR=str(tmp_path/'cache'),LOG_DIR=str(tmp_path/'logs'),
               ORNITH_API_KEY_FILE=str(key),ORNITH_BASE_URLS='http://a/v1,http://b/v1')
    result = subprocess.run(['bash',str(APP/'run_docker.sh')],cwd=APP,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stderr
    commands = trace.read_text()
    assert 'dst=/run/secrets/ornith,readonly' in commands
    assert '--env ORNITH_API_KEY_FILE=/run/secrets/ornith' in commands
    assert '--env ORNITH_BASE_URLS=http://a/v1,http://b/v1' in commands
    assert 'mock-only' not in commands
    dockerfile = (APP/'Dockerfile').read_text()
    for flag in ['--server.headless=true','--server.enableCORS=false','--server.enableXsrfProtection=false','--browser.gatherUsageStats=false']:
        assert flag in dockerfile
