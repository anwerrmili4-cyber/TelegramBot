"""Public, responsive landing page for the Telegram shop."""

from __future__ import annotations

import html


def render_public_site(bot_username: str, shop_name: str, public_base_url: str) -> str:
    """Render the public page without exposing any administrative data."""
    bot_username = bot_username.strip().lstrip("@")
    bot_url = f"https://t.me/{html.escape(bot_username)}"
    safe_shop = html.escape(shop_name)
    social_image_url = f"{html.escape(public_base_url)}/assets/blackmarket-midnight-og.png"
    bars = "".join(
        f'<span style="--height:{height}%"></span>'
        for height in (38, 72, 48, 88, 62, 96, 55, 80, 44, 92, 68, 84)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#050b14">
  <meta name="description" content="Catalogue, commandes et assistance en temps réel depuis le bot Telegram officiel {safe_shop}.">
  <title>{safe_shop} · Bot Telegram officiel</title>
  <meta property="og:title" content="{safe_shop} · Telegram Commerce">
  <meta property="og:description" content="Catalogue, commandes et support depuis le bot Telegram officiel.">
  <meta property="og:image" content="{social_image_url}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{social_image_url}">
  <style>
    :root {{ color-scheme:dark; --bg:#050b14; --panel:rgba(15,29,48,.72); --line:rgba(148,163,184,.18); --text:#f5f8fc; --muted:#9eb0c7; --brand:#22d3ee; --brand-dark:#0891b2; --success:#34d399; --danger:#fb7185; }}
    * {{ box-sizing:border-box; }} html {{ scroll-behavior:smooth; }}
    body {{ margin:0; min-height:100vh; overflow-x:hidden; font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif; background:radial-gradient(circle at 15% 10%,rgba(8,145,178,.18),transparent 32%),radial-gradient(circle at 90% 30%,rgba(79,70,229,.14),transparent 30%),var(--bg); color:var(--text); }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.2; background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px); background-size:42px 42px; mask-image:linear-gradient(to bottom,black,transparent 75%); }}
    a {{ color:inherit; text-decoration:none; }} button {{ font:inherit; }}
    .shell {{ width:min(1180px,calc(100% - 40px)); margin:auto; position:relative; }}
    nav {{ min-height:82px; display:flex; align-items:center; justify-content:space-between; gap:20px; }}
    .brand {{ display:flex; align-items:center; gap:11px; font-weight:850; letter-spacing:-.02em; }}
    .brand-mark {{ width:38px; height:38px; display:grid; place-items:center; border-radius:12px; background:linear-gradient(145deg,var(--brand),#2563eb); box-shadow:0 10px 30px rgba(34,211,238,.22); }}
    .nav-actions {{ display:flex; align-items:center; gap:10px; }}
    .status-pill,.notify-button {{ display:inline-flex; align-items:center; gap:8px; min-height:40px; padding:0 13px; border:1px solid var(--line); border-radius:999px; background:rgba(7,16,29,.72); color:var(--muted); backdrop-filter:blur(14px); }}
    .notify-button {{ cursor:pointer; color:var(--text); }} .notify-button:hover {{ border-color:rgba(34,211,238,.55); }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:var(--success); box-shadow:0 0 16px var(--success); transition:.25s; }}
    .dot.offline {{ background:var(--danger); box-shadow:0 0 16px var(--danger); }}
    main {{ padding:70px 0 34px; }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr); gap:48px; align-items:center; }}
    .eyebrow {{ display:inline-flex; align-items:center; gap:8px; color:var(--brand); font-size:13px; font-weight:800; letter-spacing:.13em; text-transform:uppercase; }}
    h1 {{ margin:18px 0 20px; font-size:clamp(46px,8vw,84px); line-height:.98; letter-spacing:-.055em; max-width:800px; }}
    h1 span {{ background:linear-gradient(120deg,#fff 20%,var(--brand) 75%); -webkit-background-clip:text; color:transparent; }}
    .lead {{ margin:0; max-width:680px; color:var(--muted); font-size:clamp(17px,2vw,20px); line-height:1.7; }}
    .cta-row {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:30px; }}
    .btn {{ min-height:54px; padding:0 20px; display:inline-flex; align-items:center; justify-content:center; gap:9px; border:1px solid var(--line); border-radius:14px; background:rgba(15,29,48,.72); font-weight:800; transition:transform .2s,border-color .2s,box-shadow .2s; }}
    .btn.primary {{ border-color:transparent; background:linear-gradient(135deg,var(--brand-dark),var(--brand)); color:#031018; box-shadow:0 14px 38px rgba(34,211,238,.2); }}
    .btn:hover {{ transform:translateY(-2px); border-color:rgba(34,211,238,.55); }}
    .live-card {{ position:relative; overflow:hidden; padding:25px; border:1px solid var(--line); border-radius:26px; background:linear-gradient(150deg,rgba(20,39,64,.88),rgba(9,20,35,.82)); box-shadow:0 28px 90px rgba(0,0,0,.4); backdrop-filter:blur(20px); }}
    .live-card::after {{ content:""; position:absolute; width:220px; height:220px; right:-100px; top:-110px; border-radius:50%; background:rgba(34,211,238,.13); filter:blur(12px); }}
    .live-head {{ display:flex; justify-content:space-between; align-items:center; gap:15px; position:relative; z-index:1; }} .live-head strong {{ font-size:18px; }}
    .live-tag {{ color:var(--success); font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.1em; }}
    .metric {{ margin:38px 0 28px; position:relative; z-index:1; }} .metric-value {{ font-size:42px; font-weight:900; letter-spacing:-.04em; }}
    .metric-label,.updated {{ color:var(--muted); font-size:13px; }}
    .signal {{ display:flex; gap:5px; height:45px; align-items:end; position:relative; z-index:1; }}
    .signal span {{ flex:1; min-width:3px; height:var(--height); border-radius:5px; background:linear-gradient(to top,var(--brand-dark),var(--brand)); animation:pulse 2.5s ease-in-out infinite alternate; }}
    .signal span:nth-child(2n) {{ animation-delay:-.7s; }} .signal span:nth-child(3n) {{ animation-delay:-1.4s; }}
    @keyframes pulse {{ from {{ transform:scaleY(.35); opacity:.55; }} to {{ transform:scaleY(1); opacity:1; }} }}
    .updated {{ margin-top:14px; }}
    .features {{ padding:90px 0 70px; display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
    .feature {{ min-height:190px; padding:24px; border:1px solid var(--line); border-radius:22px; background:var(--panel); backdrop-filter:blur(14px); transition:transform .2s,border-color .2s; }}
    .feature:hover {{ transform:translateY(-4px); border-color:rgba(34,211,238,.4); }}
    .feature-icon {{ width:44px; height:44px; display:grid; place-items:center; border-radius:13px; background:rgba(34,211,238,.1); color:var(--brand); font-size:21px; }}
    .feature h2 {{ margin:20px 0 9px; font-size:19px; }} .feature p {{ margin:0; color:var(--muted); line-height:1.6; }}
    footer {{ padding:25px 0 38px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; }}
    .footer-row {{ display:flex; justify-content:space-between; align-items:center; gap:20px; flex-wrap:wrap; }} .footer-links {{ display:flex; gap:18px; flex-wrap:wrap; }} .footer-links a:hover {{ color:var(--brand); }}
    :focus-visible {{ outline:3px solid rgba(34,211,238,.5); outline-offset:3px; }}
    @media(max-width:800px) {{ .hero {{ grid-template-columns:1fr; }} main {{ padding-top:40px; }} .features {{ grid-template-columns:1fr; padding-top:65px; }} .live-card {{ max-width:560px; }} }}
    @media(max-width:560px) {{ .shell {{ width:min(100% - 24px,1180px); }} nav {{ min-height:70px; }} .brand-name,.status-copy {{ display:none; }} .notify-button {{ width:40px; padding:0; justify-content:center; }} main {{ padding-top:28px; }} h1 {{ font-size:43px; }} .cta-row .btn {{ width:100%; }} .hero {{ gap:30px; }} }}
    @media(prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ scroll-behavior:auto!important; animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; }} }}
  </style>
</head>
<body>
  <header class="shell"><nav aria-label="Navigation principale"><a class="brand" href="/" aria-label="Accueil {safe_shop}"><span class="brand-mark">✦</span><span class="brand-name">{safe_shop}</span></a><div class="nav-actions"><span class="status-pill"><span class="dot" id="status-dot"></span><span class="status-copy" id="status-copy">Connexion en direct</span></span><button class="notify-button" id="notify-button" type="button" aria-label="Activer les notifications" title="Activer les notifications">🔔<span class="status-copy">Notifications</span></button></div></nav></header>
  <main class="shell">
    <section class="hero">
      <div><div class="eyebrow"><span>●</span> Commerce Telegram en temps réel</div><h1>Tout votre catalogue, <span>directement dans Telegram.</span></h1><p class="lead">Découvrez les offres, commandez, suivez vos achats et contactez le support depuis une expérience simple, rapide et sécurisée.</p><div class="cta-row"><a class="btn primary" href="{bot_url}" target="_blank" rel="noopener">Lancer @{html.escape(bot_username)} <span>↗</span></a><a class="btn" href="{bot_url}?start=catalog" target="_blank" rel="noopener">Voir le catalogue</a></div></div>
      <aside class="live-card" aria-live="polite"><div class="live-head"><strong>État du service</strong><span class="live-tag" id="live-tag">En ligne</span></div><div class="metric"><div class="metric-value" id="metric-value">Opérationnel</div><div class="metric-label">Bot, commandes et assistance</div></div><div class="signal" aria-hidden="true">{bars}</div><div class="updated">Dernière vérification : <span id="last-check">maintenant</span></div></aside>
    </section>
    <section class="features" aria-label="Services disponibles"><a class="feature" href="{bot_url}?start=catalog" target="_blank" rel="noopener"><span class="feature-icon">◇</span><h2>Catalogue instantané</h2><p>Consultez les offres et disponibilités mises à jour directement dans le bot.</p></a><a class="feature" href="{bot_url}?start=orders" target="_blank" rel="noopener"><span class="feature-icon">↗</span><h2>Suivi des commandes</h2><p>Retrouvez le statut et la livraison de tous vos achats depuis Telegram.</p></a><a class="feature" href="{bot_url}?start=support" target="_blank" rel="noopener"><span class="feature-icon">◎</span><h2>Support connecté</h2><p>Envoyez votre demande et recevez la réponse de l’administrateur dans le bot.</p></a></section>
  </main>
  <footer><div class="shell footer-row"><span>© <span id="year"></span> {safe_shop} · Bot officiel @{html.escape(bot_username)}</span><span class="footer-links"><a href="{bot_url}?start=catalog">Catalogue</a><a href="{bot_url}?start=support">Support</a></span></div></footer>
  <script>
    const state = {{ online: null }};
    const dot = document.getElementById("status-dot"), copy = document.getElementById("status-copy"), tag = document.getElementById("live-tag"), metric = document.getElementById("metric-value"), lastCheck = document.getElementById("last-check"), notifyButton = document.getElementById("notify-button");
    document.getElementById("year").textContent = new Date().getFullYear();
    function announceStatus(online) {{
      if (state.online !== null && state.online !== online && "Notification" in window && Notification.permission === "granted") new Notification("{safe_shop}", {{ body: online ? "Le service est de nouveau en ligne." : "Le service est momentanément indisponible." }});
      state.online = online; dot.classList.toggle("offline", !online); copy.textContent = online ? "Connexion en direct" : "Service indisponible"; tag.textContent = online ? "En ligne" : "Hors ligne"; tag.style.color = online ? "var(--success)" : "var(--danger)"; metric.textContent = online ? "Opérationnel" : "Connexion interrompue"; lastCheck.textContent = new Date().toLocaleTimeString("fr-FR", {{ hour:"2-digit", minute:"2-digit", second:"2-digit" }});
    }}
    async function checkHealth() {{ try {{ const response = await fetch("/health", {{ cache:"no-store" }}), data = await response.json(); announceStatus(response.ok && data.ok === true); }} catch (_) {{ announceStatus(false); }} }}
    notifyButton.addEventListener("click", async () => {{ if (!("Notification" in window)) {{ notifyButton.title = "Notifications non prises en charge"; return; }} const permission = await Notification.requestPermission(); notifyButton.innerHTML = permission === "granted" ? '🔔<span class="status-copy">Activées</span>' : '🔕<span class="status-copy">Refusées</span>'; if (permission === "granted") new Notification("{safe_shop}", {{ body:"Les alertes de disponibilité sont activées." }}); }});
    checkHealth(); setInterval(checkHealth, 15000);
  </script>
</body>
</html>"""
