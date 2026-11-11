"""Export identical Vertex AutoML partitions for AWS; TEST stays separate."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

source = Path('output/cloud-data-gcp/automl.csv')
out = Path('output/aws-credit/autopilot-data')
out.mkdir(parents=True, exist_ok=True)
with source.open(newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    assert fields and 'data_split' in fields and 'Pago_atiempo' in fields
    features = [x for x in fields if x not in ('data_split', 'Pago_atiempo')]
    buckets = {x: [] for x in ('TRAIN', 'VALIDATE', 'TEST')}
    for row in reader:
        buckets[row['data_split']].append(row)
expected={'TRAIN':(6027,331),'VALIDATE':(1507,72),'TEST':(3229,108)}
for split, rows in buckets.items():
    assert (len(rows), sum(r['Pago_atiempo']=='0' for r in rows)) == expected[split]
    filename=out / (split.lower()+'.csv')
    with filename.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=features+['Pago_atiempo'],extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
with (out/'test-features.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f)
    w.writerows([[r[x] for x in features] for r in buckets['TEST']])
with (out/'test-labels.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['Pago_atiempo']); w.writerows([[r['Pago_atiempo']] for r in buckets['TEST']])
with Path('output/cloud-data-gcp/holdout-features.csv').open(newline='',encoding='utf-8') as f:
    previous=csv.DictReader(f)
    assert previous.fieldnames==['row_id']+features
    for row, reference in zip(buckets['TEST'],previous,strict=True):
        assert all(row[k]==reference[k] for k in features)
manifest={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'features':features,'partitions':{},'test_input_has_header':False}
for split, rows in buckets.items():
    p=out/(split.lower()+'.csv')
    manifest['partitions'][split]={'rows':len(rows),'label_counts':dict(Counter(r['Pago_atiempo'] for r in rows)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest['partitions'],indent=2))
