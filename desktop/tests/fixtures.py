"""Own generated media and synthetic speech, never user or game assets."""
from pathlib import Path
import os
import subprocess


def fixtures(root):
    root.mkdir(exist_ok=True)
    video = root / 'original.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=12:d=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-shortest', str(video)], check=True, capture_output=True)
    subtitle = root / 'original.srt'
    subtitle.write_text('1\n00:00:00,100 --> 00:00:01,800\nNEW CAPTION\n\n', encoding='utf-8')
    return video, subtitle


def speech(root):
    wav = root / 'own-speech.wav'
    phrase = 'Welcome to the subtitle studio. This is a test of local speech recognition. Please add clear subtitles to this video.'
    if os.name == 'nt':
        script = root / 'own-speech.ps1'
        script.write_text("Add-Type -AssemblyName System.Speech\n"
                          "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
                          "$voice.SetOutputToWaveFile((Join-Path $PSScriptRoot 'own-speech.wav'))\n"
                          "$voice.Speak('" + phrase + "')\n$voice.Dispose()\n", encoding='utf-8-sig')
        subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script)], check=True, capture_output=True)
    else:
        subprocess.run(['espeak', '-s', '135', '-w', str(wav), phrase], check=True)
    video = root / 'own-speech.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=12',
                    '-i', str(wav), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(video)],
                    check=True, capture_output=True)
    return video
