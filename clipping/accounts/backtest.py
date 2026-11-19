"""Stage backtest 27: from a fresh config, one run creates all 10 aliases, labels, passwords, handle checks, kits
and worksheets with no input; test codes land in the right language+platform row only; a wrong account is rejected
at connect; a second run changes nothing."""

from __future__ import annotations

import json
from email.message import EmailMessage

import httpx

from clipping.accounts import provision
from clipping.core import config, db
from clipping.eval.harness import Example, StageResult, scratch_db, stage


class FakeAddy:
    def __init__(self):
        self.aliases, self.creates = {}, 0

    def handle(self, req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            q = req.url.params.get("filter[search]")
            return httpx.Response(
                200, json={"data": [a for a in self.aliases.values() if a["local_part"] == q]}
            )
        b = json.loads(req.content)
        self.creates += 1
        a = {
            "id": f"a{len(self.aliases)}",
            "local_part": b["local_part"],
            "domain": b["domain"],
            "email": f"{b['local_part']}@{b['domain']}",
        }
        self.aliases[b["local_part"]] = a
        return httpx.Response(201, json={"data": a})


class FakeGmail:
    def __init__(self):
        self.labels, self.filters = [], []

    def handle(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("/labels") and req.method == "GET":
            return httpx.Response(200, json={"labels": self.labels})
        if p.endswith("/labels"):
            lb = {"id": f"L{len(self.labels)}", "name": json.loads(req.content)["name"]}
            self.labels.append(lb)
            return httpx.Response(200, json=lb)
        if p.endswith("/filters") and req.method == "GET":
            return httpx.Response(200, json={"filter": self.filters})
        self.filters.append(json.loads(req.content))
        return httpx.Response(200, json={})


def code_mail(to: str, sender: str, code: str) -> bytes:
    m = EmailMessage()
    m["To"], m["From"], m["Subject"] = to, sender, f"{code} is your verification code"
    m.set_content(f"Your code is {code}. It expires in 10 minutes.")
    return m.as_bytes()


@stage("27", "Account Provisioning Tool")
def run() -> StageResult:
    ex = []
    addy, gm = FakeAddy(), FakeGmail()
    taken = {"gta6clips.en", "gta6clips_en"}
    prof = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200 if any(t in str(r.url) for t in taken) else 404)
        )
    )
    import tempfile
    from pathlib import Path

    saved_ws = provision.WORKSHEETS
    tmp_ws = tempfile.TemporaryDirectory()
    provision.WORKSHEETS = Path(tmp_ws.name)  # hermetic: never read or write the real var/worksheets
    try:
        return _run(provision, ex, addy, gm, taken, prof)
    finally:
        provision.WORKSHEETS = saved_ws
        tmp_ws.cleanup()


def _run(provision, ex, addy, gm, taken, prof) -> StageResult:
    with scratch_db() as c:
        api = provision.Addy("k", "gta6clips.anonaddy.com", httpx.MockTransport(addy.handle))
        gmail = provision.Gmail("t", httpx.MockTransport(gm.handle))
        s1 = provision.provision(c, alias_api=api, gmail=gmail, http=prof, include_inactive=True)
        n_ch = len(config.channels())
        slots = db.scalar(c, "SELECT count(*) FROM account_slot")
        full = (
            s1["aliases_created"] == n_ch
            and slots == n_ch * 6
            and s1["passwords"] == n_ch * 6
            and s1["kits"] == n_ch
            and s1["worksheets"] == n_ch
            and len(gm.labels) == n_ch
            and len(gm.filters) == n_ch
            and s1["handles_checked"] == n_ch * 6
        )
        named = (
            all(re.search(rf"-{a['code']}-[a-z]+@", a["address"]) for a in db.all_(c, "SELECT * FROM alias"))
            if (re := __import__("re"))
            else False
        )
        before, nl, nf = addy.creates, len(gm.labels), len(gm.filters)
        s2 = provision.provision(c, alias_api=api, gmail=gmail, http=prof, include_inactive=True)
        idem = (
            addy.creates == before
            and s2["passwords"] == 0
            and s2["aliases_created"] == 0
            and s2["worksheets"] == 0
            and s2["kits"] == 0
            and len(gm.labels) == nl
            and len(gm.filters) == nf
        )
        en_ig = db.one(c, "SELECT handle_final FROM account_slot WHERE code='en' AND platform='instagram'")[
            "handle_final"
        ]
        variant_ok = en_ig not in taken
        # codes: one per alias x platform sender; each must land only in its row
        senders = {
            "youtube": "no-reply@accounts.google.com",
            "tiktok": "register@account.tiktok.com",
            "instagram": "security@mail.instagram.com",
            "facebook": "security@facebookmail.com",
            "snapchat": "no_reply@snapchat.com",
        }
        routed_ok = []
        for a in db.all_(c, "SELECT * FROM alias"):
            for plat, snd in senders.items():
                code = f"{abs(hash((a['code'], plat))) % 900000 + 100000}"
                r = provision.route_code(c, code_mail(a["address"], snd, code))
                ok = r is not None and r["code"] == a["code"] and r["platform"] == plat and r["value"] == code
                routed_ok.append(ok)
                if not ok:
                    ex.append(Example(f"{a['code']}:{plat}", "code_routing", 0, str(r)))
        leaks = db.scalar(
            c,
            "SELECT count(*) FROM (SELECT slot_code, platform, count(*) FROM verification_code GROUP BY 1,2 HAVING count(*) > 1) x",
        )
        # connect check: Spanish TikTok slot receives the Japanese account -> rejected
        from clipping.produce import sync_channels

        sync_channels(c)
        es_tt = db.scalar(
            c,
            "SELECT a.id FROM account a JOIN channel ch ON ch.id=a.channel_id WHERE ch.key='gta6-es' AND a.platform='tiktok'",
        )
        wrong, _ = provision.connect_check(c, es_tt, "tiktok", {"id": "x", "handle": "gta6clips.ja"})
        right, _ = provision.connect_check(
            c,
            es_tt,
            "tiktok",
            {
                "id": "y",
                "handle": db.scalar(
                    c, "SELECT handle_final FROM account_slot WHERE code='es' AND platform='tiktok'"
                ),
            },
        )
        reject_ok = (
            isinstance(wrong, str) and "gta6clips.ja" in wrong and "es:tiktok" in wrong and right is True
        )
    return StageResult(
        {
            "one_run_creates_everything": 1.0 if full else 0.0,
            "naming_carries_language": 1.0 if named else 0.0,
            "taken_handle_gets_variant": 1.0 if variant_ok else 0.0,
            "codes_route_to_right_slot": sum(routed_ok) / len(routed_ok),
            "no_cross_language_codes": 1.0 if leaks == 0 else 0.0,
            "wrong_account_rejected": 1.0 if reject_ok else 0.0,
            "rerun_changes_nothing": 1.0 if idem else 0.0,
        },
        ex,
        "fake-services@v1",
        {"run1": s1, "run2": s2},
    )
