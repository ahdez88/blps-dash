"""
BLPS Meta Ads Dashboard — Streamlit App
"""

import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import StringIO
import re

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BLPS Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth ────────────────────────────────────────────────────────────────────
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.title("🔒 BLPS Dashboard")
    password = st.text_input("Contraseña", type="password")
    if st.button("Entrar", type="primary"):
        if password == st.secrets.get("APP_PASSWORD", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta")
    return False

if not check_password():
    st.stop()

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = st.secrets.get("META_ACCESS_TOKEN", "")
AD_ACCOUNTS = {
    "act_5302103159848505": "BL AC 01",
    "act_234789602496820": "BL AC 2",
    "act_1542649216514133": "BL AC 3",
    "act_836269185004901": "BL AC 2b",
    "act_938706057445508": "BL-plastic",
    "act_811057274877067": "BLPS-LIDERIFY",
}
API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

TYPE_COLORS = {
    "Instant Form": "#FF6384", "Landing Page": "#36A2EB",
    "Sales / Conversiones": "#FFCE56", "Mensajes IG/DM": "#4BC0C0",
    "WhatsApp": "#25D366", "Brand / Awareness": "#9966FF",
    "Tráfico": "#FF9F40", "Leads (sin clasificar)": "#C9CBCF",
    "Engagement (sin clasificar)": "#E7E9ED", "Otro": "#999999",
}
DOCTOR_COLORS = {
    "Dr. Simmons": "#FF6384", "Dr. Flores": "#36A2EB",
    "Dra. Sophie": "#FFCE56", "Dr. Salgado": "#4BC0C0",
    "Clínica (BLPS)": "#9966FF", "Mix Doctores": "#FF9F40",
    "Sin clasificar": "#C9CBCF",
}


# ── Classification ──────────────────────────────────────────────────────────

def classify_campaign_type(name, objective):
    name_upper = name.upper()
    if objective == "OUTCOME_SALES":
        return "Sales / Conversiones"
    if objective == "OUTCOME_TRAFFIC":
        return "Tráfico"
    if any(kw in name_upper for kw in ["WHA", "WPP", "WHATS APP", "WHATSAPP"]):
        return "WhatsApp"
    if any(kw in name_upper for kw in ["MESSAGE", "-MES-", "| MES |", "DIRECT", "[MESSAGE]"]):
        return "Mensajes IG/DM"
    if objective == "OUTCOME_AWARENESS":
        return "Brand / Awareness"
    if any(kw in name_upper for kw in ["VIDEO PLAY", "REPRODUCCIONVIDEO", "VDEO_PLAY", "VIDEO_PLAY"]):
        return "Brand / Awareness"
    if any(kw in name_upper for kw in ["[REACH]", "BA |", "ENGAGEMENT |"]):
        return "Brand / Awareness"
    if "CALL CENTER" in name_upper:
        return "Mensajes IG/DM"
    if any(kw in name_upper for kw in [
        "IF ", "IF|", "IF-", "-IF-", "INSTANTFORM", "INSTANT FORM",
        "LEADSONFB", "[FORMS]", "FORMS |", "-IF_", "IF_"
    ]):
        return "Instant Form"
    if any(kw in name_upper for kw in [
        "LP", "WEBSITE", "WEB ", "WEB|", "-LP-",
        "[WEBSITE]", "[SITE]", "SITE |", "CADASTRO"
    ]):
        return "Landing Page"
    if objective == "OUTCOME_LEADS":
        return "Leads (sin clasificar)"
    if objective == "OUTCOME_ENGAGEMENT":
        return "Engagement (sin clasificar)"
    return "Otro"


def classify_doctor(name):
    name_upper = name.upper()
    has_simmons = any(kw in name_upper for kw in ["SIMMONS", "DRSIMMONS", "DR SIMMONS", "DR. SIMMONS"])
    has_flores = any(kw in name_upper for kw in ["FLORES", "DRFLORES", "DR FLORES", "DR. FLORES"])
    has_sophie = any(kw in name_upper for kw in ["SOPHIE", "DRSOPHIE", "DR SOPHIE", "LESSARD"])
    has_salgado = any(kw in name_upper for kw in ["SALGADO", "DRSALGADO", "DR SALGADO"])
    doctors_found = sum([has_simmons, has_flores, has_sophie, has_salgado])
    if doctors_found > 1:
        return "Mix Doctores"
    if has_simmons:
        return "Dr. Simmons"
    if has_flores:
        return "Dr. Flores"
    if has_sophie:
        return "Dra. Sophie"
    if has_salgado:
        return "Dr. Salgado"
    if any(kw in name_upper for kw in ["MIXDRS", "MIX DRS", "[DOCTORS]", "DOCTORS |", "DOCTOR |"]):
        return "Mix Doctores"
    if any(kw in name_upper for kw in ["BLPS", "BEAUTYLAND", "BEAUTY LAND", "CLINICA", "CLINIC", "BEAUTY |", "[BEAUTY]"]):
        return "Clínica (BLPS)"
    return "Sin clasificar"


# ── Cross-Analysis Source Key Mapping ──────────────────────────────────────

def meta_campaign_to_source_key(name):
    """Map Meta campaign name to normalized source key for cross-analysis.
    Returns key like 'DRSIMMONS-LP-EN', 'WHA', 'BRAND', or None.
    """
    n = name.strip().upper()

    # Brand / Awareness → no direct lead attribution
    if any(kw in n for kw in [
        "REACH", "REPRODUCCIONVIDEO", "BA | BE", "ENGAGEMENT |",
        "EVP |", "BODYSCULPT", "-BRAND"
    ]):
        return "BRAND"

    # WhatsApp campaigns
    if "WHA" in n:
        return "WHA"

    # Messages (IG DM campaigns)
    if any(kw in n for kw in ["-MES-", "MESSAGE |", "MESSAGES |"]):
        if "SIMMONS" in n:
            return "DRSIMMONS-MES-EN"
        if "FLORES" in n:
            return "DRFLORES-MES-EN"
        return "BLPS-MES"

    # Extract page with number (DRSIMMONS1 → DRSIMMONS, DRSIMMONS2 stays)
    page = None
    m = re.search(r'(DRSIMMONS|DRSOPHIE|DRSALGADO|DRFLORES|BLPS)(\d*)', n)
    if m:
        base, num = m.group(1), m.group(2)
        page = base if num in ("", "1") else f"{base}{num}"
    else:
        # Pipe-format fallback (IF | SIMMONS | ENG ...)
        for kw, pg in [("SIMMONS", "DRSIMMONS"), ("FLORES", "DRFLORES"),
                        ("SOPHIE", "DRSOPHIE"), ("SALGADO", "DRSALGADO"),
                        ("BLPS", "BLPS"), ("BEAUTYLAND", "BLPS")]:
            if kw in n:
                page = pg
                break

    if page is None:
        return None

    # Extract campaign type
    ctype = None
    if any(kw in n for kw in ["IF ", "IF|", "-IF-", "IF_", "INSTANTFORM", "| IF"]):
        ctype = "IF"
    elif any(kw in n for kw in ["-LP-", "WEBSITE", "WEB ", "WEB|"]):
        ctype = "LP"

    if ctype is None:
        return None

    # Special: Florida geo-targeted → LP-FL
    if "FLORIDA" in n:
        return f"{page}-LP-FL"

    # Special: DRSIMMONS4 = Lookalike test
    if page == "DRSIMMONS4":
        return "DRSIMMONS4-LKL"

    # Extract language
    lang = "EN"
    if "ESP" in n:
        lang = "ES"
    elif re.search(r'[\-| ]ES[\-| _]', n) or n.endswith("-ES"):
        lang = "ES"

    return f"{page}-{ctype}-{lang}"


def crm_source_to_meta_key(source):
    """Map CRM source to Meta source key. Returns None for non-Meta sources."""
    if not isinstance(source, str):
        return None
    su = source.strip().upper()

    # WhatsApp sources → all from Meta WHA campaigns
    if su.startswith("WA-") or su == "WHATSAPP LEAD":
        return "WHA"

    # Instagram Messages from MES campaigns (confirmed by user)
    if su.startswith("SIMMON") and "INSTAGRAM" in su and "MESSAGE" in su:
        return "DRSIMMONS-MES-EN"

    # Special: Lookalike
    if su == "DRSIMMONS4-LKL":
        return "DRSIMMONS4-LKL"

    # Standard format: PAGE(N)-TYPE-LANG(-SUFFIX)
    m = re.match(
        r'^((?:DR)?[A-Z]+)(\d*)-(IF|LP)-(EN|ENG|ES|ESP|FL)(?:[_-].+)?$', su
    )
    if m:
        base, num, ctype, lang_raw = m.group(1), m.group(2), m.group(3), m.group(4)
        page = base if num in ("", "1") else f"{base}{num}"
        lang = "EN" if lang_raw.startswith("EN") else ("FL" if lang_raw == "FL" else "ES")
        return f"{page}-{ctype}-{lang}"

    # Non-Meta sources (organic, referral, call center, etc.)
    return None


def source_key_label(key):
    """Convert source key to human-readable label."""
    if key == "BRAND":
        return "Brand / Awareness"
    if key == "WHA":
        return "WhatsApp"
    if key == "BLPS-MES":
        return "BLPS · Mensajes"
    page_map = {
        "DRSIMMONS": "Simmons", "DRFLORES": "Flores",
        "DRSOPHIE": "Sophie", "DRSALGADO": "Salgado", "BLPS": "BLPS",
    }
    type_map = {
        "IF": "Inst. Form", "LP": "Landing Page", "MES": "Mensajes", "LKL": "Lookalike",
    }
    parts = key.split("-")
    page_raw = parts[0]
    page_label = page_raw
    for base, name in page_map.items():
        if page_raw.startswith(base):
            num = page_raw[len(base):]
            page_label = f"{name}({num})" if num else name
            break
    ctype_label = type_map.get(parts[1], parts[1]) if len(parts) > 1 else ""
    lang_label = parts[2] if len(parts) > 2 else ""
    result = page_label
    if ctype_label:
        result += f" · {ctype_label}"
    if lang_label:
        result += f" · {lang_label}"
    return result


# ── Data Loading ────────────────────────────────────────────────────────────

CACHE_URL = "https://raw.githubusercontent.com/ahdez88/blps-dash/master/data_cache.json"


@st.cache_data(show_spinner=False)
def load_cached_data():
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return cache.get("insights", []), cache.get("last_updated", "unknown")
    resp = requests.get(CACHE_URL)
    if resp.status_code == 200:
        cache = resp.json()
        return cache.get("insights", []), cache.get("last_updated", "unknown")
    st.error("No se pudo cargar el cache de datos.")
    return [], "error"


@st.cache_data(show_spinner=False)
def load_sales_cache():
    """Load sales data from committed JSON cache."""
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales_cache.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        records = cache.get("records", [])
        if records:
            return pd.DataFrame(records), cache.get("last_updated", "")
    return None, ""


@st.cache_data(show_spinner=False)
def load_leads_cache():
    """Load leads distribution from committed JSON cache."""
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads_cache.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        records = cache.get("records", [])
        if records:
            return pd.DataFrame(records), cache.get("last_updated", "")
    return None, ""


def merge_sales(existing_df, new_raw_df):
    """Merge new sales CSV into existing DataFrame. Dedup by Invoice+Procedure+Date."""
    new_df = build_sales_dataframe(new_raw_df)
    existing_df["_key"] = (
        existing_df["Invoice"].astype(str) + "|" +
        existing_df["Sales W Payments"].astype(str) + "|" +
        existing_df["Sales Dates"].astype(str)
    )
    new_df["_key"] = (
        new_df["Invoice"].astype(str) + "|" +
        new_df["Sales W Payments"].astype(str) + "|" +
        new_df["Sales Dates"].astype(str)
    )
    before = len(existing_df)
    combined = pd.concat([existing_df, new_df]).drop_duplicates(subset="_key", keep="last")
    combined = combined.drop(columns="_key")
    added = len(combined) - before
    return combined, added


# ── Processing ──────────────────────────────────────────────────────────────

def extract_leads(actions):
    if not actions:
        return 0
    for a in actions:
        if a.get("action_type") in ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"):
            return int(a.get("value", 0))
    return 0


def build_ads_dataframe(insights):
    rows = []
    for row in insights:
        name = row.get("campaign_name", "")
        objective = row.get("objective", "")
        spend = float(row.get("spend", 0))
        impressions = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        reach = int(row.get("reach", 0))
        leads = extract_leads(row.get("actions"))
        date_start = row.get("date_start", "")
        month = date_start[:7] if date_start else "unknown"
        rows.append({
            "campaign_id": row.get("campaign_id", ""),
            "campaign": name,
            "objective": objective,
            "tipo": classify_campaign_type(name, objective),
            "pagina": classify_doctor(name),
            "account": row.get("_account", ""),
            "date_start": date_start,
            "month": month,
            "spend": spend,
            "impressions": impressions,
            "clicks": clicks,
            "reach": reach,
            "leads": leads,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce")
        df["week"] = df["date_start"].dt.to_period("W-SUN").astype(str)
    return df


def build_sales_dataframe(df_raw):
    """Process raw sales CSV into an enriched DataFrame."""
    df = df_raw.copy()
    df["Sales Dates"] = pd.to_datetime(df["Sales Dates"], errors="coerce")
    df["Contact Date"] = pd.to_datetime(df["Contact Date"], errors="coerce")
    df["month"] = df["Sales Dates"].dt.to_period("M").astype(str)
    df["week"] = df["Sales Dates"].dt.to_period("W-SUN").astype(str)
    df["days_to_close"] = (df["Sales Dates"] - df["Contact Date"]).dt.days
    # Classify procedure groups
    df["proc_group"] = df["Sales W Payments"].apply(classify_procedure)
    return df


def classify_procedure(name):
    """Group procedures into main categories."""
    n = name.upper() if isinstance(name, str) else ""
    if "BBL" in n or "FAT TRANSFER TO BUTTOCKS" in n:
        return "BBL"
    if "ABDOMINOPLASTY" in n or "TUMMY" in n:
        return "Tummy Tuck"
    if "LIPO" in n and "BBL" not in n and "FAT TRANSFER" not in n:
        return "Liposuction"
    if "BREAST LIFT" in n or "MASTOPEXY" in n:
        return "Breast Lift"
    if "BREAST AUGMENT" in n:
        return "Breast Augmentation"
    if "BREAST REDUC" in n:
        return "Breast Reduction"
    if "MOMMY" in n or "MUMMY" in n:
        return "Mommy Makeover"
    if "J-PLASMA" in n or "J PLASMA" in n or "J- PLASMA" in n:
        return "J-Plasma"
    if "RHINO" in n:
        return "Rhinoplasty"
    if "FACELIFT" in n or "FACE LIFT" in n:
        return "Facelift"
    if "NECK" in n:
        return "Neck Lift"
    if "BROW" in n or "EYE LIFT" in n or "BLEPHARO" in n:
        return "Face (otros)"
    if "BIOPOLYMER" in n:
        return "Biopolymer Removal"
    return "Otros"


# ── Sidebar (shared) ───────────────────────────────────────────────────────

def render_sidebar():
    """Render sidebar with date filters. Returns date_start_str, date_end_str."""
    st.sidebar.image("https://beautylandplasticsurgery.com/wp-content/uploads/2024/07/logo-beautyland.webp", width=200)
    st.sidebar.title("Filtros")

    today = datetime.now().date()
    this_monday = today - timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)
    prev_month = (first_of_month - timedelta(days=1))
    first_of_prev_month = prev_month.replace(day=1)

    presets = {
        "Personalizado": None,
        "Últimos 7 días": (today - timedelta(days=7), today),
        "Últimos 14 días": (today - timedelta(days=14), today),
        "Últimos 30 días": (today - timedelta(days=30), today),
        "Últimos 90 días": (today - timedelta(days=90), today),
        "Esta semana (Lun-Hoy)": (this_monday, today),
        "Semana pasada": (this_monday - timedelta(days=7), this_monday - timedelta(days=1)),
        "Mes hasta la fecha": (first_of_month, today),
        "Mes pasado": (first_of_prev_month, prev_month),
        "Este año": (today.replace(month=1, day=1), today),
        "Todo (desde Ene 2025)": (datetime(2025, 1, 1).date(), today),
    }

    preset = st.sidebar.selectbox("Período", list(presets.keys()), index=len(presets) - 1)

    if preset == "Personalizado":
        date_start = st.sidebar.date_input("Fecha inicio", value=datetime(2025, 1, 1))
        date_end = st.sidebar.date_input("Fecha fin", value=today)
    else:
        date_start, date_end = presets[preset]
        st.sidebar.caption(f"📅 {date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}")

    if st.sidebar.button("🔄 Recargar caché", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    return date_start.strftime("%Y-%m-%d"), date_end.strftime("%Y-%m-%d")


# ── Tab: Meta Ads ───────────────────────────────────────────────────────────

def render_ads_tab(df, daily_df, date_start_str, date_end_str):
    """Render the Meta Ads performance tab."""

    # Sidebar filters for ads
    all_types = sorted(df["tipo"].unique())
    all_doctors = sorted(df["pagina"].unique())
    selected_types = st.sidebar.multiselect("Tipo de campaña", all_types, default=all_types)
    selected_doctors = st.sidebar.multiselect("Página / Doctor", all_doctors, default=all_doctors)

    mask = df["tipo"].isin(selected_types) & df["pagina"].isin(selected_doctors)
    df_f = df[mask]

    # KPIs
    total_spend = df_f["spend"].sum()
    total_impressions = df_f["impressions"].sum()
    total_clicks = df_f["clicks"].sum()
    total_leads = df_f["leads"].sum()
    cpm = (total_spend / total_impressions * 1000) if total_impressions else 0
    cpc = (total_spend / total_clicks) if total_clicks else 0
    ctr = (total_clicks / total_impressions * 100) if total_impressions else 0
    cpl = (total_spend / total_leads) if total_leads else 0

    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
    k1.metric("Inversión", f"${total_spend:,.0f}")
    k2.metric("Impresiones", f"{total_impressions:,.0f}")
    k3.metric("Clicks", f"{total_clicks:,.0f}")
    k4.metric("Leads", f"{total_leads:,.0f}")
    k5.metric("CPM", f"${cpm:.2f}")
    k6.metric("CPC", f"${cpc:.2f}")
    k7.metric("CTR", f"{ctr:.2f}%")
    k8.metric("CPL", f"${cpl:.2f}")

    st.divider()

    # Donut Charts
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Inversión por Tipo de Campaña")
        type_df = df_f.groupby("tipo", as_index=False)["spend"].sum().sort_values("spend", ascending=False)
        type_df["pct"] = (type_df["spend"] / type_df["spend"].sum() * 100).round(1)
        type_df["label"] = type_df.apply(lambda r: f"{r['tipo']}<br>{r['pct']}% — ${r['spend']:,.0f}", axis=1)
        fig = px.pie(type_df, values="spend", names="tipo", hole=0.45,
                     color="tipo", color_discrete_map=TYPE_COLORS)
        fig.update_traces(text=type_df["label"], textinfo="text", textposition="outside",
                          textfont_size=13, outsidetextfont_size=13)
        fig.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Inversión por Página / Doctor")
        doc_df = df_f.groupby("pagina", as_index=False)["spend"].sum().sort_values("spend", ascending=False)
        doc_df["pct"] = (doc_df["spend"] / doc_df["spend"].sum() * 100).round(1)
        doc_df["label"] = doc_df.apply(lambda r: f"{r['pagina']}<br>{r['pct']}% — ${r['spend']:,.0f}", axis=1)
        fig2 = px.pie(doc_df, values="spend", names="pagina", hole=0.45,
                      color="pagina", color_discrete_map=DOCTOR_COLORS)
        fig2.update_traces(text=doc_df["label"], textinfo="text", textposition="outside",
                           textfont_size=13, outsidetextfont_size=13)
        fig2.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Breakdown Tables
    col_t, col_d = st.columns(2)
    with col_t:
        st.subheader("Desglose por Tipo de Campaña")
        tt = df_f.groupby("tipo", as_index=False).agg(
            Inversión=("spend", "sum"), Impresiones=("impressions", "sum"),
            Clicks=("clicks", "sum"), Leads=("leads", "sum"),
        ).sort_values("Inversión", ascending=False)
        tt["% Presup."] = (tt["Inversión"] / tt["Inversión"].sum() * 100).round(1)
        tt["CTR"] = (tt["Clicks"] / tt["Impresiones"] * 100).round(2)
        tt["CPL"] = tt.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
        for c in ["Inversión"]:
            tt[c] = tt[c].apply(lambda x: f"${x:,.0f}")
        tt["% Presup."] = tt["% Presup."].apply(lambda x: f"{x}%")
        tt["CTR"] = tt["CTR"].apply(lambda x: f"{x}%")
        tt["CPL"] = tt["CPL"].apply(lambda x: f"${x:,.2f}")
        for c in ["Impresiones", "Clicks", "Leads"]:
            tt[c] = tt[c].apply(lambda x: f"{x:,}")
        st.dataframe(tt.rename(columns={"tipo": "Tipo"}), use_container_width=True, hide_index=True)

    with col_d:
        st.subheader("Desglose por Página / Doctor")
        dt = df_f.groupby("pagina", as_index=False).agg(
            Inversión=("spend", "sum"), Impresiones=("impressions", "sum"),
            Clicks=("clicks", "sum"), Leads=("leads", "sum"),
        ).sort_values("Inversión", ascending=False)
        dt["% Presup."] = (dt["Inversión"] / dt["Inversión"].sum() * 100).round(1)
        dt["CTR"] = (dt["Clicks"] / dt["Impresiones"] * 100).round(2)
        dt["CPL"] = dt.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
        dt["Inversión"] = dt["Inversión"].apply(lambda x: f"${x:,.0f}")
        dt["% Presup."] = dt["% Presup."].apply(lambda x: f"{x}%")
        dt["CTR"] = dt["CTR"].apply(lambda x: f"{x}%")
        dt["CPL"] = dt["CPL"].apply(lambda x: f"${x:,.2f}")
        for c in ["Impresiones", "Clicks", "Leads"]:
            dt[c] = dt[c].apply(lambda x: f"{x:,}")
        st.dataframe(dt.rename(columns={"pagina": "Página"}), use_container_width=True, hide_index=True)

    st.divider()

    # Time charts
    time_mode = st.radio("Agrupar por:", ["Mensual", "Semanal"], horizontal=True, key="ads_time_mode")
    time_col = "month" if time_mode == "Mensual" else "week"
    time_label = "Mes" if time_mode == "Mensual" else "Semana"

    st.subheader(f"Inversión {time_mode} por Tipo de Campaña")
    fig_mt = px.bar(df_f.groupby([time_col, "tipo"], as_index=False)["spend"].sum().sort_values(time_col),
                    x=time_col, y="spend", color="tipo", color_discrete_map=TYPE_COLORS,
                    labels={time_col: time_label, "spend": "Inversión ($)", "tipo": "Tipo"})
    fig_mt.update_layout(barmode="stack", height=450, margin=dict(t=20))
    st.plotly_chart(fig_mt, use_container_width=True)

    st.subheader(f"Inversión {time_mode} por Página / Doctor")
    fig_md = px.bar(df_f.groupby([time_col, "pagina"], as_index=False)["spend"].sum().sort_values(time_col),
                    x=time_col, y="spend", color="pagina", color_discrete_map=DOCTOR_COLORS,
                    labels={time_col: time_label, "spend": "Inversión ($)", "pagina": "Página"})
    fig_md.update_layout(barmode="stack", height=450, margin=dict(t=20))
    st.plotly_chart(fig_md, use_container_width=True)

    col_s, col_l = st.columns(2)
    time_agg = df_f.groupby(time_col, as_index=False).agg(spend=("spend", "sum"), leads=("leads", "sum")).sort_values(time_col)
    with col_s:
        st.subheader(f"Inversión {time_mode} Total")
        fig_s = px.bar(time_agg, x=time_col, y="spend", labels={time_col: time_label, "spend": "Inversión ($)"})
        fig_s.update_traces(marker_color="#4fc3f7")
        fig_s.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig_s, use_container_width=True)
    with col_l:
        st.subheader("Leads Semanales" if time_mode == "Semanal" else "Leads Mensuales")
        fig_l = px.bar(time_agg, x=time_col, y="leads", labels={time_col: time_label, "leads": "Leads"})
        fig_l.update_traces(marker_color="#4caf50")
        fig_l.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig_l, use_container_width=True)

    st.divider()

    # Daily Trend
    if not daily_df.empty:
        st.subheader("Tendencia Diaria — Últimos 90 Días")
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Scatter(x=daily_df["date"], y=daily_df["spend"], name="Inversión ($)",
                                       line=dict(color="#4fc3f7"), fill="tozeroy",
                                       fillcolor="rgba(79,195,247,0.1)", yaxis="y"))
        fig_daily.add_trace(go.Scatter(x=daily_df["date"], y=daily_df["leads"], name="Leads",
                                       line=dict(color="#4caf50"), fill="tozeroy",
                                       fillcolor="rgba(76,175,80,0.1)", yaxis="y2"))
        fig_daily.update_layout(height=400, margin=dict(t=20),
                                yaxis=dict(title="Inversión ($)", side="left"),
                                yaxis2=dict(title="Leads", side="right", overlaying="y"),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                hovermode="x unified")
        st.plotly_chart(fig_daily, use_container_width=True)

    st.divider()

    # Top Campaigns
    st.subheader("Top 30 Campañas por Inversión")
    camp = df_f.groupby(["campaign_id", "campaign", "tipo", "pagina"], as_index=False).agg(
        Inversión=("spend", "sum"), Impresiones=("impressions", "sum"),
        Clicks=("clicks", "sum"), Leads=("leads", "sum"),
    ).sort_values("Inversión", ascending=False).head(30)
    camp["CPL"] = camp.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
    cd = camp[["campaign", "tipo", "pagina", "Inversión", "Impresiones", "Clicks", "Leads", "CPL"]].copy()
    cd["Inversión"] = cd["Inversión"].apply(lambda x: f"${x:,.0f}")
    cd["CPL"] = cd["CPL"].apply(lambda x: f"${x:,.2f}")
    for c in ["Impresiones", "Clicks", "Leads"]:
        cd[c] = cd[c].apply(lambda x: f"{x:,}")
    st.dataframe(cd.rename(columns={"campaign": "Campaña", "tipo": "Tipo", "pagina": "Página"}),
                 use_container_width=True, hide_index=True, height=600)


