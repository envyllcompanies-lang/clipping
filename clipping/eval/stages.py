"""Import every component's backtest module so its stage registers."""

import importlib

MODULES = [
    "clipping.radar.backtest", "clipping.recorder.backtest", "clipping.chat.backtest", "clipping.ingest.backtest",
    "clipping.storage.backtest", "clipping.heatmap.backtest", "clipping.audio.backtest", "clipping.transcribe.backtest",
    "clipping.events.backtest", "clipping.style.backtest", "clipping.builder.backtest", "clipping.reframe.backtest",
    "clipping.captions.backtest", "clipping.render.backtest", "clipping.packaging.backtest", "clipping.gate.backtest",
    "clipping.publish.backtest", "clipping.analytics.backtest", "clipping.accounts.backtest", "clipping.languages.backtest",
    "clipping.dashboard.backtest",
]
for m in MODULES:
    try:
        importlib.import_module(m)
    except ModuleNotFoundError as e:
        if e.name != m:
            raise
