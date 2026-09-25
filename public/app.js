/* Dashboard Nohotel — lógica de apresentação (sem dependências externas).
   Lê /config.json, /data/meta.json, /data/google.json e /data/organic.json
   (todos protegidos por senha no servidor). */
"use strict";

/* ===================================================================== utils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "href" || k === "src") { if (/^https?:\/\//i.test(String(v)) || String(v).startsWith("/")) el.setAttribute(k, v); }
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "hidden") el.hidden = !!v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
function svg(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  return el;
}

const nfBRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const nfInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const nfDec = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nfDec1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const ok = (n) => n != null && Number.isFinite(n);
const fmt = {
  brl: (n) => (ok(n) ? nfBRL.format(n) : "—"),
  int: (n) => (ok(n) ? nfInt.format(n) : "—"),
  dec: (n) => (ok(n) ? nfDec.format(n) : "—"),
  dec1: (n) => (ok(n) ? nfDec1.format(n) : "—"),
  pct: (n) => (ok(n) ? nfDec.format(n) + "%" : "—"),
  x: (n) => (ok(n) ? nfDec.format(n) + "×" : "—"),
  compact: (n) => (!ok(n) ? "—" : Math.abs(n) >= 1e6 ? nfDec1.format(n / 1e6) + " mi" : Math.abs(n) >= 1e4 ? nfDec1.format(n / 1e3) + " mil" : nfInt.format(n)),
  date: (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : "—"),
  dm: (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}` : ""),
  dateTime: (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  },
};
const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const COLOR = { meta: "#3987e5", google: "#d95926", topo: "#9085e9", brand: "#c8955a", good: "#199e70", warn: "#c98500", pink: "#d55181" };

function isoToDate(s) { return new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10))); }
function dateToIso(d) { return d.toISOString().slice(0, 10); }
function addDays(iso, n) { const d = isoToDate(iso); d.setUTCDate(d.getUTCDate() + n); return dateToIso(d); }
function daysBetween(a, b) { return Math.round((isoToDate(b) - isoToDate(a)) / 86400000) + 1; }
function monthStart(iso) { return iso.slice(0, 8) + "01"; }
function monthEnd(iso) { const d = isoToDate(monthStart(iso)); d.setUTCMonth(d.getUTCMonth() + 1); d.setUTCDate(0); return dateToIso(d); }
function daysInMonth(iso) { return +monthEnd(iso).slice(8, 10); }
function sum(arr, f) { let s = 0; for (const x of arr) s += f ? (f(x) || 0) : (x || 0); return s; }
const div = (a, b) => (b > 0 ? a / b : null);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
/** "1 reserva" / "2 reservas" — evita o "1 reservas". */
const plural = (n, word) => `${fmt.int(n)} ${n === 1 ? word : word + "s"}`;
const campWord = (n) => `${n} campanha${n === 1 ? "" : "s"}`;

function deltaBadge(cur, prev, { goodWhenUp = true, kind = "num" } = {}) {
  if (!ok(cur) || !ok(prev) || prev === 0) return h("span", { class: "delta", text: "—" });
  const pct = ((cur - prev) / Math.abs(prev)) * 100;
  if (Math.abs(pct) < 0.5) return h("span", { class: "delta", text: "= igual" });
  const up = pct > 0;
  const good = goodWhenUp ? up : !up;
  const arrow = up ? "↑" : "↓";
  return h("span", { class: `delta ${good ? "up" : "down"}`, title: `Período anterior: ${kind === "brl" ? fmt.brl(prev) : kind === "pct" ? fmt.pct(prev) : fmt.int(prev)}` }, `${arrow} ${nfDec1.format(Math.abs(pct))}%`);
}
function badge(level, text) {
  const cls = level === "ok" ? "ok" : level === "warn" ? "warn" : level === "crit" ? "crit" : "neutral";
  const ico = level === "ok" ? "●" : level === "warn" ? "▲" : level === "crit" ? "■" : "○";
  return h("span", { class: `badge ${cls}` }, `${ico} ${text}`);
}
function levelWord(level) {
  return level === "ok" ? "na meta" : level === "warn" ? "atenção" : level === "crit" ? "crítico" : "sem meta";
}
function statusBadge(effective, configured) {
  const s = effective || configured || "";
  if (s === "ACTIVE" || s === "ENABLED") return h("span", { class: "badge status-active", text: "ativo" });
  if (["PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED", "AD_PAUSED"].includes(s)) return h("span", { class: "badge status-paused", text: "pausado" });
  if (s === "ARCHIVED" || s === "REMOVED") return h("span", { class: "badge status-paused", text: s === "REMOVED" ? "removido" : "arquivado" });
  if (["WITH_ISSUES", "DISAPPROVED", "PENDING_REVIEW", "PENDING_BILLING_INFO", "IN_PROCESS"].includes(s)) {
    return h("span", { class: "badge status-issue", text: s === "PENDING_REVIEW" ? "em análise" : s === "IN_PROCESS" ? "processando" : s === "DISAPPROVED" ? "reprovado" : "com problema" });
  }
  return h("span", { class: "badge status-paused", text: String(s).toLowerCase() || "—" });
}

/* ============================================================ domínio Meta */
const OBJECTIVE_LABEL = {
  OUTCOME_LEADS: "Cadastros / conversas", OUTCOME_SALES: "Vendas / reservas", OUTCOME_TRAFFIC: "Tráfego", OUTCOME_AWARENESS: "Reconhecimento",
  OUTCOME_ENGAGEMENT: "Engajamento", OUTCOME_APP_PROMOTION: "App", MESSAGES: "Mensagens", LEAD_GENERATION: "Cadastros",
  CONVERSIONS: "Conversões", LINK_CLICKS: "Tráfego", REACH: "Alcance", BRAND_AWARENESS: "Reconhecimento", POST_ENGAGEMENT: "Engajamento",
  VIDEO_VIEWS: "Vídeo", PAGE_LIKES: "Curtidas",
};

/* Cada "def" descreve o que conta como resultado, a meta usada e a unidade exibida.
   rank = prioridade quando uma campanha tem conjuntos com objetivos diferentes. */
const DEF = {
  purchase: { id: "purchase", label: "Reservas / compras", unit: "reserva", keys: ["purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase", "web_in_store_purchase"], valueKeys: ["purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"], target: "cost_per_purchase", kind: "lead", rank: 100 },
  add_to_cart: { id: "add_to_cart", label: "Adições ao carrinho", unit: "adição", keys: ["add_to_cart", "offsite_conversion.fb_pixel_add_to_cart", "omni_add_to_cart"], target: "cost_per_add_to_cart", kind: "lead", rank: 70 },
  initiate_checkout: { id: "initiate_checkout", label: "Checkouts iniciados", unit: "checkout", keys: ["initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout", "omni_initiated_checkout"], target: "cost_per_add_to_cart", kind: "lead", rank: 80 },
  conversation: { id: "conversation", label: "Conversas iniciadas", unit: "conversa", keys: ["onsite_conversion.messaging_conversation_started_7d", "onsite_conversion.total_messaging_connection"], target: "cost_per_conversation", kind: "lead", rank: 90 },
  lead: { id: "lead", label: "Cadastros", unit: "cadastro", keys: ["lead", "onsite_conversion.lead_grouped", "leadgen_grouped"], target: "cost_per_conversation", kind: "lead", rank: 85 },
  call: { id: "call", label: "Ligações", unit: "ligação", keys: ["onsite_conversion.click_to_call", "call_confirm_grouped"], target: "cost_per_conversation", kind: "lead", rank: 85 },
  landing_page_view: { id: "landing_page_view", label: "Visualizações da página", unit: "visualização", keys: ["landing_page_view", "link_click"], kind: "traffic", rank: 40 },
  profile_visit: { id: "profile_visit", label: "Visitas ao perfil", unit: "visita", keys: ["profile_visit", "link_click"], target: "cost_per_profile_visit", kind: "traffic", rank: 45 },
  link_click: { id: "link_click", label: "Cliques no link", unit: "clique", keys: ["link_click"], kind: "traffic", rank: 30 },
  post_engagement: { id: "post_engagement", label: "Engajamentos", unit: "engajamento", keys: ["post_engagement"], kind: "awareness", rank: 20 },
  video_view: { id: "video_view", label: "Visualizações de vídeo", unit: "visualização", keys: ["video_view"], kind: "awareness", rank: 20 },
  thruplay: { id: "thruplay", label: "ThruPlays", unit: "thruplay", metric: "thruplays", kind: "awareness", rank: 20 },
  reach: { id: "reach", label: "Alcance", unit: "pessoa", metric: "reach", kind: "awareness", per: 1000, rank: 10 },
  impressions: { id: "impressions", label: "Impressões", unit: "impressão", metric: "impressions", kind: "awareness", per: 1000, rank: 10 },
  page_like: { id: "page_like", label: "Curtidas na página", unit: "curtida", keys: ["like"], kind: "awareness", rank: 20 },
};
const GOAL_DEF = {
  CONVERSATIONS: DEF.conversation,
  LEAD_GENERATION: DEF.lead, QUALITY_LEAD: DEF.lead, QUALITY_CALL: DEF.call,
  LINK_CLICKS: DEF.link_click, LANDING_PAGE_VIEWS: DEF.landing_page_view,
  PROFILE_VISIT: DEF.profile_visit, VISIT_INSTAGRAM_PROFILE: DEF.profile_visit,
  REACH: DEF.reach, AD_RECALL_LIFT: DEF.reach, IMPRESSIONS: DEF.impressions,
  THRUPLAY: DEF.thruplay, TWO_SECOND_CONTINUOUS_VIDEO_VIEWS: DEF.video_view,
  POST_ENGAGEMENT: DEF.post_engagement, PAGE_LIKES: DEF.page_like,
};
/* evento otimizado no pixel (promoted_object.custom_event_type) */
const EVENT_DEF = {
  PURCHASE: DEF.purchase, ADD_TO_CART: DEF.add_to_cart, INITIATE_CHECKOUT: DEF.initiate_checkout,
  LEAD: DEF.lead, COMPLETE_REGISTRATION: DEF.lead, CONTENT_VIEW: DEF.landing_page_view, SEARCH: DEF.landing_page_view,
};
const CONV_KEY = "onsite_conversion.messaging_conversation_started_7d";

/* ================================================================ estado */
const state = {
  config: null, meta: null, google: null, organic: null,
  since: null, until: null, preset: "30", prevSince: null, prevUntil: null,
  targets: {}, section: "exec",
  histYear: null, // ano mostrado no histórico mensal ("all" = todos)
  creativeFilter: { campaign: "all", quality: "all" },
  googleFilter: { campaign: "all" },
};
const idx = {
  campaigns: new Map(), adsets: new Map(), ads: new Map(),
  defByCampaign: new Map(), defByAdset: new Map(), kindByCampaign: new Map(), campaignByAd: new Map(),
  gCampaigns: new Map(), gAdGroups: new Map(),
};

const TARGET_KEYS = ["cost_per_purchase", "cost_per_add_to_cart", "cost_per_conversation", "cost_per_profile_visit", "google_cost_per_conversion", "meta_monthly", "google_monthly", "frequency_max", "ctr_min", "cpm_topo_max", "min_spend_for_alert"];
function loadTargets() {
  const base = { ...state.config.targets, meta_monthly: state.config.budget.meta_monthly, google_monthly: state.config.budget.google_monthly };
  try {
    const saved = JSON.parse(localStorage.getItem("nohotel.targets") || "null");
    if (saved && typeof saved === "object") return { ...base, ...saved };
  } catch { /* ignore */ }
  return base;
}
function saveTargets(t) { try { localStorage.setItem("nohotel.targets", JSON.stringify(t)); } catch { /* ignore */ } }

/* ============================================================== agregação */
function emptyAgg() { return { spend: 0, impressions: 0, reach: 0, clicks: 0, link_clicks: 0, thruplays: 0, actions: {}, values: {}, days: new Set() }; }
function addRow(agg, r) {
  agg.spend += r.spend || 0; agg.impressions += r.impressions || 0; agg.reach += r.reach || 0;
  agg.clicks += r.clicks || 0; agg.link_clicks += r.link_clicks || 0; agg.thruplays += r.thruplays || 0;
  if (r.date) agg.days.add(r.date);
  for (const [k, v] of Object.entries(r.actions || {})) agg.actions[k] = (agg.actions[k] || 0) + v;
  for (const [k, v] of Object.entries(r.values || {})) agg.values[k] = (agg.values[k] || 0) + v;
  return agg;
}
function finish(agg) {
  agg.cpm = div(agg.spend * 1000, agg.impressions);
  agg.ctr = div(agg.clicks * 100, agg.impressions);
  agg.cpc = div(agg.spend, agg.clicks);
  agg.link_ctr = div(agg.link_clicks * 100, agg.impressions);
  agg.frequency = div(agg.impressions, agg.reach);
  agg.conversations = agg.actions[CONV_KEY] || 0;
  agg.purchases = countOf(agg, DEF.purchase);
  agg.add_to_carts = countOf(agg, DEF.add_to_cart);
  agg.revenue = valueOf(agg, DEF.purchase);
  agg.roas = div(agg.revenue, agg.spend);
  agg.cost_per_purchase = div(agg.spend, agg.purchases);
  agg.cost_per_conversation = div(agg.spend, agg.conversations);
  return agg;
}
function aggregate(rows) { const a = emptyAgg(); for (const r of rows) addRow(a, r); return finish(a); }
function groupBy(rows, key) {
  const m = new Map();
  for (const r of rows) { const k = r[key]; if (!m.has(k)) m.set(k, emptyAgg()); addRow(m.get(k), r); }
  for (const v of m.values()) finish(v);
  return m;
}
function rowsIn(since, until, rows) { return (rows || state.meta?.daily || []).filter((r) => r.date >= since && r.date <= until); }

/** Primeiro action_type disponível da lista (a API muda o nome conforme a conta). */
function firstKey(agg, keys) {
  for (const k of keys || []) if (agg.actions[k]) return k;
  return (keys || [])[0];
}
function countOf(agg, def) {
  if (!def) return 0;
  if (def.metric) return agg[def.metric] || 0;
  const k = firstKey(agg, def.keys);
  return agg.actions[k] || 0;
}
function valueOf(agg, def) {
  for (const k of def?.valueKeys || []) if (agg.values[k]) return agg.values[k];
  return 0;
}
function resultsOf(agg, def) { return countOf(agg, def); }
function costPerResult(agg, def) {
  const r = resultsOf(agg, def);
  if (def?.per) return div(agg.spend * def.per, r);
  return div(agg.spend, r);
}
function targetFor(def) {
  if (!def) return null;
  if (def.target) return state.targets[def.target] || null;
  if (def.kind === "awareness" && def.per) return state.targets.cpm_topo_max || null;
  return null;
}
function assess(agg, def, { minSpend } = {}) {
  const min = minSpend ?? state.targets.min_spend_for_alert ?? 30;
  const results = resultsOf(agg, def);
  const cpr = costPerResult(agg, def);
  const target = targetFor(def);
  if (agg.spend <= 0) return { level: "neutral", text: "Sem gasto no período" };
  if (results === 0) {
    if (agg.spend >= min) return { level: "crit", text: `${fmt.brl(agg.spend)} sem nenhum resultado — pausar ou revisar`, ratio: null };
    return { level: "warn", text: "Sem resultado, mas gasto baixo — observar", ratio: null };
  }
  if (!target || !ok(cpr)) return { level: "neutral", text: "Sem meta definida para este objetivo" };
  const ratio = cpr / target;
  if (ratio <= 1) return { level: "ok", text: "Dentro da meta — manter", ratio };
  if (ratio <= 1.6) return { level: "warn", text: `Custo ${nfDec1.format(ratio)}× a meta — otimizar segmentação/criativo`, ratio };
  return { level: "crit", text: `Custo ${nfDec1.format(ratio)}× a meta — reduzir verba e revisar`, ratio };
}