# ── Tab: Ventas ─────────────────────────────────────────────────────────────

def render_sales_tab(date_start_str, date_end_str):
    """Render the Sales analysis tab."""

    # Sales data: load from cache on first run
    if "sales_df" not in st.session_state:
        cached_df, cached_updated = load_sales_cache()
        if cached_df is not None:
            st.session_state.sales_df = build_sales_dataframe(cached_df)
            st.session_state.sales_updated = cached_updated
        else:
            st.session_state.sales_df = None
            st.session_state.sales_updated = ""

    # Sidebar: status + upload + download
    st.sidebar.divider()
    st.sidebar.subheader("Datos de Ventas")

    if st.session_state.sales_df is not None:
        n = len(st.session_state.sales_df)
        upd = st.session_state.get("sales_updated", "")
        st.sidebar.caption(f"Base: {n:,} registros | Act: {upd}")

    uploaded = st.sidebar.file_uploader("Actualizar datos (CSV)", type="csv", key="sales_upload")

    if uploaded is not None:
        new_raw = pd.read_csv(uploaded, encoding="utf-8-sig")
        if st.session_state.sales_df is not None:
            combined, added = merge_sales(st.session_state.sales_df, new_raw)
            st.session_state.sales_df = combined
            st.session_state.sales_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.sidebar.success(f"Sincronizado: +{added:,} registros nuevos")
        else:
            st.session_state.sales_df = build_sales_dataframe(new_raw)
            st.session_state.sales_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.sidebar.success(f"Cargados {len(new_raw):,} registros")

    # Download merged data for committing to repo
    if st.session_state.sales_df is not None:
        dl_df = st.session_state.sales_df.drop(
            columns=["month", "week", "days_to_close", "proc_group"], errors="ignore"
        )
        dl_records = dl_df.to_dict(orient="records")
        dl_json = json.dumps({
            "records": dl_records,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_records": len(dl_records),
        }, ensure_ascii=False, default=str)
        st.sidebar.download_button(
            "Descargar cache actualizado",
            data=dl_json,
            file_name="sales_cache.json",
            mime="application/json",
            use_container_width=True,
        )

    df = st.session_state.sales_df

    if df is None:
        st.info("No hay datos de ventas. Ejecuta `update_sales.py` localmente o carga un CSV.")
        return

    # Filter by date range
    df = df[df["Sales Dates"].between(pd.Timestamp(date_start_str), pd.Timestamp(date_end_str))]

    if df.empty:
        st.warning("No hay ventas en el período seleccionado.")
        return

    # ── KPIs ──
    total_invoices = df["Invoice"].nunique()
    total_procs = int(df["Sales"].sum())
    procs_per_invoice = total_procs / total_invoices if total_invoices else 0
    q_signed_pct = (df["Q Signed"].str.upper() == "YES").mean() * 100
    q_approved_pct = (df["Q Approved"].str.upper() == "YES").mean() * 100
    median_days = df["days_to_close"].median() if df["days_to_close"].notna().any() else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Facturas", f"{total_invoices:,}")
    k2.metric("Procedimientos", f"{total_procs:,}")
    k3.metric("Procs/Factura", f"{procs_per_invoice:.2f}")
    k4.metric("Q Signed", f"{q_signed_pct:.1f}%")
    k5.metric("Q Approved", f"{q_approved_pct:.1f}%")
    k6.metric("Mediana días cierre", f"{median_days:.0f}")

    st.divider()

    # ── Donut: by Source and Procedure ──
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Ventas por Fuente (Top 15)")
        src = df.groupby("Source", as_index=False).agg(procs=("Sales", "sum")).sort_values("procs", ascending=False).head(15)
        src["pct"] = (src["procs"] / src["procs"].sum() * 100).round(1)
        src["label"] = src.apply(lambda r: f"{r['Source']}<br>{r['pct']}% ({r['procs']:,.0f})", axis=1)
        fig_src = px.pie(src, values="procs", names="Source", hole=0.4)
        fig_src.update_traces(text=src["label"], textinfo="text", textposition="outside",
                              textfont_size=12, outsidetextfont_size=12)
        fig_src.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig_src, use_container_width=True)

    with col2:
        st.subheader("Procedimientos más vendidos")
        proc = df.groupby("proc_group", as_index=False).agg(procs=("Sales", "sum")).sort_values("procs", ascending=False)
        proc["pct"] = (proc["procs"] / proc["procs"].sum() * 100).round(1)
        proc["label"] = proc.apply(lambda r: f"{r['proc_group']}<br>{r['pct']}% ({r['procs']:,.0f})", axis=1)
        fig_proc = px.pie(proc, values="procs", names="proc_group", hole=0.4)
        fig_proc.update_traces(text=proc["label"], textinfo="text", textposition="outside",
                               textfont_size=12, outsidetextfont_size=12)
        fig_proc.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig_proc, use_container_width=True)

    st.divider()

    # ── Consultants / Sellers ──
    st.subheader("Rendimiento por Vendedora")
    sellers = df.groupby("Consultant", as_index=False).agg(
        Facturas=("Invoice", "nunique"),
        Procedimientos=("Sales", "sum"),
        Aprobados=("Q Approved", lambda x: (x.str.upper() == "YES").sum()),
    ).sort_values("Procedimientos", ascending=False)
    sellers["% Aprobados"] = (sellers["Aprobados"] / sellers["Procedimientos"] * 100).round(1)
    sellers["Procs/Factura"] = (sellers["Procedimientos"] / sellers["Facturas"]).round(2)
    sellers["Procedimientos"] = sellers["Procedimientos"].astype(int)
    sellers["Aprobados"] = sellers["Aprobados"].astype(int)
    sellers["% Aprobados"] = sellers["% Aprobados"].apply(lambda x: f"{x}%")
    st.dataframe(sellers.rename(columns={"Consultant": "Vendedora"}),
                 use_container_width=True, hide_index=True)

    st.divider()

    # ── Time charts ──
    time_mode = st.radio("Agrupar por:", ["Mensual", "Semanal"], horizontal=True, key="sales_time_mode")
    time_col = "month" if time_mode == "Mensual" else "week"
    time_label = "Mes" if time_mode == "Mensual" else "Semana"

    col_s, col_p = st.columns(2)
    time_agg = df.groupby(time_col, as_index=False).agg(
        facturas=("Invoice", "nunique"), procs=("Sales", "sum")
    ).sort_values(time_col)

    with col_s:
        st.subheader(f"Facturas {time_mode}es" if time_mode == "Mensual" else "Facturas Semanales")
        fig = px.bar(time_agg, x=time_col, y="facturas", labels={time_col: time_label, "facturas": "Facturas"})
        fig.update_traces(marker_color="#4fc3f7")
        fig.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_p:
        st.subheader(f"Procedimientos {time_mode}es" if time_mode == "Mensual" else "Procedimientos Semanales")
        fig2 = px.bar(time_agg, x=time_col, y="procs", labels={time_col: time_label, "procs": "Procedimientos"})
        fig2.update_traces(marker_color="#4caf50")
        fig2.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── By Source stacked ──
    st.subheader(f"Ventas {time_mode}es por Fuente (Top 10)")
    top_sources = df.groupby("Source")["Sales"].sum().nlargest(10).index.tolist()
    df_top = df[df["Source"].isin(top_sources)]
    src_time = df_top.groupby([time_col, "Source"], as_index=False)["Sales"].sum().sort_values(time_col)
    fig_st = px.bar(src_time, x=time_col, y="Sales", color="Source",
                    labels={time_col: time_label, "Sales": "Procedimientos", "Source": "Fuente"})
    fig_st.update_layout(barmode="stack", height=450, margin=dict(t=20))
    st.plotly_chart(fig_st, use_container_width=True)

    # ── Geographic ──
    st.subheader("Ventas por Estado (Top 15)")
    states = df.groupby("State", as_index=False).agg(
        Procedimientos=("Sales", "sum"),
    ).sort_values("Procedimientos", ascending=False).head(15)
    states["Procedimientos"] = states["Procedimientos"].astype(int)
    fig_geo = px.bar(states, x="Procedimientos", y="State", orientation="h",
                     labels={"State": "Estado"})
    fig_geo.update_traces(marker_color="#9966FF")
    fig_geo.update_layout(height=450, margin=dict(t=20), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_geo, use_container_width=True)

    # ── Quality by Source ──
    st.subheader("Calidad por Fuente (Tasa de Aprobación)")
    quality = df.groupby("Source", as_index=False).agg(
        Total=("Sales", "sum"),
        Aprobados=("Q Approved", lambda x: (x.str.upper() == "YES").sum()),
    )
    quality = quality[quality["Total"] >= 10].copy()
    quality["% Aprobados"] = (quality["Aprobados"] / quality["Total"] * 100).round(1)
    quality = quality.sort_values("% Aprobados", ascending=False).head(20)
    fig_q = px.bar(quality, x="% Aprobados", y="Source", orientation="h",
                   text="% Aprobados", labels={"Source": "Fuente"})
    fig_q.update_traces(marker_color="#4caf50", texttemplate="%{text}%", textposition="outside")
    fig_q.update_layout(height=500, margin=dict(t=20), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_q, use_container_width=True)


