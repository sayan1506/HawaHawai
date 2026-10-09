"""Preview/deploy only the CDK-owned HawaHawai static production artifact. No Git."""
import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    session = boto3.Session(profile_name='hawahawai', region_name='us-east-1')
    config = Config(connect_timeout=3, read_timeout=15, retries={'total_max_attempts': 1})
    assert session.client('sts', config=config).get_caller_identity()['Account'] == '649437299529'
    cf = session.client('cloudformation', config=config)
    stack = cf.describe_stacks(StackName='HawaHawaiDev')['Stacks'][0]
    assert stack['StackStatus'] in {'CREATE_COMPLETE', 'UPDATE_COMPLETE'}
    outputs = {x['OutputKey']: x['OutputValue'] for x in stack['Outputs']}
    app_id = outputs['FrontendAppId']
    resources = cf.describe_stack_resources(StackName='HawaHawaiDev')['StackResources']
    app_arn = f'arn:aws:amplify:us-east-1:649437299529:apps/{app_id}'
    assert any(r['LogicalResourceId']=='WebApp' and r['ResourceType']=='AWS::Amplify::App' and r['PhysicalResourceId']==app_arn for r in resources)
    assert any(r['LogicalResourceId']=='WebProduction' and r['PhysicalResourceId']==app_arn+'/branches/production' for r in resources)
    amplify = session.client('amplify', config=config)
    app = amplify.get_app(appId=app_id)['app']
    assert app['name']=='hawahawai-dev-web' and app['platform']=='WEB'
    assert outputs['FrontendUrl']=='https://production.'+app['defaultDomain']
    branch = amplify.get_branch(appId=app_id, branchName='production')['branch']
    assert branch['enableAutoBuild'] is False
    dist = ROOT / 'frontend/dist'
    required = ['index.html', 'manifest.webmanifest', 'sw.js', 'icon-192.png', 'icon-512.png']
    assert all((dist / name).is_file() for name in required)
    files = sorted(p for p in dist.rglob('*') if p.is_file())
    assert all(not p.name.startswith('.env') and p.suffix not in {'.map', '.pem', '.key'} for p in files)
    archive = ROOT / '.local/phase5-frontend.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for file in files:
            zipped.write(file, file.relative_to(dist).as_posix())
    data = archive.read_bytes()
    report = {'app_id': app_id, 'branch': 'production', 'url': outputs['FrontendUrl'],
              'files': len(files), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'deployed': False}
    if args.deploy:
        deployment = amplify.create_deployment(appId=app_id, branchName='production')
        upload = urllib.parse.urlparse(deployment['zipUploadUrl'])
        assert upload.scheme=='https' and upload.hostname.endswith('.amazonaws.com')
        # This signed upload capability is private and is never printed or saved.
        request = urllib.request.Request(deployment['zipUploadUrl'], data=data, method='PUT', headers={'Content-Type':'application/zip'})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status==200
        amplify.start_deployment(appId=app_id, branchName='production', jobId=deployment['jobId'])
        for _ in range(60):
            job = amplify.get_job(appId=app_id, branchName='production', jobId=deployment['jobId'])['job']['summary']
            if job['status'] in {'SUCCEED','FAILED','CANCELLED'}:
                report.update(job_id=deployment['jobId'], status=job['status'], deployed=job['status']=='SUCCEED')
                break
            time.sleep(3)
        else:
            raise RuntimeError('Amplify deployment did not finish within the bounded verification window')
    (ROOT / '.local/phase5-amplify-deployment.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return int(args.deploy and not report['deployed'])


if __name__ == '__main__':
    raise SystemExit(main())
