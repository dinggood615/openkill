#!/usr/bin/env python3
"""Local control-plane benchmark for pure OpenKill state helpers."""
import json, os, shutil, statistics, subprocess, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HELPER=Path(__import__('os').environ.get('OPENKILL_BENCH_HELPER', str(ROOT/'luci-app-openkill/root/usr/share/openkill/openkill_network.sh')))

COUNTER_NAMES=('nft','ip','ubus','uci','grep','awk','sed','sort','uniq','cut','tr','cat','cmp','mv')
def invoke(fn, *args, env=None):
    cmd='. "$1"; '+fn+' '+' '.join('"$%d"'%(i+2) for i in range(len(args)))
    return subprocess.run(['sh','-c',cmd,'bench',str(HELPER),*map(str,args)],capture_output=True,text=True,check=True,env=env)

def main():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); s=p/'snapshot'; old=p/'old'; new=p/'new'; out=p/'batch'; v4=p/'v4'; v6=p/'v6'
        payload='SNAPSHOT_NORMALIZED=1\nWAN4_L3_DEVICE=eth0\nWAN4_ADDRESSES=192.0.2.1\nWAN6_L3_DEVICE=eth1\nWAN6_ADDRESSES=2001:db8::1\nWAN6_HOST_ADDRESSES=2001:db8::1/128\nNATIVE_IPV6_ROUTES=default from 2001:db8::/64\nINTERNAL_IPV6_PREFIXES=fd00::/8\nDNS_SERVERS=1.1.1.1\nTUN_OWNER=openkill\nIPV4_ENABLED=1\nIPV6_ENABLED=1\n'
        s.write_text(payload); old.write_text(payload); new.write_text(payload); v4.write_text('203.0.113.1\n'); v6.write_text('2001:db8::2\n')
        helper_text=HELPER.read_text()
        wrapper_dir=p/'bin'; wrapper_dir.mkdir(); counter=p/'counter'; counter.write_text('')
        for name in COUNTER_NAMES:
            real=shutil.which(name)
            if not real: continue
            (wrapper_dir/name).write_text('#!/bin/sh\nprintf "%s\\n" "'+name+'" >> "${OPENKILL_COUNTER_FILE}"\nexec "'+real+'" "$@"\n')
            (wrapper_dir/name).chmod(0o755)
        bench_env=os.environ.copy(); bench_env['PATH']=str(wrapper_dir)+':'+bench_env.get('PATH',''); bench_env['OPENKILL_COUNTER_FILE']=str(counter)
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
            for _ in range(5): invoke(fn,*args,env=bench_env)
            counter.write_text('')
            for _ in range(100):
                t=time.perf_counter_ns(); invoke(fn,*args,env=bench_env); samples.append((time.perf_counter_ns()-t)/1e6
                )
            ordered=sorted(samples); result[name]={'iterations':100,'median_ms':statistics.median(samples),'p95_ms':ordered[94]}
            counts={n:0 for n in COUNTER_NAMES}
            for line in counter.read_text().splitlines():
                if line in counts: counts[line]+=1
            result[name]['command_counts']=counts
            counter.write_text('')
        print(json.dumps({'stage':'D','environment':'local-linux','scenarios':result},indent=2,sort_keys=True))
if __name__=='__main__': main()
