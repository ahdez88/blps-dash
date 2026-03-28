"""
BLPS Meta Ads Dashboard — Streamlit App
"""

import streamlit as st
import requests
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import defaultdict

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BLPS Meta Ads Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth ────────────────────────────────────────────────────────────────────
def check_password():
    """Simple password gate."""
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

# ── Colors ──────────────────────────────────────────────────────────────────
TYPE_COLORS = {
    "Instant Form": "#FF6384",
    "Landing Page": "#36A2EB",
    "Sales / Conversiones": "#FFCE56",
    "Mensajes IG/DM": "#4BC0C0",
    "WhatsApp": "#25D366",
    "Brand / Awareness": "#9966FF",
    "Tráfico": "#FF9F40",
    "Leads (sin clasificar)": "#C9CBCF",
    "Engagement (sin clasificar)": "#E7E9ED",
    "Otro": "#999999",
}
DOCTOR_COLORS = {
    "Dr. Simmons": "#FF6384",
    "Dr. Flores": "#36A2EB",
    "Dra. Sophie": "#FFCE56",
    "Dr. Salgado": "#4BC0C0",
    "Clínica (BLPS)": "#9966FF",
    "Mix Doctores": "#FF9F40",
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


# ── API ─────────────────────────────────────────────────────────────────────

def fetch_all_pages(url, params, max_retries=3):
    all_data = []
    while url:
        for attempt in range(max_retries):
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                break
            if resp.status_code == 403 and "request limit" in resp.text.lower():
                wait = 15 * (attempt + 1)
                time.sleep(wait)
            else:
                st.warning(f"API Error {resp.status_code}: {resp.text[:150]}")
                return all_data
        else:
            st.warning(f"Rate limit persistente — se omitió parte de los datos.")
            return all_data

        data = resp.json()
        all_data.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}
        time.sleep(0.5)
    return all_data


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_all_data(date_start, date_end):
    """Fetch data from all ad accounts. Cached for 2 hours."""
    all_insights = []
    all_daily = []
    date_90_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    progress = st.progress(0, text="Cargando datos de Meta...")
    for i, (account_id, account_name) in enumerate(AD_ACCOUNTS.items()):
        progress.progress((i) / len(AD_ACCOUNTS), text=f"Cargando {account_name}...")

        # Monthly insights
        insights = fetch_all_pages(
            f"{BASE_URL}/{account_id}/insights",
            {
                "fields": "campaign_id,campaign_name,objective,spend,impressions,reach,clicks,actions",
                "level": "campaign",
                "time_range": json.dumps({"since": date_start, "until": date_end}),
                "time_increment": "monthly",
                "limit": 500,
                "access_token": TOKEN,
            }
        )
        for row in insights:
            row["_account"] = account_name
        all_insights.extend(insights)

        time.sleep(2)

        # Daily insights (last 90 days) — account level (no campaign breakdown) to reduce API load
        daily = fetch_all_pages(
            f"{BASE_URL}/{account_id}/insights",
            {
                "fields": "spend,impressions,clicks,actions",
                "time_range": json.dumps({"since": date_90_ago, "until": date_end}),
                "time_increment": 1,
                "limit": 100,
                "access_token": TOKEN,
            }
        )
        all_daily.extend(daily)

        time.sleep(2)

    progress.progress(1.0, text="Datos cargados!")
    return all_insights, all_daily


# ── Processing ──────────────────────────────────────────────────────────────

def extract_leads(actions):
    if not actions:
        return 0
    for a in actions:
        if a.get("action_type") in ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"):
            return int(a.get("value", 0))
    return 0


def build_dataframe(insights):
    """Convert raw insights into a classified DataFrame."""
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
        # Week: Monday to Sunday (ISO)
        df["week"] = df["date_start"].dt.to_period("W-SUN").astype(str)
    return df