/* ================================================================ índices */
function defForAdset(s, campaign) {
  if (s?.custom_event && EVENT_DEF[s.custom_event]) return EVENT_DEF[s.custom_event];
  if (s?.optimization_goal && GOAL_DEF[s.optimization_goal]) return GOAL_DEF[s.optimization_goal];
  if (s?.optimization_goal === "OFFSITE_CONVERSIONS" || s?.optimization_goal === "VALUE") return DEF.purchase;
  return defForObjective(campaign?.objective);
}
function defForObjective(objective) {
  switch (objective) {
    case "OUTCOME_SALES": case "CONVERSIONS": return DEF.purchase;
    case "OUTCOME_LEADS": case "LEAD_GENERATION": return DEF.lead;
    case "MESSAGES": return DEF.conversation;
    case "OUTCOME_AWARENESS": case "BRAND_AWARENESS": case "REACH": return DEF.reach;
    case "OUTCOME_ENGAGEMENT": case "POST_ENGAGEMENT": return DEF.post_engagement;
    case "VIDEO_VIEWS": return DEF.video_view;
    default: return DEF.link_click;
  }
}
function buildIndexes() {
  const m = state.meta;
  if (!m) return;
  idx.campaigns = new Map(m.campaigns.map((c) => [c.id, c]));
  idx.adsets = new Map(m.adsets.map((s) => [s.id, s]));
  idx.ads = new Map(m.ads.map((a) => [a.id, a]));
  for (const a of m.ads) idx.campaignByAd.set(a.id, a.campaign_id);
  for (const s of m.adsets) idx.defByAdset.set(s.id, defForAdset(s, idx.campaigns.get(s.campaign_id)));
  const LEAD_OBJ = new Set(["OUTCOME_LEADS", "OUTCOME_SALES", "MESSAGES", "LEAD_GENERATION", "CONVERSIONS"]);
  for (const c of m.campaigns) {
    const sets = m.adsets.filter((s) => s.campaign_id === c.id);
    const defs = sets.map((s) => idx.defByAdset.get(s.id)).filter(Boolean);
    /* conjuntos com objetivos diferentes → vale o de maior prioridade (ex.: compra acima de carrinho) */
    const def = defs.length ? defs.slice().sort((a, b) => b.rank - a.rank)[0] : defForObjective(c.objective);
    idx.defByCampaign.set(c.id, def);
    idx.kindByCampaign.set(c.id, def.kind === "lead" || LEAD_OBJ.has(c.objective) ? "captacao" : "topo");
  }
  const g = state.google;
  if (g?.configured) {
    idx.gCampaigns = new Map((g.campaigns || []).map((c) => [c.id, c]));
    idx.gAdGroups = new Map((g.ad_groups || []).map((a) => [a.id, a]));
  }
}
const defFor = (campaignId) => idx.defByCampaign.get(campaignId) || DEF.link_click;
const isCaptacao = (campaignId) => idx.kindByCampaign.get(campaignId) === "captacao";

/* ============================================================ Google Ads */
const gEnabled = () => !!(state.google && state.google.configured);
const GOOGLE_CHANNEL = {
  SEARCH: "Pesquisa", DISPLAY: "Display", SHOPPING: "Shopping", VIDEO: "Vídeo", PERFORMANCE_MAX: "Performance Max",
  MULTI_CHANNEL: "Multicanal", LOCAL: "Local", SMART: "Smart", DISCOVERY: "Discovery", DEMAND_GEN: "Demand Gen", HOTEL: "Hotel",
};
function gEmpty() { return { cost: 0, impressions: 0, clicks: 0, conversions: 0, conversions_value: 0, all_conversions: 0, days: new Set() }; }
function gAdd(a, r) {
  a.cost += r.cost || 0; a.impressions += r.impressions || 0; a.clicks += r.clicks || 0;
  a.conversions += r.conversions || 0; a.conversions_value += r.conversions_value || 0; a.all_conversions += r.all_conversions || 0;
  if (r.date) a.days.add(r.date);
  return a;
}
function gFinish(a) {
  a.cpm = div(a.cost * 1000, a.impressions);
  a.ctr = div(a.clicks * 100, a.impressions);
  a.cpc = div(a.cost, a.clicks);
  a.cpa = div(a.cost, a.conversions);
  a.roas = div(a.conversions_value, a.cost);
  a.conversions = Math.round(a.conversions * 100) / 100;
  return a;
}
function gAggregate(rows) { const a = gEmpty(); for (const r of rows) gAdd(a, r); return gFinish(a); }
function gGroupBy(rows, key) {
  const m = new Map();
  for (const r of rows) { const k = r[key]; if (!m.has(k)) m.set(k, gEmpty()); gAdd(m.get(k), r); }
  for (const v of m.values()) gFinish(v);
  return m;
}
function gRowsIn(since, until, rows) {
  if (!gEnabled()) return [];
  return (rows || state.google.daily || []).filter((r) => r.date >= since && r.date <= until);
}
function gAssess(agg) {
  const min = state.targets.min_spend_for_alert ?? 30;
  const target = state.targets.google_cost_per_conversion;
  if (agg.cost <= 0) return { level: "neutral", text: "Sem gasto no período" };
  if (!agg.conversions) {
    if (agg.cost >= min) return { level: "crit", text: `${fmt.brl(agg.cost)} sem nenhuma conversão — revisar palavras-chave e página` };
    return { level: "warn", text: "Sem conversão, mas gasto baixo — observar" };
  }
  if (!target || !ok(agg.cpa)) return { level: "neutral", text: "Sem meta definida" };
  const ratio = agg.cpa / target;
  if (ratio <= 1) return { level: "ok", text: "Dentro da meta — manter", ratio };
  if (ratio <= 1.6) return { level: "warn", text: `Custo ${nfDec1.format(ratio)}× a meta — revisar lances e termos`, ratio };
  return { level: "crit", text: `Custo ${nfDec1.format(ratio)}× a meta — reduzir verba e revisar`, ratio };
}

/* ================================================================= período */
function dataBounds() {
  const since = [], until = [];
  if (state.meta?.range) { since.push(state.meta.range.since); until.push(state.meta.range.until); }
  if (gEnabled() && state.google.range) { since.push(state.google.range.since); until.push(state.google.range.until); }
  if (!since.length) { const t = dateToIso(new Date()); return { first: addDays(t, -29), last: t }; }
  /* começa no primeiro dia com entrega, para “Desde o início” não virar um período vazio */
  const dates = [];
  for (const r of state.meta?.daily || []) if (r.spend > 0 || r.impressions > 0) dates.push(r.date);
  for (const r of (gEnabled() && state.google.daily) || []) if (r.cost > 0 || r.impressions > 0) dates.push(r.date);
  const firstData = dates.length ? dates.reduce((a, b) => (a < b ? a : b)) : null;
  const first = firstData || since.reduce((a, b) => (a < b ? a : b));
  return { first, last: until.reduce((a, b) => (a > b ? a : b)) };
}
function computePeriod() {
  const { first, last } = dataBounds();
  let since, until = last;
  switch (state.preset) {
    case "7": since = addDays(last, -6); break;
    case "14": since = addDays(last, -13); break;
    case "30": since = addDays(last, -29); break;
    case "90": since = addDays(last, -89); break;
    case "month": since = monthStart(last); break;
    case "lastmonth": { const e = addDays(monthStart(last), -1); since = monthStart(e); until = e; break; }
    case "max": since = first; break;
    case "custom": since = state.since || addDays(last, -29); until = state.until || last; break;
    default: since = addDays(last, -29);
  }
  if (since < first && state.preset !== "custom") since = first;
  if (since > until) since = until;
  state.since = since; state.until = until;
  const len = daysBetween(since, until);
  state.prevUntil = addDays(since, -1);
  state.prevSince = addDays(since, -len);
}

/* ================================================================== charts */
let tooltipEl;
function showTooltip(x, y, title, rows) {
  tooltipEl.replaceChildren(h("div", { class: "tt-title", text: title }), ...rows.map((r) => h("div", { class: "tt-row" }, h("span", {}, r.color ? h("i") : null, r.label), h("b", { text: r.value }))));
  $$(".tt-row i", tooltipEl).forEach((i, k) => { i.style.background = rows[k].color; });
  tooltipEl.hidden = false;
  const rect = tooltipEl.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + rect.width > window.innerWidth - 8) left = x - rect.width - 14;
  if (top + rect.height > window.innerHeight - 8) top = y - rect.height - 14;
  tooltipEl.style.left = left + "px"; tooltipEl.style.top = top + "px";
}
function hideTooltip() { tooltipEl.hidden = true; }

function niceTicks(max, count = 4) {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.999; v += step) ticks.push(+v.toFixed(6));
  return ticks;
}
function roundedTop(x, y, w, hgt, r) {
  if (hgt <= 0) return "";
  r = Math.min(r, w / 2, hgt);
  return `M${x},${y + hgt} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${y + hgt} Z`;
}

