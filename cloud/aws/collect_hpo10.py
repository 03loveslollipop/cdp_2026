"""Collect completed AutoML and per-job receipts; estimate only compute cost."""
import concurrent.futures,datetime as dt,json,subprocess
from pathlib import Path

name='credit-auto-hpo10-20261109'; prefix=name[:20]; out=Path('output/aws-credit/hpo10'); out.mkdir(parents=True,exist_ok=True)
rates={'ml.m5.2xlarge':0.461,'ml.m5.4xlarge':0.922,'ml.m5.12xlarge':2.765,'ml.r5.16xlarge':4.838}
def aws(*args):
 p=subprocess.run(['aws','sagemaker',*args,'--output','json'],capture_output=True,text=True,check=True);return json.loads(p.stdout)
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
parent=aws('describe-auto-ml-job-v2','--auto-ml-job-name',name)
if parent['AutoMLJobStatus']!='Completed':raise RuntimeError('AutoML not completed')
save(out/'completed.json',parent)
candidates=aws('list-candidates-for-auto-ml-job','--auto-ml-job-name',name);save(out/'candidates.json',candidates)
tune=aws('list-hyper-parameter-tuning-jobs','--name-contains',prefix);save(out/'tuning-jobs.json',tune)
plist=aws('list-processing-jobs','--name-contains',prefix);tlist=aws('list-training-jobs','--name-contains',prefix)
save(out/'processing-jobs.json',plist);save(out/'training-jobs.json',tlist)
jobs=[('processing',j['ProcessingJobName']) for j in plist['ProcessingJobSummaries']]+[('training',j['TrainingJobName']) for j in tlist['TrainingJobSummaries']]
def describe(x):
 typ,job=x;return typ,aws('describe-'+typ+'-job','--'+typ+'-job-name',job)
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool: details=list(pool.map(describe,jobs))
receipts=out/'jobs';receipts.mkdir(exist_ok=True);summaries=[]
for typ,j in details:
 if typ=='processing':
  job=j['ProcessingJobName'];status=j['ProcessingJobStatus']; cfg=j['ProcessingResources']['ClusterConfig'];start=j.get('ProcessingStartTime');end=j.get('ProcessingEndTime')
  seconds=(dt.datetime.fromisoformat(end)-dt.datetime.fromisoformat(start)).total_seconds() if start and end else None
 else:
  job=j['TrainingJobName'];status=j['TrainingJobStatus'];cfg=j['ResourceConfig'];seconds=j.get('BillableTimeInSeconds')
 if status not in ('Completed','Failed','Stopped') or seconds is None:raise RuntimeError(f'Incomplete job or missing runtime: {job} {status}')
 if cfg['InstanceType'] not in rates:raise RuntimeError('Missing rate: '+cfg['InstanceType'])
 price=rates[cfg['InstanceType']];cost=price*seconds*cfg['InstanceCount']/3600
 summaries.append({'name':job,'status':status,'instance':cfg['InstanceType'],'count':cfg['InstanceCount'],'seconds':seconds,'rate_usd_per_hour':price,'compute_estimate_usd':cost})
 save(receipts/(job+'.json'),j)
summary={'source':'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonSageMaker/current/us-east-1/index.json','rates_observed':'2026-11-09','jobs':summaries,'compute_estimate_usd':sum(j['compute_estimate_usd'] for j in summaries),'excludes':['EBS','S3','ECR','CloudWatch','taxes','other account activity'],'note':'Estimate from job timestamps and public prices, not billed charges'}
save(out/'compute-cost-estimate.json',summary)
start=dt.datetime.fromisoformat(parent['CreationTime']);end=dt.datetime.fromisoformat(parent['EndTime'])
print(json.dumps({'status':parent['AutoMLJobStatus'],'seconds':(end-start).total_seconds(),'candidate_count':len(candidates['Candidates']),'best':parent['BestCandidate']['CandidateName'],'validation_auc':parent['BestCandidate']['FinalAutoMLJobObjectiveMetric']['Value'],'compute_estimate_usd':summary['compute_estimate_usd'],'job_count':len(summaries)},indent=2))
