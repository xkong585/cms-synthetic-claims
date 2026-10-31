"""Aggregate-only ML reporting; no participant predictions are published."""
import json, html
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def publish(root, result):
    r=root/'reports';e=root/'evidence';r.mkdir(exist_ok=True)
    (e/'ml_results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    scores=result['scores'];frame=result['primary_metric']
    if 'calibration' in result:
        fig,ax=plt.subplots(figsize=(8,4));ax.plot([0,1],[0,1],'--',color='grey',label='Perfect calibration')
        for name in dict.fromkeys(x['model'] for x in result['calibration']):
            points=[x for x in result['calibration'] if x['model']==name];ax.plot([x['mean_probability'] for x in points],[x['observed_rate'] for x in points],marker='o',label=name)
        ax.set(xlabel='Mean predicted probability',ylabel='Observed fraction');ax.legend(fontsize=8);fig.tight_layout();fig.savefig(r/'ml_calibration.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4));ax.barh([x['model'] for x in scores],[x[frame] for x in scores],color='#147d78');ax.set_xlabel(frame);ax.set_title(result['title']);fig.tight_layout();fig.savefig(r/'ml_comparison.png',dpi=160);plt.close(fig)
    columns=['model']+[k for k in scores[0] if k!='model']
    rows=[[str(x.get(k,'')) if not isinstance(x.get(k),float) else f"{x[k]:.4f}" for k in columns] for x in scores]
    table='<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'
    body='<h1>'+result['title']+'</h1><p>'+html.escape(result['scope'])+'</p><h2>Validation</h2><p>'+html.escape(result['validation'])+'</p>'+table+'<img src="ml_comparison.png" style="width:100%;max-width:900px"><h2>Interpretation and limits</h2><p>'+html.escape(result['limitations'])+'</p><p><a href="ml_brief.pdf">Download ML brief</a> · <a href="../evidence/ml_results.json">Full aggregate evidence</a> · <a href="report.html">Original analysis</a></p>'
    body += '<h2>Interpretation diagnostics</h2><p>Permutation importance is a predictive diagnostic, not a causal effect. Correlated features can share importance.</p><pre style="white-space:pre-wrap">'+html.escape(json.dumps(result['permutation_importance'],indent=2))+'</pre>'
    if 'calibration' in result:body += '<img src="ml_calibration.png" style="width:100%;max-width:850px">'
    body += '<h2>Subgroup errors</h2><details><summary>Show age/sex and other aggregate diagnostics</summary><pre style="white-space:pre-wrap">'+html.escape(json.dumps(result['subgroups'],indent=2))+'</pre></details>'
    (r/'ml_report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+result['title']+'</title><style>body{font:16px system-ui;background:#f6f4ec;color:#183a3a;max-width:1100px;margin:50px auto;padding:24px}h1{font-size:38px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #cbd8d5;text-align:left}a{color:#096c64}p{line-height:1.7}</style>'+body)
    styles=getSampleStyleSheet();story=[Paragraph(result['title'],styles['Title']),Spacer(1,12)]
    for heading,key in [('Scope','scope'),('Validation','validation')]:story += [Paragraph(heading,styles['Heading2']),Paragraph(result[key],styles['BodyText']),Spacer(1,8)]
    # Compact table fits letter page. Full precision remains in JSON.
    short=['model',frame];data=[short]+[[str(x[k]) if k=='model' else f'{x[k]:.4f}' for k in short] for x in scores]
    t=Table(data,colWidths=[340,120]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#147d78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('BOTTOMPADDING',(0,0),(-1,-1),9),('LINEBELOW',(0,0),(-1,-1),.3,colors.lightgrey)]));story += [t,Spacer(1,12),Image(str(r/'ml_comparison.png'),width=460,height=204),Paragraph('Interpretation and limits',styles['Heading2']),Paragraph(result['limitations'],styles['BodyText'])]
    SimpleDocTemplate(str(r/'ml_brief.pdf'),pagesize=(612,792),rightMargin=54,leftMargin=54,topMargin=36,bottomMargin=36).build(story)

def link_main(root):
    for name in ['report.html','index.html']:
        p=root/'reports'/name
        if p.exists():
            s=p.read_text();banner='<aside style="padding:18px;background:#d8eee7;text-align:center"><a href="ml_report.html">Machine learning supplement: validation, model comparison and limitations</a></aside>'
            import re
            s=re.sub(r'(<body[^>]*>)',lambda m:m[0]+banner,s,count=1);p.write_text(s)