function renderChart(container, { type = "bar", labels, series, stacked = true, format = fmt.int, target = null, targetLabel = "meta", height = 210 }) {
  container.replaceChildren();
  const W = Math.max(280, container.clientWidth || 600), H = height;
  const padL = 46, padR = 10, padT = 10, padB = 24;
  const iw = W - padL - padR, ih = H - padT - padB;
  const n = labels.length;
  const el = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img" });
  if (!n) { container.append(el); return; }
  let max = 0;
  for (let i = 0; i < n; i++) {
    if (type === "bar" && stacked) max = Math.max(max, sum(series, (s) => s.values[i] || 0));
    else for (const s of series) max = Math.max(max, s.values[i] || 0);
  }
  if (ok(target)) max = Math.max(max, target * 1.1);
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1] || 1;
  const y = (v) => padT + ih - (v / top) * ih;
  for (const t of ticks) {
    el.append(svg("line", { x1: padL, x2: W - padR, y1: y(t), y2: y(t), class: "grid-line" }));
    const tx = svg("text", { x: padL - 6, y: y(t) + 3, "text-anchor": "end" }); tx.textContent = fmt.compact(t); el.append(tx);
  }
  const slot = iw / n;
  const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(iw / 42))));
  for (let i = 0; i < n; i++) {
    if (i % every !== 0 && i !== n - 1) continue;
    const tx = svg("text", { x: padL + slot * (i + 0.5), y: H - 6, "text-anchor": "middle" }); tx.textContent = labels[i]; el.append(tx);
  }
  if (type === "bar") {
    const bw = Math.min(24 * (stacked ? 1 : series.length), slot * 0.72);
    for (let i = 0; i < n; i++) {
      let acc = 0;
      series.forEach((s, si) => {
        const v = s.values[i] || 0; if (v <= 0) return;
        const x0 = stacked ? padL + slot * (i + 0.5) - bw / 2 : padL + slot * (i + 0.5) - bw / 2 + (bw / series.length) * si;
        const w = stacked ? bw : bw / series.length - 1;
        const yTop = y(acc + v), yBot = y(acc);
        const gap = stacked && acc > 0 ? 2 : 0;
        const isTop = stacked ? si === series.length - 1 || series.slice(si + 1).every((t) => !(t.values[i] > 0)) : true;
        const hh = Math.max(0, yBot - yTop - gap);
        el.append(isTop ? svg("path", { d: roundedTop(x0, yTop, w, hh, 4), fill: s.color }) : svg("rect", { x: x0, y: yTop, width: w, height: hh, fill: s.color }));
        acc += v;
      });
    }
  } else {
    series.forEach((s) => {
      const pts = [];
      for (let i = 0; i < n; i++) { const v = s.values[i]; pts.push(ok(v) ? [padL + slot * (i + 0.5), y(v)] : null); }
      let d = "", pen = false;
      for (const p of pts) { if (!p) { pen = false; continue; } d += (pen ? "L" : "M") + p[0] + "," + p[1]; pen = true; }
      el.append(svg("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      pts.forEach((p) => { if (p) el.append(svg("circle", { cx: p[0], cy: p[1], r: 4, fill: s.color, stroke: "#18181a", "stroke-width": 2 })); });
    });
  }
  if (ok(target)) {
    el.append(svg("line", { x1: padL, x2: W - padR, y1: y(target), y2: y(target), class: "target-line" }));
    const tx = svg("text", { x: W - padR, y: y(target) - 4, "text-anchor": "end" }); tx.textContent = `${targetLabel} ${format(target)}`; el.append(tx);
  }
  for (let i = 0; i < n; i++) {
    const hit = svg("rect", { x: padL + slot * i, y: padT, width: slot, height: ih, class: "hit" });
    const show = (ev) => showTooltip(ev.clientX, ev.clientY, labels[i], series.map((s) => ({ label: s.name, value: format(s.values[i] ?? null), color: s.color })));
    hit.addEventListener("mousemove", show); hit.addEventListener("mouseleave", hideTooltip);
    el.append(hit);
  }
  container.append(el);
}
function chartCard(title, subtitle, series, buildOpts) {
  const card = h("div", { class: "chart-card" });
  const head = h("div", { class: "chart-head" }, h("h3", {}, title, subtitle ? h("small", { text: subtitle }) : null));
  if (series.length >= 2) head.append(h("div", { class: "legend" }, ...series.map((s) => { const i = h("i"); i.style.background = s.color; return h("span", {}, i, s.name); })));
  const body = h("div", { class: "chart" });
  card.append(head, body);
  card._render = () => renderChart(body, { ...buildOpts, series });
  requestAnimationFrame(card._render);
  return card;
}

/* ============================================================ tiles/utils */
function tile({ label, value, sub, delta, accent, hero, cls }) {
  return h("div", { class: `tile${accent ? " accent" : ""}${cls ? " " + cls : ""}` },
    h("div", { class: "label", text: label }),
    h("div", { class: `value${hero ? " hero" : ""}` }, value),
    (sub || delta) ? h("div", { class: "sub" }, delta || null, sub || null) : null,
  );
}
function block(title, subtitle, ...children) {
  return h("div", { class: "block" }, h("div", { class: "block-head" }, h("h2", {}, title, subtitle ? h("small", { text: subtitle }) : null)), ...children);
}
/** Igual ao block(), mas com um controle (filtro, botão) alinhado à direita do título. */
function blockWith(title, subtitle, control, ...children) {
  return h("div", { class: "block" },
    h("div", { class: "block-head" }, h("h2", {}, title, subtitle ? h("small", { text: subtitle }) : null), control || null),
    ...children);
}
function progressBar(pct, level) {
  const p = h("div", { class: "progress" }); const i = h("i", { class: level || "" }); i.style.width = clamp(pct, 0, 100) + "%"; p.append(i); return p;
}
function spanDot(color) { const i = h("i", { class: "dot" }); i.style.background = color; return i; }
function cprCell(agg, def) {
  const cpr = costPerResult(agg, def);
  const target = targetFor(def);
  const wrap = h("div", { class: "cpr" }, h("span", { text: ok(cpr) ? (def.per ? `${fmt.brl(cpr)}/mil` : fmt.brl(cpr)) : "—" }));
  if (ok(cpr) && target) {
    const ratio = cpr / target;
    const bar = h("div", { class: "bar" }); const i = h("i", { class: ratio <= 1 ? "" : ratio <= 1.6 ? "warn" : "crit" });
    i.style.width = Math.min(100, (1 / Math.max(ratio, 0.01)) * 60) + "%";
    bar.append(i); wrap.append(bar);
  }
  return wrap;
}
function gCprCell(agg) {
  const target = state.targets.google_cost_per_conversion;
  const wrap = h("div", { class: "cpr" }, h("span", { text: ok(agg.cpa) ? fmt.brl(agg.cpa) : "—" }));
  if (ok(agg.cpa) && target) {
    const ratio = agg.cpa / target;
    const bar = h("div", { class: "bar" }); const i = h("i", { class: ratio <= 1 ? "" : ratio <= 1.6 ? "warn" : "crit" });
    i.style.width = Math.min(100, (1 / Math.max(ratio, 0.01)) * 60) + "%";
    bar.append(i); wrap.append(bar);
  }
  return wrap;
}
function thumbOf(ad) { return ad?.creative?.image_url || ad?.creative?.thumbnail_url || null; }
function adLink(ad) { return ad?.creative?.instagram_permalink_url || ad?.preview_link || null; }
function platformBar(kind, title, targetText, cells, level) {
  return h("div", { class: "platform-bar" },
    h("div", { class: `head ${kind}` },
      h("span", {}, title, level ? h("span", {}, " ", badge(level, levelWord(level))) : null),
      h("span", { class: "meta-target", text: targetText || "" })),
    h("div", { class: "body" }, ...cells.map(([v, k]) => h("div", {}, h("div", { class: "v" }, v), h("div", { class: "k", text: k })))),
  );
}

/* ===================================================== seção: executiva */
function renderExec() {
  const sec = $("#sec-exec"); sec.replaceChildren();
  const m = state.meta; const T = state.targets;
  const { last } = dataBounds();

  const rows = rowsIn(state.since, state.until);
  const prevRows = rowsIn(state.prevSince, state.prevUntil);
  const all = aggregate(rows), prevAll = aggregate(prevRows);
  const cap = aggregate(rows.filter((r) => isCaptacao(r.campaign_id))), prevCap = aggregate(prevRows.filter((r) => isCaptacao(r.campaign_id)));
  const topo = aggregate(rows.filter((r) => !isCaptacao(r.campaign_id)));
  const gRows = gRowsIn(state.since, state.until), gPrevRows = gRowsIn(state.prevSince, state.prevUntil);
  const g = gAggregate(gRows), gPrev = gAggregate(gPrevRows);

  const presetKey = { 7: "last_7d", 14: "last_14d", 30: "last_30d", month: "this_month", lastmonth: "last_month", max: "maximum" }[state.preset];
  const exact = presetKey && m.presets?.[presetKey];
  const reach = exact?.reach ?? all.reach;
  const reachNote = exact ? "alcance exato (API)" : "soma dos alcances diários";

  const totalSpend = all.spend + g.cost;
  const prevTotalSpend = prevAll.spend + gPrev.cost;
  const totalRevenue = all.revenue + g.conversions_value;
  const totalRoas = div(totalRevenue, totalSpend);
  const totalConv = all.purchases + g.conversions;

  /* --- controle de investimento ------------------------------------------- */
  const monthRows = rowsIn(monthStart(last), last);
  const monthAgg = aggregate(monthRows);
  const gMonthAgg = gAggregate(gRowsIn(monthStart(last), last));
  const monthSpend = monthAgg.spend + gMonthAgg.cost;
  const dayN = +last.slice(8, 10), dim = daysInMonth(last);
  const gDailyBudget = gEnabled() ? sum((state.google.campaigns || []).filter((c) => c.status === "ENABLED"), (c) => c.daily_budget || 0) : 0;
  /* verba do Google não definida → estimada pelos orçamentos diários das campanhas ativas */
  const googleBudgetEstimated = gEnabled() && !(T.google_monthly > 0);
  const budgetMeta = T.meta_monthly || 0;
  const budgetGoogle = !gEnabled() ? 0 : googleBudgetEstimated ? gDailyBudget * dim : T.google_monthly;
  const budget = budgetMeta + budgetGoogle;
  const pace = monthSpend / Math.max(1, dayN);
  const projection = pace * dim;
  const remainingDays = dim - dayN;
  const needPace = remainingDays > 0 ? Math.max(0, budget - monthSpend) / remainingDays : 0;
  const usedPct = budget ? (monthSpend / budget) * 100 : 0;
  const paceLevel = !budget ? "" : projection > budget * 1.15 ? "crit" : projection > budget * 1.05 ? "warn" : "good";
  const dailyBudgetTotal = sum(m.campaigns.filter((c) => c.effective_status === "ACTIVE"), (c) => c.daily_budget || 0)
    + sum(m.adsets.filter((s) => s.effective_status === "ACTIVE" && !(idx.campaigns.get(s.campaign_id)?.daily_budget > 0)), (s) => s.daily_budget || 0);
  const capLeft = m.account.spend_cap > 0 ? m.account.spend_cap - m.account.amount_spent_lifetime : null;

  const invest = h("div", { class: "grid c3" },
    h("div", { class: "tile accent brand" },
      h("div", { class: "label", text: `Verba do mês · ${MONTHS[+last.slice(5, 7) - 1]} ${last.slice(0, 4)}` }),
      h("div", { class: "value hero", text: fmt.brl(monthSpend) }),
      h("div", { class: "sub" }, `de ${fmt.brl(budget)} · ${fmt.dec1(usedPct)}% usado`,
        badge(paceLevel === "good" ? "ok" : paceLevel === "warn" ? "warn" : paceLevel === "crit" ? "crit" : "neutral",
          paceLevel === "good" ? "no ritmo" : paceLevel === "warn" ? "ritmo alto" : paceLevel === "crit" ? "acima da verba" : "sem verba definida")),
      progressBar(usedPct, paceLevel),
      h("div", { class: "split" },
        h("div", { class: "split-row" }, h("span", {}, spanDot(COLOR.meta), "Meta Ads"), progressBar(budgetMeta ? (monthAgg.spend / budgetMeta) * 100 : 0), h("b", { text: fmt.brl(monthAgg.spend) })),
        gEnabled() || budgetGoogle
          ? h("div", { class: "split-row" }, h("span", {}, spanDot(COLOR.google), googleBudgetEstimated ? "Google Ads (verba estimada)" : "Google Ads"), progressBar(budgetGoogle ? (gMonthAgg.cost / budgetGoogle) * 100 : 0, "google"), h("b", { text: fmt.brl(gMonthAgg.cost) }))
          : null,
      ),
    ),
    h("div", { class: "tile" },
      h("div", { class: "label", text: "Ritmo de gasto" }),
      h("div", { class: "value" }, fmt.brl(pace), h("span", { class: "faint", text: "/dia" })),
      h("div", { class: "sub", text: `Ciclo ${fmt.date(monthStart(last))} a ${fmt.date(monthEnd(last))} · dia ${dayN} de ${dim}` }),
      h("div", { class: "sub" }, "Projeção do mês: ", h("b", { text: fmt.brl(projection) }),
        budget ? (projection > budget ? badge("warn", `${fmt.brl(projection - budget)} acima`) : badge("ok", `${fmt.brl(budget - projection)} sobram`)) : null),
      remainingDays > 0 ? h("div", { class: "sub", text: `Cabe ${fmt.brl(needPace)}/dia nos ${remainingDays} dias restantes` }) : h("div", { class: "sub", text: "Mês encerrado" }),
      h("div", { class: "sub faint", text: `Orçamento diário configurado: Meta ${fmt.brl(dailyBudgetTotal)}/dia${gEnabled() ? ` · Google ${fmt.brl(gDailyBudget)}/dia` : ""}` }),
    ),
    h("div", { class: "tile" },
      h("div", { class: "label", text: "Contas de anúncios" }),
      h("div", { class: "value", text: m.account.balance > 0 ? fmt.brl(m.account.balance) : fmt.brl(m.account.amount_spent_lifetime) }),
      h("div", { class: "sub", text: m.account.balance > 0 ? "saldo devedor no Meta (pós-pago)" : "investido no Meta desde o início da conta" }),
      h("div", { class: "sub" }, m.account.status === 1 ? badge("ok", "Meta ativa") : badge("crit", `Meta status ${m.account.status}`),
        ok(capLeft) ? badge(capLeft <= 0 ? "crit" : capLeft < 1000 ? "warn" : "neutral", `limite: restam ${fmt.brl(capLeft)}`) : null),
      h("div", { class: "sub faint", text: `${m.campaigns.filter((c) => c.effective_status === "ACTIVE").length} campanhas ativas de ${m.campaigns.length} no Meta · fuso ${m.account.timezone}` }),
      h("div", { class: "sub faint" }, gEnabled()
        ? `Google Ads ${state.config.google_ads.customer_id}: ${(state.google.campaigns || []).filter((c) => c.status === "ENABLED").length} campanhas ativas`
        : `Google Ads ${state.config.google_ads.customer_id}: aguardando credenciais da API`),
    ),
  );

  /* --- o que está acontecendo -------------------------------------------- */
  const kpis = h("div", { class: "grid c6" },
    tile({
      label: "Investimento no período", value: fmt.brl(totalSpend), accent: true, cls: "brand",
      delta: deltaBadge(totalSpend, prevTotalSpend, { goodWhenUp: false, kind: "brl" }),
      sub: `Meta ${fmt.brl(all.spend)}${gEnabled() ? ` · Google ${fmt.brl(g.cost)}` : ""}`,
    }),
    gEnabled()
      ? tile({
        label: "Reservas / compras", value: fmt.int(Math.round(all.purchases + g.conversions)), accent: true,
        delta: deltaBadge(all.purchases + g.conversions, prevAll.purchases + gPrev.conversions),
        sub: `Meta ${fmt.int(all.purchases)} a ${fmt.brl(cap.cost_per_purchase)} · Google ${fmt.dec1(g.conversions)} a ${fmt.brl(g.cpa)}`,
      })
      : tile({
        label: "Reservas / compras", value: fmt.int(all.purchases), accent: true,
        delta: deltaBadge(all.purchases, prevAll.purchases),
        sub: h("span", {}, `${fmt.brl(cap.cost_per_purchase)} cada · meta ${fmt.brl(T.cost_per_purchase)} `,
          all.purchases > 0 ? badge(assess(cap, DEF.purchase).level, levelWord(assess(cap, DEF.purchase).level)) : null),
      }),
    totalRevenue > 0
      ? tile({
        label: "Receita atribuída", value: fmt.brl(totalRevenue),
        delta: deltaBadge(all.revenue, prevAll.revenue, { kind: "brl" }),
        sub: `ROAS ${fmt.x(totalRoas)} · ticket ${fmt.brl(div(totalRevenue, totalConv))}`,
      })
      : tile({
        label: "Checkouts iniciados", value: fmt.int(countOf(all, DEF.initiate_checkout)),
        delta: deltaBadge(countOf(all, DEF.initiate_checkout), countOf(prevAll, DEF.initiate_checkout)),
        sub: "o pixel não envia o valor da compra — sem receita e ROAS",
      }),
    tile({
      label: "Adições ao carrinho", value: fmt.int(all.add_to_carts),
      delta: deltaBadge(all.add_to_carts, prevAll.add_to_carts),
      sub: `${fmt.brl(div(cap.spend, all.add_to_carts))} por adição`,
    }),
    tile({
      label: "Conversas no WhatsApp", value: fmt.int(all.conversations),
      delta: deltaBadge(all.conversations, prevAll.conversations),
      sub: `${fmt.brl(all.cost_per_conversation)} por conversa`,
    }),
    tile({
      label: "Alcance e cliques", value: fmt.compact(reach),
      delta: deltaBadge(all.reach, prevAll.reach),
      sub: `${reachNote} · ${fmt.int(all.link_clicks + g.clicks)} cliques · CPM ${fmt.brl(all.cpm)}`,
    }),
  );

  const metaLevel = assess(cap, DEF.purchase).level;
  const bars = h("div", { class: "grid c3" },
    platformBar("meta", "Meta Ads · conversão", `meta ${fmt.brl(T.cost_per_purchase)} por reserva`, [
      [fmt.brl(cap.spend), "investido em conversão"],
      [fmt.int(cap.purchases), "reservas"],
      [fmt.brl(cap.cost_per_purchase), "custo por reserva"],
    ], cap.spend > 0 ? metaLevel : null),
    platformBar("topo", "Meta Ads · topo de funil", "tráfego, alcance e engajamento", [
      [fmt.brl(topo.spend), "investido"],
      [fmt.compact(topo.reach), "alcance (soma diária)"],
      [fmt.brl(topo.cpm), "CPM"],
    ]),
    gEnabled()
      ? platformBar("google", "Google Ads", `meta ${fmt.brl(T.google_cost_per_conversion)} por conversão`, [
        [fmt.brl(g.cost), "investido"],
        [fmt.dec1(g.conversions), "conversões"],
        [fmt.brl(g.cpa), "custo por conversão"],
      ], g.cost > 0 ? gAssess(g).level : null)
      : platformBar("google", "Google Ads", "aguardando integração", [
        ["—", "investido"], ["—", "conversões"], ["—", "custo por conversão"],
      ]),
  );

  /* --- evolução diária ----------------------------------------------------- */
  const days = []; for (let d = state.since; d <= state.until; d = addDays(d, 1)) days.push(d);
  const labels = days.map(fmt.dm);
  const byDayCap = groupBy(rows.filter((r) => isCaptacao(r.campaign_id)), "date");
  const byDayTopo = groupBy(rows.filter((r) => !isCaptacao(r.campaign_id)), "date");
  const byDayAll = groupBy(rows, "date");
  const gByDay = gGroupBy(gRows, "date");

  const investSeries = [
    { name: "Meta · conversão", color: COLOR.meta, values: days.map((d) => byDayCap.get(d)?.spend || 0) },
    { name: "Meta · topo", color: COLOR.topo, values: days.map((d) => byDayTopo.get(d)?.spend || 0) },
  ];
  if (gEnabled()) investSeries.push({ name: "Google Ads", color: COLOR.google, values: days.map((d) => gByDay.get(d)?.cost || 0) });

  const resultSeries = [{ name: "Reservas (Meta)", color: COLOR.meta, values: days.map((d) => byDayAll.get(d)?.purchases || 0) }];
  if (gEnabled()) resultSeries.push({ name: "Conversões (Google)", color: COLOR.google, values: days.map((d) => gByDay.get(d)?.conversions || 0) });

  const charts = h("div", { class: "grid c3" },
    chartCard("Investimento por dia", "por plataforma e etapa do funil", investSeries, { labels, type: "bar", stacked: true, format: fmt.brl }),
    chartCard("Resultados por dia", "reservas e conversões", resultSeries, { labels, type: "bar", stacked: true }),
    chartCard("Custo por reserva, por dia", "gasto em conversão ÷ reservas do dia",
      [{ name: "Custo por reserva", color: COLOR.warn, values: days.map((d) => byDayCap.get(d)?.cost_per_purchase ?? null) }],
      { labels, type: "line", format: fmt.brl, target: T.cost_per_purchase }),
  );

  /* --- histórico mensal ---------------------------------------------------- */
  const months = groupBy((m.daily || []).map((r) => ({ ...r, month: r.date.slice(0, 7) })), "month");
  const monthsCap = groupBy((m.daily || []).filter((r) => isCaptacao(r.campaign_id)).map((r) => ({ ...r, month: r.date.slice(0, 7) })), "month");
  const gMonths = gEnabled() ? gGroupBy((state.google.daily || []).map((r) => ({ ...r, month: r.date.slice(0, 7) })), "month") : new Map();
  const monthKeys = Array.from(new Set([...months.keys(), ...gMonths.keys()])).sort();
  const years = Array.from(new Set(monthKeys.map((k) => k.slice(0, 4)))).sort().reverse();
  if (state.histYear !== "all" && !years.includes(state.histYear)) state.histYear = years[0] || "all";
  const showAllYears = state.histYear === "all" || years.length <= 1;
  const shownKeys = showAllYears ? monthKeys : monthKeys.filter((k) => k.startsWith(state.histYear));

  const yearSelect = years.length > 1
    ? h("label", { class: "year-filter" }, "Ano",
      h("select", {
        "aria-label": "Ano do histórico mensal",
        onchange: (e) => {
          state.histYear = e.target.value;
          renderExec();
          requestAnimationFrame(() => $$("#sec-exec .chart-card").forEach((c) => c._render && c._render()));
        },
      },
        ...years.map((y) => h("option", { value: y, text: y, selected: state.histYear === y ? "" : null })),
        h("option", { value: "all", text: "Todos os anos", selected: state.histYear === "all" ? "" : null })))
    : null;

  /* linha por mês + total do período mostrado */
  const totals = { spend: 0, meta: 0, google: 0, gconv: 0, purchases: 0, capSpend: 0, revenue: 0, carts: 0, conversations: 0, impressions: 0, clicks: 0 };
  const monthRowsEls = shownKeys.map((k) => {
    const a = months.get(k) || finish(emptyAgg());
    const c = monthsCap.get(k) || finish(emptyAgg());
    const gm = gMonths.get(k) || gFinish(gEmpty());
    const spend = a.spend + gm.cost;
    const rev = a.revenue + gm.conversions_value;
    const impressions = a.impressions + gm.impressions;
    const clicks = a.clicks + gm.clicks;
    const partial = k === last.slice(0, 7);
    totals.spend += spend; totals.meta += a.spend; totals.google += gm.cost; totals.gconv += gm.conversions;
    totals.purchases += a.purchases; totals.capSpend += c.spend; totals.revenue += rev;
    totals.carts += a.add_to_carts; totals.conversations += a.conversations;
    totals.impressions += impressions; totals.clicks += clicks;
    return h("tr", { class: partial ? "parcial" : "" },
      h("td", {}, `${MONTHS[+k.slice(5, 7) - 1]}${showAllYears ? " " + k.slice(0, 4) : ""} `, partial ? h("span", { class: "badge warn", text: "parcial" }) : null),
      h("td", { text: fmt.brl(spend) }), h("td", { text: fmt.brl(a.spend) }), h("td", { text: gEnabled() ? fmt.brl(gm.cost) : "—" }),
      gEnabled() ? h("td", { text: fmt.dec1(gm.conversions) }) : null,
      h("td", { text: fmt.int(a.purchases) }), h("td", { text: fmt.brl(c.cost_per_purchase) }),
      h("td", { text: rev > 0 ? fmt.brl(rev) : "—" }), h("td", { text: rev > 0 ? fmt.x(div(rev, spend)) : "—" }),
      h("td", { text: fmt.int(a.add_to_carts) }), h("td", { text: fmt.int(a.conversations) }),
      h("td", { text: fmt.int(impressions) }), h("td", { text: fmt.int(clicks) }),
      h("td", { text: fmt.pct(div(clicks * 100, impressions)) }), h("td", { text: fmt.brl(div(spend, clicks)) }));
  });
  const totalRow = shownKeys.length > 1
    ? h("tr", { class: "total" },
      h("td", { text: showAllYears ? `Total · ${years.length} anos` : `Total ${state.histYear}` }),
      h("td", { text: fmt.brl(totals.spend) }), h("td", { text: fmt.brl(totals.meta) }), h("td", { text: gEnabled() ? fmt.brl(totals.google) : "—" }),
      gEnabled() ? h("td", { text: fmt.dec1(totals.gconv) }) : null,
      h("td", { text: fmt.int(totals.purchases) }), h("td", { text: fmt.brl(div(totals.capSpend, totals.purchases)) }),
      h("td", { text: totals.revenue > 0 ? fmt.brl(totals.revenue) : "—" }), h("td", { text: totals.revenue > 0 ? fmt.x(div(totals.revenue, totals.spend)) : "—" }),
      h("td", { text: fmt.int(totals.carts) }), h("td", { text: fmt.int(totals.conversations) }),
      h("td", { text: fmt.int(totals.impressions) }), h("td", { text: fmt.int(totals.clicks) }),
      h("td", { text: fmt.pct(div(totals.clicks * 100, totals.impressions)) }), h("td", { text: fmt.brl(div(totals.spend, totals.clicks)) }))
    : null;

  const histTable = h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {},
      h("th", { text: "Mês" }), h("th", { text: "Investimento" }), h("th", { text: "Meta" }), h("th", { text: "Google" }),
      gEnabled() ? h("th", { text: "Conv. Google" }) : null,
      h("th", { text: "Reservas" }), h("th", { text: "Custo/reserva" }), h("th", { text: "Receita" }), h("th", { text: "ROAS" }),
      h("th", { text: "Carrinhos" }), h("th", { text: "Conversas" }), h("th", { text: "Impressões" }), h("th", { text: "Cliques" }), h("th", { text: "CTR" }), h("th", { text: "CPC" }))),
    h("tbody", {}, ...monthRowsEls, totalRow),
  ));

  /* --- onde está o resultado ----------------------------------------------- */
  const byAd = groupBy(rows, "ad_id");
  const adRows = Array.from(byAd.entries()).map(([id, a]) => ({ id, ad: idx.ads.get(id), agg: a, def: defFor(idx.campaignByAd.get(id)) })).filter((x) => x.ad);
  const best = adRows.filter((x) => x.def.kind === "lead" && resultsOf(x.agg, x.def) >= 1).sort((a, b) => costPerResult(a.agg, a.def) - costPerResult(b.agg, b.def)).slice(0, 6);
  const noReturn = adRows.filter((x) => x.def.kind === "lead" && resultsOf(x.agg, x.def) === 0 && x.agg.spend > 0).sort((a, b) => b.agg.spend - a.agg.spend).slice(0, 6);

  const byCamp = groupBy(rows, "campaign_id");
  const campRows = Array.from(byCamp.entries()).map(([id, a]) => ({ id, c: idx.campaigns.get(id), agg: a, def: defFor(id) })).filter((x) => x.c);
  const gByCamp = gGroupBy(gRows, "campaign_id");
  const gCampRows = Array.from(gByCamp.entries()).map(([id, a]) => ({ id, c: idx.gCampaigns.get(id), agg: a })).filter((x) => x.c);
  const offTarget = [
    ...campRows.map((x) => ({ name: x.c.name, plat: "Meta", spend: x.agg.spend, as: assess(x.agg, x.def), detail: `${x.def.label.toLowerCase()}: ${fmt.int(resultsOf(x.agg, x.def))}` })),
    ...gCampRows.map((x) => ({ name: x.c.name, plat: "Google", spend: x.agg.cost, as: gAssess(x.agg), detail: `conversões: ${fmt.dec1(x.agg.conversions)}` })),
  ].filter((x) => x.as.level === "crit" || x.as.level === "warn").sort((a, b) => b.spend - a.spend).slice(0, 6);

  const listItem = (rank, cls, thumb, name, sub, link) => h("div", { class: "list-item" },
    h("span", { class: `rank ${cls}`, text: rank }),
    thumb ? h("img", { class: "thumb", src: thumb, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null,
    h("div", { class: "txt" },
      link ? h("div", { class: "n" }, h("a", { href: link, target: "_blank", rel: "noopener noreferrer", text: name })) : h("div", { class: "n", text: name }),
      h("div", { class: "s", text: sub })),
  );
  const results = h("div", { class: "grid c3" },
    h("div", { class: "card" }, h("h3", {}, "🏆 Criativos mais eficientes"), h("div", { class: "muted", text: "menor custo por resultado nas campanhas de conversão" }),
      best.length ? h("div", { class: "list" }, ...best.map((x, i) => listItem(i + 1, "good", thumbOf(x.ad), x.ad.name,
        `${fmt.brl(costPerResult(x.agg, x.def))} por ${x.def.unit} · ${plural(resultsOf(x.agg, x.def), x.def.unit)} · ${fmt.brl(x.agg.spend)}`, adLink(x.ad))))
        : h("div", { class: "empty", text: "Ainda não há criativos com resultado no período." })),
    h("div", { class: "card" }, h("h3", {}, "🔥 Dinheiro sem retorno"),
      h("div", { class: "muted", text: `${fmt.brl(sum(noReturn, (x) => x.agg.spend))} em ${noReturn.length} criativo${noReturn.length === 1 ? "" : "s"} de conversão sem nenhum resultado` }),
      noReturn.length ? h("div", { class: "list" }, ...noReturn.map((x, i) => listItem(i + 1, "bad", thumbOf(x.ad), x.ad.name,
        `${fmt.brl(x.agg.spend)} · zero ${x.def.unit} · ${fmt.int(x.agg.link_clicks)} cliques`, adLink(x.ad))))
        : h("div", { class: "empty", text: "Nenhum criativo de conversão gastando sem resultado." })),
    h("div", { class: "card" }, h("h3", {}, "⚠️ Campanhas fora da meta"),
      h("div", { class: "muted", text: `${fmt.brl(sum(offTarget, (x) => x.spend))} em ${campWord(offTarget.length)}` }),
      offTarget.length ? h("div", { class: "list" }, ...offTarget.map((x, i) => listItem(i + 1, x.as.level === "crit" ? "bad" : "", null,
        `${x.name}`, `${x.plat} · ${fmt.brl(x.spend)} · ${x.detail} · ${x.as.text}`)))
        : h("div", { class: "empty", text: "Todas as campanhas com meta estão dentro do esperado." })),
  );

  /* --- qual ação tomar ----------------------------------------------------- */
  const alerts = buildAlerts({ rows, cap, prevCap, all, prevAll, campRows, gCampRows, adRows, projection, budget, monthSpend, capLeft, g, gPrev });
  const actions = h("div", { class: "alerts" }, ...(alerts.length
    ? alerts.map((a) => h("div", { class: `alert ${a.level}` }, h("div", { class: "t" }, badge(a.level, levelWord(a.level)), a.title), a.detail ? h("div", { class: "d", text: a.detail }) : null))
    : [h("div", { class: "empty", text: "Sem alertas para o período." })]));

  sec.append(
    block("Controle de investimento", "ciclo mensal e distribuição do gasto entre plataformas", invest),
    block("O que está acontecendo", `volume e eficiência · ${fmt.date(state.since)} a ${fmt.date(state.until)}`, kpis, bars),
    block("Como está evoluindo", "dia a dia do período selecionado", charts),
    blockWith("Histórico mensal", "mês a mês — independe do filtro de período do topo", yearSelect, histTable,
      h("div", { class: "faint", text: "“Reservas” são as compras registradas pelo pixel do site. Campanhas de topo de funil (tráfego, alcance, engajamento) entram no investimento total, mas não no custo por reserva." })),
    block("Onde está o resultado", "e onde o dinheiro está parado", results),
    block("Qual ação tomar", "alertas priorizados por dinheiro em jogo", actions),
  );
}

function buildAlerts({ rows, cap, prevCap, all, prevAll, campRows, gCampRows, adRows, projection, budget, monthSpend, capLeft, g }) {
  const T = state.targets; const out = [];
  const withAs = campRows.map((x) => ({ ...x, as: assess(x.agg, x.def) }));
  const gWithAs = gCampRows.map((x) => ({ ...x, as: gAssess(x.agg) }));

  if (ok(capLeft) && capLeft <= 0) {
    out.push({ level: "crit", title: "Limite de gasto da conta do Meta atingido — os anúncios param de rodar", detail: "Ajustar ou remover o limite de gasto da conta no Gerenciador de Anúncios (Configurações → Faturamento → Limite de gasto da conta)." });
  } else if (ok(capLeft) && capLeft < 1000) {
    out.push({ level: "warn", title: `Limite de gasto da conta do Meta: restam ${fmt.brl(capLeft)}`, detail: "Quando o limite é atingido a entrega para imediatamente. Aumentar ou zerar o limite em Faturamento → Limite de gasto da conta." });
  }

  const crit = withAs.filter((x) => x.as.level === "crit");
  const warn = withAs.filter((x) => x.as.level === "warn");
  const okc = withAs.filter((x) => x.as.level === "ok");
  if (crit.length) {
    out.push({ level: "crit", title: `Meta: ${fmt.brl(sum(crit, (x) => x.agg.spend))} em ${campWord(crit.length)} em situação crítica`,
      detail: crit.sort((a, b) => b.agg.spend - a.agg.spend).slice(0, 3).map((x) => `${x.c.name} (${fmt.brl(x.agg.spend)}, ${x.as.text.toLowerCase()})`).join(" · ") });
  }
  if (warn.length) {
    out.push({ level: "warn", title: `Meta: ${fmt.brl(sum(warn, (x) => x.agg.spend))} em ${campWord(warn.length)} acima da meta`,
      detail: warn.sort((a, b) => b.agg.spend - a.agg.spend).slice(0, 3).map((x) => `${x.c.name} (${x.def.label.toLowerCase()} a ${fmt.brl(costPerResult(x.agg, x.def))})`).join(" · ") });
  }
  const gCrit = gWithAs.filter((x) => x.as.level === "crit");
  if (gCrit.length) {
    out.push({ level: "crit", title: `Google: ${fmt.brl(sum(gCrit, (x) => x.agg.cost))} em ${campWord(gCrit.length)} em situação crítica`,
      detail: gCrit.sort((a, b) => b.agg.cost - a.agg.cost).slice(0, 3).map((x) => `${x.c.name} (${fmt.brl(x.agg.cost)}, ${x.as.text.toLowerCase()})`).join(" · ") });
  }

  const last7 = rowsIn(addDays(state.until, -6), state.until);
  const spent7 = groupBy(last7, "campaign_id");
  const idle = (state.meta.campaigns || []).filter((c) => c.effective_status === "ACTIVE" && !(spent7.get(c.id)?.spend > 0));
  if (idle.length) {
    out.push({ level: "warn", title: `${campWord(idle.length)} ativa${idle.length === 1 ? "" : "s"} sem nenhuma entrega nos últimos 7 dias`,
      detail: idle.map((c) => c.name).join(" · ") + ". Campanha ligada que não gasta costuma estar com público esgotado, anúncio reprovado ou orçamento baixo demais para entrar no leilão." });
  }

  const noRet = adRows.filter((x) => x.def.kind === "lead" && resultsOf(x.agg, x.def) === 0 && x.agg.spend >= (T.min_spend_for_alert || 30));
  if (noRet.length) {
    out.push({ level: "crit", title: `${fmt.brl(sum(noRet, (x) => x.agg.spend))} em ${noRet.length} criativo${noRet.length === 1 ? "" : "s"} de conversão sem nenhum resultado`,
      detail: "Pausar e substituir por variações do criativo que melhor converte. " + noRet.slice(0, 3).map((x) => `${x.ad.name} (${fmt.brl(x.agg.spend)})`).join(" · ") });
  }

  if (ok(cap.cost_per_purchase) && ok(prevCap.cost_per_purchase) && prevCap.purchases >= 2 && cap.cost_per_purchase > prevCap.cost_per_purchase * 1.25) {
    out.push({ level: "warn", title: `Custo por reserva subiu ${nfDec1.format(((cap.cost_per_purchase / prevCap.cost_per_purchase) - 1) * 100)}% vs. período anterior`,
      detail: `${fmt.brl(prevCap.cost_per_purchase)} → ${fmt.brl(cap.cost_per_purchase)}. Verificar saturação de público (frequência), troca de criativo ou queda de CTR.` });
  }
  if (all.add_to_carts >= 5 && all.purchases === 0) {
    out.push({ level: "crit", title: `${fmt.int(all.add_to_carts)} adições ao carrinho e nenhuma reserva concluída`,
      detail: "O anúncio está trazendo interesse, mas o checkout não fecha. Conferir disponibilidade, preço, formas de pagamento e se o evento de compra do pixel está disparando." });
  }
  const highFreq = campRows.filter((x) => x.agg.frequency > (T.frequency_max || 2.5) && x.agg.spend > 20 && x.def.kind !== "awareness");
  if (highFreq.length) {
    out.push({ level: "warn", title: `Frequência acima de ${fmt.dec1(T.frequency_max)} em ${campWord(highFreq.length)}`,
      detail: "Público saturando: ampliar segmentação ou renovar criativos. " + highFreq.map((x) => `${x.c.name} (${fmt.dec(x.agg.frequency)}×)`).join(" · ") });
  }
  const lowCtr = campRows.filter((x) => x.def.kind !== "awareness" && x.agg.impressions > 1000 && x.agg.ctr < (T.ctr_min || 1));
  if (lowCtr.length) {
    out.push({ level: "warn", title: `CTR abaixo de ${fmt.pct(T.ctr_min || 1)} em ${campWord(lowCtr.length)}`,
      detail: "Criativo/gancho pouco atrativo para o público. " + lowCtr.slice(0, 4).map((x) => `${x.c.name} (${fmt.pct(x.agg.ctr)})`).join(" · ") });
  }
  if (gEnabled()) {
    const lostBudget = (state.google.campaigns || []).filter((c) => ok(c.lost_is_budget) && c.lost_is_budget >= 10);
    if (lostBudget.length) {
      out.push({ level: "warn", title: `Google: ${campWord(lostBudget.length)} ${lostBudget.length === 1 ? "perde" : "perdem"} impressões por falta de orçamento`,
        detail: lostBudget.slice(0, 3).map((c) => `${c.name} (${fmt.pct(c.lost_is_budget)} de perda por orçamento)`).join(" · ") + ". Se o custo por conversão está na meta, aumentar o orçamento diário." });
    }
    const wasteTerms = (state.google.search_terms || []).filter((t) => t.cost >= (T.min_spend_for_alert || 30) && !t.conversions);
    if (wasteTerms.length) {
      out.push({ level: "warn", title: `Google: ${fmt.brl(sum(wasteTerms, (t) => t.cost))} em termos de pesquisa sem conversão (30 dias)`,
        detail: "Avaliar como palavra-chave negativa: " + wasteTerms.slice(0, 5).map((t) => `“${t.term}” (${fmt.brl(t.cost)})`).join(" · ") });
    }
  } else {
    out.push({ level: "warn", title: "Google Ads ainda não está conectado ao dashboard",
      detail: `Conta ${state.config.google_ads.customer_id} já existe. Falta cadastrar as credenciais da Google Ads API nos segredos do repositório — o passo a passo está na aba Google Ads.` });
  }
  if (budget && projection > budget * 1.15) {
    out.push({ level: "crit", title: `Projeção do mês (${fmt.brl(projection)}) estoura a verba de ${fmt.brl(budget)}`,
      detail: `Já gastos ${fmt.brl(monthSpend)}. Reduzir primeiro o orçamento diário das campanhas de topo de funil.` });
  } else if (budget && projection < budget * 0.7 && rows.length) {
    out.push({ level: "warn", title: `Projeção do mês (${fmt.brl(projection)}) fica bem abaixo da verba de ${fmt.brl(budget)}`,
      detail: "Há espaço para escalar as campanhas que estão na meta ou testar novos criativos." });
  }
  if (okc.length) {
    out.push({ level: "ok", title: `${campWord(okc.length)} do Meta dentro da meta`,
      detail: okc.map((x) => `${x.c.name} (${x.def.label.toLowerCase()} a ${fmt.brl(costPerResult(x.agg, x.def))}${x.def.per ? "/mil" : ""}, ${fmt.int(resultsOf(x.agg, x.def))} resultados)`).join(" · ") });
  }
  const gOk = gWithAs.filter((x) => x.as.level === "ok");
  if (gOk.length) {
    out.push({ level: "ok", title: `${campWord(gOk.length)} do Google dentro da meta`,
      detail: gOk.map((x) => `${x.c.name} (${fmt.dec1(x.agg.conversions)} conversões a ${fmt.brl(x.agg.cpa)})`).join(" · ") });
  }
  return out;
}

/* ======================================================= seção: Meta Ads */
function renderMeta() {
  const sec = $("#sec-meta"); sec.replaceChildren();
  const m = state.meta; const T = state.targets;
  const rows = rowsIn(state.since, state.until), prevRows = rowsIn(state.prevSince, state.prevUntil);
  const byCamp = groupBy(rows, "campaign_id"), prevByCamp = groupBy(prevRows, "campaign_id");
  const cap = aggregate(rows.filter((r) => isCaptacao(r.campaign_id)));
  const campRows = m.campaigns.map((c) => ({ c, agg: byCamp.get(c.id) || finish(emptyAgg()), prev: prevByCamp.get(c.id), def: defFor(c.id) }))
    .filter((x) => x.agg.spend > 0 || x.c.effective_status === "ACTIVE")
    .sort((a, b) => b.agg.spend - a.agg.spend);
  const withSpend = campRows.filter((x) => x.agg.spend > 0);
  const onTarget = withSpend.filter((x) => assess(x.agg, x.def).level === "ok");
  const bestCap = withSpend.filter((x) => x.def.kind === "lead" && resultsOf(x.agg, x.def) > 0).sort((a, b) => costPerResult(a.agg, a.def) - costPerResult(b.agg, b.def))[0];

  const head = h("div", { class: "grid c4" },
    platformBar("meta", "Meta Ads · conversão", `meta ${fmt.brl(T.cost_per_purchase)} por reserva`, [
      [fmt.brl(cap.spend), "investido em conversão"],
      [fmt.int(cap.purchases), "reservas"],
      [fmt.brl(cap.cost_per_purchase), "custo por reserva"],
    ], cap.spend > 0 ? assess(cap, DEF.purchase).level : null),
    tile({ label: "Campanhas", value: fmt.int(campRows.length), sub: `${withSpend.length} com investimento no período` }),
    tile({ label: "Dentro da meta", value: fmt.int(onTarget.length), sub: h("span", {}, `de ${withSpend.length}`, withSpend.length ? badge(onTarget.length === withSpend.length ? "ok" : onTarget.length ? "warn" : "crit", `${Math.round((onTarget.length / withSpend.length) * 100)}%`) : null) }),
    tile({ label: "Receita e ROAS", value: fmt.brl(cap.revenue), sub: `ROAS ${fmt.x(cap.roas)} · ${fmt.int(cap.add_to_carts)} carrinhos` }),
  );

  const table = h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { text: "Status" }), h("th", { class: "l", text: "Campanha" }), h("th", { text: "Orçam./dia" }), h("th", { text: "Result." }),
      h("th", { text: "Custo/result." }), h("th", { text: "Receita" }), h("th", { text: "ROAS" }), h("th", { text: "Impress." }), h("th", { text: "Alcance" }),
      h("th", { text: "CPM" }), h("th", { text: "CTR" }), h("th", { text: "Cliques" }), h("th", { text: "CPC" }), h("th", { text: "Gasto" }), h("th", { class: "l", text: "Ação" }))),
    h("tbody", {}, ...campRows.map((x) => campaignRow(x))),
  ));

  const byAdset = groupBy(rows, "adset_id"), prevByAdset = groupBy(prevRows, "adset_id");
  const groups = campRows.map((x) => {
    const sets = m.adsets.filter((s) => s.campaign_id === x.c.id)
      .map((s) => ({ c: s, agg: byAdset.get(s.id) || finish(emptyAgg()), prev: prevByAdset.get(s.id), def: idx.defByAdset.get(s.id) || x.def, parent: x.c }))
      .filter((y) => y.agg.spend > 0 || y.c.effective_status === "ACTIVE")
      .sort((a, b) => b.agg.spend - a.agg.spend);
    if (!sets.length) return null;
    return h("details", { open: x === campRows[0] ? "" : null },
      h("summary", { class: "group-head" }, h("span", {}, x.c.name),
        h("small", { text: `${sets.length} conjunto${sets.length === 1 ? "" : "s"} · ${fmt.brl(x.agg.spend)} · ${x.def.label.toLowerCase()}: ${fmt.int(resultsOf(x.agg, x.def))} · ${sets.filter((s) => assess(s.agg, s.def).level === "ok").length} na meta` })),
      h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "Status" }), h("th", { class: "l", text: "Conjunto" }), h("th", { text: "Orçam./dia" }), h("th", { text: "Result." }),
        h("th", { text: "Custo/result." }), h("th", { text: "Receita" }), h("th", { text: "ROAS" }), h("th", { text: "Impress." }), h("th", { text: "Alcance" }),
        h("th", { text: "CPM" }), h("th", { text: "CTR" }), h("th", { text: "Cliques" }), h("th", { text: "CPC" }), h("th", { text: "Gasto" }), h("th", { class: "l", text: "Ação" }))),
        h("tbody", {}, ...sets.map((y) => campaignRow(y, true)))),
    );
  }).filter(Boolean);

  const bd = m.breakdowns || {};
  const bdCards = [];
  const bdTable = (title, sub, label, list) => h("div", { class: "table-wrap" },
    h("div", { class: "group-head" }, h("span", { text: title }), h("small", { text: sub })),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: label }), h("th", { text: "Gasto" }), h("th", { text: "Reservas" }), h("th", { text: "Custo/reserva" }), h("th", { text: "Carrinhos" }), h("th", { text: "CTR" }))),
      h("tbody", {}, ...list.map(([k, a]) => h("tr", {}, h("td", { text: k }), h("td", { text: fmt.brl(a.spend) }), h("td", { text: fmt.int(a.purchases) }),
        h("td", { text: fmt.brl(a.cost_per_purchase) }), h("td", { text: fmt.int(a.add_to_carts) }), h("td", { text: fmt.pct(a.ctr) }))))));
  const collect = (arr, keyFn) => {
    const map = new Map();
    for (const r of arr) { const k = keyFn(r); if (!map.has(k)) map.set(k, emptyAgg()); addRow(map.get(k), r); }
    return Array.from(map.entries()).map(([k, a]) => [k, finish(a)]).sort((a, b) => b[1].spend - a[1].spend).slice(0, 10);
  };
  if (bd.age_gender?.length) bdCards.push(bdTable("Idade e gênero", "últimos 30 dias · todas as campanhas", "Faixa", collect(bd.age_gender, (r) => `${r.age} · ${r.gender === "female" ? "F" : r.gender === "male" ? "M" : "?"}`)));
  if (bd.region?.length) bdCards.push(bdTable("Região (estado)", "últimos 30 dias", "Região", collect(bd.region, (r) => r.region || "—")));
  if (bd.platform_position?.length) bdCards.push(bdTable("Posicionamento", "últimos 30 dias", "Posicionamento", collect(bd.platform_position, (r) => `${r.publisher_platform || "?"} · ${(r.platform_position || "").replace(/_/g, " ")}`)));

  sec.append(
    block("Meta Ads", `${fmt.date(state.since)} a ${fmt.date(state.until)} · meta de ${fmt.brl(T.cost_per_purchase)} por reserva`, head, table),
    block("Conjuntos por campanha", "orçamento é definido no conjunto quando a campanha não usa CBO",
      ...(groups.length ? groups.map((g) => h("div", { class: "table-wrap" }, g)) : [h("div", { class: "empty", text: "Sem conjuntos com dados no período." })])),
    bdCards.length ? block("Quem está respondendo", "distribuição do gasto e dos resultados", h("div", { class: "grid c3" }, ...bdCards)) : null,
  );
}
function campaignRow(x, isAdset = false) {
  const { c, agg, prev, def } = x;
  const as = assess(agg, def);
  const results = resultsOf(agg, def);
  const prevResults = prev ? resultsOf(prev, def) : null;
  const goal = isAdset ? c.optimization_goal : null;
  const tg = isAdset ? c.targeting : null;
  const revenue = valueOf(agg, def) || agg.revenue;
  const nameCell = h("td", { class: "name" },
    h("div", { class: "n", text: c.name }),
    h("div", { class: "s", text: isAdset ? `${x.parent?.name || ""}${goal ? " · " + (GOAL_DEF[goal]?.label || goal) : ""}${c.custom_event ? " · evento " + c.custom_event.toLowerCase().replace(/_/g, " ") : ""}` : `${OBJECTIVE_LABEL[c.objective] || c.objective || ""} · ${def.label}` }),
    tg ? h("div", {}, tg.age_min ? h("span", { class: "tag", text: `${tg.age_min}–${tg.age_max || "65+"}` }) : null,
      tg.advantage_audience ? h("span", { class: "tag", text: "Advantage+" }) : null,
      ...(tg.geo || []).slice(0, 4).map((g) => h("span", { class: "tag", text: g }))) : null,
  );
  const budget = c.daily_budget > 0 ? fmt.brl(c.daily_budget) : c.lifetime_budget > 0 ? `${fmt.brl(c.lifetime_budget)} total` : "—";
  return h("tr", {},
    h("td", {}, statusBadge(c.effective_status, c.status)),
    nameCell,
    h("td", { text: budget }),
    h("td", {}, h("b", { text: fmt.int(results) }), " ", prevResults != null ? deltaBadge(results, prevResults) : null),
    h("td", {}, cprCell(agg, def)),
    h("td", { text: revenue > 0 ? fmt.brl(revenue) : "—" }),
    h("td", { text: revenue > 0 ? fmt.x(div(revenue, agg.spend)) : "—" }),
    h("td", { text: fmt.int(agg.impressions) }),
    h("td", { text: fmt.int(agg.reach) }),
    h("td", { text: fmt.brl(agg.cpm) }),
    h("td", { text: fmt.pct(agg.ctr) }),
    h("td", { text: fmt.int(agg.clicks) }),
    h("td", { text: fmt.brl(agg.cpc) }),
    h("td", { text: fmt.brl(agg.spend) }),
    h("td", { class: "act-cell" }, h("div", { class: "act" }, badge(as.level, levelWord(as.level)), h("span", { text: as.text }))),
  );
}

