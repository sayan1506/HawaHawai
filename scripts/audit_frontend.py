"""Audit public source/build bytes without printing private key values."""
import argparse
import json
import re
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', default='phase5', choices=['phase5', 'phase6'])
    args = parser.parse_args()
    private = [value.encode() for key, value in dotenv_values(ROOT/'backend/.env').items()
               if value and (key.endswith('API_KEY') or 'SECRET' in key or 'TOKEN' in key) and len(value) >= 12]
    patterns = [rb'GEMINI_API_KEY|GROQ_API_KEY|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID',
                rb'(?:AKIA|ASIA)[A-Z0-9]{16}', rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'Bearer\s+[A-Za-z0-9._~+/=-]{12,}', rb'AIza[\w-]{35}|gsk_[\w-]{32,}',
                rb'HAWAHAWAI_AI_SECRET_ARN|HAWAHAWAI_DYNAMODB_TABLE|\.env(?:\b|\.)']
    files = [p for folder in ['frontend/src','frontend/public','frontend/dist'] for p in (ROOT/folder).rglob('*') if p.is_file()]
    findings = []
    for file in files:
        data = file.read_bytes()
        # Vite's documented public configuration object is not a private .env file.
        searchable = data.replace(b'import.meta.env', b'PUBLIC_CONFIG')
        if any(value in data for value in private) or any(re.search(pattern, searchable) for pattern in patterns):
            findings.append(str(file.relative_to(ROOT)))
    assert not findings, 'Public asset findings: '+str(findings)
    for file in (ROOT/'frontend').glob('.env*'):
        config = dotenv_values(file)
        assert all(key == 'VITE_API_BASE_URL' and value and not any(secret.decode() in value for secret in private) for key, value in config.items()), 'Only public API URL configuration is permitted'
    sw = (ROOT/'frontend/dist/sw.js').read_text(encoding='utf-8')
    assert 'NetworkOnly' in sw and '/v1/' in sw and '/health' in sw
    def audit_json(name):
        data = (ROOT/'.local'/name).read_bytes()
        return json.loads(data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'))
    full = audit_json(f'{args.phase}-npm-audit.json')
    runtime = audit_json(f'{args.phase}-runtime-npm-audit.json')
    def contrast(a, b):
        def lum(color):
            values = [int(color[n:n+2],16)/255 for n in [1,3,5]]
            values = [v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(values,[.2126,.7152,.0722]))
        x,y = sorted([lum(a),lum(b)]); return round((y+.05)/(x+.05),2)
    contrasts = {f'{fg} on {bg}':contrast(fg,bg) for fg,bg in [('#233b3a','#ffffff'),('#526763','#fff9ed'),('#146458','#ffffff'),('#ffffff','#155e55'),('#885000','#fff9ed')]}
    assert all(value >= 4.5 for value in contrasts.values())
    result = {'files_checked':len(files),'private_values_checked':len(private),'secret_findings':findings,
              'service_worker':'static precache with NetworkOnly safety/health routes',
              'dependency_audit':full['metadata']['vulnerabilities'],'frontend_runtime_audit':runtime['metadata']['vulnerabilities'],
              'contrast_ratios':contrasts}
    (ROOT/f'.local/{args.phase}-public-security.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
