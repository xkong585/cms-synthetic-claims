"""Aggregate-only, synthetic-labeled research report and two-page brief."""
from pathlib import Path
import html,json,os
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.utils import ImageReader
from claims import ROOT

TEAL='#087e81';INK='#143c45'
LIMITATIONS='Fully synthetic data for software development and training, not real patient records or reliable Medicare population inference. Claim counts are not hospitalization episodes. The annual rule is claim-through date, not admission or payment year. Partial coverage and death can limit observation; counts per beneficiary are not full-year incidence rates. Conflicting claims are quarantined and affected beneficiaries excluded from complete-analysis summaries; exclusions can change the descriptive distributions. Synthetic dates, covered days and amounts must not be altered to make medical patterns look realistic. No hospital ranking, causal conclusion, cost saving or clinical recommendation is supported.'

def charts(ledger,annual):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','text.color':INK,'figure.facecolor':'white'})
    d=ledger[ledger.analysis_eligible];p=d.payment_total_cents.dropna().astype(float)/100
    labels=['Negative','$0','$0-<1k','$1k-<5k','$5k-<10k','$10k-<25k','$25k+']
    masks=[p.lt(0),p.eq(0),p.gt(0)&p.lt(1000),p.ge(1000)&p.lt(5000),p.ge(5000)&p.lt(10000),p.ge(10000)&p.lt(25000),p.ge(25000)]
    counts=[int(m.sum()) for m in masks]
    pd.DataFrame({'synthetic_payment_band':labels,'beneficiaries':counts}).to_csv(ROOT/'evidence/payment_distribution.csv',index=False)
    fig,ax=plt.subplots(figsize=(8,3.4),layout='constrained');ax.bar(labels,counts,color=[TEAL if l!='$0' else '#9dcdd0' for l in labels]);ax.set_ylabel('Synthetic beneficiaries');ax.set_title('Synthetic 2008 payment distribution (including true zeros)',loc='left')
    for i,n in enumerate(counts):ax.text(i,n+max(counts)*.018,f'{n:,}',ha='center',fontsize=9)
    ax.set_ylim(0,max(counts)*1.18);ax.tick_params(axis='x',labelsize=8);fig.savefig(ROOT/'reports/payment_distribution.png',dpi=180);plt.close(fig)
    t=pd.read_csv(ROOT/'evidence/summary_tables.csv');t=t[(t.scope=='All coverage')&t.age_group.isin(['<65','65-74','75-84','85+'])]
    fig,axes=plt.subplots(1,2,figsize=(9,3.3),layout='constrained')
    axes[0].bar(t.age_group,t.claimant_fraction*100,color=TEAL);axes[0].set_ylabel('With >=1 accepted claim (%)');axes[0].set_title('Synthetic claimants by age')
    axes[1].bar(t.age_group,t.payment_mean_USD,color='#bf893e');axes[1].set_ylabel('Synthetic payment / beneficiary (USD)');axes[1].set_title('Includes zero-claim beneficiaries')
    fig.savefig(ROOT/'reports/age_group_summary.png',dpi=180);plt.close(fig)
    # Diagram is conceptual, not a screenshot of synthetic individual records.
    fig,ax=plt.subplots(figsize=(9,2.2),layout='constrained');ax.axis('off')
    boxes=[('Segment staging','Person + claim + segment'),('Claim table','Person + claim'),('2008 claim domain','Thru date in 2008'),('Annual ledger','Every beneficiary')]
    for i,(title,sub) in enumerate(boxes):
        x=.02+i*.25;ax.text(x+.105,.55,title+'\n'+sub,ha='center',va='center',fontsize=10,bbox={'boxstyle':'round,pad=.9','facecolor':'#e7f2f1','edgecolor':TEAL},transform=ax.transAxes)
        if i<3:ax.annotate('',xy=(x+.24,.55),xytext=(x+.21,.55),arrowprops={'arrowstyle':'->','color':TEAL},xycoords=ax.transAxes)
    ax.text(.5,.1,'SYNTHETIC · Sample 1 · Claim amounts counted once only after conflict checks',ha='center',transform=ax.transAxes,fontsize=10)
    fig.savefig(ROOT/'reports/grain_flow.png',dpi=170);plt.close(fig)

