#!/usr/bin/env python3
"""
Gera o relatório mensal em HTML (Meta Ads + Google Ads + orgânico) de um cliente.

Busca os dados direto nas APIs, para o mês fechado e o mês anterior, e escreve um HTML
único, sem dependências externas, pronto para enviar ao cliente ou imprimir em PDF.

Uso:
    python scripts/relatorio_mensal.py                 # mês anterior ao de hoje
    python scripts/relatorio_mensal.py --mes 2026-09
    python scripts/relatorio_mensal.py --mes 2026-09 --saida "C:/.../relatorio.html"

Credenciais: as mesmas do dashboard (.env.meta e .env.google, ou variáveis de ambiente).
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import html
import importlib.util
import io
import json
import os
import sys
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- utilidades

def brl(v, casas=2):
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return "R$" + s


def num(v, casas=0):
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return s


def pct(v, casas=2):
    return "—" if v is None else num(v, casas) + "%"


def div(a, b):
    return (a / b) if b else None


def esc(s):
    return html.escape(str(s if s is not None else ""))


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def carregar_env(caminho):
    out = {}
    if os.path.exists(caminho):
        for l in io.open(caminho, encoding="utf-8"):
            l = l.strip()
            if l and not l.startswith("#") and "=" in l:
                k, v = l.split("=", 1)
                out[k.strip()] = v.strip()
    return out


# ------------------------------------------------------------------ Meta API

class Meta:
    def __init__(self, token, conta, versao="v23.0"):
        self.t, self.conta, self.v = token, f"act_{conta}", versao

    def _get(self, path, **p):
        p["access_token"] = self.t
        url = f"https://graph.facebook.com/{self.v}/{path}?" + urllib.parse.urlencode(p)
        with urllib.request.urlopen(url, timeout=300) as r:
            return json.load(r)

    def insights(self, desde, ate, **extra):
        p = {"time_range": json.dumps({"since": desde, "until": ate}), "limit": 500,
             "fields": "spend,impressions,reach,frequency,clicks,inline_link_clicks,actions"}
        p.update(extra)
        out, d = [], self._get(f"{self.conta}/insights", **p)
        out += d.get("data", [])
        while d.get("paging", {}).get("next"):
            cur = d["paging"].get("cursors", {}).get("after")
            if not cur:
                break
            p["after"] = cur
            d = self._get(f"{self.conta}/insights", **p)
            out += d.get("data", [])
        return out

    def nomes(self, recurso, campos):
        out, p = [], {"fields": campos, "limit": 400,
                      "filtering": json.dumps([{"field": "effective_status", "operator": "IN",
                                                "value": ["ACTIVE", "PAUSED", "ARCHIVED", "CAMPAIGN_PAUSED",
                                                          "ADSET_PAUSED", "WITH_ISSUES", "IN_PROCESS"]}])}
        d = self._get(f"{self.conta}/{recurso}", **p)
        out += d.get("data", [])
        while d.get("paging", {}).get("next"):
            cur = d["paging"].get("cursors", {}).get("after")
            if not cur:
                break
            p["after"] = cur
            d = self._get(f"{self.conta}/{recurso}", **p)
            out += d.get("data", [])
        return out


def acoes(linha):
    return {a["action_type"]: float(a["value"]) for a in (linha.get("actions") or [])}


def m_totais(linhas):
    t = {"spend": 0.0, "impressions": 0, "reach": 0, "clicks": 0, "link": 0,
         "purchase": 0.0, "atc": 0.0, "ic": 0.0, "conversa": 0.0}
    for r in linhas:
        a = acoes(r)
        t["spend"] += float(r.get("spend", 0))
        t["impressions"] += int(r.get("impressions", 0) or 0)
        t["reach"] += int(r.get("reach", 0) or 0)
        t["clicks"] += int(r.get("clicks", 0) or 0)
        t["link"] += int(r.get("inline_link_clicks", 0) or 0)
        t["purchase"] += a.get("purchase", 0)
        t["atc"] += a.get("add_to_cart", 0)
        t["ic"] += a.get("initiate_checkout", 0)
        t["conversa"] += a.get("onsite_conversion.messaging_conversation_started_7d", 0)
    t["cpm"] = div(t["spend"] * 1000, t["impressions"])
    t["cpc_link"] = div(t["spend"], t["link"])
    t["ctr_link"] = div(t["link"] * 100, t["impressions"])
    t["custo_compra"] = div(t["spend"], t["purchase"])
    t["custo_atc"] = div(t["spend"], t["atc"])
    return t


# ---------------------------------------------------------------- Google API

def google_client():
    spec = importlib.util.spec_from_file_location("fg", os.path.join("scripts", "fetch_google.py"))
    fg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fg)
    c = fg.pick_version(fg.access_token())
    if not fg.LOGIN_CID:
        fg.resolve_login_customer(c)
    return fg, c


def g_m(r):
    m = r.get("metrics", {}) or {}
    return {
        "cost": int(m.get("costMicros", 0) or 0) / 1e6,
        "clicks": int(m.get("clicks", 0) or 0),
        "impressions": int(m.get("impressions", 0) or 0),
        "conversions": float(m.get("conversions", 0) or 0),
        "all_conversions": float(m.get("allConversions", 0) or 0),
    }


def g_soma(linhas):
    t = {"cost": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0, "all_conversions": 0.0}
    for r in linhas:
        m = g_m(r) if "metrics" in r else r
        for k in t:
            t[k] += m.get(k, 0)
    t["cpc"] = div(t["cost"], t["clicks"])
    t["cpm"] = div(t["cost"] * 1000, t["impressions"])
    t["ctr"] = div(t["clicks"] * 100, t["impressions"])
    t["tx_conv"] = div(t["conversions"] * 100, t["clicks"])
    t["custo_conv"] = div(t["cost"], t["conversions"])
    return t


# ------------------------------------------------------------------- blocos

def kpi(label, valor, anterior, inverso=False, fmt=num, casas=0):
    """inverso=True quando subir é ruim (custo, CPC)."""
    atual_s = fmt(valor, casas) if fmt is not num else num(valor, casas)
    if anterior in (None, 0) or valor is None:
        delta = '<span class="kpi-delta" style="color:#9099a6">—</span>'
        prev = "sem base de comparação"
    else:
        var = (valor - anterior) / abs(anterior) * 100
        subiu = var > 0
        bom = (not subiu) if inverso else subiu
        if abs(var) < 0.05:
            delta = '<span class="kpi-delta" style="color:#9099a6">= estável</span>'
        else:
            cor = "#1a8a4a" if bom else "#c0392b"
            delta = f'<span class="kpi-delta" style="color:{cor}">{"▲" if subiu else "▼"} {num(abs(var), 2)}%</span>'
        prev = f"{fmt(anterior, casas) if fmt is not num else num(anterior, casas)} no período anterior"
    return (f'<div class="kpi"><div class="kpi-label">{esc(label)}</div>'
            f'<div class="kpi-main"><span class="kpi-value">{atual_s}</span>{delta}</div>'
            f'<div class="kpi-prev">{esc(prev)}</div></div>')


def barras_v(dados, cor="#1877f2", largura=576, altura=162, rotulo=lambda k: k):
    """dados: lista de (rotulo, valor). Barras verticais com tooltip."""
    if not dados:
        return ""
    n = len(dados)
    mx = max(v for _, v in dados) or 1
    passo = largura / n
    bw = passo * 0.6
    h = altura - 22
    p = [f'<svg viewBox="0 0 {largura} {altura}" width="100%" preserveAspectRatio="xMidYMid meet">']
    for i, (k, v) in enumerate(dados):
        alt = v / mx * h
        x = i * passo + (passo - bw) / 2
        p.append(f'<rect x="{x:.1f}" y="{h - alt:.1f}" width="{bw:.1f}" height="{alt:.1f}" rx="2" fill="{cor}">'
                 f'<title>{esc(k)}: {num(v)}</title></rect>')
    cada = max(1, n // 16)
    for i, (k, _) in enumerate(dados):
        if i % cada == 0 or i == n - 1:
            p.append(f'<text x="{i * passo + passo / 2:.1f}" y="{altura - 8}" font-size="9" '
                     f'fill="#8a8f98" text-anchor="middle">{esc(rotulo(k))}</text>')
    p.append("</svg>")
    return "".join(p)


def barras_duplas(dados, cor1="#1f4e5f", cor2="#c8971b", nome1="Impressões", nome2="Alcance"):
    """dados: lista de (rotulo, v1, v2)."""
    if not dados:
        return ""
    largura, h = 540, 170
    n = len(dados)
    mx = max(max(a, b) for _, a, b in dados) or 1
    passo = largura / n
    bw = passo * 0.3
    leg = (f"<div style='margin-bottom:8px'><svg viewBox='0 0 300 14' width='230' height='14'>"
           f"<rect width='11' height='11' rx='2' fill='{cor1}'/><text x='16' y='10' font-size='11' fill='#5a5f68'>{nome1}</text>"
           f"<rect x='150' width='11' height='11' rx='2' fill='{cor2}'/><text x='166' y='10' font-size='11' fill='#5a5f68'>{nome2}</text>"
           f"</svg></div>")
    p = [leg, f'<svg viewBox="0 0 {largura} {h + 22}" width="100%" preserveAspectRatio="xMidYMid meet">']
    for i, (k, a, b) in enumerate(dados):
        x0 = i * passo + passo * 0.12
        for j, (v, c, nome) in enumerate(((a, cor1, nome1), (b, cor2, nome2))):
            alt = v / mx * h
            p.append(f'<rect x="{x0 + j * (bw + 3):.1f}" y="{h - alt:.1f}" width="{bw:.1f}" height="{alt:.1f}" '
                     f'rx="2" fill="{c}"><title>{nome}: {num(v)}</title></rect>')
        p.append(f'<text x="{i * passo + passo / 2:.1f}" y="{h + 16}" font-size="10" fill="#5a5f68" '
                 f'text-anchor="middle">{esc(k)}</text>')
    p.append("</svg>")
    return "".join(p)


def barras_h(dados, cor="#1877f2"):
    """dados: lista de (rotulo, valor). Barras horizontais."""
    if not dados:
        return ""
    mx = max(v for _, v in dados) or 1
    alt = 26 * len(dados)
    p = [f'<svg viewBox="0 0 460 {alt}" width="100%" preserveAspectRatio="xMidYMid meet">']
    for i, (k, v) in enumerate(dados):
        y = i * 26
        w = v / mx * 250
        p.append(f'<text x="0" y="{y + 16}" font-size="11" fill="#3a3f48">{esc(k)}</text>'
                 f'<rect x="140" y="{y + 5}" width="{w:.1f}" height="14" rx="3" fill="{cor}"/>'
                 f'<text x="{146 + w:.1f}" y="{y + 16}" font-size="10" fill="#5a5f68">{num(v)}</text>')
    p.append("</svg>")
    return "".join(p)


def linha_barra(dias, custos, cliques):
    """Barras de custo + linha de cliques, no mesmo gráfico."""
    if not dias:
        return ""
    largura, h = 744, 140
    n = len(dias)
    passo = largura / n
    mxc = max(custos) or 1
    mxk = max(cliques) or 1
    p = [f'<svg viewBox="0 0 {largura} {h + 22}" width="100%" preserveAspectRatio="xMidYMid meet">']
    for i, c in enumerate(custos):
        alt = c / mxc * h
        p.append(f'<rect x="{i * passo + passo * 0.2:.1f}" y="{h - alt:.1f}" width="{passo * 0.55:.1f}" '
                 f'height="{alt:.1f}" rx="2" fill="#ea4335" opacity="0.85"><title>dia {dias[i]}: {brl(c)}</title></rect>')
    pts = " ".join(f"{i * passo + passo / 2:.1f},{h - (k / mxk * h):.1f}" for i, k in enumerate(cliques))
    p.append(f'<polyline points="{pts}" fill="none" stroke="#4285f4" stroke-width="2.5"/>')
    for i, k in enumerate(cliques):
        p.append(f'<circle cx="{i * passo + passo / 2:.1f}" cy="{h - (k / mxk * h):.1f}" r="2.5" fill="#4285f4">'
                 f'<title>dia {dias[i]}: {num(k)} cliques</title></circle>')
    for i, d in enumerate(dias):
        if i % 2 == 0:
            p.append(f'<text x="{i * passo + passo / 2:.1f}" y="{h + 16}" font-size="9" fill="#8a8f98" '
                     f'text-anchor="middle">{d}</text>')
    p.append("</svg>")
    return "".join(p)


def tabela(colunas, linhas, min_width=920):
    th = "".join(f'<th{" class=\"r\"" if a else ""}>{esc(c)}</th>' for c, a in colunas)
    corpo = []
    for ln in linhas:
        tds = []
        for i, cel in enumerate(ln):
            cls = "r" if colunas[i][1] else ("nm" if i == 0 else "")
            tds.append(f'<td class="{cls}">{cel}</td>')
        corpo.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div class="tbl-wrap"><table class="ent" style="min-width:{min_width}px">'
            f"<thead><tr>{th}</tr></thead><tbody>{''.join(corpo)}</tbody></table></div>")


CSS = """*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#22262e;background:#e9ecf1;line-height:1.45}
.page{max-width:1000px;margin:22px auto;background:#fff;padding:44px 46px 60px;border-radius:12px;box-shadow:0 8px 34px rgba(20,30,60,.08)}
.head{border-bottom:4px solid #1f4e5f;padding-bottom:20px}
.brandrow{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.client{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:#1f4e5f;font-weight:700}
h1{margin:6px 0 3px;font-size:27px}.sub{color:#6b7280;font-size:14px}
.period{background:#1f4e5f;color:#fff;font-weight:600;font-size:13px;padding:9px 15px;border-radius:8px;white-space:nowrap;text-align:center}
.intro{color:#4b5563;font-size:13.5px;margin:16px 0 4px}
.platform{display:flex;align-items:center;gap:12px;margin:40px 0 6px;padding:14px 18px;border-radius:10px;color:#fff}
.platform.meta{background:linear-gradient(90deg,#1877f2,#0d5fc0)}.platform.google{background:linear-gradient(90deg,#4285f4,#34a853)}
.platform.geral{background:linear-gradient(90deg,#1f4e5f,#2a6577)}.platform.organico{background:linear-gradient(90deg,#d6336c,#f06595)}
.platform h2{margin:0;font-size:20px}.platform .pill{margin-left:auto;font-size:12px;background:rgba(255,255,255,.2);padding:5px 11px;border-radius:20px}
h2.section{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#9099a6;margin:30px 0 14px;border-bottom:1px solid #eceef2;padding-bottom:7px}
h3.sub2{font-size:14px;margin:24px 0 10px;color:#2a2f38}
.kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}
.kpi{border:1px solid #e6e8ee;border-radius:11px;padding:14px 16px;background:#fbfcfd}
.kpi-label{font-size:11.5px;color:#6b7280;min-height:30px;line-height:1.3}
.kpi-main{display:flex;align-items:baseline;gap:8px;margin-top:4px}.kpi-value{font-size:22px;font-weight:700}
.kpi-delta{font-size:12.5px;font-weight:600}.kpi-prev{font-size:11px;color:#9099a6;margin-top:3px}
.funil{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.funil-item{background:linear-gradient(135deg,#1f4e5f,#2a6577);color:#fff;border-radius:10px;padding:15px 16px}
.funil-num{font-size:20px;font-weight:700}.funil-lab{font-size:11px;opacity:.9;margin-top:2px}
.charts2{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.chart-card{border:1px solid #eceef2;border-radius:10px;padding:15px 17px}
.chart-title{font-size:12.5px;font-weight:600;color:#3a3f48;margin-bottom:12px}
.tbl-wrap{overflow-x:auto}table.ent{width:100%;border-collapse:collapse;font-size:12px}
table.ent th{padding:9px 7px;border-bottom:2px solid #e6e8ee;color:#9099a6;font-size:10px;text-transform:uppercase;text-align:left}
table.ent td{padding:9px 7px;border-bottom:1px solid #eceef2;font-variant-numeric:tabular-nums}
table.ent tbody tr:nth-child(even){background:#fafbfc}td.nm{font-weight:600;max-width:260px}.r{text-align:right !important}
tr.alerta td{background:#fff6f5 !important}tr.bom td{background:#f3fbf6 !important}
.ad-preview{border:1px solid #e6e8ee;border-radius:10px;padding:15px 18px;max-width:560px;background:#fff}
.ad-badge{display:inline-block;font-size:10px;font-weight:700;border:1px solid #3a3f48;border-radius:4px;padding:1px 5px;margin-bottom:6px}
.ad-head{color:#1a0dab;font-size:17px;font-weight:600;line-height:1.3}.ad-url{color:#006621;font-size:12.5px;margin:2px 0 6px}.ad-desc{color:#4d5156;font-size:13px}
.mini-title{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#9099a6;margin-bottom:6px}
.assets{display:flex;flex-wrap:wrap;gap:6px}.asset{background:#eef4ff;color:#1a56c4;font-size:11.5px;padding:4px 9px;border-radius:6px}
.desc-list{margin:0;padding-left:18px;font-size:12.5px;color:#4b5563}.desc-list li{margin:3px 0}
.terms{display:flex;flex-wrap:wrap;gap:7px}.term{background:#f1f5f9;color:#37414d;font-size:12px;padding:5px 11px;border-radius:20px;border:1px solid #e6e8ee}
.resumo{background:#f7f9fb;border-left:4px solid #1f4e5f;border-radius:8px;padding:20px 24px;font-size:13.5px;color:#37414d;line-height:1.6}
.destaque{border-left:4px solid #c0392b;background:#fff6f5;border-radius:8px;padding:14px 18px;font-size:13px;color:#37414d;margin:14px 0}
.destaque.ok{border-left-color:#1a8a4a;background:#f3fbf6}
.destaque b{color:#22262e}
.acoes{counter-reset:a;padding:0;margin:12px 0 0;list-style:none}
.acoes li{position:relative;padding:12px 16px 12px 46px;border:1px solid #e6e8ee;border-radius:9px;margin-bottom:9px;font-size:13px;background:#fff}
.acoes li::before{counter-increment:a;content:counter(a);position:absolute;left:14px;top:12px;width:20px;height:20px;border-radius:50%;background:#1f4e5f;color:#fff;font-size:11px;font-weight:700;display:grid;place-items:center}
footer{margin-top:40px;padding-top:16px;border-top:1px solid #eceef2;color:#9099a6;font-size:12px;display:flex;justify-content:space-between}
@media print{body{background:#fff}.page{box-shadow:none;margin:0;max-width:none;border-radius:0;padding:0}.chart-card,.kpi,.funil-item,tr,.platform,.ad-preview,.acoes li{page-break-inside:avoid}}
@media(max-width:760px){.kpi-grid{grid-template-columns:1fr 1fr}.funil{grid-template-columns:1fr 1fr}.charts2{grid-template-columns:1fr}}"""


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=None, help="AAAA-MM (padrão: mês passado)")
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(raiz)
    cfg = json.load(open("public/config.json", encoding="utf-8"))

    hoje = dt.date.today()
    if args.mes:
        ano, mes = int(args.mes[:4]), int(args.mes[5:7])
    else:
        primeiro = hoje.replace(day=1)
        ult = primeiro - dt.timedelta(days=1)
        ano, mes = ult.year, ult.month
    ini = dt.date(ano, mes, 1)
    fim = dt.date(ano, mes, calendar.monthrange(ano, mes)[1])
    pfim = ini - dt.timedelta(days=1)
    pini = dt.date(pfim.year, pfim.month, 1)
    rot = f"{MESES[mes - 1]}/{ano}"
    rot_ant = f"{MESES[pfim.month - 1]}/{pfim.year}"
    d = lambda x: x.strftime("%d/%m/%Y")

    print(f"Relatório de {rot} (comparando com {rot_ant})")

    # ---------------------------------------------------------------- Meta
    tok = (carregar_env(".env.meta").get("META_ACCESS_TOKEN")
           or os.environ.get("META_ACCESS_TOKEN", ""))
    if not tok:
        print("ERRO: META_ACCESS_TOKEN não encontrado (.env.meta)")
        return 2
    meta = Meta(tok, cfg["meta"]["ad_account_id"])
    print("  Meta: totais do mês")
    mes_tot = m_totais(meta.insights(str(ini), str(fim), level="account"))
    ant_tot = m_totais(meta.insights(str(pini), str(pfim), level="account"))
    # alcance deduplicado (não é a soma dos dias)
    mes_tot["reach"] = int((meta.insights(str(ini), str(fim), level="account") or [{}])[0].get("reach", 0) or 0)
    ant_tot["reach"] = int((meta.insights(str(pini), str(pfim), level="account") or [{}])[0].get("reach", 0) or 0)

    print("  Meta: campanhas, conjuntos e anúncios")
    nomes_camp = {c["id"]: c["name"] for c in meta.nomes("campaigns", "id,name")}
    nomes_set = {s["id"]: s["name"] for s in meta.nomes("adsets", "id,name")}
    nomes_ad = {a["id"]: a["name"] for a in meta.nomes("ads", "id,name")}

    def por(nivel, chave, nomes):
        linhas = meta.insights(str(ini), str(fim), level=nivel,
                               fields=f"{chave},spend,impressions,reach,clicks,inline_link_clicks,actions")
        agrup = {}
        for r in linhas:
            k = r.get(chave)
            agrup.setdefault(k, []).append(r)
        itens = [(nomes.get(k, k), m_totais(v)) for k, v in agrup.items()]
        return sorted(itens, key=lambda x: -x[1]["spend"])

    camps = por("campaign", "campaign_id", nomes_camp)
    conjuntos = por("adset", "adset_id", nomes_set)
    anuncios = por("ad", "ad_id", nomes_ad)

    print("  Meta: recortes (hora, idade, gênero, posicionamento)")
    def bd(breakdowns, nivel="account"):
        try:
            return meta.insights(str(ini), str(fim), level=nivel, breakdowns=breakdowns)
        except Exception as e:
            print(f"    aviso: recorte {breakdowns} indisponível ({str(e)[:70]})")
            return []

    hora = bd("hourly_stats_aggregated_by_advertiser_time_zone")
    idade_gen = bd("age,gender")
    posic = bd("publisher_platform,platform_position")

    print("  Meta: série diária")
    diario = meta.insights(str(ini), str(fim), level="account", time_increment=1)

    # ------------------------------------------------------------- Google
    print("  Google: conectando")
    gcfg = cfg.get("google_ads", {})
    g_ok, g = False, None
    try:
        fg, g = google_client()
        g_ok = True
    except Exception as e:
        print(f"    aviso: Google indisponível ({str(e)[:90]})")

    gm = gant = {}
    g_camps = g_rede = g_disp = g_kw = g_termos = g_conv = []
    g_dia = []
    g_anuncio = None
    if g_ok:
        R = f"segments.date BETWEEN '{ini}' AND '{fim}'"
        RA = f"segments.date BETWEEN '{pini}' AND '{pfim}'"
        MET = "metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions, metrics.all_conversions"
        print("  Google: totais, campanhas e recortes")
        gm = g_soma(g.search(f"SELECT campaign.id, {MET} FROM campaign WHERE {R}"))
        gant = g_soma(g.search(f"SELECT campaign.id, {MET} FROM campaign WHERE {RA}"))
        nome_c = {str(r["campaign"]["id"]): r["campaign"]["name"]
                  for r in g.search("SELECT campaign.id, campaign.name FROM campaign")}
        acc = {}
        for r in g.search(f"SELECT campaign.id, {MET} FROM campaign WHERE {R}"):
            acc.setdefault(str(r["campaign"]["id"]), []).append(r)
        g_camps = sorted(((nome_c.get(k, k), g_soma(v)) for k, v in acc.items()), key=lambda x: -x[1]["cost"])
        # campanhas pausadas sem entrega no mês só poluem a tabela
        g_camps = [(k, v) for k, v in g_camps if v["cost"] > 0 or v["impressions"] > 0]
        red = {}
        for r in g.search(f"SELECT segments.ad_network_type, {MET} FROM campaign WHERE {R}"):
            red.setdefault(r["segments"]["adNetworkType"], []).append(r)
        g_rede = sorted(((k, g_soma(v)) for k, v in red.items()), key=lambda x: -x[1]["cost"])
        dis = {}
        for r in g.search(f"SELECT segments.device, {MET} FROM campaign WHERE {R}"):
            dis.setdefault(r["segments"]["device"], []).append(r)
        g_disp = sorted(((k, g_soma(v)) for k, v in dis.items()), key=lambda x: -x[1]["cost"])
        g_kw = [(r["adGroupCriterion"]["keyword"], g_m(r)) for r in g.search(
            f"SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, {MET} "
            f"FROM keyword_view WHERE {R} AND metrics.impressions > 0 ORDER BY metrics.cost_micros DESC LIMIT 12")]
        g_termos = [(r["searchTermView"]["searchTerm"], g_m(r)) for r in g.search(
            f"SELECT search_term_view.search_term, {MET} FROM search_term_view WHERE {R} "
            f"ORDER BY metrics.clicks DESC LIMIT 16")]
        cv = {}
        for r in g.search(f"SELECT segments.conversion_action_name, segments.conversion_action_category, "
                          f"metrics.conversions, metrics.all_conversions FROM campaign WHERE {R} "
                          f"AND metrics.all_conversions > 0"):
            s = r["segments"]
            k = (s.get("conversionActionName"), s.get("conversionActionCategory"))
            m = r.get("metrics", {})
            a = cv.setdefault(k, [0.0, 0.0])
            a[0] += float(m.get("conversions", 0) or 0)
            a[1] += float(m.get("allConversions", 0) or 0)
        g_conv = sorted(cv.items(), key=lambda x: -x[1][1])
        dd = {}
        for r in g.search(f"SELECT segments.date, {MET} FROM campaign WHERE {R}"):
            dd.setdefault(r["segments"]["date"], []).append(r)
        g_dia = [(k, g_soma(v)) for k, v in sorted(dd.items())]
        try:
            an = g.search(f"SELECT ad_group_ad.ad.responsive_search_ad.headlines, "
                          f"ad_group_ad.ad.responsive_search_ad.descriptions, ad_group_ad.ad.final_urls, {MET} "
                          f"FROM ad_group_ad WHERE {R} AND metrics.impressions > 0 "
                          f"ORDER BY metrics.impressions DESC LIMIT 5")
            for r in an:
                rsa = (r["adGroupAd"]["ad"].get("responsiveSearchAd") or {})
                if rsa.get("headlines"):
                    g_anuncio = {
                        "titulos": [h["text"] for h in rsa.get("headlines", []) if h.get("text")],
                        "descricoes": [x["text"] for x in rsa.get("descriptions", []) if x.get("text")],
                        "url": (r["adGroupAd"]["ad"].get("finalUrls") or [""])[0],
                        **g_m(r),
                    }
                    break
        except Exception as e:
            print(f"    aviso: criativo de pesquisa indisponível ({str(e)[:60]})")
        # parcela de impressões (últimos 30 dias, é o que a API expõe de forma estável)
        try:
            isr = {}
            for r in g.search("SELECT campaign.id, metrics.search_impression_share, "
                              "metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share "
                              "FROM campaign WHERE segments.date DURING LAST_30_DAYS"):
                m = r.get("metrics", {})
                if m.get("searchImpressionShare") is not None:
                    isr[nome_c.get(str(r["campaign"]["id"]))] = (
                        float(m.get("searchImpressionShare", 0)) * 100,
                        float(m.get("searchBudgetLostImpressionShare", 0)) * 100,
                        float(m.get("searchRankLostImpressionShare", 0)) * 100)
            g_is = isr
        except Exception:
            g_is = {}
    else:
        g_is = {}

    # ------------------------------------------------------------ orgânico
    org = {}
    if os.path.exists("public/data/organic.json"):
        org = json.load(open("public/data/organic.json", encoding="utf-8"))

    def serie_mes(serie):
        return [p for p in (serie or []) if str(ini) <= p["date"] <= str(fim)]

    ig = org.get("instagram") or {}
    fb = org.get("facebook") or {}
    ig_alcance = sum(p["value"] for p in serie_mes((ig.get("daily") or {}).get("reach")))
    ig_seg = sum(p["value"] for p in serie_mes((ig.get("daily") or {}).get("follower_count")))
    ig_visitas = sum(p["value"] for p in serie_mes((ig.get("daily") or {}).get("profile_views")))
    ig_eng = sum(p["value"] for p in serie_mes((ig.get("daily") or {}).get("accounts_engaged")))
    fb_eng = sum(p["value"] for p in serie_mes((fb.get("daily") or {}).get("page_post_engagements")))
    fb_seg = sum(p["value"] for p in serie_mes((fb.get("daily") or {}).get("page_daily_follows_total")))
    fb_vis = sum(p["value"] for p in serie_mes((fb.get("daily") or {}).get("page_views_total")))
    posts_mes = [p for p in (ig.get("media") or []) if str(ini) <= (p.get("timestamp") or "")[:10] <= str(fim)]
    for p in posts_mes:
        i = p.get("insights") or {}
        p["_alc"] = i.get("reach", 0)
        p["_int"] = (p.get("likes", 0) or 0) + (p.get("comments", 0) or 0) + i.get("saved", 0) + i.get("shares", 0)
    posts_mes.sort(key=lambda p: -p["_alc"])

    # -------------------------------------------------------------- montar
    cli = cfg["client"]
    total_inv = mes_tot["spend"] + (gm.get("cost", 0) if g_ok else 0)
    total_inv_ant = ant_tot["spend"] + (gant.get("cost", 0) if g_ok else 0)
    total_res = mes_tot["purchase"] + (gm.get("conversions", 0) if g_ok else 0)
    total_res_ant = ant_tot["purchase"] + (gant.get("conversions", 0) if g_ok else 0)

    P = []
    P.append(f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Relatório {esc(rot)} — {esc(cli['name'])}</title>
<style>{CSS}</style></head><body><div class="page">
<div class="head"><div class="brandrow">
<div><div class="client">{esc(cli['name'])}</div><h1>Relatório Mensal — {esc(rot)}</h1>
<div class="sub">{esc(cli.get('segment', ''))} · Meta Ads + Google Ads + orgânico</div></div>
<div class="period">{d(ini)} a {d(fim)}<br><span style="font-weight:400;opacity:.85">vs {d(pini)} a {d(pfim)}</span></div></div>
<div class="intro">Relatório gerado dos dados analisados entre <b>{d(ini)} e {d(fim)}</b>, comparado com
<b>{d(pini)} e {d(pfim)}</b>. Fontes: Meta Marketing API, Google Ads API e Graph API (orgânico).</div></div>""")

    # ---- visão consolidada
    P.append('<div class="platform geral"><h2>Visão consolidada</h2>'
             f'<span class="pill">{esc(cli["name"])} · as duas plataformas</span></div>')
    P.append('<h2 class="section">Investimento e retorno somados</h2><div class="kpi-grid">')
    P.append(kpi("Investimento total", total_inv, total_inv_ant, inverso=False, fmt=brl, casas=2))
    P.append(kpi("Reservas totais (Meta + Google)", total_res, total_res_ant, casas=0))
    P.append(kpi("Custo médio por reserva", div(total_inv, total_res), div(total_inv_ant, total_res_ant),
                 inverso=True, fmt=brl, casas=2))
    P.append(kpi("Investimento Meta Ads", mes_tot["spend"], ant_tot["spend"], fmt=brl, casas=2))
    if g_ok:
        P.append(kpi("Investimento Google Ads", gm["cost"], gant["cost"], fmt=brl, casas=2))
        P.append(kpi("Participação do Google no total", div(gm["cost"] * 100, total_inv),
                     div(gant["cost"] * 100, total_inv_ant), fmt=pct, casas=1))
    P.append("</div>")
    if g_ok and total_res:
        mcusto = mes_tot["custo_compra"]
        gcusto = gm["custo_conv"]
        if mcusto and gcusto:
            melhor = "Google Ads" if gcusto < mcusto else "Meta Ads"
            P.append(f'<div class="destaque"><b>Comparativo direto:</b> o {melhor} entregou reserva mais barata no mês — '
                     f'Meta a {brl(mcusto)} contra Google a {brl(gcusto)} por reserva.</div>')
        elif gcusto and not mes_tot["purchase"]:
            P.append(f'<div class="destaque"><b>Comparativo direto:</b> todas as {num(gm["conversions"], 0)} reservas do mês '
                     f'vieram do Google Ads, a {brl(gcusto)} cada. O Meta Ads investiu {brl(mes_tot["spend"])} '
                     f'sem registrar compra no período.</div>')

    # ---- Meta
    P.append(f'<div class="platform meta"><h2>Meta Ads</h2><span class="pill">{esc(cli["name"])} · mês completo</span></div>')
    P.append('<h2 class="section">Visão geral (mês atual vs. anterior)</h2><div class="kpi-grid">')
    P.append(kpi("Valor investido", mes_tot["spend"], ant_tot["spend"], fmt=brl, casas=2))
    P.append(kpi("Compras", mes_tot["purchase"], ant_tot["purchase"]))
    P.append(kpi("Custo por compra", mes_tot["custo_compra"], ant_tot["custo_compra"], inverso=True, fmt=brl, casas=2))
    P.append(kpi("Adições ao carrinho", mes_tot["atc"], ant_tot["atc"]))
    P.append(kpi("Custo por adição", mes_tot["custo_atc"], ant_tot["custo_atc"], inverso=True, fmt=brl, casas=2))
    P.append(kpi("Checkouts iniciados", mes_tot["ic"], ant_tot["ic"]))
    P.append(kpi("Impressões", mes_tot["impressions"], ant_tot["impressions"]))
    P.append(kpi("Alcance", mes_tot["reach"], ant_tot["reach"]))
    P.append(kpi("Cliques no link", mes_tot["link"], ant_tot["link"]))
    P.append(kpi("CPC (link)", mes_tot["cpc_link"], ant_tot["cpc_link"], inverso=True, fmt=brl, casas=2))
    P.append(kpi("CPM médio", mes_tot["cpm"], ant_tot["cpm"], inverso=True, fmt=brl, casas=2))
    P.append(kpi("CTR (link)", mes_tot["ctr_link"], ant_tot["ctr_link"], fmt=pct, casas=2))
    P.append("</div>")

    P.append('<h2 class="section">Funil</h2><div class="funil">')
    for v, lab in ((mes_tot["impressions"], "Impressões"), (mes_tot["reach"], "Alcance"),
                   (mes_tot["link"], "Cliques no link"), (mes_tot["atc"], "Adições ao carrinho"),
                   (mes_tot["purchase"], "Compras")):
        P.append(f'<div class="funil-item"><div class="funil-num">{num(v)}</div><div class="funil-lab">{lab}</div></div>')
    P.append("</div><div style='height:22px'></div>")

    if hora:
        dados = sorted(((r["hourly_stats_aggregated_by_advertiser_time_zone"][:2],
                         int(r.get("impressions", 0) or 0)) for r in hora), key=lambda x: x[0])
        dados = [(str(int(k)), v) for k, v in dados]
        P.append('<div class="charts2"><div class="chart-card"><div class="chart-title">Impressões por hora do dia</div>'
                 + barras_v(dados) + "</div>")
    else:
        P.append('<div class="charts2"><div class="chart-card"><div class="chart-title">Impressões por hora</div>'
                 '<div style="color:#9099a6;font-size:12px">Recorte indisponível no período.</div></div>')

    if idade_gen:
        faixas = {}
        for r in idade_gen:
            k = r.get("age")
            a = faixas.setdefault(k, [0, 0])
            a[0] += int(r.get("impressions", 0) or 0)
            a[1] += int(r.get("reach", 0) or 0)
        ordem = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
        dd = [(k, faixas[k][0], faixas[k][1]) for k in ordem if k in faixas]
        P.append('<div class="chart-card"><div class="chart-title">Impressões e alcance por idade</div>'
                 + barras_duplas(dd) + "</div></div>")
    else:
        P.append("</div>")

    P.append("<div style='height:20px'></div><div class='charts2'>")
    if idade_gen:
        gen = {}
        for r in idade_gen:
            k = {"female": "Feminino", "male": "Masculino"}.get(r.get("gender"), "Não especificado")
            gen[k] = gen.get(k, 0) + int(r.get("impressions", 0) or 0)
        P.append('<div class="chart-card"><div class="chart-title">Impressões por gênero</div>'
                 + barras_h(sorted(gen.items(), key=lambda x: -x[1])) + "</div>")
    P.append('<div class="chart-card" style="display:flex;flex-direction:column;justify-content:center">'
             f'<div class="chart-title">Resumo Meta — {esc(MESES[mes - 1])}</div>'
             '<div style="font-size:12.5px;color:#4b5563;line-height:1.8">'
             f'Investimento: <b>{brl(mes_tot["spend"])}</b><br>'
             f'Compras: <b>{num(mes_tot["purchase"])}</b> · custo/compra <b>{brl(mes_tot["custo_compra"])}</b><br>'
             f'Adições: <b>{num(mes_tot["atc"])}</b> · custo <b>{brl(mes_tot["custo_atc"])}</b><br>'
             f'Alcance: <b>{num(mes_tot["reach"])}</b> · CTR <b>{pct(mes_tot["ctr_link"])}</b> · '
             f'CPC <b>{brl(mes_tot["cpc_link"])}</b></div></div></div>')

    if posic:
        pl = {}
        for r in posic:
            k = f'{r.get("publisher_platform", "?")} · {str(r.get("platform_position", "")).replace("_", " ")}'
            a = pl.setdefault(k, {"spend": 0.0, "imp": 0, "link": 0, "atc": 0.0})
            ac = acoes(r)
            a["spend"] += float(r.get("spend", 0))
            a["imp"] += int(r.get("impressions", 0) or 0)
            a["link"] += int(r.get("inline_link_clicks", 0) or 0)
            a["atc"] += ac.get("add_to_cart", 0)
        top = sorted(pl.items(), key=lambda x: -x[1]["spend"])[:9]
        P.append('<h3 class="sub2">Onde os anúncios apareceram (posicionamento)</h3>')
        P.append(tabela([("Posicionamento", False), ("Investido", True), ("Impressões", True),
                         ("Cliques link", True), ("CTR link", True), ("CPC link", True), ("Carrinhos", True)],
                        [[esc(k), brl(v["spend"]), num(v["imp"]), num(v["link"]),
                          pct(div(v["link"] * 100, v["imp"])), brl(div(v["spend"], v["link"])), num(v["atc"])]
                         for k, v in top], 760))

    def linhas_meta(itens, limite=6):
        out = []
        for nome, t in itens[:limite]:
            cls = ' class="bom"' if t["purchase"] else (' class="alerta"' if t["spend"] > 100 and not t["atc"] else "")
            out.append((cls, [esc(nome), num(t["purchase"]), num(t["atc"]), num(t["impressions"]), num(t["reach"]),
                              num(t["link"]), brl(t["cpc_link"]), brl(t["cpm"]), pct(t["ctr_link"]), brl(t["spend"])]))
        return out

    COLS_M = [("Nome", False), ("Compras", True), ("Adições", True), ("Impressões", True), ("Alcance", True),
              ("Cliques link", True), ("CPC", True), ("CPM", True), ("CTR link", True), ("Investido", True)]
    for titulo, itens in (("Campanhas em destaque", camps), ("Conjuntos de anúncios em destaque", conjuntos),
                          ("Anúncios em destaque", anuncios)):
        P.append(f'<h3 class="sub2">{titulo}</h3>')
        th = "".join(f'<th{" class=\"r\"" if a else ""}>{esc(c)}</th>' for c, a in COLS_M)
        corpo = "".join("<tr" + cls + ">" + "".join(
            f'<td class="{"r" if COLS_M[i][1] else ("nm" if i == 0 else "")}">{cel}</td>'
            for i, cel in enumerate(cells)) + "</tr>" for cls, cells in linhas_meta(itens))
        P.append(f'<div class="tbl-wrap"><table class="ent" style="min-width:920px"><thead><tr>{th}</tr></thead>'
                 f"<tbody>{corpo}</tbody></table></div>")

    # ---- Google
    if g_ok:
        P.append(f'<div class="platform google"><h2>Google Ads</h2>'
                 f'<span class="pill">{esc(cli["name"])} · mês completo</span></div>')
        P.append('<h2 class="section">Visão geral (mês atual vs. anterior)</h2><div class="kpi-grid">')
        P.append(kpi("Custo", gm["cost"], gant["cost"], fmt=brl, casas=2))
        P.append(kpi("Compras (reservas)", gm["conversions"], gant["conversions"], casas=0))
        P.append(kpi("Custo por reserva", gm["custo_conv"], gant["custo_conv"], inverso=True, fmt=brl, casas=2))
        P.append(kpi("Impressões", gm["impressions"], gant["impressions"]))
        P.append(kpi("Cliques", gm["clicks"], gant["clicks"]))
        P.append(kpi("CPC médio", gm["cpc"], gant["cpc"], inverso=True, fmt=brl, casas=2))
        P.append(kpi("CPM médio", gm["cpm"], gant["cpm"], inverso=True, fmt=brl, casas=2))
        P.append(kpi("CTR", gm["ctr"], gant["ctr"], fmt=pct, casas=2))
        P.append(kpi("Taxa de conversão", gm["tx_conv"], gant["tx_conv"], fmt=pct, casas=2))
        P.append("</div><div style='height:22px'></div>")

        if g_dia:
            dias = [k[8:10].lstrip("0") for k, _ in g_dia]
            P.append('<div class="charts2"><div class="chart-card">'
                     f'<div class="chart-title">Custo e cliques por dia — {esc(MESES[mes - 1])}</div>'
                     '<div style="font-size:11px;color:#5a5f68;margin-bottom:6px">'
                     '<span style="color:#ea4335">■</span> Custo (R$) &nbsp; '
                     '<span style="color:#4285f4">▬</span> Cliques</div>'
                     + linha_barra(dias, [v["cost"] for _, v in g_dia], [v["clicks"] for _, v in g_dia]) + "</div>")
            P.append('<div class="chart-card">'
                     f'<div class="chart-title">Conversões por dia — {esc(MESES[mes - 1])}</div>'
                     + barras_v([(k[8:10].lstrip("0"), v["conversions"]) for k, v in g_dia], "#34a853", 744, 142)
                     + "</div></div>")

        if g_rede:
            P.append('<h3 class="sub2">Desempenho por rede</h3>')
            nomes_rede = {"SEARCH": "Pesquisa do Google", "SEARCH_PARTNERS": "Parceiros de pesquisa",
                          "CONTENT": "Rede de Display", "YOUTUBE": "YouTube", "DISCOVER": "Discover",
                          "MAPS": "Google Maps", "MIXED": "Várias redes"}
            tot_rede = sum(v["cost"] for _, v in g_rede) or 1
            lin = []
            for k, v in g_rede:
                cls = ' class="alerta"' if v["cost"] > 20 and not v["conversions"] else (
                    ' class="bom"' if v["conversions"] else "")
                lin.append((cls, [esc(nomes_rede.get(k, k)), num(v["clicks"]), num(v["impressions"]),
                                  pct(div(v["cost"] * 100, tot_rede), 1), brl(v["cost"]),
                                  brl(v["cpc"]), num(v["conversions"], 1)]))
            cols = [("Rede", False), ("Cliques", True), ("Impressões", True), ("% do custo", True),
                    ("Custo", True), ("CPC", True), ("Reservas", True)]
            th = "".join(f'<th{" class=\"r\"" if a else ""}>{esc(c)}</th>' for c, a in cols)
            corpo = "".join("<tr" + cls + ">" + "".join(
                f'<td class="{"r" if cols[i][1] else ("nm" if i == 0 else "")}">{cel}</td>'
                for i, cel in enumerate(cells)) + "</tr>" for cls, cells in lin)
            P.append(f'<div class="tbl-wrap"><table class="ent" style="min-width:700px"><thead><tr>{th}</tr></thead>'
                     f"<tbody>{corpo}</tbody></table></div>")
            desperdicio = sum(v["cost"] for k, v in g_rede if not v["conversions"])
            cliques_sem = sum(v["clicks"] for k, v in g_rede if not v["conversions"])
            if desperdicio > 0 and gm["cost"]:
                P.append(f'<div class="destaque"><b>{brl(desperdicio)}</b> '
                         f'({pct(div(desperdicio * 100, gm["cost"]), 1)} do investimento) foram para redes que não '
                         f'geraram nenhuma reserva no mês, consumindo <b>{num(cliques_sem)} cliques</b> '
                         f'({pct(div(cliques_sem * 100, gm["clicks"]), 1)} do total). '
                         f'Esses cliques derrubam a taxa de conversão média sem trazer receita.</div>')

        if g_disp:
            P.append('<h3 class="sub2">Desempenho por dispositivo</h3>')
            nomes_d = {"MOBILE": "Smartphones", "DESKTOP": "Computadores", "TABLET": "Tablets",
                       "CONNECTED_TV": "TV conectada", "OTHER": "Outros"}
            tot_d = sum(v["cost"] for _, v in g_disp) or 1
            P.append(tabela([("Dispositivo", False), ("Cliques", True), ("Impressões", True), ("% do custo", True),
                             ("Custo", True), ("CPC", True), ("Reservas", True)],
                            [[esc(nomes_d.get(k, k)), num(v["clicks"]), num(v["impressions"]),
                              pct(div(v["cost"] * 100, tot_d), 1), brl(v["cost"]), brl(v["cpc"]),
                              num(v["conversions"], 1)] for k, v in g_disp], 700))

        if g_camps:
            P.append('<h3 class="sub2">Todas as campanhas</h3>')
            P.append(tabela([("Campanha", False), ("Reservas", True), ("Custo/reserva", True), ("Impressões", True),
                             ("Cliques", True), ("CPC", True), ("CTR", True), ("Custo", True)],
                            [[esc(k), num(v["conversions"], 1), brl(v["custo_conv"]), num(v["impressions"]),
                              num(v["clicks"]), brl(v["cpc"]), pct(v["ctr"]), brl(v["cost"])]
                             for k, v in g_camps], 736))

        if g_is:
            P.append('<h3 class="sub2">Parcela de impressões — quanto do mercado estamos capturando</h3>')
            P.append(tabela([("Campanha", False), ("Parcela obtida", True), ("Perdida por orçamento", True),
                             ("Perdida por classificação", True)],
                            [[esc(k), pct(v[0], 1), pct(v[1], 1), pct(v[2], 1)] for k, v in g_is.items()], 620))
            pior = max(g_is.items(), key=lambda x: x[1][2]) if g_is else None
            if pior and pior[1][2] > 50:
                P.append(f'<div class="destaque"><b>{esc(pior[0])}</b> deixa de aparecer em '
                         f'<b>{pct(pior[1][2], 1)}</b> das buscas por classificação do anúncio, e só '
                         f'{pct(pior[1][1], 1)} por falta de orçamento. Ou seja: aumentar a verba isolada resolve pouco. '
                         f'O caminho é lance, qualidade do anúncio e relevância da página de destino.</div>')

        if g_kw:
            P.append('<h3 class="sub2">Top palavras-chave</h3>')
            lin = []
            for k, v in g_kw:
                cls = ' class="bom"' if v["conversions"] else (' class="alerta"' if v["cost"] > 20 else "")
                lin.append((cls, [esc(k.get("text", "")), esc(str(k.get("matchType", "")).lower()),
                                  num(v["clicks"]), num(v["impressions"]), brl(div(v["cost"], v["clicks"])),
                                  num(v["conversions"], 1), brl(v["cost"])]))
            cols = [("Palavra-chave", False), ("Correspondência", False), ("Cliques", True), ("Impressões", True),
                    ("CPC", True), ("Reservas", True), ("Custo", True)]
            th = "".join(f'<th{" class=\"r\"" if a else ""}>{esc(c)}</th>' for c, a in cols)
            corpo = "".join("<tr" + cls + ">" + "".join(
                f'<td class="{"r" if cols[i][1] else ("nm" if i == 0 else "")}">{cel}</td>'
                for i, cel in enumerate(cells)) + "</tr>" for cls, cells in lin)
            P.append(f'<div class="tbl-wrap"><table class="ent" style="min-width:720px"><thead><tr>{th}</tr></thead>'
                     f"<tbody>{corpo}</tbody></table></div>")

        if g_termos:
            P.append('<h3 class="sub2">Principais termos de pesquisa</h3><div class="terms">')
            for t, v in g_termos:
                cor = ' style="background:#f3fbf6;border-color:#bfe7cf"' if v["conversions"] else ""
                P.append(f'<span class="term"{cor}>{esc(t)}</span>')
            P.append("</div>")

        if g_conv:
            P.append('<h3 class="sub2">Ações de conversão registradas</h3>')
            cat = {"PURCHASE": "Compra", "CONTACT": "Contato", "PAGE_VIEW": "Visualização de página",
                   "ENGAGEMENT": "Engajamento", "SUBMIT_LEAD_FORM": "Formulário", "UNKNOWN": "Não classificada"}
            P.append(tabela([("Ação de conversão", False), ("Categoria", False), ("Conversões principais", True),
                             ("Todas as conversões", True)],
                            [[esc(k[0]), esc(cat.get(k[1], k[1])), num(v[0], 1), num(v[1], 1)]
                             for k, v in g_conv], 680))
            P.append('<div style="font-size:12px;color:#6b7280;margin-top:8px">Só a ação marcada como '
                     '<b>conversão principal</b> entra no custo por reserva. As demais são registradas para '
                     'acompanhamento e não representam venda.</div>')

        if g_anuncio:
            P.append('<h3 class="sub2">Criativo do anúncio de pesquisa</h3><div class="ad-preview">'
                     '<div class="ad-badge">Anúncio</div>'
                     f'<div class="ad-head">{esc(" | ".join(g_anuncio["titulos"][:3]))}</div>'
                     f'<div class="ad-url">{esc(g_anuncio["url"].replace("https://", "").replace("http://", ""))}</div>'
                     f'<div class="ad-desc">{esc((g_anuncio["descricoes"] or [""])[0])}</div></div>')
            P.append('<div style="margin-top:14px"><div class="mini-title">Títulos utilizados</div><div class="assets">'
                     + "".join(f'<span class="asset">{esc(t)}</span>' for t in g_anuncio["titulos"]) + "</div></div>")
            if g_anuncio["descricoes"]:
                P.append('<div style="margin-top:12px"><div class="mini-title">Descrições</div><ul class="desc-list">'
                         + "".join(f"<li>{esc(x)}</li>" for x in g_anuncio["descricoes"]) + "</ul></div>")

    # ---- orgânico
    if ig or fb:
        P.append('<div class="platform organico"><h2>Orgânico — Instagram e Facebook</h2>'
                 '<span class="pill">sem investimento em mídia</span></div>')
        P.append('<h2 class="section">Perfil e alcance no mês</h2><div class="kpi-grid">')
        if ig:
            P.append(kpi("Seguidores no Instagram (total)", ig.get("followers"), None))
            P.append(kpi(f"Novos seguidores em {MESES[mes - 1]}", ig_seg, None))
            P.append(kpi("Alcance do Instagram (soma diária)", ig_alcance, None))
            P.append(kpi("Visitas ao perfil no mês", ig_visitas, None))
            P.append(kpi("Contas engajadas no mês", ig_eng, None))
            P.append(kpi("Publicações no mês", len(posts_mes), None))
        if fb:
            P.append(kpi("Seguidores no Facebook", fb.get("followers") or fb.get("fans"), None))
            P.append(kpi("Engajamentos no Facebook", fb_eng, None))
            P.append(kpi("Visitas à página do Facebook", fb_vis, None))
        P.append("</div>")
        P.append('<div style="font-size:12px;color:#6b7280;margin-top:10px">O alcance orgânico é a soma do '
                 'alcance de cada dia: quem viu o perfil em dias diferentes é contado mais de uma vez. '
                 'Serve para comparar meses, não como número de pessoas distintas.</div>')
        if posts_mes:
            P.append('<h3 class="sub2">Publicações com maior alcance no mês</h3>')
            P.append(tabela([("Publicação", False), ("Formato", False), ("Data", False), ("Alcance", True),
                             ("Curtidas", True), ("Comentários", True), ("Interações", True), ("Engajamento", True)],
                            [[esc((p.get("caption") or "(sem legenda)")[:70]),
                              esc(str(p.get("product_type") or p.get("media_type") or "").lower()),
                              esc((p.get("timestamp") or "")[8:10] + "/" + (p.get("timestamp") or "")[5:7]),
                              num(p["_alc"]), num(p.get("likes", 0)), num(p.get("comments", 0)), num(p["_int"]),
                              pct(div(p["_int"] * 100, p["_alc"]))] for p in posts_mes[:8]], 820))

    # ---- resumo
    P.append(f'<h2 class="section" style="margin-top:44px">Resumo de desempenho — {esc(rot)}</h2>')
    resumo = montar_resumo(rot, rot_ant, mes_tot, ant_tot, gm, gant, g_ok, g_rede, g_is, camps, anuncios,
                           total_inv, total_inv_ant, total_res, total_res_ant, ig, ig_alcance)
    P.append(f'<div class="resumo">{resumo}</div>')

    P.append(f'<footer><span>Relatório gerado via Meta Marketing API + Google Ads API + Graph API</span>'
             f'<span>{esc(cli["name"])} · {esc(rot)}</span></footer></div></body></html>')

    saida = args.saida or os.path.join(
        os.path.expanduser("~"), "Desktop", "relatórios",
        f"relatorio_{cfg['client']['name'].lower().replace(' ', '_')}_{MESES[mes - 1].lower()}_{ano}.html")
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    io.open(saida, "w", encoding="utf-8", newline="\n").write("".join(P))
    print(f"\nRelatório salvo em: {saida}")
    return 0


def montar_resumo(rot, rot_ant, m, ma, gm, gant, g_ok, g_rede, g_is, camps, anuncios,
                  inv, inv_ant, res, res_ant, ig, ig_alcance):
    """Texto do resumo, montado a partir dos números reais do mês."""
    t = []
    var_inv = ((inv - inv_ant) / inv_ant * 100) if inv_ant else 0
    direcao = "subiu" if var_inv > 1 else ("caiu" if var_inv < -1 else "ficou estável")
    t.append(f"No consolidado, o investimento {direcao} para <b>{brl(inv)}</b> "
             f"({'+' if var_inv >= 0 else ''}{num(var_inv, 2)}% vs. {rot_ant}) e o mês fechou com "
             f"<b>{num(res)} reserva{'s' if res != 1 else ''}</b>, a um custo médio de "
             f"<b>{brl(div(inv, res))}</b> cada.")

    if m["purchase"] == 0 and m["atc"] > 0:
        t.append(f"<br><br>No <b>Meta Ads</b>, o topo de funil melhorou mas a venda não aconteceu: "
                 f"o CTR subiu para {pct(m['ctr_link'])} e o CPC caiu para {brl(m['cpc_link'])}, "
                 f"com {num(m['atc'])} adições ao carrinho e {num(m['ic'])} checkouts iniciados — "
                 f"porém <b>nenhuma compra registrada</b> em {brl(m['spend'])} investidos. "
                 f"Quando o anúncio entrega interesse e o checkout não fecha, a causa costuma estar fora da mídia: "
                 f"disponibilidade, preço, formas de pagamento ou o próprio evento de compra do pixel parado.")
    elif m["purchase"]:
        t.append(f"<br><br>No <b>Meta Ads</b>, {brl(m['spend'])} investidos geraram {num(m['purchase'])} "
                 f"compra{'s' if m['purchase'] != 1 else ''} a {brl(m['custo_compra'])} cada, "
                 f"com CTR de {pct(m['ctr_link'])} e CPC de {brl(m['cpc_link'])}.")

    if g_ok:
        t.append(f"<br><br>No <b>Google Ads</b>, {brl(gm['cost'])} geraram {num(gm['conversions'], 1)} "
                 f"reservas a {brl(gm['custo_conv'])} cada")
        if gant.get("custo_conv") and gm.get("custo_conv"):
            v = (gm["custo_conv"] - gant["custo_conv"]) / gant["custo_conv"] * 100
            t.append(f", contra {brl(gant['custo_conv'])} em {rot_ant} "
                     f"({'+' if v >= 0 else ''}{num(v, 1)}%)")
        t.append(".")
        sem = [(k, v) for k, v in g_rede if not v["conversions"] and v["cost"] > 5]
        if sem:
            nomes = {"MAPS": "Google Maps", "YOUTUBE": "YouTube", "CONTENT": "Display", "DISCOVER": "Discover"}
            det = " · ".join(f"{nomes.get(k, k)} {brl(v['cost'])} em {num(v['clicks'])} cliques" for k, v in sem[:3])
            t.append(f" A entrega fora da pesquisa continua sendo o ponto fraco: {det}, tudo sem reserva.")
        if g_is:
            pior = max(g_is.items(), key=lambda x: x[1][2])
            if pior[1][2] > 50:
                t.append(f" A campanha <b>{esc(pior[0])}</b> captura apenas {pct(pior[1][0], 1)} das impressões "
                         f"disponíveis e perde {pct(pior[1][2], 1)} por classificação.")

    if ig and ig_alcance:
        t.append(f"<br><br>No <b>orgânico</b>, o Instagram somou {num(ig_alcance)} de alcance diário no mês "
                 f"(a soma repete quem viu em dias diferentes), com {num(ig.get('followers'))} seguidores no total.")

    t.append("<br><br><b>Recomendações para o próximo mês:</b>")
    acoes_lista = []
    if m["purchase"] == 0 and m["atc"] > 0:
        acoes_lista.append("Auditar o funil de compra do site e o disparo do evento <b>Purchase</b> do pixel. "
                           "Enquanto o carrinho enche e a compra não registra, não dá para saber se o problema é "
                           "venda ou medição.")
    if g_ok:
        sem = [(k, v) for k, v in g_rede if not v["conversions"] and v["cost"] > 5]
        if sem:
            acoes_lista.append("Restringir a Performance Max às redes que convertem. "
                               "Hoje a maior parte dos cliques vem de superfícies que não trouxeram reserva nenhuma.")
        if g_is:
            pior = max(g_is.items(), key=lambda x: x[1][2])
            if pior[1][2] > 50 and pior[1][1] < 15:
                acoes_lista.append(f"Trabalhar lance e qualidade na campanha de pesquisa, que é a mais eficiente "
                                   f"e está aparecendo em apenas {pct(pior[1][0], 1)} das buscas. "
                                   f"A perda é por classificação, não por verba.")
    if m["ctr_link"] and m["ctr_link"] < 1:
        acoes_lista.append("Renovar os criativos do Meta: o CTR segue abaixo de 1%, sinal de que o anúncio "
                           "já cansou o público.")
    acoes_lista.append("Marcar no Google Ads como <b>conversão principal</b> apenas o que é reserva de verdade, "
                       "para o custo por resultado continuar comparável entre as plataformas.")
    t.append('<ol class="acoes">' + "".join(f"<li>{a}</li>" for a in acoes_lista) + "</ol>")
    return "".join(t)


if __name__ == "__main__":
    sys.exit(main())
