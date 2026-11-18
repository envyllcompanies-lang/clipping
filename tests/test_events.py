import datetime as dt
import time

import numpy as np

from clipping.core import db
from clipping.eval import eventfx
from clipping.eval.fixtures import make_segments
from clipping.events import detect, service
from clipping.recorder import recorder

UTC = dt.UTC


def test_keyword_fuzzy_match():
    assert detect.keyword_hit("wasteo\n", ["wasted"]) == "wasted"
    assert detect.keyword_hit("mission pased", ["mission passed"]) == "mission passed"
    assert detect.keyword_hit("waited for you", ["busted"]) is None


def test_overlay_mask_covers_chat_box_not_hud():
    m = detect.learn_overlay_mask(eventfx.layout_sample(2))
    H, W = m.shape
    assert m[int(0.5 * H), int(0.9 * W)]  # chat box
    assert not m[int(0.06 * H), int(0.9 * W)]  # HUD stars stay visible
    assert m.mean() < 0.3


def test_detects_death_with_fake_ocr_and_ignores_chat_text():
    c = eventfx.clip(800, "death")
    calls = []

    def fake_ocr(img):
        calls.append(img.shape)
        return "wasted"

    evs = detect.detect(
        c["frames"], c["times"], ocr_fn=fake_ocr, mask=detect.learn_overlay_mask(eventfx.layout_sample(1))
    )
    assert [e.type for e in evs] == ["death"] and abs(evs[0].t - c["truth"]["t"]) < 1.5
    assert len(calls) <= 4  # OCR only on candidate frames


def test_loading_is_negative_span():
    c = eventfx.clip(805, "loading")
    evs = detect.detect(c["frames"], c["times"], ocr_fn=lambda i: "")
    spans = detect.negative_spans(evs)
    assert spans and spans[0][0] >= c["truth"]["t"] - 1


def test_process_window_stores_stream_time_events(conn, tmp_data):
    cr = db.scalar(
        conn,
        "INSERT INTO creator(platform,platform_id,handle,language) VALUES ('twitch','1','h','en') RETURNING id",
    )
    base = int(time.time()) - 300
    sid = recorder.start_stream(conn, cr, "x", dt.datetime.fromtimestamp(base, UTC))
    d = recorder.segment_dir("h", sid)
    make_segments(d, 3, base)
    recorder.register_segments(conn, sid, d, include_last=True)
    mid = db.scalar(
        conn,
        "INSERT INTO moment(stream_id,start_s,end_s,peak_s,score) VALUES (%s,70,100,90,1) RETURNING id",
        sid,
    )
    wid = db.scalar(conn, 'INSERT INTO "window"(moment_id) VALUES (%s) RETURNING id', mid)
    recorder.extract_window(conn, wid)
    res = service.process_window(conn, wid)
    assert "events" in res
    assert db.scalar(conn, "SELECT layout ? 'overlay_mask' FROM stream WHERE id=%s", sid)
    assert np.isfinite(res["negative_share"])
