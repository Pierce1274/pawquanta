"""Private, explicit one-off mining pause. Contains no credentials or commands."""
import json
from pathlib import Path
import time
from core_runtime import MAIN_GENESIS

def read(profile):
    file=Path(profile)/'mining-schedule.json'
    if not file.exists():return None
    value=json.loads(file.read_text())
    if value.get('genesis')!=MAIN_GENESIS or value.get('state') not in ('paused','resume_requested','cancelled'):raise ValueError('Invalid mining schedule identity')
    if type(value.get('resume_at_utc')) not in (int,float) or not 0<value['resume_at_utc']<4102444800:raise ValueError('Invalid scheduled resume time')
    return value

def update(profile,value,state):
    value={**value,'state':state,'changed_at_utc':time.time()}
    file=Path(profile)/'mining-schedule.json';temporary=file.with_suffix('.new')
    temporary.write_text(json.dumps(value,indent=2));temporary.replace(file)

def cancel(profile):
    value=read(profile)
    if value and value['state']!='cancelled':update(profile,value,'cancelled')
