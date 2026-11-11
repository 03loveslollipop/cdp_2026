"""Generate comparison figures from the stored experiment receipts."""
from datetime import datetime
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'figuras'
OUT.mkdir(exist_ok=True)

def load(path):
    return json.loads((ROOT / path).read_text())

def comma(value, digits=3):
    return f'{value:.{digits}f}'.replace('.', ',')

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.labelcolor': '#333333', 'text.color': '#222222',
                     'xtick.color': '#444444', 'ytick.color': '#333333',
                     'pdf.fonttype': 42, 'savefig.facecolor': 'white'})
blue, orange, green = '#4E79A7', '#F28E2B', '#59A18F'

# The custom model is identical in AWS and GCP. AutoML metrics use P(default)>=0.5.
custom = load('output/vertex-custom-normalized.json')['metrics']
aws = load('output/aws-credit/hpo10/test-metrics.json')
gcp = load('output/vertex-automl-native.json')['metrics']
keys = ['default_precision', 'default_recall', 'default_f1', 'roc_auc']
names = ['Precisión', 'Recall', 'F1', 'ROC-AUC']
series = [('Personalizado AWS / GCP', custom, blue),
          ('AWS AutoML (10 candidatos)', aws, orange),
          ('GCP AutoML', gcp, green)]
fig, ax = plt.subplots(figsize=(9, 4.05))
y = np.arange(len(keys)); height = 0.23
for i, (label, data, color) in enumerate(series):
    values = [data[k] for k in keys]
    bars = ax.barh(y + (i-1)*height, values, height, label=label, color=color)
    for bar, value in zip(bars, values):
        ax.text(value + .012, bar.get_y()+bar.get_height()/2, comma(value), va='center', fontsize=9)
ax.set_yticks(y, names); ax.invert_yaxis(); ax.set_xlim(0, 0.83)
ax.set_xlabel('Valor de la métrica en TEST (clase de incumplimiento = 0)')
ax.xaxis.grid(True, alpha=.18); ax.set_axisbelow(True)
ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.20), ncol=3, frameon=False, fontsize=9)
fig.subplots_adjust(left=.15, right=.97, top=.79, bottom=.15)
fig.savefig(OUT/'metricas.pdf', bbox_inches='tight')
fig.savefig(OUT/'metricas.png', dpi=200, bbox_inches='tight')
plt.close(fig)

# Rates and usage are distinct estimates, not final bills; GCP AutoML is a budget.
aws_job = load('output/aws-credit/processing-job.json')
start = datetime.fromisoformat(aws_job['ProcessingStartTime'])
end = datetime.fromisoformat(aws_job['ProcessingEndTime'])
aws_custom = (end-start).total_seconds() * 0.115 / 3600
vertex_custom = load('output/gcp-receipts/cost-estimate.json')['worker_cost_estimate_usd']
azure_hour = load('output/cloud-comparison/azure-d2sv5.json')['items'][0]['retailPrice']
aws_auto = load('output/aws-credit/hpo10/compute-cost-estimate.json')['compute_estimate_usd']
values = [[aws_custom, vertex_custom, 212*azure_hour/3600], [aws_auto, 21.252, azure_hour]]
fig, axes = plt.subplots(1, 2, figsize=(9, 3.65), gridspec_kw={'width_ratios':[1,1.1]})
for ax, vals, title, maxval, places in zip(axes, values,
        ['Pipeline personalizado', 'AutoML'], [0.010, 27], [4, 3]):
    bars = ax.barh([0,1,2], vals, color=[orange,blue,green], height=.54)
    bars[1].set_hatch('//') if title == 'AutoML' else None
    bars[2].set_hatch('..')
    for bar, value in zip(bars, vals):
        ax.text(value + maxval*.025, bar.get_y()+bar.get_height()/2,
                'USD '+comma(value, places), va='center', fontsize=9)
    ax.set_yticks([0,1,2], ['AWS','GCP','Azure'])
    ax.invert_yaxis(); ax.set_xlim(0,maxval); ax.set_title(title,fontsize=11,weight='bold',pad=10)
    ax.set_xlabel('USD'); ax.xaxis.grid(True,alpha=.18); ax.set_axisbelow(True)
    ax.tick_params(axis='x',labelsize=8)
axes[0].set_xticks([0,.005,.010],['0','0,005','0,010'])
axes[1].set_xticks([0,10,20],['0','10','20'])
fig.text(.5,.04,'GCP AutoML: presupuesto máximo  •  Azure: escenario hipotético\nCómputo solamente; no incluye almacenamiento ni otros cargos',ha='center',fontsize=9,color='#444444')
fig.subplots_adjust(left=.07,right=.98,top=.88,bottom=.29,wspace=.35)
fig.savefig(OUT/'costos.pdf',bbox_inches='tight')
fig.savefig(OUT/'costos.png',dpi=200,bbox_inches='tight')
plt.close(fig)
print('Gráficos guardados en', OUT)
