"""Fail-closed one-command pipeline: source -> staging -> claims -> annual ledger -> report."""
from pathlib import Path
import json,os,platform,subprocess,time
from datetime import datetime,timezone
from importlib.metadata import version
from download_data import ROOT,download,sha
from claims import build
from analyze import analyze

def run(tests=True):
    start=time.perf_counter();e=ROOT/'evidence';e.mkdir(parents=True,exist_ok=True)
    reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    public=['report.html','brief.pdf','ml_report.html','ml_brief.pdf','READY.json']
    for name in public:(reports/name).unlink(missing_ok=True)
    log={'started_at_utc':datetime.now(timezone.utc).isoformat(),'status':'running','steps':[]}
    try:
        t=time.perf_counter();download();log['steps'].append({'stage':'download_verify','seconds':round(time.perf_counter()-t,3)})
        t=time.perf_counter();parts=build();log['steps'].append({'stage':'typed_staging_claim_resolution_annual_ledger','seconds':round(time.perf_counter()-t,3)})
        t=time.perf_counter();payload,ledger,annual=analyze(parts);log['steps'].append({'stage':'independent_SQL_and_descriptives','seconds':round(time.perf_counter()-t,3)})
        from ml import run_ml
        t=time.perf_counter();run_ml();log['steps'].append({'stage':'ML_benchmarks','seconds':round(time.perf_counter()-t,3)})
        if tests:
            subprocess.run([os.sys.executable,'-m','pytest','-q','tests','--junitxml=evidence/tests.xml'],cwd=ROOT,check=True)
        from report import create_report
        create_report(payload,ledger,annual)
        from ml_report import link_main
        link_main(ROOT)
        (reports/'READY.json').write_text(json.dumps({'status':'passed','source_lock_sha256':sha(ROOT/'docs/source_lock.json'),'year':2008,'sample':1,'synthetic':True},indent=2))
        log['ml_plan_sha256']=__import__('hashlib').sha256((ROOT/'docs/ml_plan.md').read_bytes()).hexdigest()
        log.update(status='passed',elapsed_seconds=round(time.perf_counter()-start,3),environment={'python':platform.python_version(),'platform':platform.platform(),'packages':{p:version(p) for p in ['pandas','numpy','pyarrow','duckdb','matplotlib','reportlab','pytest','scikit-learn','joblib','threadpoolctl']}},source_lock_sha256=sha(ROOT/'docs/source_lock.json'),scope_sha256=sha(ROOT/'docs/scope.md'))
    except Exception as exc:
        for name in public:(reports/name).unlink(missing_ok=True)
        (ROOT/'evidence/ml_results.json').unlink(missing_ok=True)
        log.update(status='failed',error=str(exc),elapsed_seconds=round(time.perf_counter()-start,3));raise
    finally:(e/'run_log.json').write_text(json.dumps(log,indent=2)+'\n')
if __name__=='__main__':run()
