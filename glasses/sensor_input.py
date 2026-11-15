"""Camera and microphone adapters for explicitly selected sensor transports."""


class SensorCamera:
    def __init__(self, transport): self.transport = transport
    @property
    def error(self): return self.transport.error
    def start(self): self.transport.set_camera(True)
    def stop(self): self.transport.set_camera(False)
    def is_running(self):
        return self.transport.camera_enabled and self.transport.status()['connected']
    def snapshot(self): return self.transport.snapshot()


class SensorInputStream:
    def __init__(self, transport, callback):
        self.transport, self.callback = transport, callback
    def start(self): self.transport.set_audio(True, self.callback)
    @property
    def active(self):
        return self.transport.audio_enabled and self.transport.status()['connected'] and self.transport.error is None
    def abort(self): self.transport.set_audio(False)
    def close(self): self.transport.set_audio(False)
