"""Numeric-only wireless capture test. Never retains camera or audio recordings."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from glasses.wifi_transport import WiFiTransport


def local_json(url, data=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                     headers={'Content-Type':'application/json'})
    with opener.open(request, timeout=12) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=25)
    parser.add_argument('--power-phase', choices=['usb_connected','external'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-check', action='store_true')
    args=parser.parse_args()
    if not 5<=args.seconds<=300: parser.error('seconds must be 5--300')
    config=json.loads((ROOT/'config.app.json').read_text(encoding='utf-8'))
    from serial.tools import list_ports
    usb_present=any((p.serial_number or '').lower()==config['xiao_wifi']['expected_mac'].lower() for p in list_ports.comports())
    if args.power_phase=='external' and usb_present:
        raise RuntimeError('The selected board is still enumerated over USB; external-only handoff cannot be claimed')
    t=WiFiTransport(config['xiao_wifi'])
    result={'scope':'Actual AP/TCP JPEG/PCM transport; no recorded media, ASR accuracy, acoustic onset or Pi timing',
            'power_phase':args.power_phase,'matching_usb_device_present':usb_present,'passed':False}
    try:
        device=local_json('http://192.168.4.1/api/status')
        if device.get('transport')!='wifi_tcp': raise RuntimeError('Wrong firmware transport')
        if not device.get('wifi_ready') or not device.get('camera_ready') or not device.get('microphone_ready'):
            raise RuntimeError('Firmware reports a non-ready subsystem')
        result['device_at_start']=device
        t.set_camera(True); t.set_audio(True,lambda *_:None)
        start=time.monotonic(); age_samples=[]
        while time.monotonic()-start<args.seconds:
            time.sleep(.25)
            if t.error: raise RuntimeError(t.error)
            if t.frames_received:
                frame, stamp=t.snapshot(); age_samples.append((time.monotonic()-stamp)*1000)
        elapsed=time.monotonic()-start
        frame,stamp=t.snapshot()
        result.update(duration_s=elapsed,frames=t.frames_received,
                      audio_samples=t.audio_samples_received,bad_packets=t.parser.bad_packets,
                      fps=t.frames_received/elapsed,sample_rate_received=t.audio_samples_received/elapsed,
                      frame_shape=list(frame.shape),max_sampled_frame_age_ms=max(age_samples),
                      firmware_dropped_packets=t.device.get('dropped_packets'))
        t.set_camera(False); time.sleep(.3)
        result['audio_remains_after_camera_stop']=t.audio_enabled and t.status()['connected']
        t.set_audio(False)
        result['socket_released']=not t.status()['connected']
        if not (result['fps']>=2.5 and result['sample_rate_received']>=14500 and result['bad_packets']==0
                and result['audio_remains_after_camera_stop'] and result['socket_released']):
            raise RuntimeError('Wireless throughput/integrity/lifecycle criterion failed')
        if args.app_check:
            try:
                local_json('http://127.0.0.1:8765/api/camera', {'enabled':True})
                deadline=time.monotonic()+6
                while time.monotonic()<deadline:
                    state=local_json('http://127.0.0.1:8765/api/status')
                    if state['sensor_status']['frames_received']: break
                    time.sleep(.2)
                answer=local_json('http://127.0.0.1:8765/api/ask', {'text':'前面是什么','speak':False,'mode':'adaptive'})
                result['app_check']={'sensor_source':state['sensor_source'], 'route':answer['route'],
                                     'text_ready_ms':answer['timings']['text_ready_ms'], 'completed':True}
                if state['sensor_source']!='xiao_wifi' or answer['route']!='object':
                    raise RuntimeError('App did not use explicit wireless object path')
            finally:
                local_json('http://127.0.0.1:8765/api/camera', {'enabled':False})
        result['passed']=True
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        t.set_audio(False);t.set_camera(False)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='device_at_start'},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
