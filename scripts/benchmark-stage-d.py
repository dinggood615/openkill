#!/usr/bin/env python3
"""Local control-plane benchmark for pure OpenKill state helpers."""
import json, statistics, subprocess, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HELPER=Path(__import__('os').environ.get('OPENKILL_BENCH_HELPER', str(ROOT/'luci-app-openkill/root/usr/share/openkill/openkill_network.sh')))

def invoke(fn, *args):
    cmd='. "$1"; '+fn+' '+' '.join('"$%d"'%(i+2) for i in range(len(args)))
    return subprocess.run(['sh','-c',cmd,'bench',str(HELPER),*map(str,args)],capture_output=True,text=True,check=True)

def main():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); s=p/'snapshot'; old=p/'old'; new=p/'new'; out=p/'batch'; v4=p/'v4'; v6=p/'v6'
        payload='WAN4_L3_DEVICE=eth0\nWAN4_ADDRESSES=192.0.2.1\nWAN6_L3_DEVICE=eth1\nWAN6_ADDRESSES=2001:db8::1\nNATIVE_IPV6_ROUTES=default from 2001:db8::/64\nINTERNAL_IPV6_PREFIXES=fd00::/8\nDNS_SERVERS=1.1.1.1\nTUN_OWNER=openkill\nIPV4_ENABLED=1\nIPV6_ENABLED=1\n'
        s.write_text(payload); old.write_text(payload); new.write_text(payload); v4.write_text('203.0.113.1\n'); v6.write_text('2001:db8::2\n')
        helper_text=HELPER.read_text()
        cases={'desired_state':('openkill_build_desired_state',(s,p/'desired')),
               'fingerprint':('openkill_network_fingerprint',(s,p/'fp')),
               'noop_diff':('openkill_desired_diff',(old,new)),}
        if 'openkill_render_nft_set_batch()' in helper_text:
            cases['nft_batch']=('openkill_render_nft_set_batch',(v4,v6,out))
        if 'openkill_render_classifier_order()' in helper_text:
            cases['classifier']=('openkill_render_classifier_order',())
        result={}
        for name,(fn,args) in cases.items():
            samples=[]
            for _ in range(5): invoke(fn,*args)
            for _ in range(100):
                t=time.perf_counter_ns(); invoke(fn,*args); samples.append((time.perf_counter_ns()-t)/1e6
                )
            ordered=sorted(samples); result[name]={'iterations':100,'median_ms':statistics.median(samples),'p95_ms':ordered[94]}
        print(json.dumps({'stage':'D','environment':'local-linux','scenarios':result},indent=2,sort_keys=True))
if __name__=='__main__': main()
