#!/usr/bin/env python3
"""
Coletor de dados do Google Ads para o dashboard Nohotel (Steink Performance).

Gera public/data/google.json com: conta, campanhas, grupos de anúncios, série diária por grupo de
anúncios, conversões por ação, palavras-chave, termos de pesquisa, anúncios, dispositivos e
localidades (últimos 30 dias).

Uso:
  GOOGLE_ADS_DEVELOPER_TOKEN=... GOOGLE_ADS_CLIENT_ID=... GOOGLE_ADS_CLIENT_SECRET=... \
  GOOGLE_ADS_REFRESH_TOKEN=... GOOGLE_ADS_LOGIN_CUSTOMER_ID=... python scripts/fetch_google.py

Variáveis de ambiente:
  GOOGLE_ADS_DEVELOPER_TOKEN     (obrigatória) token de desenvolvedor da conta administradora (MCC)
  GOOGLE_ADS_CLIENT_ID           (obrigatória) OAuth client id (Google Cloud → APIs e serviços → Credenciais)
  GOOGLE_ADS_CLIENT_SECRET       (obrigatória) OAuth client secret
  GOOGLE_ADS_REFRESH_TOKEN       (obrigatória) refresh token gerado com o escopo https://www.googleapis.com/auth/adwords
  GOOGLE_ADS_LOGIN_CUSTOMER_ID   (recomendada) ID da conta administradora (MCC) que gerencia a Nohotel
  GOOGLE_ADS_CUSTOMER_ID         (padrão 781-346-4105) conta Google Ads da Nohotel
  GOOGLE_ADS_API_VERSION         (opcional) ex. v22; se vazio, tenta as versões mais recentes conhecidas
  GOOGLE_SINCE                   (padrão 2025-04-01) início da série diária
  OUT_DIR                        (padrão public/data)

Sem credenciais o script grava google.json com {"configured": false} e sai com código 0 — o dashboard
mostra o passo a passo de configuração no lugar dos dados.

Sem dependências externas (apenas biblioteca padrão). Segredos nunca são impressos.
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

def _load_env_file(path: str = ".env.google") -> None:
    """Uso local: carrega .env.google (fora do git) sem sobrescrever o ambiente."""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


_load_env_file()

DEV_TOKEN = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
CLIENT_ID = os.environ.get("GOOGLE_ADS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "").strip()
LOGIN_CID = re.sub(r"\D", "", os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""))
CUSTOMER_ID = re.sub(r"\D", "", os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "781-346-4105"))
FORCED_VERSION = os.environ.get("GOOGLE_ADS_API_VERSION", "").strip()
SINCE = (os.environ.get("GOOGLE_SINCE") or "2025-04-01").strip()
OUT_DIR = os.environ.get("OUT_DIR", "public/data")

# versões candidatas (a mais nova primeiro). A API mantém ~3 versões ativas; a primeira que responder é usada.
CANDIDATE_VERSIONS = ["v23", "v22", "v21", "v20", "v19"]

SECRET_RE = re.compile(r"(developer-token|access_token|refresh_token|client_secret|Bearer)[\s=:\"]*[^\s\"&,]+", re.I)
WARNINGS: list[str] = []


def clean(msg) -> str:
    return SECRET_RE.sub(r"\1=***", str(msg))


def log(msg: str) -> None:
    print(clean(msg), flush=True)


def warn(msg: str) -> None:
    WARNINGS.append(clean(msg))
    log(f"AVISO: {clean(msg)}")


class ApiError(Exception):
    def __init__(self, message, http=None, status=None):
        super().__init__(clean(message))
        self.http = http
        self.status = status


# ----------------------------------------------------------------------------
# OAuth + transporte
# ----------------------------------------------------------------------------

def access_token() -> str:
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(raw)
            msg = f"{err.get('error')}: {err.get('error_description')}"
        except Exception:
            msg = raw[:200]
        raise ApiError(f"OAuth falhou ({e.code}): {msg}", http=e.code)
    tok = data.get("access_token")
    if not tok:
        raise ApiError("OAuth não devolveu access_token")
    return tok


class Client:
    def __init__(self, token: str, version: str):
        self.token = token
        self.version = version

    def search(self, query: str, customer_id: str = CUSTOMER_ID, retries: int = 4) -> list[dict]:
        """googleAds:searchStream — devolve a lista de results concatenada de todos os lotes."""
        url = f"https://googleads.googleapis.com/{self.version}/customers/{customer_id}/googleAds:searchStream"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "developer-token": DEV_TOKEN,
            "Content-Type": "application/json",
        }
        if LOGIN_CID:
            headers["login-customer-id"] = LOGIN_CID
        body = json.dumps({"query": " ".join(query.split())}).encode()
        last: Exception | None = None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    batches = json.load(resp)
                out: list[dict] = []
                for b in batches if isinstance(batches, list) else [batches]:
                    out.extend(b.get("results", []))
                return out
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                status, msg = None, raw[:300]
                try:
                    err = json.loads(raw)
                    err = err[0] if isinstance(err, list) else err
                    e0 = err.get("error", {})
                    status = e0.get("status")
                    msg = e0.get("message", msg)
                    for d in e0.get("details", []) or []:
                        for ge in d.get("errors", []) or []:
                            msg = f"{msg} · {ge.get('message', '')}"
                except Exception:
                    pass
                last = ApiError(f"HTTP {e.code} {status or ''}: {msg}", http=e.code, status=status)
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(min(60, 5 * (2 ** attempt)))
                    continue
                raise last
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = ApiError(f"rede: {getattr(e, 'reason', e)}")
                if attempt < retries - 1:
                    time.sleep(5 * (2 ** attempt))
                    continue
                raise last
        raise last or ApiError("falha desconhecida")


def list_accessible(token: str, version: str) -> list[str]:
    """customers:listAccessibleCustomers — contas que o usuário OAuth enxerga direto."""
    url = f"https://googleads.googleapis.com/{version}/customers:listAccessibleCustomers"
    headers = {"Authorization": f"Bearer {token}", "developer-token": DEV_TOKEN}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise ApiError(f"listAccessibleCustomers HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}", http=e.code)
    return [r.rsplit("/", 1)[-1] for r in data.get("resourceNames", [])]


def resolve_login_customer(c: Client) -> None:
    """Descobre qual conta administradora dá acesso a CUSTOMER_ID e fixa o cabeçalho.

    Sem isso, contas de cliente gerenciadas por um MCC respondem PERMISSION_DENIED /
    USER_PERMISSION_DENIED mesmo com o token correto.
    """
    global LOGIN_CID
    try:
        accessible = list_accessible(c.token, c.version)
    except ApiError as e:
        warn(f"não foi possível listar as contas acessíveis: {e}")
        return
    log(f"Contas acessíveis pelo login: {len(accessible)}")
    if CUSTOMER_ID in accessible:
        LOGIN_CID = ""  # acesso direto, sem MCC
        return
    for cand in accessible:
        LOGIN_CID = cand
        try:
            rows = c.search(
                "SELECT customer_client.id, customer_client.manager, customer_client.descriptive_name, customer_client.level "
                "FROM customer_client WHERE customer_client.status = 'ENABLED'",
                customer_id=cand, retries=1)
        except ApiError:
            continue
        ids = {str((r.get("customerClient") or {}).get("id")) for r in rows}
        if CUSTOMER_ID in ids:
            log(f"Conta {CUSTOMER_ID} encontrada sob a administradora {cand}")
            return
    LOGIN_CID = ""
    warn(f"a conta {CUSTOMER_ID} não apareceu em nenhuma administradora acessível — verifique o vínculo com o MCC")


def pick_version(token: str) -> Client:
    versions = [FORCED_VERSION] if FORCED_VERSION else CANDIDATE_VERSIONS
    errors = []
    for v in versions:
        c = Client(token, v)
        try:
            try:
                c.search("SELECT customer.id FROM customer LIMIT 1", retries=1)
            except ApiError as inner:
                # conta gerida por MCC costuma exigir o cabeçalho login-customer-id
                if inner.http in (401, 403) or "PERMISSION" in str(inner).upper():
                    resolve_login_customer(c)
                    c.search("SELECT customer.id FROM customer LIMIT 1", retries=1)
                else:
                    raise
            log(f"Google Ads API {v} OK")
            return c
        except ApiError as e:
            errors.append(f"{v}: {e}")
            # 404 = versão desativada/inexistente; qualquer outro erro é de credencial/conta e não muda com a versão
            if e.http == 404 or "UNIMPLEMENTED" in str(e):
                continue
            raise
    raise ApiError("nenhuma versão da API respondeu: " + " | ".join(errors))


# ----------------------------------------------------------------------------
# utilitários
# ----------------------------------------------------------------------------

def money(micros) -> float:
    try:
        return round(int(micros) / 1_000_000, 2)
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


def rid(resource: str | None) -> str | None:
    """'customers/123/campaigns/456' -> '456'"""
    if not resource:
        return None
    return resource.rsplit("/", 1)[-1]


def metrics_of(r: dict) -> dict:
    m = r.get("metrics", {}) or {}
    return {
        "cost": money(m.get("costMicros")),
        "impressions": inum(m.get("impressions")),
        "clicks": inum(m.get("clicks")),
        "conversions": round(fnum(m.get("conversions")), 2),
        "conversions_value": round(fnum(m.get("conversionsValue")), 2),
        "all_conversions": round(fnum(m.get("allConversions")), 2),
        "interactions": inum(m.get("interactions")),
        "video_views": inum(m.get("videoViews")),
    }


# ----------------------------------------------------------------------------
# coleta
# ----------------------------------------------------------------------------

def collect(c: Client) -> dict:
    today = dt.date.today()
    since = dt.date.fromisoformat(SINCE)
    until = today
    rng = f"segments.date BETWEEN '{since.isoformat()}' AND '{until.isoformat()}'"

    log("Conta")
    cust = c.search("SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, customer.status, customer.manager, customer.auto_tagging_enabled FROM customer")
    cu = (cust[0] if cust else {}).get("customer", {})
    customer = {
        "id": CUSTOMER_ID, "name": cu.get("descriptiveName"), "currency": cu.get("currencyCode", "BRL"),
        "timezone": cu.get("timeZone"), "status": cu.get("status"), "login_customer_id": LOGIN_CID or None,
        "auto_tagging": cu.get("autoTaggingEnabled"),
    }

    log("Campanhas")
    campaigns = []
    for r in c.search("""
        SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status, campaign.advertising_channel_type,
               campaign.advertising_channel_sub_type, campaign.bidding_strategy_type, campaign.start_date, campaign.end_date,
               campaign_budget.amount_micros, campaign_budget.period
        FROM campaign WHERE campaign.status != 'REMOVED' ORDER BY campaign.id"""):
        cp, bd = r.get("campaign", {}), r.get("campaignBudget", {}) or {}
        campaigns.append({
            "id": str(cp.get("id")), "name": cp.get("name"), "status": cp.get("status"), "serving_status": cp.get("servingStatus"),
            "channel_type": cp.get("advertisingChannelType"), "channel_sub_type": cp.get("advertisingChannelSubType"),
            "bidding_strategy_type": cp.get("biddingStrategyType"), "start_date": cp.get("startDate"), "end_date": cp.get("endDate"),
            "daily_budget": money(bd.get("amountMicros")) if (bd.get("period") in (None, "DAILY")) else 0.0,
            "impression_share": None, "lost_is_budget": None, "lost_is_rank": None,
        })
    by_id = {cp["id"]: cp for cp in campaigns}

    # parcela de impressão (últimos 30 dias) — só campanhas de pesquisa/shopping devolvem
    try:
        for r in c.search("""
            SELECT campaign.id, metrics.search_impression_share, metrics.search_budget_lost_impression_share,
                   metrics.search_rank_lost_impression_share
            FROM campaign WHERE segments.date DURING LAST_30_DAYS AND campaign.status != 'REMOVED'"""):
            cp = by_id.get(str(r.get("campaign", {}).get("id")))
            m = r.get("metrics", {}) or {}
            if cp and m.get("searchImpressionShare") is not None:
                cp["impression_share"] = round(fnum(m.get("searchImpressionShare")) * 100, 1)
                cp["lost_is_budget"] = round(fnum(m.get("searchBudgetLostImpressionShare")) * 100, 1)
                cp["lost_is_rank"] = round(fnum(m.get("searchRankLostImpressionShare")) * 100, 1)
    except ApiError as e:
        warn(f"parcela de impressão: {e}")

    log("Grupos de anúncios")
    ad_groups = []
    for r in c.search("""
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type, ad_group.campaign, ad_group.cpc_bid_micros
        FROM ad_group WHERE ad_group.status != 'REMOVED' ORDER BY ad_group.id"""):
        ag = r.get("adGroup", {})
        ad_groups.append({
            "id": str(ag.get("id")), "name": ag.get("name"), "status": ag.get("status"), "type": ag.get("type"),
            "campaign_id": rid(ag.get("campaign")), "cpc_bid": money(ag.get("cpcBidMicros")),
        })

    log(f"Série diária por campanha: {since} a {until}")
    daily = []
    for r in c.search(f"""
        SELECT campaign.id, segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions,
               metrics.conversions_value, metrics.all_conversions, metrics.interactions, metrics.video_views
        FROM campaign WHERE {rng} AND metrics.impressions > 0"""):
        daily.append({"date": r.get("segments", {}).get("date"), "campaign_id": str(r.get("campaign", {}).get("id")), **metrics_of(r)})

    log("Série diária por grupo de anúncios")
    daily_ad_groups = []
    try:
        for r in c.search(f"""
            SELECT campaign.id, ad_group.id, segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.conversions_value, metrics.all_conversions
            FROM ad_group WHERE {rng} AND metrics.impressions > 0"""):
            daily_ad_groups.append({
                "date": r.get("segments", {}).get("date"), "campaign_id": str(r.get("campaign", {}).get("id")),
                "ad_group_id": str(r.get("adGroup", {}).get("id")), **metrics_of(r),
            })
    except ApiError as e:
        warn(f"série por grupo de anúncios: {e}")

    log("Conversões por ação")
    conversions_daily = []
    try:
        for r in c.search(f"""
            SELECT campaign.id, segments.date, segments.conversion_action_name, segments.conversion_action_category,
                   metrics.conversions, metrics.conversions_value, metrics.all_conversions
            FROM campaign WHERE {rng} AND metrics.all_conversions > 0"""):
            sg, m = r.get("segments", {}), r.get("metrics", {}) or {}
            conversions_daily.append({
                "date": sg.get("date"), "campaign_id": str(r.get("campaign", {}).get("id")),
                "action": sg.get("conversionActionName"), "category": sg.get("conversionActionCategory"),
                "conversions": round(fnum(m.get("conversions")), 2), "value": round(fnum(m.get("conversionsValue")), 2),
                "all_conversions": round(fnum(m.get("allConversions")), 2),
            })
    except ApiError as e:
        warn(f"conversões por ação: {e}")

    log("Palavras-chave (30 dias)")
    keywords = []
    try:
        for r in c.search("""
            SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type, ad_group_criterion.status, ad_group_criterion.quality_info.quality_score,
                   metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value
            FROM keyword_view WHERE segments.date DURING LAST_30_DAYS AND ad_group_criterion.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC LIMIT 150"""):
            cr = r.get("adGroupCriterion", {})
            keywords.append({
                "campaign_id": str(r.get("campaign", {}).get("id")), "ad_group_id": str(r.get("adGroup", {}).get("id")),
                "id": str(cr.get("criterionId")), "text": (cr.get("keyword") or {}).get("text"),
                "match_type": (cr.get("keyword") or {}).get("matchType"), "status": cr.get("status"),
                "quality_score": (cr.get("qualityInfo") or {}).get("qualityScore"), **metrics_of(r),
            })
    except ApiError as e:
        warn(f"palavras-chave: {e}")

    log("Termos de pesquisa (30 dias)")
    search_terms = []
    try:
        for r in c.search("""
            SELECT campaign.id, ad_group.id, search_term_view.search_term, search_term_view.status,
                   metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value
            FROM search_term_view WHERE segments.date DURING LAST_30_DAYS
            ORDER BY metrics.cost_micros DESC LIMIT 150"""):
            st = r.get("searchTermView", {})
            search_terms.append({
                "campaign_id": str(r.get("campaign", {}).get("id")), "ad_group_id": str(r.get("adGroup", {}).get("id")),
                "term": st.get("searchTerm"), "status": st.get("status"), **metrics_of(r),
            })
    except ApiError as e:
        warn(f"termos de pesquisa: {e}")

    log("Anúncios (30 dias)")
    ads = []
    try:
        for r in c.search("""
            SELECT campaign.id, ad_group.id, ad_group_ad.ad.id, ad_group_ad.ad.type, ad_group_ad.ad.name, ad_group_ad.status,
                   ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.ad.responsive_search_ad.descriptions, ad_group_ad.ad_strength,
                   metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value
            FROM ad_group_ad WHERE segments.date DURING LAST_30_DAYS AND ad_group_ad.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC LIMIT 100"""):
            aga = r.get("adGroupAd", {})
            ad = aga.get("ad", {}) or {}
            rsa = ad.get("responsiveSearchAd") or {}
            ads.append({
                "campaign_id": str(r.get("campaign", {}).get("id")), "ad_group_id": str(r.get("adGroup", {}).get("id")),
                "id": str(ad.get("id")), "type": ad.get("type"), "name": ad.get("name"), "status": aga.get("status"),
                "strength": aga.get("adStrength"), "final_url": (ad.get("finalUrls") or [None])[0],
                "headlines": [x.get("text") for x in rsa.get("headlines", []) if x.get("text")][:15],
                "descriptions": [x.get("text") for x in rsa.get("descriptions", []) if x.get("text")][:4],
                **metrics_of(r),
            })
    except ApiError as e:
        warn(f"anúncios: {e}")

    log("Dispositivos (30 dias)")
    devices = []
    try:
        for r in c.search("""
            SELECT campaign.id, segments.device, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions
            FROM campaign WHERE segments.date DURING LAST_30_DAYS AND metrics.impressions > 0"""):
            devices.append({"campaign_id": str(r.get("campaign", {}).get("id")), "device": r.get("segments", {}).get("device"), **metrics_of(r)})
    except ApiError as e:
        warn(f"dispositivos: {e}")

    log("Localidades (30 dias)")
    geo = []
    try:
        rows = c.search("""
            SELECT campaign.id, geographic_view.country_criterion_id, segments.geo_target_city, segments.geo_target_region,
                   metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions
            FROM geographic_view WHERE segments.date DURING LAST_30_DAYS AND metrics.impressions > 0""")
        ids = set()
        for r in rows:
            sg = r.get("segments", {})
            for k in ("geoTargetCity", "geoTargetRegion"):
                if sg.get(k):
                    ids.add(sg[k])
        names = {}
        ids = sorted(ids)
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            q = "SELECT geo_target_constant.resource_name, geo_target_constant.name, geo_target_constant.canonical_name FROM geo_target_constant WHERE geo_target_constant.resource_name IN (" + ",".join(f"'{x}'" for x in chunk) + ")"
            try:
                for g in c.search(q):
                    gc = g.get("geoTargetConstant", {})
                    names[gc.get("resourceName")] = gc.get("name")
            except ApiError as e:
                warn(f"nomes de localidades: {e}")
                break
        agg: dict = {}
        for r in rows:
            sg = r.get("segments", {})
            city = names.get(sg.get("geoTargetCity")) or (sg.get("geoTargetCity") or "").rsplit("/", 1)[-1] or None
            region = names.get(sg.get("geoTargetRegion")) or None
            key = (str(r.get("campaign", {}).get("id")), city or region or "—", region)
            m = metrics_of(r)
            a = agg.setdefault(key, {"campaign_id": key[0], "city": city, "region": region, "cost": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0})
            a["cost"] = round(a["cost"] + m["cost"], 2); a["impressions"] += m["impressions"]; a["clicks"] += m["clicks"]; a["conversions"] = round(a["conversions"] + m["conversions"], 2)
        geo = sorted(agg.values(), key=lambda x: -x["cost"])[:60]
    except ApiError as e:
        warn(f"localidades: {e}")

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "configured": True,
        "api_version": c.version,
        "customer": customer,
        "range": {"since": since.isoformat(), "until": until.isoformat()},
        "campaigns": campaigns,
        "ad_groups": ad_groups,
        "daily": daily,
        "daily_ad_groups": daily_ad_groups,
        "conversions_daily": conversions_daily,
        "keywords": keywords,
        "search_terms": search_terms,
        "ads": ads,
        "devices": devices,
        "geo": geo,
        "warnings": list(WARNINGS),
    }


def write(out: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "google.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    missing = [n for n, v in (("GOOGLE_ADS_DEVELOPER_TOKEN", DEV_TOKEN), ("GOOGLE_ADS_CLIENT_ID", CLIENT_ID),
                              ("GOOGLE_ADS_CLIENT_SECRET", CLIENT_SECRET), ("GOOGLE_ADS_REFRESH_TOKEN", REFRESH_TOKEN)) if not v]
    if missing:
        log(f"Google Ads não configurado — faltam: {', '.join(missing)}")
        write({
            "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
            "configured": False, "reason": f"credenciais ausentes: {', '.join(missing)}",
            "customer": {"id": CUSTOMER_ID}, "warnings": [],
        })
        return 0
    try:
        tok = access_token()
        c = pick_version(tok)
        if not LOGIN_CID:
            resolve_login_customer(c)
        out = collect(c)
        write(out)
        log(f"google.json: {len(out['campaigns'])} campanhas, {len(out['ad_groups'])} grupos, {len(out['daily'])} linhas diárias, avisos={len(out['warnings'])}")
        return 0
    except Exception as e:  # noqa: BLE001
        msg = clean(str(e))
        log(f"ERRO Google Ads: {msg}")
        write({
            "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
            "configured": False, "reason": f"erro na coleta: {msg}",
            "customer": {"id": CUSTOMER_ID, "login_customer_id": LOGIN_CID or None}, "warnings": list(WARNINGS),
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
