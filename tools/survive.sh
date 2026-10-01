#!/bin/zsh
# The Aquila under the Mandate strike group's focused fire, without the mind (the lead's balance check in the real game):
# hull, shields, heat, speed, the ranges to the Acheron, a Styx and the Praetorian, and the helm's and tactical's modes every 15 s.
#   tools/survive.sh [label]
cd "$(dirname "$0")/.."
PY=/opt/homebrew/bin/python3.13
LABEL=${1:-run}
$PY tools/play.py quit >/dev/null 2>&1; pkill -f astra-mind
while pgrep -f astra_harness_port >/dev/null; do sleep 1; done
$PY tools/play.py launch --nomind 2>&1 | tail -1 | cut -c1-30
sleep 10
$PY tools/play.py cmd "astra.battle.time 170" >/dev/null
sleep 14                                   # (the strike group arrives at 180: an order before that applies to nobody)
$PY tools/play.py cmd 'astra.cmd mandate_tactics {"focus":"AQUILA","stance":"flank","missiles":"salvo","ew":"jam"}' | tail -1 | cut -c1-160
for i in {1..24}; do
  sleep 15
  $PY tools/play.py ship 2>/dev/null | $PY -c "
import json,sys
s=json.load(sys.stdin)
th=s.get('thermal') or {}; sh=s.get('shields') or {}
cs={c.get('id'):c for c in s.get('contacts',[])}
r=lambda k: cs.get(k,{}).get('range_km','-')
st=s.get('stations') or {}
modes={k:(v.get('modes') if isinstance(v,dict) else v) for k,v in st.items() if k in ('helm','tactical')}
print('$LABEL t=%3ds hull %s%% sh %s heat %s rad %s | spd %s | T21 %s T22 %s T01 %s | incidents %d' % ($i*15, s.get('hull_pct'), sh.get('strength_pct'), th.get('heat_pct'), th.get('radiators'), s.get('speed_mps'), r('T-21'), r('T-22'), r('T-01'), len(s.get('damage') or [])))
" || break
  $PY tools/play.py ship 2>/dev/null | grep -q '"abandon": *{' && break
done