def build_daily_df(daily_insights):
    rows = []
    for row in daily_insights:
        rows.append({
            "date": row.get("date_start", ""),
            "spend": float(row.get("spend", 0)),
            "clicks": int(row.get("clicks", 0)),
            "leads": extract_leads(row.get("actions")),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.groupby("date", as_index=False).sum()
        df = df.sort_values("date")
    return df


# ── Dashboard UI ────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        st.error("⚠️ No se encontró META_ACCESS_TOKEN. Configúralo en Secrets.")
        st.stop()

    # ── Sidebar ──
    st.sidebar.image("https://beautylandplasticsurgery.com/wp-content/uploads/2024/07/logo-beautyland.webp", width=200)
    st.sidebar.title("Filtros")

    today = datetime.now().date()
    # Monday of current week
    this_monday = today - timedelta(days=today.weekday())
    # First day of current month
    first_of_month = today.replace(day=1)
    # First day of previous month
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

    date_start_str = date_start.strftime("%Y-%m-%d")
    date_end_str = date_end.strftime("%Y-%m-%d")

    if st.sidebar.button("🔄 Actualizar datos", type="primary", use_container_width=True):
        st.cache_data.clear()

    # ── Fetch & Process ──
    raw_insights, raw_daily = fetch_all_data(date_start_str, date_end_str)

    if not raw_insights:
        st.warning("No se encontraron datos para el período seleccionado.")
        st.stop()

    df = build_dataframe(raw_insights)
    daily_df = build_daily_df(raw_daily)

    # Sidebar filters
    all_types = sorted(df["tipo"].unique())
    all_doctors = sorted(df["pagina"].unique())

    selected_types = st.sidebar.multiselect("Tipo de campaña", all_types, default=all_types)
    selected_doctors = st.sidebar.multiselect("Página / Doctor", all_doctors, default=all_doctors)

    # Apply filters
    mask = df["tipo"].isin(selected_types) & df["pagina"].isin(selected_doctors)
    df_filtered = df[mask]

    # ── Header ──
    st.title("📊 Beautyland Plastic Surgery — Meta Ads Dashboard")
    st.caption(f"Período: {date_start_str} → {date_end_str}  |  {len(df_filtered['campaign_id'].unique())} campañas  |  6 cuentas publicitarias")

    # ── KPI Cards ──
    total_spend = df_filtered["spend"].sum()
    total_impressions = df_filtered["impressions"].sum()
    total_clicks = df_filtered["clicks"].sum()
    total_leads = df_filtered["leads"].sum()
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

    # ── Donut Charts ──
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Inversión por Tipo de Campaña")
        type_df = df_filtered.groupby("tipo", as_index=False)["spend"].sum().sort_values("spend", ascending=False)
        type_df["pct"] = (type_df["spend"] / type_df["spend"].sum() * 100).round(1)
        type_df["label"] = type_df.apply(lambda r: f"{r['tipo']}<br>{r['pct']}% — ${r['spend']:,.0f}", axis=1)
        color_map = {t: TYPE_COLORS.get(t, "#888") for t in type_df["tipo"]}
        fig_type = px.pie(type_df, values="spend", names="tipo", hole=0.45,
                          color="tipo", color_discrete_map=color_map)
        fig_type.update_traces(
            text=type_df["label"], textinfo="text", textposition="outside",
            textfont_size=13, outsidetextfont_size=13,
        )
        fig_type.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig_type, use_container_width=True)

    with col2:
        st.subheader("Inversión por Página / Doctor")
        doc_df = df_filtered.groupby("pagina", as_index=False)["spend"].sum().sort_values("spend", ascending=False)
        doc_df["pct"] = (doc_df["spend"] / doc_df["spend"].sum() * 100).round(1)
        doc_df["label"] = doc_df.apply(lambda r: f"{r['pagina']}<br>{r['pct']}% — ${r['spend']:,.0f}", axis=1)
        color_map_doc = {d: DOCTOR_COLORS.get(d, "#888") for d in doc_df["pagina"]}
        fig_doc = px.pie(doc_df, values="spend", names="pagina", hole=0.45,
                         color="pagina", color_discrete_map=color_map_doc)
        fig_doc.update_traces(
            text=doc_df["label"], textinfo="text", textposition="outside",
            textfont_size=13, outsidetextfont_size=13,
        )
        fig_doc.update_layout(showlegend=False, margin=dict(t=40, b=80, l=60, r=60), height=500)
        st.plotly_chart(fig_doc, use_container_width=True)

    st.divider()

    # ── Breakdown Tables ──
    col_t, col_d = st.columns(2)

    with col_t:
        st.subheader("Desglose por Tipo de Campaña")
        type_table = df_filtered.groupby("tipo", as_index=False).agg(
            Inversión=("spend", "sum"),
            Impresiones=("impressions", "sum"),
            Clicks=("clicks", "sum"),
            Leads=("leads", "sum"),
        ).sort_values("Inversión", ascending=False)
        type_table["% Presup."] = (type_table["Inversión"] / type_table["Inversión"].sum() * 100).round(1)
        type_table["CTR"] = (type_table["Clicks"] / type_table["Impresiones"] * 100).round(2)
        type_table["CPL"] = type_table.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
        type_table["Inversión"] = type_table["Inversión"].apply(lambda x: f"${x:,.0f}")
        type_table["% Presup."] = type_table["% Presup."].apply(lambda x: f"{x}%")
        type_table["CTR"] = type_table["CTR"].apply(lambda x: f"{x}%")
        type_table["CPL"] = type_table["CPL"].apply(lambda x: f"${x:,.2f}")
        type_table["Impresiones"] = type_table["Impresiones"].apply(lambda x: f"{x:,}")
        type_table["Clicks"] = type_table["Clicks"].apply(lambda x: f"{x:,}")
        type_table["Leads"] = type_table["Leads"].apply(lambda x: f"{x:,}")
        st.dataframe(type_table.rename(columns={"tipo": "Tipo"}), use_container_width=True, hide_index=True)

    with col_d:
        st.subheader("Desglose por Página / Doctor")
        doc_table = df_filtered.groupby("pagina", as_index=False).agg(
            Inversión=("spend", "sum"),
            Impresiones=("impressions", "sum"),
            Clicks=("clicks", "sum"),
            Leads=("leads", "sum"),
        ).sort_values("Inversión", ascending=False)
        doc_table["% Presup."] = (doc_table["Inversión"] / doc_table["Inversión"].sum() * 100).round(1)
        doc_table["CTR"] = (doc_table["Clicks"] / doc_table["Impresiones"] * 100).round(2)
        doc_table["CPL"] = doc_table.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
        doc_table["Inversión"] = doc_table["Inversión"].apply(lambda x: f"${x:,.0f}")
        doc_table["% Presup."] = doc_table["% Presup."].apply(lambda x: f"{x}%")
        doc_table["CTR"] = doc_table["CTR"].apply(lambda x: f"{x}%")
        doc_table["CPL"] = doc_table["CPL"].apply(lambda x: f"${x:,.2f}")
        doc_table["Impresiones"] = doc_table["Impresiones"].apply(lambda x: f"{x:,}")
        doc_table["Clicks"] = doc_table["Clicks"].apply(lambda x: f"{x:,}")
        doc_table["Leads"] = doc_table["Leads"].apply(lambda x: f"{x:,}")
        st.dataframe(doc_table.rename(columns={"pagina": "Página"}), use_container_width=True, hide_index=True)

    st.divider()

    # ── Time Period Toggle ──
    time_mode = st.radio("Agrupar por:", ["Mensual", "Semanal"], horizontal=True, key="time_mode")
    time_col = "month" if time_mode == "Mensual" else "week"
    time_label = "Mes" if time_mode == "Mensual" else "Semana"

    # ── Stacked Bar: by Type ──
    st.subheader(f"Inversión {time_mode} por Tipo de Campaña")
    time_type = df_filtered.groupby([time_col, "tipo"], as_index=False)["spend"].sum().sort_values(time_col)
    fig_mt = px.bar(time_type, x=time_col, y="spend", color="tipo",
                    color_discrete_map=TYPE_COLORS,
                    labels={time_col: time_label, "spend": "Inversión ($)", "tipo": "Tipo"})
    fig_mt.update_layout(barmode="stack", height=450, margin=dict(t=20))
    st.plotly_chart(fig_mt, use_container_width=True)

    # ── Stacked Bar: by Doctor ──
    st.subheader(f"Inversión {time_mode} por Página / Doctor")
    time_doc = df_filtered.groupby([time_col, "pagina"], as_index=False)["spend"].sum().sort_values(time_col)
    fig_md = px.bar(time_doc, x=time_col, y="spend", color="pagina",
                    color_discrete_map=DOCTOR_COLORS,
                    labels={time_col: time_label, "spend": "Inversión ($)", "pagina": "Página"})
    fig_md.update_layout(barmode="stack", height=450, margin=dict(t=20))
    st.plotly_chart(fig_md, use_container_width=True)

    # ── Totals ──
    col_s, col_l = st.columns(2)
    time_agg = df_filtered.groupby(time_col, as_index=False).agg(spend=("spend", "sum"), leads=("leads", "sum")).sort_values(time_col)

    with col_s:
        st.subheader(f"Inversión {time_mode} Total")
        fig_s = px.bar(time_agg, x=time_col, y="spend",
                       labels={time_col: time_label, "spend": "Inversión ($)"})
        fig_s.update_traces(marker_color="#4fc3f7")
        fig_s.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig_s, use_container_width=True)

    with col_l:
        st.subheader(f"Leads {time_mode}es" if time_mode == "Mensual" else "Leads Semanales")
        fig_l = px.bar(time_agg, x=time_col, y="leads",
                       labels={time_col: time_label, "leads": "Leads"})
        fig_l.update_traces(marker_color="#4caf50")
        fig_l.update_layout(height=350, margin=dict(t=20))
        st.plotly_chart(fig_l, use_container_width=True)

    st.divider()

    # ── Daily Trend ──
    if not daily_df.empty:
        st.subheader("Tendencia Diaria — Últimos 90 Días")
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"], y=daily_df["spend"],
            name="Inversión ($)", line=dict(color="#4fc3f7"), fill="tozeroy",
            fillcolor="rgba(79,195,247,0.1)", yaxis="y"
        ))
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"], y=daily_df["leads"],
            name="Leads", line=dict(color="#4caf50"), fill="tozeroy",
            fillcolor="rgba(76,175,80,0.1)", yaxis="y2"
        ))
        fig_daily.update_layout(
            height=400, margin=dict(t=20),
            yaxis=dict(title="Inversión ($)", side="left"),
            yaxis2=dict(title="Leads", side="right", overlaying="y"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
        )
        st.plotly_chart(fig_daily, use_container_width=True)

    st.divider()

    # ── Top Campaigns Table ──
    st.subheader("Top 30 Campañas por Inversión")
    camp_df = df_filtered.groupby(["campaign_id", "campaign", "tipo", "pagina"], as_index=False).agg(
        Inversión=("spend", "sum"),
        Impresiones=("impressions", "sum"),
        Clicks=("clicks", "sum"),
        Leads=("leads", "sum"),
    ).sort_values("Inversión", ascending=False).head(30)
    camp_df["CPL"] = camp_df.apply(lambda r: round(r["Inversión"] / r["Leads"], 2) if r["Leads"] > 0 else 0, axis=1)
    camp_display = camp_df[["campaign", "tipo", "pagina", "Inversión", "Impresiones", "Clicks", "Leads", "CPL"]].copy()
    camp_display["Inversión"] = camp_display["Inversión"].apply(lambda x: f"${x:,.0f}")
    camp_display["CPL"] = camp_display["CPL"].apply(lambda x: f"${x:,.2f}")
    camp_display["Impresiones"] = camp_display["Impresiones"].apply(lambda x: f"{x:,}")
    camp_display["Clicks"] = camp_display["Clicks"].apply(lambda x: f"{x:,}")
    camp_display["Leads"] = camp_display["Leads"].apply(lambda x: f"{x:,}")
    st.dataframe(
        camp_display.rename(columns={"campaign": "Campaña", "tipo": "Tipo", "pagina": "Página"}),
        use_container_width=True, hide_index=True, height=600
    )

    # ── Footer ──
    st.divider()
    st.caption(f"Beautyland Plastic Surgery — Dashboard generado desde Meta Marketing API  |  Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
