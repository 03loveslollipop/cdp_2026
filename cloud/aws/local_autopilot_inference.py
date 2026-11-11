"""Call the three local SageMaker inference containers, preserving CSV row order."""
import argparse
import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--ports', nargs=3, type=int, required=True)
p.add_argument('--input', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
with a.input.open(newline='',encoding='utf-8') as f:
    rows=list(csv.reader(f))
results=[]
for offset in range(0,len(rows),64):
    batch=rows[offset:offset+64]
    s=io.StringIO(newline=''); csv.writer(s,lineterminator='\n').writerows(batch)
    data=s.getvalue().encode()
    for port in a.ports:
        req=urllib.request.Request(f'http://127.0.0.1:{port}/invocations',data=data,headers={'Content-Type':'text/csv','Accept':'text/csv'})
        with urllib.request.urlopen(req,timeout=120) as response:
            data=response.read()
    parsed=list(csv.reader(io.StringIO(data.decode())))
    if len(parsed)!=len(batch): raise ValueError(f'Prediction count mismatch at {offset}: {len(parsed)} vs {len(batch)}')
    results.extend(parsed)
with a.output.open('w',newline='',encoding='utf-8') as f:
    csv.writer(f,lineterminator='\n').writerows(results)
print(json.dumps({'rows':len(results),'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))
