"""Offline voice: runs only where a Spanish Windows voice is installed."""

import wave

import pytest

from fixtures import METFORMINA_850, OMEPRAZOL, TODAY, pack
from medtable import voice
from medtable.plan import build_plan
from medtable.schedule import SLOTS, Line, reconcile

pytestmark = pytest.mark.skipif(not voice.available(), reason="no Spanish Windows speech voice installed")


def test_wav_files_are_written_for_the_slots_with_medication(tmp_path):
    lines = [Line("Metformina 850 mg", {**dict.fromkeys(SLOTS, "0"), "breakfast": "1", "dinner": "1/2"}, "con las comidas", confirmed=True),
             Line("Omeprazol 20 mg", {**dict.fromkeys(SLOTS, "0"), "breakfast": "1"}, "", confirmed=True)]
    packs = [pack(METFORMINA_850), pack(OMEPRAZOL)]
    plan = build_plan(lines, reconcile(lines, packs), [], TODAY)
    files = voice.render_voice(plan, tmp_path)
    assert set(files) == {"breakfast", "dinner"}
    for path in files.values():
        with wave.open(str(path)) as w:
            assert w.getnframes() / w.getframerate() > 2  # more than two seconds of audio
