"""Stop a named lab AutoML run when estimated compute use exceeds a guardrail.

Local best-effort watchdog, not an AWS billing limit: does not include storage,
logs, taxes, or account activity, and requires valid credentials and a running host.
"""
import concurrent.futures
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

name, limit_text, output = sys.argv[1:]
limit = float(limit_text); path = Path(output)
# Public on-demand us-east-1 prices recorded 2026-11-09. Unknown active types trigger stop.
rates = {'ml.m5.2xlarge': 0.461, 'ml.m5.4xlarge': 0.922,
         'ml.m5.12xlarge': 2.765, 'ml.r5.16xlarge': 4.838}
def aws(*args):
    p=subprocess.run(['aws','sagemaker',*args,'--output','json'],capture_output=True,text=True,timeout=40)
    if p.returncode: raise RuntimeError(p.stderr.strip())
    return json.loads(p.stdout) if p.stdout.strip() else {}
def describe(spec):
    typ, name = spec
    return typ, aws('describe-'+typ+'-job','--'+typ+'-job-name',name)
def timestamp(s): return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc)
def stop(reason, jobnames):
    try: aws('stop-auto-ml-job','--auto-ml-job-name',name)
    except Exception as exc: print('parent stop:',str(exc),flush=True)
    for typ, child in jobnames:
        try: aws('stop-'+typ+'-job','--'+typ+'-job-name',child)
        except Exception as exc: print('child stop:',str(exc),flush=True)
    print('stop requested:',reason,flush=True)
while True:
    try:
        parent=aws('describe-auto-ml-job-v2','--auto-ml-job-name',name)
        processing=aws('list-processing-jobs','--name-contains',name[:20])['ProcessingJobSummaries']
        training=aws('list-training-jobs','--name-contains',name[:20])['TrainingJobSummaries']
        jobs=[('processing',x['ProcessingJobName']) for x in processing]+[('training',x['TrainingJobName']) for x in training]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: details=list(pool.map(describe,jobs))
        now=dt.datetime.now(dt.timezone.utc); total=0; unknown=[]; active=[]; rows=[]
        for typ,j in details:
            if typ=='processing':
                config=j['ProcessingResources']['ClusterConfig']; kind=j['ProcessingJobStatus']; start=j.get('ProcessingStartTime'); end=j.get('ProcessingEndTime'); child=j['ProcessingJobName']
            else:
                config=j['ResourceConfig']; kind=j['TrainingJobStatus']; start=j.get('TrainingStartTime'); end=j.get('TrainingEndTime'); child=j['TrainingJobName']
            running=kind in ('InProgress','Stopping')
            if running:active.append((typ,child))
            # While provisioning, creation time is a conservative upper bound for billable time.
            begin=start or (j.get('CreationTime') if running else None)
            seconds=max(0,((timestamp(end) if end else now)-timestamp(begin)).total_seconds()) if begin else 0
            rate=rates.get(config['InstanceType'])
            if rate is None and running: unknown.append(config['InstanceType'])
            cost=seconds*config['InstanceCount']*rate/3600 if rate is not None else None
            if cost is not None:total+=cost
            rows.append({'name':child,'status':kind,'instance':config['InstanceType'],'count':config['InstanceCount'],'seconds_upper':seconds,'compute_estimate_usd':cost})
        state={'observed_utc':now.isoformat(),'parent_status':parent['AutoMLJobStatus'],'parent_stage':parent.get('AutoMLJobSecondaryStatus'),'compute_estimate_upper_usd':total,'guard_usd':limit,'unknown_active_instance_types':unknown,'jobs':rows}
        path.write_text(json.dumps(state,indent=2)+'\n')
        print(now.isoformat(),parent['AutoMLJobStatus'],parent.get('AutoMLJobSecondaryStatus'),round(total,3),'active',len(active),'unknown',unknown,flush=True)
        if parent['AutoMLJobStatus'] not in ('Completed','Failed','Stopped','Stopping') and (total>=limit or unknown):
            stop('estimated compute guardrail or unknown instance type',active)
        if parent['AutoMLJobStatus'] in ('Completed','Failed','Stopped') and not active: break
    except Exception as exc:
        print(dt.datetime.now(dt.timezone.utc).isoformat(),'watchdog error',repr(exc),flush=True)
    time.sleep(25)
