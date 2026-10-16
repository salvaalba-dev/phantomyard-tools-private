"""Activate the AU-only analysis pilot after reviewing its explicit access scope."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
from datetime import datetime, timezone

BASE=Path('/opt/phantomview-au')
STATE=Path('/var/lib/phantomview-au')
FILES=['access_gate.py','phantomview.py','index.html','style.css','assistant.js','review.js',
       'consultation.py','consultation-ui.js','bridge_assistant.cjs','assistant_worker.py','bounded_process.py']


def deploy(staging):
    staging=Path(staging).resolve()
    assert BASE.is_dir() and STATE.is_dir() and staging.is_relative_to(STATE/'collector')
    binary=BASE/'runtime/phantombot-assistant';manifest=BASE/'runtime/build-manifest.json'
    assert binary.is_file() and not binary.is_symlink() and binary.stat().st_uid==0
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==json.loads(manifest.read_text())['sha256']
    assert os.access(binary,os.X_OK)
    assert (Path('/home/pb-paco/.local/state/phantombot')).is_dir()
    native_state=Path('/home/pb-paco/.local/share/pi-native/personas/paco/agent')
    assert native_state.is_dir() and not native_state.is_symlink()
    assert native_state.resolve().is_relative_to(Path('/home/pb-paco'))
    assert native_state.stat().st_uid==pwd.getpwnam('pb-paco').pw_uid
    for port in (8745,8746):
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    policy_path=STATE/'reader/access.json';policy=json.loads(policy_path.read_text())
    default=json.loads((STATE/'collector/default-persona.json').read_text())
    assert policy['actor']==default['persona']=='paco' and default['org']=='aquaponics-united'
    assert not Path('/var/lib/phantomview-au-assistant').exists(), 'Existing assistant deployment requires an explicit upgrade'
    backup=STATE/'collector'/('before-consultation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    shutil.copy2(policy_path,backup/'access.json')
    for name in FILES:
        source=staging/name;assert source.is_file() and not source.is_symlink()
        if (BASE/name).exists():shutil.copy2(BASE/name,backup/name)
    # Syntax checks complete before any live source is replaced.
    subprocess.run(['python3','-m','py_compile',*[str(staging/f) for f in FILES if f.endswith('.py')]],check=True)
    for name in ('consultation-ui.js','assistant.js','review.js','bridge_assistant.cjs'):
        subprocess.run(['node','--check',str(staging/name)],check=True)
    reader_gid=pwd.getpwnam('aunited').pw_gid;persona_gid=pwd.getpwnam('pb-paco').pw_gid
    private=Path('/var/lib/phantomview-au-assistant');assert not private.exists(), 'Do not replace assistant credentials'
    private.mkdir(mode=0o755)
    private.chmod(0o711)  # Root's restrictive umask must not block the two service users.
    token=secrets.token_hex(32)
    def write(name,body,gid):
        file=private/name;file.write_text(body,encoding='utf8');os.chown(file,0,gid);file.chmod(0o640)
    # Separate server-owned copies; neither is exposed in HTML, cookies or URLs.
    write('reader.token',token,reader_gid);write('worker.token',token,persona_gid)
    worker=dict(org='aquaponics-united',persona='paco',port=8746,token_file=str(private/'worker.token'),
                executable=str(binary),manifest=str(manifest),working_dir='/home/pb-paco')
    write('worker.json',json.dumps(worker),persona_gid)
    write('bridge.json',json.dumps(dict(worker_port=8746,token_file=str(private/'reader.token'))),reader_gid)
    write('client.json',json.dumps(dict(bridge_port=8745,token_file=str(private/'reader.token'))),reader_gid)
    for name in FILES:
        target=BASE/name;temporary=target.with_suffix(target.suffix+'.consultation-tmp')
        temporary.write_bytes((staging/name).read_bytes());temporary.chmod(0o644);os.replace(temporary,target)
    common='\nRestart=on-failure\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=read-only\nRestrictSUIDSGID=true\nCapabilityBoundingSet=\nUMask=0077\n'
    units={
        'phantomview-au-assistant.service':'[Unit]\nDescription=PhantomView AU analysis-only persona worker\nAfter=network.target\n[Service]\nUser=pb-paco\nWorkingDirectory=/home/pb-paco\nExecStart=/usr/bin/python3 '+str(BASE/'assistant_worker.py')+' --config '+str(private/'worker.json')+common+'ReadWritePaths=/home/pb-paco/.local/share/phantombot /home/pb-paco/.local/state/phantombot '+str(native_state)+'\n[Install]\nWantedBy=multi-user.target\n',
        'phantomview-au-assistant-bridge.service':'[Unit]\nDescription=PhantomView AU loopback consultation adapter\nAfter=phantomview-au-assistant.service\n[Service]\nUser=aunited\nWorkingDirectory='+str(BASE)+'\nExecStart=/usr/bin/node '+str(BASE/'bridge_assistant.cjs')+' '+str(private/'bridge.json')+' 8745'+common+'[Install]\nWantedBy=multi-user.target\n'}
    for name,text in units.items():
        file=Path('/etc/systemd/system')/name;assert not file.exists();file.write_text(text)
    # Keep the issuer policy schema unchanged: the existing grant tool validates it.
    drop=Path('/etc/systemd/system/phantomview-au.service.d');drop.mkdir(exist_ok=True)
    drop_file=drop/'consultation.conf';assert not drop_file.exists()
    drop_file.write_text('[Service]\nEnvironment=PHANTOMVIEW_ASSISTANT_CONFIG='+str(private/'client.json')+'\n')
    try:
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','enable','--now',*units],check=True)
        subprocess.run(['systemctl','restart','phantomview-au.service'],check=True)
        subprocess.run(['systemctl','is-active',*units,'phantomview-au.service'],check=True)
        # Service start alone does not prove the restricted worker is ready.
        import time
        from consultation import BridgeClient
        client=BridgeClient(json.loads((private/'client.json').read_text()))
        ready=False
        for attempt in range(10):
            try:
                status,report=client.call('GET','/status')
                ready=status==200 and report.get('ready') is True and report.get('persona')=='paco'
                if ready:break
            except (OSError, ValueError):
                pass
            time.sleep(.2)
        assert ready, 'Restricted worker is not ready; restore the previous dashboard'
    except Exception:
        subprocess.run(['systemctl','disable','--now',*units],check=False)
        drop_file.write_text('[Service]\n')
        shutil.copy2(backup/'access.json',policy_path)
        for name in FILES:
            if (backup/name).exists():shutil.copy2(backup/name,BASE/name)
        subprocess.run(['systemctl','restart','phantomview-au.service'],check=False)
        raise
    print('AU-only assistant activated. Rollback source:',backup)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--staging',required=True)
    deploy(parser.parse_args().staging)
