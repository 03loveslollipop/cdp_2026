"""Score a single AWS batch output against the untouched GCP test labels."""
import ast
import csv
import json
import sys
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

predictions, labels_path, output = map(Path, sys.argv[1:4])
with labels_path.open(newline='') as f:
    y=np.array([int(r['Pago_atiempo']) == 0 for r in csv.DictReader(f)])
probs=[]
with predictions.open(newline='') as f:
    for row in csv.reader(f):
        if len(row)!=3:
            raise ValueError(f'Expected predicted_label,probabilities,labels; got {row!r}')
        values=ast.literal_eval(row[1]); classes=[str(x) for x in ast.literal_eval(row[2])]
        if sorted(classes)!=['0','1'] or len(values)!=2:
            raise ValueError(f'Unexpected classes or probabilities: {row!r}')
        vals=[float(v) for v in values]
        if any(not np.isfinite(v) or v<0 or v>1 for v in vals) or not np.isclose(sum(vals),1,atol=1e-5):
            raise ValueError(f'Invalid probability distribution: {row!r}')
        probs.append(vals[classes.index('0')])
if len(probs)!=len(y):
    raise ValueError(f'Expected {len(y)} predictions, got {len(probs)}')
p=np.array(probs); pred=p>=0.5
tn,fp,fn,tp=confusion_matrix(y,pred,labels=[False,True]).ravel()
r={'positive_class':'Pago_atiempo=0','threshold':0.5,'rows':len(y),
   'accuracy':accuracy_score(y,pred),'default_precision':precision_score(y,pred,zero_division=0),
   'default_recall':recall_score(y,pred,zero_division=0),'default_f1':f1_score(y,pred,zero_division=0),
   'roc_auc':roc_auc_score(y,p),'average_precision':average_precision_score(y,p),
   'confusion':{'TP':int(tp),'TN':int(tn),'FP':int(fp),'FN':int(fn)}}
output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
