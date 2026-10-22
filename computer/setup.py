"""Create a local deployment configuration, never a cloud account or paid host."""
import argparse,os,re,secrets,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--domain',required=True);p.add_argument('--start',action='store_true');args=p.parse_args()
if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',args.domain) or '.' not in args.domain:raise SystemExit('Enter a DNS hostname you control')
root=Path(__file__).parent;target=root/'.env'
if target.exists():raise SystemExit('.env already exists; keep its token and edit it manually rather than overwriting')
example=(root/'.env.example').read_text();example=example.replace('ORBIT_TOKEN=\n','ORBIT_TOKEN='+secrets.token_urlsafe(36)+'\n',1);example+='\nPUBLIC_BASE_URL=https://'+args.domain+'\nORBIT_DOMAIN='+args.domain+'\n'
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(example)
print('Created private .env with a random access token. Configure model/provider settings there. No token printed.')
print('Point your domain at this server and allow ports 80/443 before requesting TLS.')
if args.start:
 if not shutil.which('docker'):raise SystemExit('Docker is required. Configuration was saved; install Docker and rerun the compose command from README.')
 subprocess.run(['docker','compose','-f','compose.yml','-f','tls.yml','up','--build','-d'],cwd=root,check=True)
