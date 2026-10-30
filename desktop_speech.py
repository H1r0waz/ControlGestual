"""Bounded Windows speech output with microphone suppression; no remote services."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time

SCRIPT=r"""$ErrorActionPreference='Stop';[Console]::InputEncoding=New-Object System.Text.UTF8Encoding;$p=[Console]::In.ReadToEnd()|ConvertFrom-Json;Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;try{$v=$s.GetInstalledVoices()|Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*'}|Select-Object -First 1;if($v){$s.SelectVoice($v.VoiceInfo.Name)}else{throw 'No Spanish voice installed'};if($p.output){$s.SetOutputToWaveFile($p.output)}else{$s.SetOutputToDefaultAudioDevice()};$s.Speak([string]$p.text)}finally{$s.Dispose()}"""

class SpeechOutput:
    def __init__(self):
        self.lock=threading.RLock();self.enabled=False;self.process=None;self.thread=None
        self.epoch=0;self.busy=False;self.until=0;self.message='Respuestas habladas apagadas.'

    def state(self):
        with self.lock:return {'enabled':self.enabled,'speaking':self.busy,'message':self.message}

    def suppressed(self):
        with self.lock:return self.busy or time.monotonic()<self.until

    def enable(self,value):
        if type(value) is not bool:raise ValueError('Ajuste de voz inválido.')
        if not value:self.stop()
        with self.lock:self.enabled=value;self.message='Respuestas habladas habilitadas.' if value else 'Respuestas habladas apagadas.'

    def say(self,text):
        with self.lock:
            if not self.enabled:return
        self.stop()
        with self.lock:
            self.busy=True;self.epoch+=1;epoch=self.epoch
            self.thread=threading.Thread(target=self._speak,args=(text[:600],epoch),daemon=True);self.thread.start()

    def _speak(self,text,epoch):
        try:
            with self.lock:
                if not self.enabled or epoch!=self.epoch:return
                self.process=self.launch(text);process=self.process
            process.communicate(timeout=35)
            with self.lock:
                if epoch==self.epoch:self.message='Respuesta hablada finalizada.' if process.returncode==0 else 'No se pudo hablar. Revisá la voz española y el dispositivo de salida de Windows.'
        except (OSError,ValueError,subprocess.TimeoutExpired):
            with self.lock:
                if epoch==self.epoch:
                    if self.process and self.process.poll() is None:self.process.kill();self.process.wait(timeout=2)
                    self.message='No se pudo hablar. La respuesta sigue visible en el panel.'
        finally:
            with self.lock:
                if epoch==self.epoch:self.process=None;self.busy=False;self.until=time.monotonic()+.7;self.epoch+=1

    @staticmethod
    def launch(text,output=None):
        executable=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        process=subprocess.Popen([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-Command',SCRIPT],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        # Only JSON is written to stdin. User text never becomes PowerShell source or argv.
        try:
            process.stdin.write(json.dumps({'text':text,'output':str(output) if output else None},ensure_ascii=True).encode('utf-8'));process.stdin.close();process.stdin=None
        except (OSError,ValueError):
            if process.poll() is None:process.terminate();process.wait(timeout=2)
            raise
        return process

    def stop(self):
        with self.lock:
            was_busy=self.busy
            self.epoch+=1
            if self.process and self.process.poll() is None:
                try:self.process.terminate()
                except OSError:pass
            self.process=None;self.busy=False
            if was_busy:self.until=time.monotonic()+.7

    def close(self):
        self.enable(False)
        thread=self.thread
        if thread and thread is not threading.current_thread():thread.join(timeout=3)
