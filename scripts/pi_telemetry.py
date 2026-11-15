"""Linux Pi telemetry/perf collector; never invents Windows or power data."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--perf", action="store_true")
    args = parser.parse_args()
    if platform.system()!="Linux":
        raise RuntimeError("Run this collector on the actual Linux Raspberry Pi")
    if args.seconds<1:
        parser.error("--seconds must be positive")
    state=json.loads((ROOT/'runtime/processes.json').read_text())
    pids=[state['app_pid'],state['vlm_pid']]
    perf=None
    if args.perf:
        executable=shutil.which('perf')
        if executable is None:
            raise RuntimeError("Install matching Linux perf before --perf")
        perf=subprocess.Popen([executable,'stat','-x,','-e','cycles,instructions,cache-references,cache-misses','-p',','.join(map(str,pids)),'--timeout',str(args.seconds*1000),'-o',str(ROOT/'logs/pi-perf.csv')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    rows=[];psutil.cpu_percent()
    for _ in range(args.seconds):
        time.sleep(1)
        processes=[psutil.Process(pid) for pid in pids]
        thermal=Path('/sys/class/thermal/thermal_zone0/temp')
        row={'time':time.time(),'cpu_percent':psutil.cpu_percent(),'rss_mib':sum(p.memory_info().rss for p in processes)/1024**2,'available_memory_mib':psutil.virtual_memory().available/1024**2,'temperature_c':float(thermal.read_text())/1000 if thermal.exists() else None,'power_w':None}
        vcgencmd=shutil.which('vcgencmd')
        row['throttled']=subprocess.check_output([vcgencmd,'get_throttled'],text=True).strip() if vcgencmd else None
        rows.append(row)
    result={'scope':'Actual Linux host only; power/energy require external meter','samples':rows}
    if perf:
        _,error=perf.communicate(timeout=5)
        result['perf_returncode']=perf.returncode;result['perf_error']=error
    (ROOT/'logs/pi-telemetry.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'samples':len(rows),'perf_returncode':result.get('perf_returncode'),'power_measured':False}))


if __name__=='__main__':main()