# ── Tab: Cross-Analysis ───────────────────────────────────────────────────

def render_cross_tab(df_ads, date_start_str, date_end_str):
    """Cross-analysis: Meta spend vs CRM sales by source."""

    df_sales = st.session_state.get("sales_df")
    if df_sales is None:
        st.info("Carga un CSV de ventas en la pestaña **Ventas** para ver el cruce Meta vs Ventas.")
        return

    # Leads data: load from cache + optional upload to update
    leads_map = {}

    # Load cached leads
    if "leads_df" not in st.session_state:
        cached_leads, leads_updated = load_leads_cache()
        if cached_leads is not None:
            st.session_state.leads_df = cached_leads
            st.session_state.leads_updated = leads_updated
        else:
            st.session_state.leads_df = None
            st.session_state.leads_updated = ""

    st.sidebar.divider()
    st.sidebar.subheader("Datos de Leads")

    if st.session_state.get("leads_df") is not None:
        n_leads = len(st.session_state.leads_df)
        leads_upd = st.session_state.get("leads_updated", "")
        st.sidebar.caption(f"Base: {n_leads} fuentes | Act: {leads_upd}")

    leads_file = st.sidebar.file_uploader("Actualizar leads (CSV)", type="csv", key="leads_csv")
    if leads_file is not None:
        ldf = pd.read_csv(leads_file, encoding="utf-8-sig")
        st.session_state.leads_df = ldf
        st.session_state.leads_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        st.sidebar.success(f"{len(ldf)} fuentes actualizadas")

        # Download for committing
        dl_records = ldf.to_dict(orient="records")
        for r in dl_records:
            for k, v in r.items():
                if pd.isna(v):
                    r[k] = None
        dl_json = json.dumps({
            "records": dl_records,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_sources": len(dl_records),
        }, ensure_ascii=False, default=str)
        st.sidebar.download_button(
            "Descargar leads cache",
            data=dl_json, file_name="leads_cache.json",
            mime="application/json", use_container_width=True,
        )

    # Build leads_map from whatever source we have
    ldf = st.session_state.get("leads_df")
    if ldf is not None and "Source" in ldf.columns and "Accepted" in ldf.columns:
        for _, r in ldf.iterrows():
            k = crm_source_to_meta_key(str(r.get("Source", "")))
            if k:
                leads_map[k] = leads_map.get(k, 0) + int(r.get("Accepted", 0))

    # Filter by dates
    df_s = df_sales[df_sales["Sales Dates"].between(
        pd.Timestamp(date_start_str), pd.Timestamp(date_end_str)
    )].copy()
    df_a = df_ads.copy()

    if df_s.empty:
        st.warning("No hay ventas en el periodo seleccionado.")
        return

    # Map source keys
    df_a["source_key"] = df_a["campaign"].apply(meta_campaign_to_source_key)
    df_s["source_key"] = df_s["Source"].apply(crm_source_to_meta_key)

    # Aggregate ads by source key
    ads_g = df_a[df_a["source_key"].notna()].groupby("source_key", as_index=False).agg(
        spend=("spend", "sum"), leads_meta=("leads", "sum"))

    # Aggregate sales by source key
    sales_g = df_s[df_s["source_key"].notna()].groupby("source_key", as_index=False).agg(
        facturas=("Invoice", "nunique"), procs=("Sales", "sum"))

    # Merge
    cross = pd.merge(ads_g, sales_g, on="source_key", how="outer").fillna(0)
    for c in ["procs", "facturas", "leads_meta"]:
        cross[c] = cross[c].astype(int)

    # Add CRM leads if available
    if leads_map:
        cross["leads_crm"] = cross["source_key"].map(leads_map).fillna(0).astype(int)

    # Metrics
    cross["cpp"] = cross.apply(lambda r: r["spend"] / r["procs"] if r["procs"] > 0 else 0, axis=1)
    cross["cps"] = cross.apply(lambda r: r["spend"] / r["facturas"] if r["facturas"] > 0 else 0, axis=1)
    if leads_map:
        cross["cpl"] = cross.apply(
            lambda r: r["spend"] / r["leads_crm"] if r.get("leads_crm", 0) > 0 else 0, axis=1)
        cross["conv"] = cross.apply(
            lambda r: r["facturas"] / r["leads_crm"] * 100 if r.get("leads_crm", 0) > 0 else 0, axis=1)

    cross["label"] = cross["source_key"].apply(source_key_label)

    # Separate brand and active rows
    brand_spend = cross.loc[cross["source_key"] == "BRAND", "spend"].sum()
    cx = cross[
        (cross["source_key"] != "BRAND") & ((cross["spend"] > 0) | (cross["procs"] > 0))
    ].sort_values("spend", ascending=False).copy()

    # Non-Meta sales
    non_meta = df_s[df_s["source_key"].isna()]
    non_meta_procs = int(non_meta["Sales"].sum())

    total_spend = cx["spend"].sum()
    meta_procs = int(cx["procs"].sum())
    meta_fact = int(cx["facturas"].sum())
    total_procs = int(df_s["Sales"].sum())
    pct = meta_procs / total_procs * 100 if total_procs else 0

    # ── KPIs ──
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Inversión Meta", f"${total_spend:,.0f}")
    k2.metric("Ventas Meta", f"{meta_fact:,} facturas")
    k3.metric("Procs Meta", f"{meta_procs:,}")
    k4.metric("% Procs de Meta", f"{pct:.1f}%")
    k5.metric("Costo / Factura", f"${total_spend / meta_fact:,.0f}" if meta_fact else "-")
    k6.metric("Costo / Proc", f"${total_spend / meta_procs:,.0f}" if meta_procs else "-")

    st.divider()

    # ── Main Table ──
    st.subheader("Desglose por Fuente")
    cols = ["label", "spend", "leads_meta"]
    names = {"label": "Fuente", "spend": "Inversión", "leads_meta": "Leads (Meta)"}
    if leads_map:
        cols.append("leads_crm")
        names["leads_crm"] = "Leads (CRM)"
    cols += ["facturas", "procs", "cpp", "cps"]
    names.update({"facturas": "Facturas", "procs": "Procs", "cpp": "$/Proc", "cps": "$/Factura"})
    if leads_map:
        cols += ["cpl", "conv"]
        names.update({"cpl": "CPL", "conv": "Lead→Venta %"})

    fmt = cx[cols].copy()
    fmt["spend"] = cx["spend"].apply(lambda x: f"${x:,.0f}")
    fmt["leads_meta"] = cx["leads_meta"].apply(lambda x: f"{x:,}")
    fmt["cpp"] = cx["cpp"].apply(lambda x: f"${x:,.0f}" if x > 0 else "-")
    fmt["cps"] = cx["cps"].apply(lambda x: f"${x:,.0f}" if x > 0 else "-")
    if leads_map:
        fmt["leads_crm"] = cx["leads_crm"].apply(lambda x: f"{x:,}")
        fmt["cpl"] = cx["cpl"].apply(lambda x: f"${x:.2f}" if x > 0 else "-")
        fmt["conv"] = cx["conv"].apply(lambda x: f"{x:.1f}%" if x > 0 else "-")

    st.dataframe(fmt.rename(columns=names), use_container_width=True, hide_index=True, height=500)

    st.divider()

    # ── Donut: spend distribution vs sales origin ──
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribución de Inversión")
        inv_data = cx[cx["spend"] > 0].copy()
        inv_data["pct"] = (inv_data["spend"] / inv_data["spend"].sum() * 100).round(1)
        inv_data["text"] = inv_data.apply(
            lambda r: f"{r['label']}<br>{r['pct']}% — ${r['spend']:,.0f}", axis=1)
        fig1 = px.pie(inv_data, values="spend", names="label", hole=0.4)
        fig1.update_traces(text=inv_data["text"], textinfo="text", textposition="outside",
                           textfont_size=11, outsidetextfont_size=11)
        fig1.update_layout(showlegend=False, height=500, margin=dict(t=40, b=80, l=60, r=60))
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Origen de Ventas (Procs)")
        meta_row = pd.DataFrame(cx.groupby(cx["source_key"].apply(
            lambda k: "Meta (por fuente)" if k else "")).agg({"procs": "sum"}).reset_index())
        all_origin = pd.DataFrame([
            {"origen": "Meta Ads", "procs": meta_procs},
            {"origen": "No Meta", "procs": non_meta_procs},
        ])
        fig2 = px.pie(all_origin, values="procs", names="origen", hole=0.4,
                       color_discrete_sequence=["#4fc3f7", "#ff9800"])
        fig2.update_traces(
            text=all_origin.apply(
                lambda r: f"{r['origen']}<br>{r['procs']:,} ({r['procs']/total_procs*100:.1f}%)", axis=1),
            textinfo="text", textposition="outside", textfont_size=13)
        fig2.update_layout(showlegend=False, height=500, margin=dict(t=40, b=80, l=60, r=60))
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── Cost per Procedure bar ──
    st.subheader("Costo por Procedimiento por Fuente")
    cpp_d = cx[cx["cpp"] > 0].sort_values("cpp")
    fig3 = px.bar(cpp_d, y="label", x="cpp", orientation="h",
                  text=cpp_d["cpp"].apply(lambda x: f"${x:,.0f}"),
                  labels={"label": "", "cpp": "$/Procedimiento"})
    fig3.update_traces(marker_color="#FF6384", textposition="outside")
    fig3.update_layout(height=max(350, len(cpp_d) * 28 + 100), margin=dict(t=20, l=200))
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # ── Spend vs Procs comparison ──
    st.subheader("Inversión vs Procedimientos")
    comp = cx[(cx["spend"] > 0) & (cx["procs"] > 0)].sort_values("procs", ascending=True).copy()
    if not comp.empty:
        comp["spend_pct"] = (comp["spend"] / comp["spend"].sum() * 100).round(1)
        comp["procs_pct"] = (comp["procs"] / comp["procs"].sum() * 100).round(1)
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(y=comp["label"], x=comp["spend_pct"], name="% Inversión",
                              orientation="h", marker_color="#4fc3f7",
                              text=comp["spend_pct"].apply(lambda x: f"{x:.1f}%"),
                              textposition="outside"))
        fig4.add_trace(go.Bar(y=comp["label"], x=comp["procs_pct"], name="% Procedimientos",
                              orientation="h", marker_color="#4caf50",
                              text=comp["procs_pct"].apply(lambda x: f"{x:.1f}%"),
                              textposition="outside"))
        fig4.update_layout(barmode="group", height=max(350, len(comp) * 35 + 100),
                           margin=dict(t=20, l=200),
                           legend=dict(orientation="h", yanchor="bottom", y=1.02),
                           xaxis_title="% del total")
        st.plotly_chart(fig4, use_container_width=True)

    st.divider()

    # ── Non-Meta sources ──
    col_n, col_s = st.columns([2, 1])
    with col_n:
        st.subheader(f"Ventas No-Meta ({non_meta_procs:,} procs)")
        if not non_meta.empty:
            nm = non_meta.groupby("Source", as_index=False).agg(
                facturas=("Invoice", "nunique"), procs=("Sales", "sum")
            ).sort_values("procs", ascending=False)
            nm["procs"] = nm["procs"].astype(int)
            st.dataframe(
                nm.head(20).rename(columns={"Source": "Fuente", "facturas": "Facturas", "procs": "Procs"}),
                use_container_width=True, hide_index=True)

    with col_s:
        st.subheader("Resumen General")
        st.metric("Total Procs (todas fuentes)", f"{total_procs:,}")
        st.metric("Procs de Meta", f"{meta_procs:,} ({pct:.1f}%)")
        st.metric("Procs No-Meta", f"{total_procs - meta_procs:,} ({100-pct:.1f}%)")
        if brand_spend > 0:
            st.metric("Brand/Awareness (sin atrib.)", f"${brand_spend:,.0f}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    date_start_str, date_end_str = render_sidebar()

    # Load ads data
    raw_insights, last_updated = load_cached_data()
    if not raw_insights:
        st.warning("No se encontraron datos de ads. Ejecuta update_cache.py localmente.")
        st.stop()

    st.sidebar.caption(f"Ads actualizados: {last_updated}")

    df_ads = build_ads_dataframe(raw_insights)
    df_ads = df_ads[df_ads["date_start"].between(pd.Timestamp(date_start_str), pd.Timestamp(date_end_str))]

    # Daily trend from ads data
    date_90_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    df_recent = df_ads[df_ads["date_start"] >= pd.Timestamp(date_90_ago)].copy()
    df_recent["date"] = df_recent["date_start"].dt.strftime("%Y-%m-%d")
    daily_df = df_recent.groupby("date", as_index=False).agg(
        spend=("spend", "sum"), clicks=("clicks", "sum"), leads=("leads", "sum")
    ).sort_values("date")

    # Navigation
    st.title("📊 Beautyland Plastic Surgery")
    tab_ads, tab_sales, tab_cross = st.tabs(["🎯 Meta Ads", "💰 Ventas", "🔄 Meta vs Ventas"])

    with tab_ads:
        render_ads_tab(df_ads, daily_df, date_start_str, date_end_str)

    with tab_sales:
        render_sales_tab(date_start_str, date_end_str)

    with tab_cross:
        render_cross_tab(df_ads, date_start_str, date_end_str)

    # Footer
    st.divider()
    st.caption(f"Dashboard BLPS  |  Última actualización ads: {last_updated}")


if __name__ == "__main__":
    main()
