"""Sustained hardware test: discard media after numeric statistics; no recordings."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from glasses.usb_transport import USBTransport


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=60)
    args=parser.parse_args()
    if args.seconds<1:parser.error('seconds must be positive')
    config=json.loads((ROOT/'config.app.json').read_text(encoding='utf-8'))['xiao_usb']
    transport=USBTransport(config)
    totals={'samples':0,'sum_squares':0.,'peak':0.}
    def receive(data,*unused):
        totals['samples']+=len(data)
        totals['sum_squares']+=float(np.sum(data*data))
        totals['peak']=max(totals['peak'],float(np.max(np.abs(data))))
    started=time.monotonic();samples=[]
    try:
        transport.set_camera(True);transport.set_audio(True,receive)
        while time.monotonic()-started<args.seconds:
            time.sleep(.25)
            if transport.error:raise RuntimeError(transport.error)
            if transport.device and (not transport.device['camera_ready'] or not transport.device['microphone_ready']):
                raise RuntimeError('Firmware reports unready hardware')
            elapsed=time.monotonic()-started
            if not samples or elapsed-samples[-1]['elapsed']>=10:
                row={'elapsed':elapsed,'frames':transport.frames_received,'audio_samples':totals['samples'],'bad_packets':transport.parser.bad_packets}
                samples.append(row)
                print(json.dumps(row),flush=True)
        elapsed=time.monotonic()-started
        frame,stamp=transport.snapshot()
        result={'scope':'Sustained native USB transport only; raw images/audio are not retained; no spoken-recognition or acoustic-onset claim','duration_s':elapsed,'frame_shape':list(frame.shape),'frames':transport.frames_received,'fps':transport.frames_received/elapsed,'audio_samples':totals['samples'],'received_samples_per_second':totals['samples']/elapsed,'audio_rms':(totals['sum_squares']/max(1,totals['samples']))**.5,'peak':totals['peak'],'bad_packets':transport.parser.bad_packets,'device':transport.device,'samples':samples}
        if result['bad_packets'] or result['fps']<2.5 or result['received_samples_per_second']<15000:
            raise RuntimeError('Stream throughput/integrity failed: '+json.dumps(result))
        target=ROOT/'logs/validation/xiao-stream-stability.json'
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS: '+json.dumps({k:v for k,v in result.items() if k not in {'samples','device'}},ensure_ascii=False),flush=True)
    finally:
        transport.set_audio(False);transport.set_camera(False)


if __name__=='__main__':main()
