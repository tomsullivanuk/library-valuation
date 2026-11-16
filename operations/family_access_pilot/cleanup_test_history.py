"""Preview or execute a specific, backed-up test-request cleanup on the server."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from valuation.request_maintenance import preview,purge
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--submission',action='append',default=[]);p.add_argument('--test-email',action='append',default=[]);p.add_argument('--plan',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--backup-directory',type=Path)
a=p.parse_args();c=json.loads(a.config.read_text())
if a.execute:
 if not a.backup_directory:p.error('--execute requires --backup-directory')
 print(json.dumps(purge(c,json.loads(a.plan.read_text()),a.backup_directory),indent=2))
else:
 if a.plan.exists():p.error('Choose a new plan file')
 result=preview(c,a.submission,a.test_email);a.plan.write_text(json.dumps(result,indent=2));a.plan.chmod(0o600);print(json.dumps(dict(submissions=len(result['submissions']),requested_books=sum(x['books'] for x in result['submissions']),plan=str(a.plan)),indent=2))
