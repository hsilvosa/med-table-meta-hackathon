"""Spanish voice, offline: one WAV per moment of the day, from the plan's speech text.

Uses the Windows speech engine (System.Speech, voice "Microsoft Helena Desktop", es-ES) through PowerShell, so no text leaves
the machine and no extra package is needed. Windows only; elsewhere `available()` is False and the PDF and .ics still work.
The text is passed in a UTF-8 file, never on the command line.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from .plan import Plan, speech_text
from .schedule import SLOTS

SCRIPT = r"""
param([string]$TextFile, [string]$Out, [int]$Rate, [string]$Culture)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq $Culture } | Select-Object -First 1
if (-not $voice) { Write-Error "no voice for $Culture"; exit 3 }
$s.SelectVoice($voice.VoiceInfo.Name)
$s.Rate = $Rate
$s.SetOutputToWaveFile($Out)
$s.Speak([System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8))
$s.Dispose()
"""


def available(culture: str = "es-ES") -> bool:
    if sys.platform != "win32":
        return False
    probe = ("Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
             "| ForEach-Object { $_.VoiceInfo.Culture.Name }")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", probe], capture_output=True, text=True, timeout=30)
    return culture in done.stdout.split()


def synthesize(text: str, out: Path, rate: int = -2, culture: str = "es-ES") -> Path:
    """Write `text` as a WAV file. Rate runs from -10 to 10; -2 is a little slower than normal, for listeners with low vision or hearing."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        text_file, script = Path(tmp, "text.txt"), Path(tmp, "speak.ps1")
        text_file.write_text(text, encoding="utf-8")
        script.write_text(SCRIPT, encoding="utf-8-sig")  # BOM so PowerShell 5 reads accents correctly
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-TextFile", str(text_file),
                        "-Out", str(out.resolve()), "-Rate", str(rate), "-Culture", culture], check=True, capture_output=True, timeout=120)
    return out


def render_voice(plan: Plan, out_dir: Path, rate: int = -2) -> dict[str, Path]:
    """One WAV per slot that has medication, plus a short intro; the files are named in the order of the day."""
    files = {}
    for number, slot in enumerate(SLOTS, 1):
        if plan.slot_entries(slot):
            files[slot] = synthesize(speech_text(plan, slot), out_dir / f"{number}_{slot}.wav", rate)
    return files
