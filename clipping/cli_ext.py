"""Component subcommands."""

from __future__ import annotations

import json


def register(sub):
    w = sub.add_parser("worker", help="run a worker daemon")
    w.add_argument("role", choices=["server", "m1"])
    w.add_argument("--once", action="store_true")
    w.set_defaults(fn=lambda a: __import__("clipping.worker", fromlist=["loop"]).loop(a.role, once=a.once))

    r = sub.add_parser("radar", help="creator radar")
    r.add_argument("action", choices=["poll", "rank", "show"])
    r.add_argument("--language")
    r.set_defaults(fn=_radar)


def _radar(a):
    from clipping.core import db
    from clipping.radar import service, sources

    with db.conn() as c:
        if a.action == "poll":
            srcs = sources.live_sources()
            if not srcs:
                print("no Twitch/Kick keys in .env; nothing to poll")
                return
            print(len(service.poll_live(c, srcs, service.resolve_game_ids(srcs))), "live GTA 6 creators")
        elif a.action == "rank":
            res = service.daily_rank(c)
            print(json.dumps({k: [s.creator_id for s in v if s.selected] for k, v in res.items()}))
        else:
            for r in db.all_(
                c,
                """SELECT cs.*, cr.handle FROM creator_score cs JOIN creator cr ON cr.id=cs.creator_id
                                   WHERE date=(SELECT max(date) FROM creator_score) AND (%s::text IS NULL OR cs.language=%s)
                                   ORDER BY cs.language, cs.rank""",
                a.language,
                a.language,
            ):
                print(
                    f"{r['language']} #{r['rank']:>3} {r['handle']:<20} {r['score']:.3f} {'*' if r['selected'] else ' '} {r['selection_reason'] or ''}"
                )
