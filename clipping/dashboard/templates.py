"""Jinja templates (mobile-first, no build step)."""

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Clipping{% endblock %}</title>{% if user and refresh %}<meta http-equiv="refresh" content="15">{% endif %}
<style>
:root{--bg:#0e1116;--card:#171b22;--text:#e8eaed;--muted:#9aa3ad;--accent:#ffe11a;--bad:#ff5c5c;--ok:#3ddc84;--line:#262c36}
@media (prefers-color-scheme: light){:root{--bg:#f5f6f8;--card:#fff;--text:#14171c;--muted:#5d6672;--line:#e3e6ea;--accent:#b38f00}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center;z-index:2}
header b{color:var(--accent)}nav{display:flex;gap:6px;overflow-x:auto;padding:8px 16px;border-bottom:1px solid var(--line)}
nav a{white-space:nowrap;padding:6px 10px;border-radius:16px;background:var(--card);color:var(--text);text-decoration:none;font-size:13px}
main{padding:12px 16px;max-width:980px;margin:auto}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.row{display:flex;gap:10px;flex-wrap:wrap}.kpi{flex:1 1 140px}.kpi .v{font-size:24px;font-weight:700}.muted{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tbl{overflow-x:auto}button,.btn{background:var(--accent);color:#111;border:0;border-radius:8px;padding:7px 12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
button.danger{background:var(--bad);color:#fff}.pill{padding:2px 8px;border-radius:10px;font-size:12px;background:var(--line)}
.ok{color:var(--ok)}.bad{color:var(--bad)}form.inline{display:inline}img.thumb{width:72px;border-radius:6px}
input,select{background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px;width:100%;margin:4px 0}
</style></head><body>
<header><b>Clipping</b><span class="muted">{{ subtitle or '' }}</span>{% if user %}<span style="margin-left:auto" class="muted">{{ user.email }}</span>{% endif %}</header>
{% if user %}<nav>{% for href, label in nav %}<a href="{{ href }}">{{ label }}</a>{% endfor %}</nav>{% endif %}
<main>{% block body %}{% endblock %}</main></body></html>"""

PAGES = {
    "base.html": BASE,
    "login.html": """{% extends "base.html" %}{% block body %}<div class="card"><h2>Sign in</h2>
<form method="post" action="/login"><input name="email" placeholder="Email" autocomplete="username"><input name="password" type="password" placeholder="Password">
<input name="code" placeholder="2FA code (owner)" inputmode="numeric"><button>Sign in</button></form>
{% if error %}<p class="bad">{{ error }}</p>{% endif %}<p class="muted"><a href="/signup">Create an account</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p></div>{% endblock %}""",
    "signup.html": """{% extends "base.html" %}{% block body %}<div class="card"><h2>Create an account</h2>
<form method="post" action="/signup"><input name="email" placeholder="Email"><input name="password" type="password" placeholder="Password (12+ characters)"><button>Create account</button></form>
{% if error %}<p class="bad">{{ error }}</p>{% endif %}</div>{% endblock %}""",
    "home.html": """{% extends "base.html" %}{% block body %}
<div class="row">{% for k in kpis %}<div class="card kpi"><div class="muted">{{ k[0] }}</div><div class="v">{{ k[1] }}</div></div>{% endfor %}</div>
<div class="card"><h3>System health</h3><table>{% for h in health %}<tr><td>{{ h.name }}</td><td class="{{ 'ok' if h.ok else 'bad' }}">{{ h.status }}</td><td class="muted">{{ h.detail }}</td></tr>{% endfor %}</table></div>
<div class="card"><h3>Alerts</h3>{% for a in alerts %}<p><span class="pill {{ 'bad' if a.severity=='critical' else '' }}">{{ a.kind }}</span> {{ a.message }}
<form class="inline" method="post" action="/cmd/resolve_alert"><input type="hidden" name="alert_id" value="{{ a.id }}"><button>Resolve</button></form></p>{% else %}<p class="muted">No open alerts.</p>{% endfor %}</div>
<div class="card"><h3>Global</h3>{% if paused %}<p class="bad">Paused: scheduler and rendering halted (recording continues).</p>
<form method="post" action="/cmd/global_resume"><button>Resume everything</button></form>{% else %}
<form method="post" action="/cmd/global_pause"><button class="danger">Pause everything</button></form>{% endif %}</div>{% endblock %}""",
    "table.html": """{% extends "base.html" %}{% block body %}<div class="card"><h3>{{ heading }}</h3>{% if note %}<p class="muted">{{ note }}</p>{% endif %}
<div class="tbl"><table><tr>{% for col in cols %}<th>{{ col }}</th>{% endfor %}</tr>
{% for r in rows %}<tr>{% for cell in r %}<td>{{ cell|safe }}</td>{% endfor %}</tr>{% else %}<tr><td class="muted" colspan="{{ cols|length }}">Nothing yet.</td></tr>{% endfor %}
</table></div></div>{% block extra %}{{ extra|safe }}{% endblock %}{% endblock %}""",
    "tiktok_post.html": """{% extends "base.html" %}{% block body %}<div class="card"><h3>Post to TikTok</h3>
<p>Posting as <b>{{ creator.nickname }}</b> (@{{ creator.username }})</p>
<video src="{{ preview_url }}" controls playsinline style="width:100%;max-width:320px;border-radius:10px"></video>
<form method="post" action="/tiktok/post"><input type="hidden" name="clip_version_id" value="{{ cv_id }}"><input type="hidden" name="account_id" value="{{ account_id }}">
<label>Title<input name="title" value="{{ title }}" maxlength="2200"></label>
<label>Who can view<select name="privacy" required><option value="" disabled selected>Choose</option>{% for p in creator.privacy_level_options %}<option>{{ p }}</option>{% endfor %}</select></label>
<label><input type="checkbox" name="allow_comment" {{ 'disabled' if creator.comment_disabled }}> Allow comments</label>
<label><input type="checkbox" name="allow_duet" {{ 'disabled' if creator.duet_disabled }}> Allow Duet</label>
<label><input type="checkbox" name="allow_stitch" {{ 'disabled' if creator.stitch_disabled }}> Allow Stitch</label>
<label><input type="checkbox" name="disclose"> Disclose video content (promotional)</label>
<label><input type="checkbox" name="consent" required> By posting, I agree to TikTok's Music Usage Confirmation</label>
<p class="muted">Max video length for this account: {{ creator.max_video_post_duration_sec }} s. Processing can take a few minutes after posting.</p>
<button>Post</button></form></div>{% endblock %}""",
    "public.html": """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · {{ brand }}</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:auto;padding:24px 16px;color:#14171c;background:#fff}
h1{font-size:26px}a{color:#0b57d0}footer{margin-top:40px;font-size:13px;color:#5d6672}</style></head><body>
<h1>{{ title }}</h1>{{ body|safe }}<footer><a href="/">{{ brand }}</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/data-deletion">Data deletion</a> · Contact: {{ contact }}</footer></body></html>""",
}