def brief(payload):
    b=payload['build'];m=payload['summaries'][0];sens=next(r for r in payload['summaries'] if r['scope']=='Part A 12 months' and r['age_group']=='All ages')
    c=canvas.Canvas(str(ROOT/'reports/brief.pdf'),pagesize=(612,792));c.setTitle('Synthetic Medicare Claims | Sample 1 | 2008');c.setAuthor('Xiangyi (Sam) Kong')
    style=ParagraphStyle('p',fontName='Helvetica',fontSize=10,leading=15,textColor=HexColor(INK))
    def text(s,y):
        p=Paragraph(s,style);_,h=p.wrap(516,200);p.drawOn(c,48,y-h);return y-h
    def header(page,title):
        c.setFillColor(HexColor(TEAL));c.rect(0,744,612,48,fill=1,stroke=0);c.setFillColor(HexColor('#ffffff'));c.setFont('Helvetica-Bold',11);c.drawString(48,763,'SYNTHETIC / CMS DE-SynPUF / SAMPLE 1 / 2008')
        c.setFillColor(HexColor(INK));c.setFont('Helvetica-Bold',22);c.drawString(48,706,title)
        c.setFont('Helvetica',9);c.drawString(48,28,'Xiangyi (Sam) Kong | Independent software/data-quality portfolio | 31 Oct 2026');c.drawRightString(564,28,f'{page} / 2')
    header(1,'Claims data that reconcile.')
    text('A reproducible Python and SQL workflow over CMS synthetic inpatient claims. Annual membership: CLM_THRU_DT in 2008. No real patient or Kaiser data.',683)
    c.setFont('Helvetica-Bold',30);c.drawString(48,606,f'{b["raw_beneficiaries"]:,}');c.drawString(306,606,f'{m["accepted_claims"]:,}')
    text('Synthetic beneficiaries in the full ledger',590);c.setFont('Helvetica',10);c.drawString(306,578,'Consistent claims in complete domain');text('Complete-domain claims: 27,449 across 116,331 nonambiguous beneficiaries. Another 21 beneficiaries remain in the ledger but are excluded from complete summaries.',560)
    c.drawImage(ImageReader(str(ROOT/'reports/grain_flow.png')),48,380,width=516,height=126,mask='auto')
    text(f'<b>Grain check.</b> {b["raw_segments"]:,} source rows represent {b["distinct_claims"]:,} claim keys. Of 68 multi-segment claims, 67 have conflicting fields and are quarantined. Claim-level billing dates can be recovered from consistent nonmissing segment values; conflicting payments are never summed or chosen arbitrarily.',360)
    text('<b>Annual flow.</b> 27,496 original claim keys end in 2008; 21 are quarantined. The remaining 27,475 accepted claims link many-to-one to the beneficiary table without row or payment inflation. Excluding all accepted claims belonging to the 21 affected people yields the complete-domain 27,449 claims.',255)
    text(f'<b>Descriptive result.</b> {m["claimants"]:,} of {m["analysis_beneficiaries"]:,} nonambiguous synthetic beneficiaries ({m["claimant_fraction"]*100:.2f}%) have an accepted claim. There are {b["zero_claim_beneficiaries"]:,} true zero-claim beneficiaries. These are sample descriptions, not population or annual incidence estimates.',150)
    c.showPage();header(2,'Payments, coverage and limits.')
    c.drawImage(ImageReader(str(ROOT/'reports/payment_distribution.png')),48,433,width=516,height=219,mask='auto')
    text(f'<b>Denominator.</b> Among {m["analysis_beneficiaries"]:,} nonambiguous people, including true zeros, mean synthetic claim payment is ${m["payment_mean_USD"]:,.2f}; median $0; p90 ${m["payment_p90_USD"]:,.0f}. The 12-month Part A domain has {sens["analysis_beneficiaries"]:,} people and claimant share {sens["claimant_fraction"]*100:.2f}%.',417)
    text('<b>Exact reconciliation.</b> Independent DuckDB reconstructs claim grain from staged segments; SQLite separately checks canonical annual claims. Sixteen count/cent identities pass. The official expanded formula, payment + covered days x pass-through per diem, exactly reproduces MEDREIMB_IP for all 116,331 paired nonambiguous beneficiaries. Payment-only sums fall short by $2,733,780.',332)
    text('<b>Limits.</b> '+LIMITATIONS,224)
    text('<b>Sources.</b> CMS DE-SynPUF Sample 1 beneficiary/inpatient ZIPs; codebook IP-3/IP-7, Appendix 2, and user manual. Exact URLs and SHA256: docs/source_lock.json. Published outputs contain aggregates only.',91)
    c.save()

def create_report(payload,ledger,annual):
    (ROOT/'reports').mkdir(exist_ok=True);charts(ledger,annual);brief(payload)
    distributions=pd.read_csv(ROOT/'evidence/payment_distribution.csv').to_dict('records')
    payload={**payload,'distribution':distributions}
    template=(ROOT/'src/report_template.html').read_text()
    (ROOT/'reports/report.html').write_text(template.replace('/*__DATA__*/',json.dumps(payload,allow_nan=False)).replace('__LIMITATIONS__',html.escape(LIMITATIONS)))
    b=payload['build'];m=payload['summaries'][0]
    (ROOT/'docs/resume_bullets.md').write_text(f'''# Verified project statements | completed October 2026

- Built a reproducible Python/DuckDB workflow linking {b['accepted_claims_2008']:,} accepted synthetic inpatient claims to a {b['raw_beneficiaries']:,}-beneficiary ledger in CMS DE-SynPUF Sample 1, with explicit 2008 claim-through-date attribution.
- Audited {b['raw_segments']:,} segment records and quarantined {b['quarantined_claims']} conflicting claim keys; retained zero-claim beneficiaries and separately flagged {b['affected_beneficiaries']} people with unresolved 2008 claims, preventing false zero-payment totals.
- Independently reconciled 16 count/payment identities across Python, DuckDB and SQLite and automated aggregate reporting with exact integer-cent accounting and synthetic-data limitations.

The complete-analysis domain contains {m['accepted_claims']:,} claims across {m['analysis_beneficiaries']:,} nonambiguous beneficiaries. Do not interchange this with the full accepted claim/ledger counts. Do not claim real patient analysis, clinical benefit, cost savings or Kaiser employment.\n''')
    (ROOT/'docs/limitations.md').write_text('# Synthetic data and interpretation limits\n\n'+LIMITATIONS+'\n')