/* ===================================================== seção: Google Ads */
function renderGoogle() {
  const sec = $("#sec-google"); sec.replaceChildren();
  const cfg = state.config.google_ads || {};
  const T = state.targets;

  if (!gEnabled()) {
    const reason = state.google?.reason;
    sec.append(
      block("Google Ads", `conta ${cfg.customer_id}`,
        h("div", { class: "placeholder" },
          h("b", { text: "Google Ads ainda não está conectado ao dashboard" }),
          h("span", { text: reason ? `Motivo da última tentativa: ${reason}` : "O coletor ainda não encontrou credenciais da Google Ads API." }),
          h("span", { class: "faint", text: `${T.google_monthly > 0 ? "Verba prevista: " + fmt.brl(T.google_monthly) + "/mês. " : "Verba mensal ainda não definida (ajustável em Metas, no menu lateral). "}Assim que as credenciais forem cadastradas, esta seção mostra campanhas, grupos de anúncios, palavras-chave, termos de pesquisa, dispositivos e localidades.` }))),
      block("Como conectar", "uma vez só — depois a atualização é automática 3x por dia",
        h("div", { class: "setup" },
          h("div", { class: "card" },
            h("h3", { text: "1. Na conta administradora (MCC)" }),
            h("ol", {},
              h("li", {}, "Vincular a conta ", h("code", { text: cfg.customer_id }), " ao MCC da Steink (Ferramentas → Acesso e segurança → Gerenciadores)."),
              h("li", {}, "Pedir o ", h("b", { text: "token de desenvolvedor" }), " em Ferramentas → Configuração da API. O nível básico já atende."),
              h("li", {}, "Anotar o ID do MCC (10 dígitos) — vira ", h("code", { text: "GOOGLE_ADS_LOGIN_CUSTOMER_ID" }), "."))),
          h("div", { class: "card" },
            h("h3", { text: "2. No Google Cloud" }),
            h("ol", {},
              h("li", {}, "Criar um projeto e ativar a ", h("b", { text: "Google Ads API" }), "."),
              h("li", {}, "Criar credencial OAuth do tipo ", h("b", { text: "App para computador" }), " → guarda ", h("code", { text: "CLIENT_ID" }), " e ", h("code", { text: "CLIENT_SECRET" }), "."),
              h("li", {}, "Gerar o ", h("code", { text: "REFRESH_TOKEN" }), " com o escopo ", h("code", { text: "https://www.googleapis.com/auth/adwords" }), " (OAuth Playground ou script oficial)."))),
          h("div", { class: "card" },
            h("h3", { text: "3. No repositório do dashboard" }),
            h("ol", {},
              h("li", {}, "Settings → Secrets and variables → Actions → New repository secret."),
              h("li", {}, "Cadastrar: ", h("code", { text: "GOOGLE_ADS_DEVELOPER_TOKEN" }), ", ", h("code", { text: "GOOGLE_ADS_CLIENT_ID" }), ", ", h("code", { text: "GOOGLE_ADS_CLIENT_SECRET" }), ", ", h("code", { text: "GOOGLE_ADS_REFRESH_TOKEN" }), ", ", h("code", { text: "GOOGLE_ADS_LOGIN_CUSTOMER_ID" }), "."),
              h("li", {}, "Rodar Actions → “Atualizar dashboard” → Run workflow."))),
          h("div", { class: "card" },
            h("h3", { text: "4. Conferir as conversões" }),
            h("ol", {},
              h("li", {}, "Na conta, marcar como ", h("b", { text: "conversão principal" }), " só o que é reserva/contato de verdade."),
              h("li", {}, "O dashboard usa ", h("code", { text: "conversions" }), " (principais) para custo por conversão e ", h("code", { text: "all_conversions" }), " como referência."),
              h("li", {}, "A meta de custo por conversão fica no menu lateral, em Metas."))))),
    );
    return;
  }

  const g = state.google;
  const rows = gRowsIn(state.since, state.until), prevRows = gRowsIn(state.prevSince, state.prevUntil);
  const all = gAggregate(rows), prev = gAggregate(prevRows);
  const byCamp = gGroupBy(rows, "campaign_id"), prevByCamp = gGroupBy(prevRows, "campaign_id");
  const campRows = (g.campaigns || []).map((c) => ({ c, agg: byCamp.get(c.id) || gFinish(gEmpty()), prev: prevByCamp.get(c.id) }))
    .filter((x) => x.agg.cost > 0 || x.c.status === "ENABLED")
    .sort((a, b) => b.agg.cost - a.agg.cost);
  const withSpend = campRows.filter((x) => x.agg.cost > 0);
  const onTarget = withSpend.filter((x) => gAssess(x.agg).level === "ok");

  const head = h("div", { class: "grid c4" },
    platformBar("google", "Google Ads", `meta ${fmt.brl(T.google_cost_per_conversion)} por conversão`, [
      [fmt.brl(all.cost), "investido"],
      [fmt.dec1(all.conversions), "conversões"],
      [fmt.brl(all.cpa), "custo por conversão"],
    ], all.cost > 0 ? gAssess(all).level : null),
    tile({ label: "Campanhas", value: fmt.int(campRows.length), sub: `${withSpend.length} com investimento no período` }),
    tile({ label: "Dentro da meta", value: fmt.int(onTarget.length), sub: h("span", {}, `de ${withSpend.length}`, withSpend.length ? badge(onTarget.length === withSpend.length ? "ok" : onTarget.length ? "warn" : "crit", `${Math.round((onTarget.length / withSpend.length) * 100)}%`) : null) }),
    tile({ label: "Cliques e CTR", value: fmt.int(all.clicks), delta: deltaBadge(all.clicks, prev.clicks), sub: `CTR ${fmt.pct(all.ctr)} · CPC ${fmt.brl(all.cpc)}` }),
  );

  const days = []; for (let d = state.since; d <= state.until; d = addDays(d, 1)) days.push(d);
  const byDay = gGroupBy(rows, "date");
  const charts = h("div", { class: "grid c3" },
    chartCard("Investimento por dia", "Google Ads", [{ name: "Investimento", color: COLOR.google, values: days.map((d) => byDay.get(d)?.cost || 0) }], { labels: days.map(fmt.dm), type: "bar", format: fmt.brl }),
    chartCard("Conversões por dia", "conversões principais", [{ name: "Conversões", color: COLOR.good, values: days.map((d) => byDay.get(d)?.conversions || 0) }], { labels: days.map(fmt.dm), type: "bar" }),
    chartCard("Custo por conversão, por dia", "", [{ name: "Custo por conversão", color: COLOR.warn, values: days.map((d) => byDay.get(d)?.cpa ?? null) }], { labels: days.map(fmt.dm), type: "line", format: fmt.brl, target: T.google_cost_per_conversion }),
  );

  const table = h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", { text: "Status" }), h("th", { class: "l", text: "Campanha" }), h("th", { text: "Orçam./dia" }), h("th", { text: "Conversões" }),
      h("th", { text: "Custo/conv." }), h("th", { text: "Receita" }), h("th", { text: "ROAS" }), h("th", { text: "Impress." }), h("th", { text: "Cliques" }),
      h("th", { text: "CTR" }), h("th", { text: "CPC" }), h("th", { text: "Parc. impr." }), h("th", { text: "Gasto" }), h("th", { class: "l", text: "Ação" }))),
    h("tbody", {}, ...campRows.map(({ c, agg, prev: p }) => {
      const as = gAssess(agg);
      return h("tr", {},
        h("td", {}, statusBadge(c.status)),
        h("td", { class: "name" }, h("div", { class: "n", text: c.name }),
          h("div", { class: "s", text: `${GOOGLE_CHANNEL[c.channel_type] || c.channel_type || ""}${c.bidding_strategy_type ? " · " + c.bidding_strategy_type.toLowerCase().replace(/_/g, " ") : ""}` }),
          ok(c.lost_is_budget) && c.lost_is_budget >= 10 ? h("div", { class: "hl", text: `Perde ${fmt.pct(c.lost_is_budget)} das impressões por orçamento` }) : null),
        h("td", { text: c.daily_budget > 0 ? fmt.brl(c.daily_budget) : "—" }),
        h("td", {}, h("b", { text: fmt.dec1(agg.conversions) }), " ", p ? deltaBadge(agg.conversions, p.conversions) : null),
        h("td", {}, gCprCell(agg)),
        h("td", { text: agg.conversions_value > 0 ? fmt.brl(agg.conversions_value) : "—" }),
        h("td", { text: agg.conversions_value > 0 ? fmt.x(agg.roas) : "—" }),
        h("td", { text: fmt.int(agg.impressions) }),
        h("td", { text: fmt.int(agg.clicks) }),
        h("td", { text: fmt.pct(agg.ctr) }),
        h("td", { text: fmt.brl(agg.cpc) }),
        h("td", { text: ok(c.impression_share) ? fmt.pct(c.impression_share) : "—" }),
        h("td", { text: fmt.brl(agg.cost) }),
        h("td", { class: "act-cell" }, h("div", { class: "act" }, badge(as.level, levelWord(as.level)), h("span", { text: as.text }))));
    })),
  ));

  /* grupos de anúncios */
  const byAg = gGroupBy(gRowsIn(state.since, state.until, g.daily_ad_groups || []), "ad_group_id");
  const agGroups = campRows.map((x) => {
    const list = (g.ad_groups || []).filter((a) => a.campaign_id === x.c.id)
      .map((a) => ({ a, agg: byAg.get(a.id) || gFinish(gEmpty()) }))
      .filter((y) => y.agg.cost > 0 || y.a.status === "ENABLED")
      .sort((a, b) => b.agg.cost - a.agg.cost);
    if (!list.length) return null;
    return h("div", { class: "table-wrap" }, h("details", { open: x === campRows[0] ? "" : null },
      h("summary", { class: "group-head" }, h("span", {}, x.c.name),
        h("small", { text: `${list.length} grupo${list.length === 1 ? "" : "s"} · ${fmt.brl(x.agg.cost)} · ${fmt.dec1(x.agg.conversions)} conversões` })),
      h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "Status" }), h("th", { class: "l", text: "Grupo de anúncios" }), h("th", { text: "Conversões" }),
        h("th", { text: "Custo/conv." }), h("th", { text: "Impress." }), h("th", { text: "Cliques" }), h("th", { text: "CTR" }), h("th", { text: "CPC" }), h("th", { text: "Gasto" }), h("th", { class: "l", text: "Ação" }))),
        h("tbody", {}, ...list.map(({ a, agg }) => {
          const as = gAssess(agg);
          return h("tr", {}, h("td", {}, statusBadge(a.status)),
            h("td", { class: "name" }, h("div", { class: "n", text: a.name }), h("div", { class: "s", text: (a.type || "").toLowerCase().replace(/_/g, " ") })),
            h("td", { text: fmt.dec1(agg.conversions) }), h("td", {}, gCprCell(agg)),
            h("td", { text: fmt.int(agg.impressions) }), h("td", { text: fmt.int(agg.clicks) }), h("td", { text: fmt.pct(agg.ctr) }),
            h("td", { text: fmt.brl(agg.cpc) }), h("td", { text: fmt.brl(agg.cost) }),
            h("td", { class: "act-cell" }, h("div", { class: "act" }, badge(as.level, levelWord(as.level)), h("span", { text: as.text }))));
        }))),
    ));
  }).filter(Boolean);

  /* palavras-chave e termos */
  const comEntrega = (x) => x.cost > 0 || x.clicks > 0 || x.impressions > 0;
  const kwRows = (g.keywords || []).filter(comEntrega).slice(0, 25);
  const qsLevel = (q) => (!ok(q) ? "" : q >= 7 ? "good" : q >= 5 ? "warn" : "crit");
  const kwTable = kwRows.length ? h("div", { class: "table-wrap" },
    h("div", { class: "group-head" }, h("span", { text: "Palavras-chave" }), h("small", { text: "últimos 30 dias · maiores gastos" })),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", { class: "l", text: "Palavra-chave" }), h("th", { text: "Qualidade" }), h("th", { text: "Conversões" }),
      h("th", { text: "Custo/conv." }), h("th", { text: "Impress." }), h("th", { text: "Cliques" }), h("th", { text: "CTR" }), h("th", { text: "CPC" }), h("th", { text: "Gasto" }))),
      h("tbody", {}, ...kwRows.map((k) => {
        const a = gFinish(gAdd(gEmpty(), k));
        return h("tr", {},
          h("td", { class: "name" }, h("div", { class: "n kw", text: k.text || "—" }),
            h("div", { class: "s", text: `${(k.match_type || "").toLowerCase()} · ${idx.gCampaigns.get(k.campaign_id)?.name || ""}` })),
          h("td", {}, ok(k.quality_score) ? h("span", { class: `qs ${qsLevel(k.quality_score)}`, text: k.quality_score }) : "—"),
          h("td", { text: fmt.dec1(a.conversions) }), h("td", { text: fmt.brl(a.cpa) }), h("td", { text: fmt.int(a.impressions) }),
          h("td", { text: fmt.int(a.clicks) }), h("td", { text: fmt.pct(a.ctr) }), h("td", { text: fmt.brl(a.cpc) }), h("td", { text: fmt.brl(a.cost) }));
      }))) ) : null;

  const stRows = (g.search_terms || []).filter(comEntrega).slice(0, 25);
  const stTable = stRows.length ? h("div", { class: "table-wrap" },
    h("div", { class: "group-head" }, h("span", { text: "Termos de pesquisa" }), h("small", { text: "últimos 30 dias · o que as pessoas digitaram" })),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", { class: "l", text: "Termo" }), h("th", { text: "Conversões" }), h("th", { text: "Custo/conv." }),
      h("th", { text: "Cliques" }), h("th", { text: "CTR" }), h("th", { text: "Gasto" }), h("th", { class: "l", text: "Leitura" }))),
      h("tbody", {}, ...stRows.map((t) => {
        const a = gFinish(gAdd(gEmpty(), t));
        const waste = !a.conversions && a.cost >= (T.min_spend_for_alert || 30);
        return h("tr", {},
          h("td", { class: "name" }, h("div", { class: "n kw", text: t.term || "—" }), h("div", { class: "s", text: idx.gCampaigns.get(t.campaign_id)?.name || "" })),
          h("td", { text: fmt.dec1(a.conversions) }), h("td", { text: fmt.brl(a.cpa) }), h("td", { text: fmt.int(a.clicks) }),
          h("td", { text: fmt.pct(a.ctr) }), h("td", { text: fmt.brl(a.cost) }),
          h("td", { class: "act-cell" }, h("div", { class: "act" }, badge(waste ? "crit" : a.conversions ? "ok" : "neutral", waste ? "negativar" : a.conversions ? "converte" : "observar"))));
      }))) ) : null;

  /* anúncios, dispositivos e localidades */
  const adsRows = (g.ads || []).filter(comEntrega).slice(0, 12);
  const adsCards = adsRows.length ? h("div", { class: "cards" }, ...adsRows.map((ad) => {
    const a = gFinish(gAdd(gEmpty(), ad));
    const as = gAssess(a);
    return h("div", { class: `creative ${as.level}` }, h("div", { class: "body" },
      h("div", { class: "badges" }, statusBadge(ad.status), badge(as.level, levelWord(as.level)),
        ad.strength ? h("span", { class: "badge neutral", text: `força: ${String(ad.strength).toLowerCase()}` }) : null),
      h("div", { class: "n", text: (ad.headlines || [])[0] || ad.name || `Anúncio ${ad.id}` }),
      h("div", { class: "s", text: `${idx.gCampaigns.get(ad.campaign_id)?.name || ""} · ${idx.gAdGroups.get(ad.ad_group_id)?.name || ""}` }),
      h("div", { class: "m" }, h("span", {}, h("b", { text: fmt.brl(a.cost) }), " gasto"), h("span", {}, h("b", { text: fmt.dec1(a.conversions) }), " conversões"), h("span", {}, h("b", { text: fmt.brl(a.cpa) }), " por conversão")),
      h("div", { class: "m" }, h("span", {}, h("b", { text: fmt.pct(a.ctr) }), " CTR"), h("span", {}, h("b", { text: fmt.int(a.clicks) }), " cliques"), h("span", {}, h("b", { text: fmt.brl(a.cpc) }), " CPC")),
      (ad.headlines || []).length ? h("div", { class: "copy", text: (ad.headlines || []).slice(0, 4).join(" · ") }) : null,
      ad.final_url ? h("div", { class: "s" }, h("a", { href: ad.final_url, target: "_blank", rel: "noopener noreferrer", text: "abrir página ↗" })) : null,
    ));
  })) : null;

  const devMap = new Map();
  for (const d of g.devices || []) { const k = (d.device || "?").toLowerCase(); if (!devMap.has(k)) devMap.set(k, gEmpty()); gAdd(devMap.get(k), d); }
  const devList = Array.from(devMap.entries()).map(([k, a]) => [k, gFinish(a)]).sort((a, b) => b[1].cost - a[1].cost);
  const geoList = (g.geo || []).slice(0, 12).map((x) => [x.city || x.region || "—", gFinish(gAdd(gEmpty(), x))]);
  const simpleTable = (title, sub, label, list) => list.length ? h("div", { class: "table-wrap" },
    h("div", { class: "group-head" }, h("span", { text: title }), h("small", { text: sub })),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: label }), h("th", { text: "Gasto" }), h("th", { text: "Conversões" }), h("th", { text: "Custo/conv." }), h("th", { text: "Cliques" }), h("th", { text: "CTR" }))),
      h("tbody", {}, ...list.map(([k, a]) => h("tr", {}, h("td", { text: k }), h("td", { text: fmt.brl(a.cost) }), h("td", { text: fmt.dec1(a.conversions) }),
        h("td", { text: fmt.brl(a.cpa) }), h("td", { text: fmt.int(a.clicks) }), h("td", { text: fmt.pct(a.ctr) })))))) : null;

  /* conversões por ação */
  const convRows = gRowsIn(state.since, state.until, g.conversions_daily || []);
  const convMap = new Map();
  for (const r of convRows) {
    const k = r.action || "—";
    const a = convMap.get(k) || { conversions: 0, value: 0, all: 0 };
    a.conversions += r.conversions || 0; a.value += r.value || 0; a.all += r.all_conversions || 0;
    convMap.set(k, a);
  }
  const convList = Array.from(convMap.entries()).sort((a, b) => b[1].conversions - a[1].conversions);
  const convTable = convList.length ? h("div", { class: "table-wrap" },
    h("div", { class: "group-head" }, h("span", { text: "Conversões por ação" }), h("small", { text: "no período selecionado" })),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", { class: "l", text: "Ação de conversão" }), h("th", { text: "Principais" }), h("th", { text: "Todas" }), h("th", { text: "Valor" }))),
      h("tbody", {}, ...convList.map(([k, a]) => h("tr", {}, h("td", { class: "l", text: k }), h("td", { text: fmt.dec1(a.conversions) }),
        h("td", { text: fmt.dec1(a.all) }), h("td", { text: a.value > 0 ? fmt.brl(a.value) : "—" })))))) : null;

  sec.append(
    block("Google Ads", `${fmt.date(state.since)} a ${fmt.date(state.until)} · conta ${cfg.customer_id} · meta de ${fmt.brl(T.google_cost_per_conversion)} por conversão`, head, charts, table),
    agGroups.length ? block("Grupos de anúncios", "por campanha", ...agGroups) : null,
    (kwTable || stTable) ? block("Busca", "palavras-chave e termos de pesquisa", h("div", { class: "grid c2" }, kwTable, stTable)) : null,
    adsCards ? block("Anúncios", "últimos 30 dias · maiores gastos", adsCards) : null,
    (convTable || devList.length || geoList.length) ? block("Onde e como converte", "conversões, dispositivos e localidades",
      h("div", { class: "grid c3" }, convTable, simpleTable("Dispositivos", "últimos 30 dias", "Dispositivo", devList), simpleTable("Localidades", "últimos 30 dias", "Cidade / região", geoList))) : null,
    (g.warnings || []).length ? h("div", { class: "banner" }, h("b", { text: "Avisos da coleta do Google Ads: " }), h("ul", {}, ...g.warnings.slice(0, 8).map((w) => h("li", { text: w })))) : null,
  );
}

