import numpy as np
import pytest

from clipping.core import db
from clipping.transcribe import engine


def test_index_to_time_only_via_words():
    words = engine.number(
        [
            {"word": "a", "start": 0.0, "end": 0.3, "conf": 0.9},
            {"word": "b", "start": 0.4, "end": 0.9, "conf": 0.2},
        ]
    )
    assert engine.time_of(words, 0, 1) == (0.0, 0.9)
    assert engine.low_confidence(words) == [1]
    with pytest.raises(IndexError):
        engine.time_of(words, 1, 5)


def test_refine_timing_moves_start_after_silence():
    sr = 16000
    audio = np.zeros(sr * 2, np.float32)
    audio[int(1.0 * sr) : int(1.5 * sr)] = 0.5 * np.sin(np.arange(int(0.5 * sr)) / 3)
    out = engine.refine_timing([{"word": "hey", "start": 0.6, "end": 1.6, "conf": 1}], audio, sr)
    assert abs(out[0]["start"] - 1.0) <= 0.02 and abs(out[0]["end"] - 1.5) <= 0.02


def test_prompt_includes_game_terms_and_creator():
    p = engine.prompt_for("xqc", ["lucia_fan"])
    assert "Vice City" in p and "xqc" in p and "lucia_fan" in p


def test_engine_choice(monkeypatch):
    monkeypatch.setenv("CLIPPING_ASR_ENGINE", "mlx")
    assert engine.choose_engine() == "mlx"
    monkeypatch.delenv("CLIPPING_ASR_ENGINE")
    assert engine.choose_engine() == "faster-whisper"  # Linux container


def test_process_window_forces_creator_language(conn, tmp_data, monkeypatch):
    seen = {}

    def fake(audio, language, prompt, size):
        seen.update(language=language, prompt=prompt)
        return language, [{"word": "hola", "start": 0.1, "end": 0.4, "conf": 0.9, "speaker": None}]

    monkeypatch.setitem(engine.ENGINES, "fake", fake)
    monkeypatch.setenv("CLIPPING_ASR_ENGINE", "fake")
    import soundfile as sf

    from clipping.storage import files

    cr = db.scalar(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('kick','1','ibai','es') RETURNING id",
    )
    sid = db.scalar(
        conn,
        "INSERT INTO stream(creator_id,platform_stream_id,started_at) VALUES (%s,'s',now()) RETURNING id",
        cr,
    )
    mid = db.scalar(
        conn, "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,0,1,0,1) RETURNING id", sid
    )
    v = files.managed("work") / "voice.wav"
    sf.write(v, np.zeros(16000, np.float32), 16000)
    wid = db.scalar(
        conn,
        """INSERT INTO "window"(moment_id,path,audio) VALUES (%s,'x',%s) RETURNING id""",
        mid,
        db.j({"voice": str(v)}),
    )
    r = engine.process_window(conn, wid)
    assert seen["language"] == "es" and "ibai" in seen["prompt"] and r["words"] == 1
    assert db.scalar(conn, "SELECT words->0->>'index' FROM transcript WHERE window_id=%s", wid) == "0"
