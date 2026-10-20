"""Explicit one-shot start/end plans. App must remain open and computer awake."""
import math,time
from pathlib import Path
from wallet_v1 import atomic_json
from core_runtime import MAIN_GENESIS


def read(profile):
    file=Path(profile)/'mining-plan-v1.json'
    if not file.exists():return None
    plan=__import__('json').loads(file.read_text())
    if plan.get('genesis')!=MAIN_GENESIS or plan.get('state') not in ('armed','completed','cancelled'):raise ValueError('Invalid mining plan')
    for key in ('start','end'):
        if type(plan.get(key)) not in (int,float) or not math.isfinite(plan[key]):raise ValueError('Invalid plan time')
    if not plan['start']<plan['end']:raise ValueError('Plan end must follow its start')
    return plan


def save(profile,start,duration_minutes,now=None):
    now=time.time() if now is None else now
    if not math.isfinite(start) or not now-60<=start<=now+365*86400:raise ValueError('Choose a start within the next year')
    if type(duration_minutes) is not int or not 1<=duration_minutes<=43200:raise ValueError('Duration must be 1 to 43,200 minutes')
    value={'genesis':MAIN_GENESIS,'state':'armed','start':start,'end':start+duration_minutes*60}
    atomic_json(Path(profile)/'mining-plan-v1.json',value);return value


def state(profile,value,new):
    value={**value,'state':new};atomic_json(Path(profile)/'mining-plan-v1.json',value)


def cancel(profile):
    value=read(profile)
    if value and value['state']=='armed':state(profile,value,'cancelled')


def phase(value,now=None):
    now=time.time() if now is None else now
    if not value or value['state']!='armed':return 'inactive'
    return 'waiting' if now<value['start'] else 'ended' if now>=value['end'] else 'active'
