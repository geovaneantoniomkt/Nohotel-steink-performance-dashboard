#!/usr/bin/env python3
"""
Coletor de dados do Meta para o dashboard Nohotel (Steink Performance).

Gera dois arquivos JSON (por padrão em public/data/):
  - meta.json     -> Meta Ads: conta, campanhas, conjuntos, anúncios, série diária por anúncio
  - organic.json  -> Orgânico: página do Facebook e perfil do Instagram (melhor esforço)

Uso:
  META_ACCESS_TOKEN=EAAB... python scripts/fetch_meta.py

Variáveis de ambiente:
  META_ACCESS_TOKEN   (obrigatória)  token de usuário do sistema / usuário com ads_read,
                                     pages_read_engagement, read_insights, instagram_basic,
                                     instagram_manage_insights, business_management
  META_AD_ACCOUNT_ID  (padrão 812845936220210 — conta "Nohotel")
  META_PAGE_ID        (padrão 207987622557413 — página "Hotéis Nohotel")
  META_IG_USER_ID     (padrão 17841402216050279 — @hoteisnohotel)
  META_API_VERSION    (padrão v23.0)
  OUT_DIR             (padrão public/data)
  META_SINCE / SINCE  (padrão 2025-04-01, YYYY-MM-DD) data inicial da série diária (limite da API: 37 meses)

Sem dependências externas (apenas biblioteca padrão).
O token NUNCA é impresso — mensagens de erro são higienizadas.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = os.environ.get("META_API_VERSION", "v23.0")
TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
ACCOUNT_ID = os.environ.get("META_AD_ACCOUNT_ID", "812845936220210").strip().replace("act_", "")
PAGE_ID = os.environ.get("META_PAGE_ID", "207987622557413").strip()
IG_ID = os.environ.get("META_IG_USER_ID", "17841402216050279").strip()
OUT_DIR = os.environ.get("OUT_DIR", "public/data")
FORCE_SINCE = (os.environ.get("META_SINCE") or os.environ.get("SINCE") or "2025-04-01").strip()

BASE = f"https://graph.facebook.com/{API_VERSION}"
TOKEN_RE = re.compile(r"access_token=[^&\s]+")

WARNINGS: list[str] = []


# ----------------------------------------------------------------------------
# utilitários
# ----------------------------------------------------------------------------

def log(msg: str) -> None:
    print(TOKEN_RE.sub("access_token=***", str(msg)), flush=True)


def warn(msg: str) -> None:
    msg = TOKEN_RE.sub("access_token=***", str(msg))
    WARNINGS.append(msg)
    log(f"AVISO: {msg}")


class ApiError(Exception):
    def __init__(self, message: str, code=None, subcode=None, http=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http = http

    def __str__(self) -> str:  # nunca inclui a URL (que contém o token)
        return f"{super().__str__()} (code={self.code}, subcode={self.subcode}, http={self.http})"


def api(path: str, params: dict | None = None, token: str | None = None, retries: int = 5) -> dict:
    """GET na Graph API com retry/backoff. Levanta ApiError em erro definitivo."""
    q = dict(params or {})
    q["access_token"] = token or TOKEN
    url = f"{BASE}/{path.lstrip('/')}?{urllib.parse.urlencode(q)}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nohotel-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(body).get("error", {})
            except Exception:
                err = {"message": body[:300]}
            code = err.get("code")
            transient = e.code >= 500 or code in (1, 2, 4, 17, 32, 613, 80000, 80004)
            last_err = ApiError(err.get("message", "erro"), code, err.get("error_subcode"), e.code)
            if transient and attempt < retries - 1:
                wait = min(120, 5 * (2 ** attempt))
                log(f"  retry em {wait}s: {last_err}")
                time.sleep(wait)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = ApiError(f"rede: {getattr(e, 'reason', e)}")
            if attempt < retries - 1:
                time.sleep(5 * (2 ** attempt))
                continue
            raise last_err
    raise last_err or ApiError("falha desconhecida")


def api_all(path: str, params: dict | None = None, token: str | None = None, max_pages: int = 500) -> list:
    """Segue a paginação (paging.next) e devolve todos os itens de `data`."""
    out: list = []
    q = dict(params or {})
    q.setdefault("limit", 200)
    res = api(path, q, token)
    out.extend(res.get("data", []))
    pages = 1
    while res.get("paging", {}).get("next") and pages < max_pages:
        after = res["paging"].get("cursors", {}).get("after")
        if not after:
            break
        q["after"] = after
        res = api(path, q, token)
        out.extend(res.get("data", []))
        pages += 1
    return out


def money(v) -> float:
    """Orçamentos vêm em centavos (string). Converte para reais."""
    try:
        return round(int(v) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def fnum(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def inum(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def actions_to_dict(items) -> dict:
    d: dict = {}
    for a in items or []:
        t = a.get("action_type")
        if t:
            d[t] = d.get(t, 0) + inum(a.get("value"))
    return d


def values_to_dict(items) -> dict:
    """action_values (valor monetário das conversões, ex.: purchase) -> {tipo: reais}."""
    d: dict = {}
    for a in items or []:
        t = a.get("action_type")
        v = fnum(a.get("value"))
        if t and v:
            d[t] = round(d.get(t, 0.0) + v, 2)
    return d


def daterange_chunks(since: dt.date, until: dt.date, days: int):
    cur = since
    while cur <= until:
        end = min(until, cur + dt.timedelta(days=days - 1))
        yield cur, end
        cur = end + dt.timedelta(days=1)


def today_in(tz_name: str | None) -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tz_name or "America/Sao_Paulo")).date()
    except Exception:
        return dt.date.today()


# ----------------------------------------------------------------------------
# Meta Ads
# ----------------------------------------------------------------------------

STATUS_FILTER = json.dumps([{
    "field": "effective_status",
    "operator": "IN",
    "value": ["ACTIVE", "PAUSED", "ARCHIVED", "CAMPAIGN_PAUSED", "ADSET_PAUSED", "WITH_ISSUES",
              "IN_PROCESS", "PENDING_REVIEW", "DISAPPROVED", "PREAPPROVED", "PENDING_BILLING_INFO"],
}])

INSIGHT_FIELDS = ",".join([
    "date_start", "date_stop", "campaign_id", "adset_id", "ad_id",
    "spend", "impressions", "reach", "frequency", "clicks", "inline_link_clicks",
    "actions", "action_values", "video_thruplay_watched_actions", "video_p25_watched_actions", "video_p100_watched_actions",
])


def fetch_ads_data() -> dict:
    acct = f"act_{ACCOUNT_ID}"
    log(f"Conta {acct}: dados cadastrais")
    account_raw = api(acct, {"fields": "id,name,account_status,currency,timezone_name,balance,amount_spent,spend_cap,disable_reason"})
    tz = account_raw.get("timezone_name") or "America/Sao_Paulo"
    today = today_in(tz)
    account = {
        "id": ACCOUNT_ID,
        "name": account_raw.get("name"),
        "status": account_raw.get("account_status"),
        "disable_reason": account_raw.get("disable_reason"),
        "currency": account_raw.get("currency", "BRL"),
        "timezone": tz,
        "balance": money(account_raw.get("balance")),
        "amount_spent_lifetime": money(account_raw.get("amount_spent")),
        "spend_cap": money(account_raw.get("spend_cap")),
    }

    log("Campanhas")
    campaigns = []
    for c in api_all(f"{acct}/campaigns", {
        "fields": "id,name,status,effective_status,objective,daily_budget,lifetime_budget,created_time,start_time,stop_time,bid_strategy,buying_type,updated_time",
        "filtering": STATUS_FILTER,
    }):
        campaigns.append({
            "id": c["id"], "name": c.get("name"), "status": c.get("status"),
            "effective_status": c.get("effective_status"), "objective": c.get("objective"),
            "daily_budget": money(c.get("daily_budget")), "lifetime_budget": money(c.get("lifetime_budget")),
            "created_time": c.get("created_time"), "start_time": c.get("start_time"), "stop_time": c.get("stop_time"),
            "bid_strategy": c.get("bid_strategy"), "buying_type": c.get("buying_type"),
        })

    log("Conjuntos de anúncios")
    adsets = []
    for s in api_all(f"{acct}/adsets", {
        "fields": "id,name,campaign_id,status,effective_status,optimization_goal,billing_event,bid_strategy,daily_budget,lifetime_budget,start_time,end_time,created_time,promoted_object,targeting{age_min,age_max,genders,geo_locations,targeting_automation}",
        "filtering": STATUS_FILTER,
    }):
        tg = s.get("targeting") or {}
        geo = tg.get("geo_locations") or {}
        geo_summary = []
        for key in ("countries", "regions", "cities", "zips", "places", "custom_locations"):
            for g in geo.get(key, []) or []:
                if isinstance(g, dict):
                    geo_summary.append(g.get("name") or g.get("key") or str(g))
                else:
                    geo_summary.append(str(g))
        adsets.append({
            "id": s["id"], "name": s.get("name"), "campaign_id": s.get("campaign_id"),
            "status": s.get("status"), "effective_status": s.get("effective_status"),
            "optimization_goal": s.get("optimization_goal"), "billing_event": s.get("billing_event"),
            "custom_event": (s.get("promoted_object") or {}).get("custom_event_type"),
            "pixel_id": (s.get("promoted_object") or {}).get("pixel_id"),
            "bid_strategy": s.get("bid_strategy"),
            "daily_budget": money(s.get("daily_budget")), "lifetime_budget": money(s.get("lifetime_budget")),
            "start_time": s.get("start_time"), "end_time": s.get("end_time"), "created_time": s.get("created_time"),
            "targeting": {
                "age_min": tg.get("age_min"), "age_max": tg.get("age_max"),
                "genders": tg.get("genders"), "geo": geo_summary[:20],
                "advantage_audience": (tg.get("targeting_automation") or {}).get("advantage_audience"),
            },
        })

    log("Anúncios e criativos")
    ads = []
    creative_fields = "id,name,thumbnail_url,image_url,body,title,object_type,effective_object_story_id,instagram_permalink_url,video_id,call_to_action_type"
    try:
        raw_ads = api_all(f"{acct}/ads", {
            "fields": f"id,name,adset_id,campaign_id,status,effective_status,created_time,updated_time,preview_shareable_link,creative.thumbnail_width(600).thumbnail_height(600){{{creative_fields}}}",
            "filtering": STATUS_FILTER,
        })
    except ApiError as e:
        warn(f"anúncios com miniatura grande falhou ({e}); tentando sem parâmetros de miniatura")
        raw_ads = api_all(f"{acct}/ads", {
            "fields": f"id,name,adset_id,campaign_id,status,effective_status,created_time,updated_time,preview_shareable_link,creative{{{creative_fields}}}",
            "filtering": STATUS_FILTER,
        })
    for a in raw_ads:
        cr = a.get("creative") or {}
        ads.append({
            "id": a["id"], "name": a.get("name"), "adset_id": a.get("adset_id"), "campaign_id": a.get("campaign_id"),
            "status": a.get("status"), "effective_status": a.get("effective_status"),
            "created_time": a.get("created_time"), "updated_time": a.get("updated_time"),
            "preview_link": a.get("preview_shareable_link"),
            "creative": {
                "id": cr.get("id"), "thumbnail_url": cr.get("thumbnail_url"), "image_url": cr.get("image_url"),
                "body": (cr.get("body") or "")[:400], "title": cr.get("title"), "object_type": cr.get("object_type"),
                "instagram_permalink_url": cr.get("instagram_permalink_url"),
                "video_id": cr.get("video_id"), "cta": cr.get("call_to_action_type"),
            },
        })

    # ---- série diária por anúncio -------------------------------------------------
    created = [c["created_time"][:10] for c in campaigns if c.get("created_time")]
    if FORCE_SINCE:
        since = dt.date.fromisoformat(FORCE_SINCE)
    elif created:
        since = dt.date.fromisoformat(min(created))
    else:
        since = today - dt.timedelta(days=30)
    # limite de segurança: no máximo 37 meses de histórico (limite da API)
    since = max(since, today - dt.timedelta(days=37 * 30))
    until = today
    log(f"Série diária por anúncio: {since} a {until}")

    daily = []
    action_types: set[str] = set()
    for a, b in daterange_chunks(since, until, 31):
        rows = api_all(f"{acct}/insights", {
            "level": "ad",
            "time_increment": 1,
            "time_range": json.dumps({"since": a.isoformat(), "until": b.isoformat()}),
            "fields": INSIGHT_FIELDS,
            "limit": 500,
        })
        for r in rows:
            acts = actions_to_dict(r.get("actions"))
            action_types.update(acts.keys())
            daily.append({
                "date": r.get("date_start"),
                "campaign_id": r.get("campaign_id"), "adset_id": r.get("adset_id"), "ad_id": r.get("ad_id"),
                "spend": round(fnum(r.get("spend")), 2),
                "impressions": inum(r.get("impressions")), "reach": inum(r.get("reach")),
                "frequency": round(fnum(r.get("frequency")), 3),
                "clicks": inum(r.get("clicks")), "link_clicks": inum(r.get("inline_link_clicks")),
                "thruplays": sum(inum(x.get("value")) for x in (r.get("video_thruplay_watched_actions") or [])),
                "video_p25": sum(inum(x.get("value")) for x in (r.get("video_p25_watched_actions") or [])),
                "video_p100": sum(inum(x.get("value")) for x in (r.get("video_p100_watched_actions") or [])),
                "actions": acts,
                "values": values_to_dict(r.get("action_values")),
            })
        log(f"  {a} a {b}: {len(rows)} linhas")

    # ---- totais exatos por preset (alcance/frequência não somam entre dias) -------------
    presets = {}
    for preset in ("last_7d", "last_14d", "last_30d", "this_month", "last_month", "maximum"):
        try:
            res = api(f"{acct}/insights", {
                "level": "account", "date_preset": preset,
                "fields": "spend,impressions,reach,frequency,clicks,inline_link_clicks,actions,action_values,date_start,date_stop",
            })
            rows = res.get("data", [])
            if rows:
                r = rows[0]
                presets[preset] = {
                    "since": r.get("date_start"), "until": r.get("date_stop"),
                    "spend": round(fnum(r.get("spend")), 2), "impressions": inum(r.get("impressions")),
                    "reach": inum(r.get("reach")), "frequency": round(fnum(r.get("frequency")), 3),
                    "clicks": inum(r.get("clicks")), "link_clicks": inum(r.get("inline_link_clicks")),
                    "actions": actions_to_dict(r.get("actions")),
                    "values": values_to_dict(r.get("action_values")),
                }
        except ApiError as e:
            warn(f"preset {preset}: {e}")

    # ---- alcance por campanha no período total e nos últimos 7/30 dias -------------
    campaign_reach = {}
    for preset in ("last_7d", "last_30d", "maximum"):
        try:
            rows = api_all(f"{acct}/insights", {
                "level": "campaign", "date_preset": preset,
                "fields": "campaign_id,reach,frequency,spend",
            })
            campaign_reach[preset] = {r["campaign_id"]: {"reach": inum(r.get("reach")), "frequency": round(fnum(r.get("frequency")), 3)} for r in rows}
        except ApiError as e:
            warn(f"alcance por campanha ({preset}): {e}")

    # ---- breakdowns úteis (últimos 30 dias): idade/gênero, região, posicionamento -------
    breakdowns = {}
    for name, bd in (("age_gender", "age,gender"), ("region", "region"), ("platform_position", "publisher_platform,platform_position")):
        try:
            rows = api_all(f"{acct}/insights", {
                "level": "campaign", "date_preset": "last_30d", "breakdowns": bd,
                "fields": "campaign_id,spend,impressions,reach,clicks,inline_link_clicks,actions,action_values",
                "limit": 500,
            })
            breakdowns[name] = [{
                "campaign_id": r.get("campaign_id"),
                **{k: r.get(k) for k in bd.split(",")},
                "spend": round(fnum(r.get("spend")), 2), "impressions": inum(r.get("impressions")),
                "reach": inum(r.get("reach")), "clicks": inum(r.get("clicks")),
                "link_clicks": inum(r.get("inline_link_clicks")), "actions": actions_to_dict(r.get("actions")),
                "values": values_to_dict(r.get("action_values")),
            } for r in rows]
        except ApiError as e:
            warn(f"breakdown {name}: {e}")

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "api_version": API_VERSION,
        "account": account,
        "range": {"since": since.isoformat(), "until": until.isoformat()},
        "campaigns": campaigns,
        "adsets": adsets,
        "ads": ads,
        "daily": daily,
        "presets": presets,
        "campaign_reach": campaign_reach,
        "breakdowns": breakdowns,
        "action_types_seen": sorted(action_types),
        "warnings": [],
    }


# ----------------------------------------------------------------------------
# Orgânico: Página do Facebook + Instagram
# ----------------------------------------------------------------------------

def fetch_organic(today: dt.date) -> dict:
    out: dict = {
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "facebook": None, "instagram": None, "warnings": [],
    }
    since_90 = today - dt.timedelta(days=90)
    since_30 = today - dt.timedelta(days=30)

    # ---------------- Facebook -------------------------------------------------------
    page_token = None
    try:
        p = api(PAGE_ID, {"fields": "id,name,fan_count,followers_count,link,picture{url},access_token"})
        page_token = p.get("access_token")
        fb = {
            "id": p.get("id"), "name": p.get("name"), "fans": p.get("fan_count"),
            "followers": p.get("followers_count"), "link": p.get("link"),
            "picture": ((p.get("picture") or {}).get("data") or {}).get("url"),
            "daily": {}, "posts": [],
        }
        # A Graph API foi aposentando métricas de Página (page_impressions*, page_fans, ...).
        # Cada item é (nome no JSON, candidatos na ordem de preferência) — o primeiro que responder é usado.
        metric_groups = [
            ("page_post_engagements", ["page_post_engagements"]),
            ("page_daily_follows_total", ["page_daily_follows_unique", "page_daily_follows"]),
            ("page_follows", ["page_follows"]),
            ("page_views_total", ["page_views_total"]),
            ("page_total_actions", ["page_total_actions"]),
            ("page_video_views", ["page_video_views"]),
            ("page_impressions_unique", ["page_impressions_unique", "page_posts_impressions_unique"]),
        ]
        for key, candidates in metric_groups:
            got = False
            last_err = None
            for m in candidates:
                series = []
                try:
                    for a, b in daterange_chunks(since_90, today, 90):
                        res = api(f"{PAGE_ID}/insights", {
                            "metric": m, "period": "day",
                            "since": a.isoformat(), "until": (b + dt.timedelta(days=1)).isoformat(),
                        }, token=page_token, retries=2)
                        for d in res.get("data", []):
                            for v in d.get("values", []):
                                series.append({"date": (v.get("end_time") or "")[:10], "value": inum(v.get("value"))})
                    fb["daily"][key] = series
                    got = True
                    break
                except ApiError as e:
                    last_err = e
                    continue
            if not got and key not in ("page_impressions_unique",):
                # alcance de Página não existe mais na API; só avisa sobre as métricas que ainda deveriam existir
                out["warnings"].append(f"Facebook métrica {key}: {last_err}")
        try:
            posts = api_all(f"{PAGE_ID}/published_posts", {
                "fields": "id,message,created_time,permalink_url,full_picture,shares,likes.summary(true).limit(0),comments.summary(true).limit(0)",
                "since": since_90.isoformat(), "limit": 50,
            }, token=page_token, max_pages=3)
            for po in posts:
                fb["posts"].append({
                    "id": po.get("id"), "message": (po.get("message") or "")[:300], "created_time": po.get("created_time"),
                    "permalink": po.get("permalink_url"), "picture": po.get("full_picture"),
                    "shares": inum((po.get("shares") or {}).get("count")),
                    "likes": inum(((po.get("likes") or {}).get("summary") or {}).get("total_count")),
                    "comments": inum(((po.get("comments") or {}).get("summary") or {}).get("total_count")),
                })
        except ApiError as e:
            out["warnings"].append(f"Facebook posts: {e}")
        out["facebook"] = fb
    except ApiError as e:
        out["warnings"].append(f"Facebook página {PAGE_ID}: {e}")

    # ---------------- Instagram ------------------------------------------------------
    try:
        ig_tok = page_token or TOKEN
        p = api(IG_ID, {"fields": "id,username,name,followers_count,follows_count,media_count,profile_picture_url,biography,website"}, token=ig_tok)
        ig = {
            "id": p.get("id"), "username": p.get("username"), "name": p.get("name"),
            "followers": p.get("followers_count"), "follows": p.get("follows_count"),
            "media_count": p.get("media_count"), "profile_picture_url": p.get("profile_picture_url"),
            "biography": p.get("biography"), "website": p.get("website"),
            "daily": {}, "totals": {}, "media": [],
        }
        # séries diárias (reach e follower_count aceitam period=day)
        for m, span in (("reach", since_90), ("follower_count", since_30)):
            series = []
            try:
                for a, b in daterange_chunks(span, today, 30):
                    res = api(f"{IG_ID}/insights", {
                        "metric": m, "period": "day",
                        "since": a.isoformat(), "until": (b + dt.timedelta(days=1)).isoformat(),
                    }, token=ig_tok)
                    for d in res.get("data", []):
                        for v in d.get("values", []):
                            series.append({"date": (v.get("end_time") or "")[:10], "value": inum(v.get("value"))})
                ig["daily"][m] = series
            except ApiError as e:
                out["warnings"].append(f"Instagram métrica {m}: {e}")
        # totais por janela (metric_type=total_value)
        total_metrics = "views,profile_views,accounts_engaged,website_clicks,total_interactions,likes,comments,shares,saves,replies,follows_and_unfollows"
        for label, span in (("last_7d", 7), ("last_30d", 30)):
            try:
                res = api(f"{IG_ID}/insights", {
                    "metric": total_metrics, "period": "day", "metric_type": "total_value",
                    "since": (today - dt.timedelta(days=span)).isoformat(), "until": today.isoformat(),
                }, token=ig_tok)
                ig["totals"][label] = {d.get("name"): inum((d.get("total_value") or {}).get("value")) for d in res.get("data", [])}
            except ApiError as e:
                # tenta um subconjunto mais conservador
                try:
                    res = api(f"{IG_ID}/insights", {
                        "metric": "views,profile_views,accounts_engaged,website_clicks,total_interactions", "period": "day", "metric_type": "total_value",
                        "since": (today - dt.timedelta(days=span)).isoformat(), "until": today.isoformat(),
                    }, token=ig_tok)
                    ig["totals"][label] = {d.get("name"): inum((d.get("total_value") or {}).get("value")) for d in res.get("data", [])}
                except ApiError as e2:
                    out["warnings"].append(f"Instagram totais {label}: {e2}")
        # série diária de visitas ao perfil / contas engajadas (30 dias, 1 chamada por dia)
        pv, ae, vw = [], [], []
        for i in range(30, -1, -1):
            d = today - dt.timedelta(days=i)
            try:
                # a janela é meio-aberta: since=d, until=d+1 devolve exatamente o dia d
                # (com since == until a API responde vazio, o que zerava a série)
                res = api(f"{IG_ID}/insights", {
                    "metric": "profile_views,accounts_engaged,views", "period": "day", "metric_type": "total_value",
                    "since": d.isoformat(), "until": (d + dt.timedelta(days=1)).isoformat(),
                }, token=ig_tok, retries=2)
                vals = {x.get("name"): inum((x.get("total_value") or {}).get("value")) for x in res.get("data", [])}
                pv.append({"date": d.isoformat(), "value": vals.get("profile_views", 0)})
                ae.append({"date": d.isoformat(), "value": vals.get("accounts_engaged", 0)})
                vw.append({"date": d.isoformat(), "value": vals.get("views", 0)})
            except ApiError as e:
                out["warnings"].append(f"Instagram diário {d}: {e}")
                break
        if pv:
            ig["daily"]["profile_views"] = pv
            ig["daily"]["accounts_engaged"] = ae
            ig["daily"]["views"] = vw
        # mídias recentes + insights por mídia
        try:
            medias = api_all(f"{IG_ID}/media", {
                "fields": "id,caption,media_type,media_product_type,timestamp,permalink,thumbnail_url,media_url,like_count,comments_count,is_comment_enabled",
                "limit": 50,
            }, token=ig_tok, max_pages=2)
            for m in medias[:60]:
                item = {
                    "id": m.get("id"), "caption": (m.get("caption") or "")[:220], "media_type": m.get("media_type"),
                    "product_type": m.get("media_product_type"), "timestamp": m.get("timestamp"),
                    "permalink": m.get("permalink"), "thumbnail": m.get("thumbnail_url") or m.get("media_url"),
                    "likes": inum(m.get("like_count")), "comments": inum(m.get("comments_count")),
                    "insights": {},
                }
                candidates = ["reach,saved,shares,views,total_interactions", "reach,saved,views", "reach,saved", "reach"]
                for metric_set in candidates:
                    try:
                        res = api(f"{m['id']}/insights", {"metric": metric_set}, token=ig_tok, retries=1)
                        item["insights"] = {d.get("name"): inum((d.get("values") or [{}])[0].get("value")) for d in res.get("data", [])}
                        break
                    except ApiError:
                        continue
                ig["media"].append(item)
        except ApiError as e:
            out["warnings"].append(f"Instagram mídias: {e}")
        out["instagram"] = ig
    except ApiError as e:
        out["warnings"].append(f"Instagram conta {IG_ID}: {e}")

    return out


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main() -> int:
    if not TOKEN:
        log("ERRO: defina META_ACCESS_TOKEN")
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)

    # sanidade do token (não imprime nada sensível)
    try:
        me = api("me", {"fields": "id,name"})
        log(f"Token OK (usuário/sistema id {me.get('id')})")
    except ApiError as e:
        log(f"ERRO: token inválido ou expirado: {e}")
        return 3
    try:
        perms = api("me/permissions").get("data", [])
        granted = sorted(p["permission"] for p in perms if p.get("status") == "granted")
        needed = {"ads_read", "pages_read_engagement", "read_insights", "instagram_basic", "instagram_manage_insights"}
        missing = sorted(needed - set(granted))
        if missing:
            warn(f"permissões ausentes no token: {', '.join(missing)} (dados orgânicos podem ficar incompletos)")
    except ApiError:
        pass  # tokens de usuário do sistema nem sempre expõem /me/permissions

    ok = True
    try:
        meta = fetch_ads_data()
        meta["warnings"] = list(WARNINGS)
        with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
        log(f"meta.json: {len(meta['campaigns'])} campanhas, {len(meta['ads'])} anúncios, {len(meta['daily'])} linhas diárias")
        today = dt.date.fromisoformat(meta["range"]["until"])
    except Exception as e:  # noqa: BLE001
        log(f"ERRO ao coletar Meta Ads: {TOKEN_RE.sub('***', str(e))}")
        ok = False
        today = today_in(None)

    try:
        organic = fetch_organic(today)
        with open(os.path.join(OUT_DIR, "organic.json"), "w", encoding="utf-8") as f:
            json.dump(organic, f, ensure_ascii=False, separators=(",", ":"))
        n_ig = len((organic.get("instagram") or {}).get("media", []))
        log(f"organic.json: instagram={'ok' if organic.get('instagram') else 'indisponível'} ({n_ig} mídias), facebook={'ok' if organic.get('facebook') else 'indisponível'}, avisos={len(organic['warnings'])}")
    except Exception as e:  # noqa: BLE001
        log(f"AVISO: orgânico falhou: {TOKEN_RE.sub('***', str(e))}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