/* ====================================================== seção: criativos */
function renderCreatives() {
  const sec = $("#sec-criativos"); sec.replaceChildren();
  const m = state.meta;
  const rows = rowsIn(state.since, state.until);
  const byAd = groupBy(rows, "ad_id");
  let items = m.ads.map((ad) => ({ ad, agg: byAd.get(ad.id) || finish(emptyAgg()), def: defFor(ad.campaign_id), camp: idx.campaigns.get(ad.campaign_id), set: idx.adsets.get(ad.adset_id) }))
    .map((x) => ({ ...x, as: assess(x.agg, x.def) }))
    .filter((x) => x.agg.spend > 0 || x.ad.effective_status === "ACTIVE");
  const f = state.creativeFilter;
  const campaignsWithAds = m.campaigns.filter((c) => items.some((x) => x.ad.campaign_id === c.id));
  if (f.campaign !== "all") items = items.filter((x) => x.ad.campaign_id === f.campaign);
  if (f.quality !== "all") items = items.filter((x) => x.as.level === f.quality);
  items.sort((a, b) => b.agg.spend - a.agg.spend);

  const sel = h("select", { onchange: (e) => { state.creativeFilter.campaign = e.target.value; renderCreatives(); } },
    h("option", { value: "all", text: "Todas as campanhas" }),
    ...campaignsWithAds.map((c) => h("option", { value: c.id, text: c.name, selected: f.campaign === c.id ? "" : null })));
  const chips = ["all", "ok", "warn", "crit"].map((q) => h("button", {
    type: "button", class: `chip${f.quality === q ? " on" : ""}`,
    text: q === "all" ? "Todos" : q === "ok" ? "● Na meta" : q === "warn" ? "▲ Atenção" : "■ Crítico",
    onclick: () => { state.creativeFilter.quality = q; renderCreatives(); },
  }));
  const filters = h("div", { class: "filter-row" }, h("span", { text: "Campanha" }), sel, h("span", { text: "Qualidade" }), ...chips,
    h("span", { class: "faint", text: `${items.length} criativos · ${fmt.brl(sum(items, (x) => x.agg.spend))} investido` }));

  const cards = h("div", { class: "cards" }, ...items.map((x) => {
    const thumb = thumbOf(x.ad), link = adLink(x.ad);
    const r = resultsOf(x.agg, x.def), cpr = costPerResult(x.agg, x.def);
    const rev = valueOf(x.agg, x.def);
    return h("div", { class: `creative ${x.as.level}` },
      h("div", { class: "img" }, thumb ? h("img", { src: thumb, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null,
        link ? h("a", { href: link, target: "_blank", rel: "noopener noreferrer", text: "abrir ↗" }) : null),
      h("div", { class: "body" },
        h("div", { class: "badges" }, statusBadge(x.ad.effective_status, x.ad.status), badge(x.as.level, levelWord(x.as.level)),
          x.ad.creative?.object_type ? h("span", { class: "badge neutral", text: String(x.ad.creative.object_type).toLowerCase().replace(/_/g, " ") }) : null),
        h("div", { class: "n", text: x.ad.name }),
        h("div", { class: "s", text: `${x.camp?.name || ""} · ${x.set?.name || ""}` }),
        h("div", { class: "m" }, h("span", {}, h("b", { text: fmt.brl(x.agg.spend) }), " gasto"),
          h("span", {}, h("b", { text: fmt.int(r) }), ` ${r === 1 ? x.def.unit : x.def.unit + "s"}`),
          h("span", {}, h("b", { text: ok(cpr) ? (x.def.per ? fmt.brl(cpr) + "/mil" : fmt.brl(cpr)) : "—" }), ` por ${x.def.unit}`)),
        h("div", { class: "m" }, h("span", {}, h("b", { text: fmt.pct(x.agg.ctr) }), " CTR"), h("span", {}, h("b", { text: fmt.brl(x.agg.cpm) }), " CPM"),
          h("span", {}, h("b", { text: fmt.int(x.agg.link_clicks) }), " cliques"),
          x.agg.thruplays ? h("span", {}, h("b", { text: fmt.int(x.agg.thruplays) }), " thruplays") : null,
          rev > 0 ? h("span", {}, h("b", { text: fmt.brl(rev) }), " receita") : null),
        x.ad.creative?.body ? h("div", { class: "copy", text: x.ad.creative.body }) : null,
      ),
    );
  }));
  sec.append(block("Criativos com entrega", "clique em “abrir” para ver o anúncio publicado", filters,
    items.length ? cards : h("div", { class: "empty", text: "Nenhum criativo para este filtro." })));
}

/* ======================================================= seção: orgânico */
function seriesLast(arr, days) {
  if (!arr?.length) return [];
  const cut = addDays(dataBounds().last, -(days - 1));
  return arr.filter((p) => p.date >= cut);
}
function renderOrganic() {
  const sec = $("#sec-organico"); sec.replaceChildren();
  const o = state.organic;
  if (!o) {
    sec.append(block("Orgânico", "Instagram e Facebook", h("div", { class: "placeholder" },
      h("b", { text: "Dados orgânicos ainda não coletados" }),
      h("span", { text: "O coletor gera organic.json quando o token tiver as permissões pages_read_engagement, read_insights, instagram_basic e instagram_manage_insights." }))));
    return;
  }
  const ig = o.instagram, fb = o.facebook;
  if (o.warnings?.length) sec.append(h("div", { class: "banner" }, h("b", { text: "Avisos da coleta orgânica: " }), h("ul", {}, ...o.warnings.slice(0, 8).map((w) => h("li", { text: w })))));

  if (ig) {
    const last = dataBounds().last;
    const reach30 = seriesLast(ig.daily?.reach, 30);
    const reachPrev = ig.daily?.reach ? ig.daily.reach.filter((p) => p.date < addDays(last, -29) && p.date >= addDays(last, -59)) : [];
    const foll30 = seriesLast(ig.daily?.follower_count, 30);
    const t30 = ig.totals?.last_30d || {}, t7 = ig.totals?.last_7d || {};
    const pv30 = seriesLast(ig.daily?.profile_views, 30), ae30 = seriesLast(ig.daily?.accounts_engaged, 30);
    const tiles = h("div", { class: "grid c6" },
      tile({ label: "Seguidores", value: fmt.int(ig.followers), sub: `${fmt.int(ig.media_count)} publicações · segue ${fmt.int(ig.follows)}`, accent: true }),
      tile({ label: "Novos seguidores (30d)", value: foll30.length ? "+" + fmt.int(sum(foll30, (p) => p.value)) : "—", sub: foll30.length ? `${fmt.dec1(sum(foll30, (p) => p.value) / foll30.length)} por dia` : "série indisponível" }),
      tile({ label: "Alcance (30d)", value: reach30.length ? fmt.int(sum(reach30, (p) => p.value)) : "—", delta: reachPrev.length ? deltaBadge(sum(reach30, (p) => p.value), sum(reachPrev, (p) => p.value)) : null, sub: "soma do alcance diário" }),
      tile({ label: "Visitas ao perfil (30d)", value: fmt.int(t30.profile_views ?? (pv30.length ? sum(pv30, (p) => p.value) : null)), sub: `7d: ${fmt.int(t7.profile_views)}` }),
      tile({ label: "Contas engajadas (30d)", value: fmt.int(t30.accounts_engaged ?? (ae30.length ? sum(ae30, (p) => p.value) : null)), sub: `interações: ${fmt.int(t30.total_interactions)}` }),
      tile({ label: "Visualizações (30d)", value: fmt.int(t30.views), sub: `cliques no site: ${fmt.int(t30.website_clicks)}` }),
    );
    const charts = h("div", { class: "grid c2" });
    if (reach30.length) charts.append(chartCard("Alcance diário · Instagram", "últimos 30 dias (orgânico + pago)", [{ name: "Alcance", color: COLOR.pink, values: reach30.map((p) => p.value) }], { labels: reach30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (foll30.length) charts.append(chartCard("Novos seguidores por dia", "últimos 30 dias", [{ name: "Seguidores", color: COLOR.good, values: foll30.map((p) => p.value) }], { labels: foll30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (pv30.length) charts.append(chartCard("Visitas ao perfil por dia", "últimos 30 dias", [{ name: "Visitas", color: COLOR.meta, values: pv30.map((p) => p.value) }], { labels: pv30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (ae30.length) charts.append(chartCard("Contas engajadas por dia", "últimos 30 dias", [{ name: "Contas", color: COLOR.warn, values: ae30.map((p) => p.value) }], { labels: ae30.map((p) => fmt.dm(p.date)), type: "bar" }));

    const medias = (ig.media || []).map((x) => {
      const i = x.insights || {};
      const inter = (x.likes || 0) + (x.comments || 0) + (i.saved || 0) + (i.shares || 0);
      return { ...x, inter, reach: i.reach || 0, rate: i.reach ? (inter / i.reach) * 100 : null };
    }).sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""));
    const grid = h("div", { class: "media-grid" }, ...medias.slice(0, 24).map((x) => h("div", { class: "media" },
      h("a", { href: x.permalink, target: "_blank", rel: "noopener noreferrer" },
        h("div", { class: "pic" }, x.thumbnail ? h("img", { src: x.thumbnail, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null,
          h("span", { class: "type", text: String(x.product_type || x.media_type || "").toLowerCase() }))),
      h("div", { class: "info" }, h("div", { class: "d", text: fmt.date((x.timestamp || "").slice(0, 10)) }),
        h("div", { class: "k" }, h("span", { text: "Alcance" }), h("b", { text: fmt.int(x.reach || null) })),
        h("div", { class: "k" }, h("span", { text: "Curtidas · coment." }), h("b", { text: `${fmt.int(x.likes)} · ${fmt.int(x.comments)}` })),
        h("div", { class: "k" }, h("span", { text: "Salvos · compart." }), h("b", { text: `${fmt.int(x.insights?.saved ?? null)} · ${fmt.int(x.insights?.shares ?? null)}` })),
        h("div", { class: "k" }, h("span", { text: "Engajamento" }), h("b", { text: ok(x.rate) ? fmt.pct(x.rate) : "—" }))))));
    const top = medias.filter((x) => x.reach > 0).sort((a, b) => b.reach - a.reach).slice(0, 5);
    const topList = top.length ? h("div", { class: "card" }, h("h3", { text: "Publicações com maior alcance" }),
      h("div", { class: "list" }, ...top.map((x, i) => h("div", { class: "list-item" }, h("span", { class: "rank good", text: i + 1 }),
        x.thumbnail ? h("img", { class: "thumb", src: x.thumbnail, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null,
        h("div", { class: "txt" }, h("div", { class: "n" }, h("a", { href: x.permalink, target: "_blank", rel: "noopener noreferrer", text: x.caption ? x.caption.slice(0, 80) : (x.product_type || "publicação") })),
          h("div", { class: "s", text: `${fmt.date((x.timestamp || "").slice(0, 10))} · alcance ${fmt.int(x.reach)} · ${fmt.int(x.inter)} interações · ${ok(x.rate) ? fmt.pct(x.rate) : "—"} engaj.` })))))) : null;

    sec.append(block("Instagram", `@${ig.username}`,
      h("div", { class: "card profile" }, ig.profile_picture_url ? h("img", { src: ig.profile_picture_url, alt: "", referrerpolicy: "no-referrer" }) : null,
        h("div", {}, h("div", { class: "n", text: ig.name || ig.username }), h("div", { class: "s", text: ig.biography || "" }))),
      tiles, charts, topList,
      block("Publicações recentes", "métricas por publicação (Instagram Insights)", medias.length ? grid : h("div", { class: "empty", text: "Sem publicações coletadas." }))));
  } else {
    sec.append(block("Instagram", "", h("div", { class: "placeholder" }, h("b", { text: "Instagram indisponível" }),
      h("span", { text: "Verifique as permissões instagram_basic e instagram_manage_insights do token e se o perfil está vinculado à página." }))));
  }

  if (fb) {
    const d = fb.daily || {};
    const imp30 = seriesLast(d.page_impressions_unique, 30), eng30 = seriesLast(d.page_post_engagements, 30);
    const fol30 = seriesLast(d.page_daily_follows_total, 30), views30 = seriesLast(d.page_views_total, 30);
    const vid30 = seriesLast(d.page_video_views, 30), act30 = seriesLast(d.page_total_actions, 30);
    const tiles = h("div", { class: "grid c4" },
      tile({ label: "Seguidores da página", value: fmt.int(fb.followers ?? fb.fans), sub: `${fmt.int(fb.fans)} curtidas` }),
      tile({ label: "Novos seguidores (30d)", value: fol30.length ? "+" + fmt.int(sum(fol30, (p) => p.value)) : "—", sub: fol30.length ? `${fmt.dec1(sum(fol30, (p) => p.value) / fol30.length)} por dia` : "série indisponível" }),
      tile({ label: "Engajamentos (30d)", value: eng30.length ? fmt.int(sum(eng30, (p) => p.value)) : "—", sub: `${act30.length ? fmt.int(sum(act30, (p) => p.value)) : "—"} cliques em botões` }),
      tile({ label: "Visitas à página (30d)", value: views30.length ? fmt.int(sum(views30, (p) => p.value)) : "—", sub: vid30.length ? `${fmt.int(sum(vid30, (p) => p.value))} visualizações de vídeo` : "" }),
    );
    const charts = h("div", { class: "grid c2" });
    if (imp30.length) charts.append(chartCard("Alcance diário · Facebook", "últimos 30 dias", [{ name: "Alcance", color: COLOR.meta, values: imp30.map((p) => p.value) }], { labels: imp30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (eng30.length) charts.append(chartCard("Engajamentos por dia · Facebook", "últimos 30 dias", [{ name: "Engajamentos", color: COLOR.good, values: eng30.map((p) => p.value) }], { labels: eng30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (fol30.length) charts.append(chartCard("Novos seguidores por dia · Facebook", "últimos 30 dias", [{ name: "Seguidores", color: COLOR.brand, values: fol30.map((p) => p.value) }], { labels: fol30.map((p) => fmt.dm(p.date)), type: "bar" }));
    if (views30.length) charts.append(chartCard("Visitas à página por dia", "últimos 30 dias", [{ name: "Visitas", color: COLOR.topo, values: views30.map((p) => p.value) }], { labels: views30.map((p) => fmt.dm(p.date)), type: "bar" }));
    const posts = (fb.posts || []).slice(0, 10);
    const list = posts.length ? h("div", { class: "card" }, h("h3", { text: "Publicações recentes da página" }),
      h("div", { class: "list" }, ...posts.map((p) => h("div", { class: "list-item" },
        p.picture ? h("img", { class: "thumb", src: p.picture, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : null,
        h("div", { class: "txt" }, h("div", { class: "n" }, h("a", { href: p.permalink, target: "_blank", rel: "noopener noreferrer", text: p.message ? p.message.slice(0, 90) : "publicação" })),
          h("div", { class: "s", text: `${fmt.date((p.created_time || "").slice(0, 10))} · ${fmt.int(p.likes)} curtidas · ${fmt.int(p.comments)} comentários · ${fmt.int(p.shares)} compart.` })))))) : null;
    sec.append(block("Facebook", fb.name || "", tiles, charts, list));
  }
}

/* ======================================================== seção: legendas */
function renderLegend() {
  const sec = $("#sec-legendas"); sec.replaceChildren();
  const T = state.targets;
  const cfg = state.config;
  const dl = (pairs) => h("dl", { class: "dl" }, ...pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
  sec.append(
    block("Métricas", "", h("div", { class: "card" }, dl([
      ["Reserva / compra", "Evento de compra registrado pelo pixel do site a partir do anúncio. É o resultado principal da Nohotel."],
      ["Custo por reserva", "Gasto das campanhas de conversão ÷ reservas. Meta atual: " + fmt.brl(T.cost_per_purchase) + "."],
      ["Receita e ROAS", "Valor das compras informado pelo pixel ÷ investimento. ROAS 3× significa R$ 3 de receita para cada R$ 1 investido."],
      ["Adição ao carrinho", "Passo anterior à reserva. Serve para ver se o problema está no anúncio (poucos carrinhos) ou no checkout (muitos carrinhos, poucas reservas)."],
      ["Conversa iniciada", "Pessoas que abriram conversa no WhatsApp a partir do anúncio (atribuição de 7 dias após o clique)."],
      ["Conversão (Google)", "Ação marcada como conversão principal na conta do Google Ads. Pode ser reserva, ligação ou formulário."],
      ["Conversão vs. topo de funil", "Conversão = campanhas de venda, cadastro e conversa. Topo = tráfego, alcance, engajamento e visitas ao perfil. O custo por reserva usa só a conversão."],
      ["Alcance", "Contas únicas que viram o anúncio. Não soma entre dias — os atalhos de período usam o valor exato da API; períodos personalizados somam o alcance diário (aproximação)."],
      ["Frequência", "Impressões ÷ alcance. Acima de " + fmt.dec1(T.frequency_max) + " indica saturação do público."],
      ["CPM", "Custo por mil impressões. Para campanhas de topo de funil a meta é até " + fmt.brl(T.cpm_topo_max) + "."],
      ["CTR", "Cliques ÷ impressões. Abaixo de " + fmt.pct(T.ctr_min) + " sugere criativo pouco atrativo."],
      ["Parcela de impressões", "Google Ads: quanto das buscas elegíveis o anúncio apareceu. Perda por orçamento indica verba insuficiente."],
      ["Índice de qualidade", "Nota de 1 a 10 do Google para a palavra-chave. Abaixo de 5 encarece o clique."],
      ["ThruPlay", "Reproduções de vídeo de 15 s ou até o fim (quando menor)."],
    ]))),
    block("Status e qualidade", "", h("div", { class: "card" }, dl([
      ["● Na meta", "Custo por resultado igual ou abaixo da meta — manter."],
      ["▲ Atenção", "Custo até 1,6× a meta, ou sem resultado com gasto baixo — otimizar segmentação/criativo ou observar."],
      ["■ Crítico", "Custo acima de 1,6× a meta, ou gasto ≥ " + fmt.brl(T.min_spend_for_alert) + " sem nenhum resultado — reduzir verba, pausar ou revisar."],
      ["Ativo / Pausado / Com problema", "Status efetivo de entrega informado pela plataforma."],
      ["Período anterior", "Todas as variações (↑ ↓) comparam com o período imediatamente anterior de mesma duração."],
    ]))),
    block("Fontes e atualização", "", h("div", { class: "card" }, dl([
      ["Meta Ads", `Marketing API ${state.meta.api_version} · conta ${state.meta.account.id} (${state.meta.account.name}) · série diária por anúncio desde ${fmt.date(state.meta.range.since)}.`],
      ["Google Ads", gEnabled()
        ? `Google Ads API ${state.google.api_version} · conta ${cfg.google_ads.customer_id} · série diária desde ${fmt.date(state.google.range.since)}.`
        : `Conta ${cfg.google_ads.customer_id} — aguardando credenciais da API. Passo a passo na aba Google Ads.`],
      ["Orgânico", `Graph API: página do Facebook (${cfg.meta.page_id}) e Instagram @${cfg.instagram.username}. Séries dos últimos 30/90 dias; métricas por publicação via Instagram Insights.`],
      ["Pixel", `ID ${cfg.meta.pixel_id}. As reservas e carrinhos vêm dos eventos desse pixel — se ele parar de disparar, o dashboard mostra zero resultado mesmo com vendas acontecendo.`],
      ["Atualização", "Automática 3x por dia (6h, 12h e 18h, Brasília) via GitHub Actions. Última coleta: " + fmt.dateTime(state.meta.generated_at) + "."],
      ["Metas", "Editáveis no menu lateral (ficam salvas apenas neste navegador). Padrão definido em config.json."],
    ]))),
  );
}

/* ================================================================ header */
function renderHeader() {
  const c = state.config.client;
  $("#brand-name").textContent = c.name;
  $("#brand-sub").textContent = `${c.legal_name || "Performance"} · ${c.agency || ""}`.trim();
  $("#brand-market").textContent = c.market;
  $("#topbar-sub").textContent = `${c.segment} · Meta Ads${gEnabled() ? ", Google Ads" : ""} e orgânico`;
  $("#hdr-period").textContent = `${fmt.date(state.since)} — ${fmt.date(state.until)}`;
  $("#hdr-compare").textContent = `${fmt.date(state.prevSince)} — ${fmt.date(state.prevUntil)}`;
  $("#hdr-updated").textContent = fmt.dateTime(state.meta.generated_at);
  const { first, last } = dataBounds();
  $("#f-note").textContent = `Dados disponíveis de ${fmt.date(first)} a ${fmt.date(last)}`;
  $("#f-since").value = state.since; $("#f-until").value = state.until;
  $("#f-since").min = first; $("#f-until").max = last;
  $("#t-purchase").textContent = fmt.brl(state.targets.cost_per_purchase);
  $("#t-conv").textContent = fmt.brl(state.targets.cost_per_conversation);
  $("#t-gconv").textContent = fmt.brl(state.targets.google_cost_per_conversion);
  $("#t-budget").textContent = fmt.brl(state.targets.meta_monthly);
  if (state.targets.google_monthly > 0) $("#t-gbudget").textContent = fmt.brl(state.targets.google_monthly);
  else if (gEnabled()) {
    const daily = sum((state.google.campaigns || []).filter((c) => c.status === "ENABLED"), (c) => c.daily_budget || 0);
    $("#t-gbudget").textContent = `≈ ${fmt.brl(daily * 30)}`;
    $("#t-gbudget").title = "Estimada pelos orçamentos diários das campanhas ativas × 30 dias. Defina o valor real em Metas → editar.";
  } else $("#t-gbudget").textContent = "a definir";
  const warnings = [
    ...(state.meta.warnings || []).map((w) => `Meta: ${w}`),
    ...(!gEnabled() && state.google?.reason ? [`Google Ads: ${state.google.reason}`] : []),
  ];
  const banner = $("#banner");
  /* a coleta roda 3x por dia; passar de 30h sem coleta quer dizer que a atualização parou */
  const ageH = (Date.now() - new Date(state.meta.generated_at).getTime()) / 36e5;
  const stale = ok(ageH) && ageH > 30;
  banner.classList.toggle("error", stale);
  if (stale) {
    banner.hidden = false;
    banner.replaceChildren(
      h("b", { text: `Dados desatualizados: a última coleta foi em ${fmt.dateTime(state.meta.generated_at)} (há ${Math.floor(ageH / 24) || 1} dia(s)).` }),
      h("div", { text: "A atualização automática não rodou desde então. Os números abaixo não incluem os dias seguintes." }),
      warnings.length ? h("ul", {}, ...warnings.slice(0, 6).map((w) => h("li", { text: w }))) : null,
    );
  } else if (warnings.length) {
    banner.hidden = false;
    banner.replaceChildren(h("b", { text: "Avisos da última coleta:" }), h("ul", {}, ...warnings.slice(0, 6).map((w) => h("li", { text: w }))));
  } else banner.hidden = true;
}

function renderAll() {
  computePeriod();
  renderHeader();
  renderExec(); renderMeta(); renderGoogle(); renderCreatives(); renderOrganic(); renderLegend();
  showSection(state.section);
}
function showSection(name) {
  state.section = name;
  for (const s of $$(".section")) s.hidden = s.id !== `sec-${name}`;
  for (const a of $$(".nav-item")) a.classList.toggle("active", a.dataset.section === name);
  requestAnimationFrame(() => $$(".chart-card").forEach((c) => c._render && c._render()));
  window.scrollTo({ top: 0 });
}

/* ================================================================== boot */
async function fetchJson(url, { optional = false } = {}) {
  const res = await fetch(url, { cache: "no-store", credentials: "same-origin" });
  if (res.status === 401) { location.href = "/login"; throw new Error("sessão expirada"); }
  if (!res.ok) { if (optional) return null; throw new Error(`${url}: HTTP ${res.status}`); }
  return res.json();
}
async function boot() {
  tooltipEl = $("#tooltip");
  try {
    state.config = await fetchJson("/config.json");
    state.meta = await fetchJson("/data/meta.json", { optional: true });
    state.google = await fetchJson("/data/google.json", { optional: true });
    state.organic = await fetchJson("/data/organic.json", { optional: true });
  } catch (e) {
    $("#banner").hidden = false; $("#banner").classList.add("error");
    $("#banner").textContent = `Falha ao carregar dados: ${e.message}`;
    return;
  }
  if (!state.meta) {
    $("#banner").hidden = false; $("#banner").classList.add("error");
    $("#banner").textContent = "Ainda não há dados coletados (public/data/meta.json). Rode o workflow “Atualizar dashboard” no GitHub Actions ou `python scripts/fetch_meta.py` com META_ACCESS_TOKEN.";
    return;
  }
  state.targets = loadTargets();
  buildIndexes();
  const { first, last } = dataBounds();
  state.preset = daysBetween(first, last) <= 45 ? "max" : "30";
  $("#f-preset").value = state.preset;
  const hash = location.hash.replace("#", "");
  if (["exec", "meta", "google", "criativos", "organico", "legendas"].includes(hash)) state.section = hash;

  $("#f-preset").addEventListener("change", (e) => { state.preset = e.target.value; if (state.preset !== "custom") renderAll(); });
  $("#f-apply").addEventListener("click", () => {
    const s = $("#f-since").value, u = $("#f-until").value;
    if (s && u && s <= u) { state.preset = "custom"; $("#f-preset").value = "custom"; state.since = s; state.until = u; renderAll(); }
  });
  for (const inp of ["#f-since", "#f-until"]) $(inp).addEventListener("change", () => { $("#f-preset").value = "custom"; state.preset = "custom"; });
  window.addEventListener("hashchange", () => { const hsh = location.hash.replace("#", ""); if ($(`#sec-${hsh}`)) showSection(hsh); });
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => $$(".chart-card").forEach((c) => c._render && c._render()), 150); });

  const form = $("#targets-form");
  const FORM_KEYS = ["cost_per_purchase", "cost_per_conversation", "google_cost_per_conversion", "meta_monthly", "google_monthly", "frequency_max"];
  $("#btn-edit-targets").addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) for (const k of FORM_KEYS) if (form.elements[k]) form.elements[k].value = state.targets[k];
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const t = { ...state.targets };
    for (const k of FORM_KEYS) {
      const el = form.elements[k]; if (!el) continue;
      const v = parseFloat(el.value); if (ok(v) && v >= 0) t[k] = v;
    }
    state.targets = t; saveTargets(t); form.hidden = true; renderAll();
  });
  $("#btn-reset-targets").addEventListener("click", () => {
    try { localStorage.removeItem("nohotel.targets"); } catch { /* ignore */ }
    state.targets = loadTargets(); form.hidden = true; renderAll();
  });

  renderAll();
}
document.addEventListener("DOMContentLoaded", boot);
