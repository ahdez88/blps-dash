"""
BLPS Meta Ads Dashboard Generator
Fetches data from Meta Marketing API and generates an interactive HTML dashboard.
"""

import requests
import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = os.getenv("META_ACCESS_TOKEN", "")
if not TOKEN:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("META_ACCESS_TOKEN="):
                    TOKEN = line.strip().split("=", 1)[1]

AD_ACCOUNTS = [
    "act_5302103159848505",  # BL AC 01
    "act_234789602496820",   # BL AC 2
    "act_1542649216514133",  # BL AC 3
    "act_836269185004901",   # BL AC 2
    "act_938706057445508",   # BL-plastic
    "act_811057274877067",   # BLPS-LIDERIFY
]

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# Date range: Jan 1 2025 to today
DATE_START = "2025-01-01"
DATE_END = datetime.now().strftime("%Y-%m-%d")


# ── Campaign Classification ────────────────────────────────────────────────

def classify_campaign_type(name, objective):
    """Classify campaign by type based on name patterns and objective."""
    name_upper = name.upper()

    # Sales/Conversions (by objective first)
    if objective == "OUTCOME_SALES":
        return "Sales / Conversiones"

    # Traffic
    if objective == "OUTCOME_TRAFFIC":
        return "Tráfico"

    # WhatsApp (check before general messages)
    if any(kw in name_upper for kw in ["WHA", "WPP", "WHATS APP", "WHATSAPP"]):
        return "WhatsApp"

    # Messages / Instagram DM
    if any(kw in name_upper for kw in ["MESSAGE", "-MES-", "| MES |", "DIRECT", "[MESSAGE]"]):
        return "Mensajes IG/DM"

    # Brand / Awareness / Video
    if objective == "OUTCOME_AWARENESS":
        return "Brand / Awareness"
    if any(kw in name_upper for kw in ["VIDEO PLAY", "REPRODUCCIONVIDEO", "VDEO_PLAY", "VIDEO_PLAY"]):
        return "Brand / Awareness"
    if any(kw in name_upper for kw in ["[REACH]", "BA |", "ENGAGEMENT |"]):
        return "Brand / Awareness"

    # Call Center (engagement but specific)
    if "CALL CENTER" in name_upper:
        return "Mensajes IG/DM"

    # Instant Form (check before LP since some IF campaigns have OUTCOME_LEADS)
    if any(kw in name_upper for kw in [
        "IF ", "IF|", "IF-", "-IF-",
        "INSTANTFORM", "INSTANT FORM",
        "LEADSONFB", "[FORMS]", "FORMS |",
        "-IF_", "IF_"
    ]):
        return "Instant Form"

    # Landing Page / Website
    if any(kw in name_upper for kw in [
        "LP", "WEBSITE", "WEB ", "WEB|", "-LP-",
        "[WEBSITE]", "[SITE]", "SITE |",
        "CADASTRO"
    ]):
        return "Landing Page"

    # Fallback by objective
    if objective == "OUTCOME_LEADS":
        return "Leads (sin clasificar)"
    if objective == "OUTCOME_ENGAGEMENT":
        return "Engagement (sin clasificar)"

    return "Otro"


def classify_doctor(name):
    """Classify campaign by doctor/page based on name patterns."""
    name_upper = name.upper()

    # Check specific doctors first (order matters for mixed names)
    has_simmons = any(kw in name_upper for kw in ["SIMMONS", "DRSIMMONS", "DR SIMMONS", "DR. SIMMONS"])
    has_flores = any(kw in name_upper for kw in ["FLORES", "DRFLORES", "DR FLORES", "DR. FLORES"])
    has_sophie = any(kw in name_upper for kw in ["SOPHIE", "DRSOPHIE", "DR SOPHIE", "LESSARD", "DRSOPHIE"])
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

    # Mix doctors patterns
    if any(kw in name_upper for kw in ["MIXDRS", "MIX DRS", "[DOCTORS]", "DOCTORS |", "DOCTOR |"]):
        return "Mix Doctores"

    # Clinic/Brand
    if any(kw in name_upper for kw in ["BLPS", "BEAUTYLAND", "BEAUTY LAND", "CLINICA", "CLINIC", "BEAUTY |", "[BEAUTY]"]):
        return "Clínica (BLPS)"

    return "Sin clasificar"


# ── API Fetching ────────────────────────────────────────────────────────────

def fetch_all_pages(url, params):
    """Fetch all pages of a paginated Meta API response."""
    all_data = []
    while url:
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            print(f"  Error {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        all_data.extend(data.get("data", []))
        paging = data.get("paging", {})
        url = paging.get("next")
        params = {}  # next URL already includes params
    return all_data


def fetch_campaigns_with_insights(account_id):
    """Fetch all campaigns and their insights for an account."""
    print(f"  Fetching campaigns for {account_id}...")

    # Get campaigns
    campaigns = fetch_all_pages(
        f"{BASE_URL}/{account_id}/campaigns",
        {
            "fields": "name,objective,status",
            "limit": 200,
            "access_token": TOKEN,
        }
    )
    print(f"    Found {len(campaigns)} campaigns")

    # Get insights at campaign level with date breakdown
    print(f"    Fetching insights...")
    insights = fetch_all_pages(
        f"{BASE_URL}/{account_id}/insights",
        {
            "fields": "campaign_id,campaign_name,objective,spend,impressions,reach,clicks,cpc,cpm,ctr,actions",
            "level": "campaign",
            "time_range": json.dumps({"since": DATE_START, "until": DATE_END}),
            "time_increment": "monthly",
            "limit": 500,
            "access_token": TOKEN,
        }
    )
    print(f"    Got {len(insights)} insight rows")

    # Also get daily insights for trend chart (last 90 days)
    date_90_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    daily_insights = fetch_all_pages(
        f"{BASE_URL}/{account_id}/insights",
        {
            "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions",
            "level": "campaign",
            "time_range": json.dumps({"since": date_90_ago, "until": DATE_END}),
            "time_increment": 1,
            "limit": 1000,
            "access_token": TOKEN,
        }
    )
    print(f"    Got {len(daily_insights)} daily insight rows")

    return campaigns, insights, daily_insights


# ── Data Processing ─────────────────────────────────────────────────────────

def extract_leads_from_actions(actions):
    """Extract lead count from actions array."""
    if not actions:
        return 0
    for action in actions:
        if action.get("action_type") in ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"):
            return int(action.get("value", 0))
    return 0


def process_data(all_campaigns, all_insights, all_daily_insights):
    """Process raw API data into dashboard-ready structures."""

    # Build campaign lookup
    campaign_lookup = {}
    for c in all_campaigns:
        campaign_lookup[c["id"]] = c

    # ── Aggregate by campaign type ──
    type_totals = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "leads": 0})
    doctor_totals = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "leads": 0})
    monthly_totals = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "leads": 0})
    monthly_by_type = defaultdict(lambda: defaultdict(lambda: {"spend": 0}))
    monthly_by_doctor = defaultdict(lambda: defaultdict(lambda: {"spend": 0}))
    campaign_totals = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0, "leads": 0, "name": "", "type": "", "doctor": "", "objective": ""})
    grand_total = {"spend": 0, "impressions": 0, "clicks": 0, "reach": 0, "leads": 0}

    for row in all_insights:
        campaign_id = row.get("campaign_id", "")
        campaign_name = row.get("campaign_name", "")
        objective = row.get("objective", "")
        spend = float(row.get("spend", 0))
        impressions = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        reach = int(row.get("reach", 0))
        leads = extract_leads_from_actions(row.get("actions"))
        date_start = row.get("date_start", "")
        month_key = date_start[:7] if date_start else "unknown"

        camp_type = classify_campaign_type(campaign_name, objective)
        doctor = classify_doctor(campaign_name)

        # By type
        type_totals[camp_type]["spend"] += spend
        type_totals[camp_type]["impressions"] += impressions
        type_totals[camp_type]["clicks"] += clicks
        type_totals[camp_type]["reach"] += reach
        type_totals[camp_type]["leads"] += leads

        # By doctor
        doctor_totals[doctor]["spend"] += spend
        doctor_totals[doctor]["impressions"] += impressions
        doctor_totals[doctor]["clicks"] += clicks
        doctor_totals[doctor]["reach"] += reach
        doctor_totals[doctor]["leads"] += leads

        # Monthly
        monthly_totals[month_key]["spend"] += spend
        monthly_totals[month_key]["impressions"] += impressions
        monthly_totals[month_key]["clicks"] += clicks
        monthly_totals[month_key]["leads"] += leads

        # Monthly by type & doctor
        monthly_by_type[month_key][camp_type]["spend"] += spend
        monthly_by_doctor[month_key][doctor]["spend"] += spend

        # Per campaign
        campaign_totals[campaign_id]["spend"] += spend
        campaign_totals[campaign_id]["impressions"] += impressions
        campaign_totals[campaign_id]["clicks"] += clicks
        campaign_totals[campaign_id]["leads"] += leads
        campaign_totals[campaign_id]["name"] = campaign_name
        campaign_totals[campaign_id]["type"] = camp_type
        campaign_totals[campaign_id]["doctor"] = doctor
        campaign_totals[campaign_id]["objective"] = objective

        # Grand total
        grand_total["spend"] += spend
        grand_total["impressions"] += impressions
        grand_total["clicks"] += clicks
        grand_total["reach"] += reach
        grand_total["leads"] += leads

    # Daily trend (last 90 days)
    daily_totals = defaultdict(lambda: {"spend": 0, "leads": 0, "clicks": 0})
    for row in all_daily_insights:
        date_key = row.get("date_start", "")
        spend = float(row.get("spend", 0))
        clicks = int(row.get("clicks", 0))
        leads = extract_leads_from_actions(row.get("actions"))
        daily_totals[date_key]["spend"] += spend
        daily_totals[date_key]["leads"] += leads
        daily_totals[date_key]["clicks"] += clicks

    return {
        "grand_total": grand_total,
        "type_totals": dict(type_totals),
        "doctor_totals": dict(doctor_totals),
        "monthly_totals": dict(monthly_totals),
        "monthly_by_type": {k: dict(v) for k, v in monthly_by_type.items()},
        "monthly_by_doctor": {k: dict(v) for k, v in monthly_by_doctor.items()},
        "campaign_totals": dict(campaign_totals),
        "daily_totals": dict(daily_totals),
    }


# ── HTML Dashboard Generation ──────────────────────────────────────────────

def generate_dashboard(data):
    """Generate the HTML dashboard file."""

    gt = data["grand_total"]
    cpm = (gt["spend"] / gt["impressions"] * 1000) if gt["impressions"] else 0
    cpc = (gt["spend"] / gt["clicks"]) if gt["clicks"] else 0
    ctr = (gt["clicks"] / gt["impressions"] * 100) if gt["impressions"] else 0
    cpl = (gt["spend"] / gt["leads"]) if gt["leads"] else 0

    # Sort months
    months_sorted = sorted(data["monthly_totals"].keys())
    monthly_labels = months_sorted
    monthly_spend = [data["monthly_totals"][m]["spend"] for m in months_sorted]
    monthly_leads = [data["monthly_totals"][m]["leads"] for m in months_sorted]
    monthly_clicks = [data["monthly_totals"][m]["clicks"] for m in months_sorted]

    # Type data for pie chart
    type_labels = sorted(data["type_totals"].keys(), key=lambda k: data["type_totals"][k]["spend"], reverse=True)
    type_spend = [round(data["type_totals"][t]["spend"], 2) for t in type_labels]
    total_spend = sum(type_spend)
    type_pcts = [round(s / total_spend * 100, 1) if total_spend else 0 for s in type_spend]

    # Doctor data for pie chart
    doctor_labels = sorted(data["doctor_totals"].keys(), key=lambda k: data["doctor_totals"][k]["spend"], reverse=True)
    doctor_spend = [round(data["doctor_totals"][d]["spend"], 2) for d in doctor_labels]
    doctor_pcts = [round(s / total_spend * 100, 1) if total_spend else 0 for s in doctor_spend]

    # Type table rows
    type_table_rows = ""
    for t in type_labels:
        d = data["type_totals"][t]
        t_cpl = d["spend"] / d["leads"] if d["leads"] else 0
        t_ctr = d["clicks"] / d["impressions"] * 100 if d["impressions"] else 0
        t_pct = d["spend"] / total_spend * 100 if total_spend else 0
        type_table_rows += f"""<tr>
            <td>{t}</td>
            <td>${d['spend']:,.2f}</td>
            <td>{t_pct:.1f}%</td>
            <td>{d['impressions']:,}</td>
            <td>{d['clicks']:,}</td>
            <td>{t_ctr:.2f}%</td>
            <td>{d['leads']:,}</td>
            <td>${t_cpl:.2f}</td>
        </tr>"""

    # Doctor table rows
    doctor_table_rows = ""
    for doc in doctor_labels:
        d = data["doctor_totals"][doc]
        d_cpl = d["spend"] / d["leads"] if d["leads"] else 0
        d_ctr = d["clicks"] / d["impressions"] * 100 if d["impressions"] else 0
        d_pct = d["spend"] / total_spend * 100 if total_spend else 0
        doctor_table_rows += f"""<tr>
            <td>{doc}</td>
            <td>${d['spend']:,.2f}</td>
            <td>{d_pct:.1f}%</td>
            <td>{d['impressions']:,}</td>
            <td>{d['clicks']:,}</td>
            <td>{d_ctr:.2f}%</td>
            <td>{d['leads']:,}</td>
            <td>${d_cpl:.2f}</td>
        </tr>"""

    # Top campaigns table (top 30 by spend)
    sorted_campaigns = sorted(data["campaign_totals"].items(), key=lambda x: x[1]["spend"], reverse=True)[:30]
    campaign_rows = ""
    for cid, c in sorted_campaigns:
        c_cpl = c["spend"] / c["leads"] if c["leads"] else 0
        campaign_rows += f"""<tr>
            <td title="{c['name']}">{c['name'][:50]}{'...' if len(c['name']) > 50 else ''}</td>
            <td>{c['type']}</td>
            <td>{c['doctor']}</td>
            <td>${c['spend']:,.2f}</td>
            <td>{c['impressions']:,}</td>
            <td>{c['clicks']:,}</td>
            <td>{c['leads']:,}</td>
            <td>${c_cpl:.2f}</td>
        </tr>"""

    # Daily trend data (sorted)
    daily_sorted = sorted(data["daily_totals"].keys())
    daily_labels = daily_sorted
    daily_spend = [round(data["daily_totals"][d]["spend"], 2) for d in daily_sorted]
    daily_leads = [data["daily_totals"][d]["leads"] for d in daily_sorted]

    # Monthly spend by type (stacked bar)
    all_types = list(set(t for m in data["monthly_by_type"].values() for t in m))
    monthly_type_datasets = []
    type_colors = {
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
    for t in all_types:
        color = type_colors.get(t, "#888888")
        values = [round(data["monthly_by_type"].get(m, {}).get(t, {}).get("spend", 0), 2) for m in months_sorted]
        monthly_type_datasets.append({"label": t, "data": values, "backgroundColor": color})

    # Monthly spend by doctor (stacked bar)
    all_doctors = list(set(d for m in data["monthly_by_doctor"].values() for d in m))
    doctor_colors = {
        "Dr. Simmons": "#FF6384",
        "Dr. Flores": "#36A2EB",
        "Dra. Sophie": "#FFCE56",
        "Dr. Salgado": "#4BC0C0",
        "Clínica (BLPS)": "#9966FF",
        "Mix Doctores": "#FF9F40",
        "Sin clasificar": "#C9CBCF",
    }
    monthly_doctor_datasets = []
    for doc in all_doctors:
        color = doctor_colors.get(doc, "#888888")
        values = [round(data["monthly_by_doctor"].get(m, {}).get(doc, {}).get("spend", 0), 2) for m in months_sorted]
        monthly_doctor_datasets.append({"label": doc, "data": values, "backgroundColor": color})

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BLPS Meta Ads Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px 32px; border-bottom: 1px solid #2a2a4a; }}
.header h1 {{ font-size: 24px; color: #fff; }}
.header .subtitle {{ color: #888; font-size: 14px; margin-top: 4px; }}
.header .date-range {{ color: #4fc3f7; font-size: 13px; margin-top: 8px; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.kpi-card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 20px; text-align: center; }}
.kpi-card .label {{ font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
.kpi-card .value {{ font-size: 28px; font-weight: 700; color: #fff; margin-top: 8px; }}
.kpi-card .value.green {{ color: #4caf50; }}
.kpi-card .value.blue {{ color: #4fc3f7; }}
.kpi-card .value.orange {{ color: #ff9800; }}
.kpi-card .value.purple {{ color: #ab47bc; }}
.section {{ margin-bottom: 32px; }}
.section-title {{ font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #2a2a4a; }}
.chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
.chart-card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 20px; }}
.chart-card.full {{ grid-column: 1 / -1; }}
.chart-card h3 {{ font-size: 14px; color: #888; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
.chart-container {{ position: relative; width: 100%; }}
.chart-container.pie {{ max-width: 400px; margin: 0 auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #16213e; color: #4fc3f7; padding: 10px 12px; text-align: left; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; position: sticky; top: 0; }}
td {{ padding: 10px 12px; border-bottom: 1px solid #1e1e3a; }}
tr:hover {{ background: #1e1e3a; }}
.table-wrapper {{ max-height: 500px; overflow-y: auto; border-radius: 8px; border: 1px solid #2a2a4a; }}
.pct-bar {{ display: inline-block; height: 8px; border-radius: 4px; background: #4fc3f7; margin-right: 8px; vertical-align: middle; }}
.footer {{ text-align: center; color: #555; font-size: 12px; padding: 24px; }}
@media (max-width: 768px) {{
    .chart-grid {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>

<div class="header">
    <h1>Beautyland Plastic Surgery — Meta Ads Dashboard</h1>
    <div class="subtitle">6 cuentas publicitarias consolidadas</div>
    <div class="date-range">Período: {DATE_START} → {DATE_END} &nbsp;|&nbsp; Generado: {generated_at}</div>
</div>

<div class="container">

<!-- KPI Cards -->
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="label">Inversión Total</div>
        <div class="value blue">${gt['spend']:,.0f}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Impresiones</div>
        <div class="value">{gt['impressions']:,}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Clicks</div>
        <div class="value">{gt['clicks']:,}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Leads (Form)</div>
        <div class="value green">{gt['leads']:,}</div>
    </div>
    <div class="kpi-card">
        <div class="label">CPM</div>
        <div class="value orange">${cpm:.2f}</div>
    </div>
    <div class="kpi-card">
        <div class="label">CPC</div>
        <div class="value orange">${cpc:.2f}</div>
    </div>
    <div class="kpi-card">
        <div class="label">CTR</div>
        <div class="value purple">{ctr:.2f}%</div>
    </div>
    <div class="kpi-card">
        <div class="label">CPL</div>
        <div class="value green">${cpl:.2f}</div>
    </div>
</div>

<!-- Charts Row 1: Distribution Pies -->
<div class="chart-grid">
    <div class="chart-card">
        <h3>Distribución de Inversión por Tipo de Campaña</h3>
        <div class="chart-container pie">
            <canvas id="typePieChart"></canvas>
        </div>
    </div>
    <div class="chart-card">
        <h3>Distribución de Inversión por Página / Doctor</h3>
        <div class="chart-container pie">
            <canvas id="doctorPieChart"></canvas>
        </div>
    </div>
</div>

<!-- Type Breakdown Table -->
<div class="section">
    <div class="section-title">Desglose por Tipo de Campaña</div>
    <div class="table-wrapper">
        <table>
            <thead><tr>
                <th>Tipo</th><th>Inversión</th><th>% Presup.</th><th>Impresiones</th><th>Clicks</th><th>CTR</th><th>Leads</th><th>CPL</th>
            </tr></thead>
            <tbody>{type_table_rows}</tbody>
        </table>
    </div>
</div>

<!-- Doctor Breakdown Table -->
<div class="section">
    <div class="section-title">Desglose por Página / Doctor</div>
    <div class="table-wrapper">
        <table>
            <thead><tr>
                <th>Página</th><th>Inversión</th><th>% Presup.</th><th>Impresiones</th><th>Clicks</th><th>CTR</th><th>Leads</th><th>CPL</th>
            </tr></thead>
            <tbody>{doctor_table_rows}</tbody>
        </table>
    </div>
</div>

<!-- Charts Row 2: Monthly Trends -->
<div class="chart-grid">
    <div class="chart-card full">
        <h3>Inversión Mensual por Tipo de Campaña</h3>
        <div class="chart-container"><canvas id="monthlyTypeChart"></canvas></div>
    </div>
</div>
<div class="chart-grid">
    <div class="chart-card full">
        <h3>Inversión Mensual por Página / Doctor</h3>
        <div class="chart-container"><canvas id="monthlyDoctorChart"></canvas></div>
    </div>
</div>
<div class="chart-grid">
    <div class="chart-card">
        <h3>Inversión Mensual Total</h3>
        <div class="chart-container"><canvas id="monthlySpendChart"></canvas></div>
    </div>
    <div class="chart-card">
        <h3>Leads Mensuales (Form)</h3>
        <div class="chart-container"><canvas id="monthlyLeadsChart"></canvas></div>
    </div>
</div>

<!-- Daily Trend -->
<div class="chart-grid">
    <div class="chart-card full">
        <h3>Tendencia Diaria — Últimos 90 Días (Inversión + Leads)</h3>
        <div class="chart-container"><canvas id="dailyTrendChart"></canvas></div>
    </div>
</div>

<!-- Top Campaigns Table -->
<div class="section">
    <div class="section-title">Top 30 Campañas por Inversión</div>
    <div class="table-wrapper">
        <table>
            <thead><tr>
                <th>Campaña</th><th>Tipo</th><th>Página</th><th>Inversión</th><th>Impresiones</th><th>Clicks</th><th>Leads</th><th>CPL</th>
            </tr></thead>
            <tbody>{campaign_rows}</tbody>
        </table>
    </div>
</div>

</div>

<div class="footer">
    Beautyland Plastic Surgery — Dashboard generado automáticamente desde Meta Marketing API<br>
    Datos de {len(data['campaign_totals'])} campañas en 6 cuentas publicitarias
</div>

<script>
Chart.defaults.color = '#aaa';
Chart.defaults.borderColor = '#2a2a4a';

const typeColors = {json.dumps([type_colors.get(t, '#888') for t in type_labels])};
const doctorColors = {json.dumps([doctor_colors.get(d, '#888') for d in doctor_labels])};

// Type Pie
new Chart(document.getElementById('typePieChart'), {{
    type: 'doughnut',
    data: {{
        labels: {json.dumps([f"{t} ({p}%)" for t, p in zip(type_labels, type_pcts)])},
        datasets: [{{ data: {json.dumps(type_spend)}, backgroundColor: typeColors, borderWidth: 0 }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 8 }} }} }} }}
}});

// Doctor Pie
new Chart(document.getElementById('doctorPieChart'), {{
    type: 'doughnut',
    data: {{
        labels: {json.dumps([f"{d} ({p}%)" for d, p in zip(doctor_labels, doctor_pcts)])},
        datasets: [{{ data: {json.dumps(doctor_spend)}, backgroundColor: doctorColors, borderWidth: 0 }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 8 }} }} }} }}
}});

// Monthly Spend
new Chart(document.getElementById('monthlySpendChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(monthly_labels)},
        datasets: [{{ label: 'Inversión ($)', data: {json.dumps(monthly_spend)}, backgroundColor: '#4fc3f7' }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }} }}
}});

// Monthly Leads
new Chart(document.getElementById('monthlyLeadsChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(monthly_labels)},
        datasets: [{{ label: 'Leads', data: {json.dumps(monthly_leads)}, backgroundColor: '#4caf50' }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
}});

// Monthly by Type (stacked)
new Chart(document.getElementById('monthlyTypeChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(monthly_labels)},
        datasets: {json.dumps(monthly_type_datasets)}
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }} }}
}});

// Monthly by Doctor (stacked)
new Chart(document.getElementById('monthlyDoctorChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(monthly_labels)},
        datasets: {json.dumps(monthly_doctor_datasets)}
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, ticks: {{ callback: v => '$' + v.toLocaleString() }} }} }} }}
}});

// Daily Trend
new Chart(document.getElementById('dailyTrendChart'), {{
    type: 'line',
    data: {{
        labels: {json.dumps(daily_labels)},
        datasets: [
            {{ label: 'Inversión ($)', data: {json.dumps(daily_spend)}, borderColor: '#4fc3f7', backgroundColor: 'rgba(79,195,247,0.1)', fill: true, tension: 0.3, yAxisID: 'y' }},
            {{ label: 'Leads', data: {json.dumps(daily_leads)}, borderColor: '#4caf50', backgroundColor: 'rgba(76,175,80,0.1)', fill: true, tension: 0.3, yAxisID: 'y1' }}
        ]
    }},
    options: {{
        responsive: true,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{
            y: {{ type: 'linear', position: 'left', ticks: {{ callback: v => '$' + v.toLocaleString() }} }},
            y1: {{ type: 'linear', position: 'right', grid: {{ drawOnChartArea: false }} }},
            x: {{ ticks: {{ maxTicksLimit: 15 }} }}
        }}
    }}
}});
</script>

</body>
</html>"""

    return html


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("ERROR: No META_ACCESS_TOKEN found. Set it in .env file.")
        return

    print(f"BLPS Meta Ads Dashboard Generator")
    print(f"Period: {DATE_START} to {DATE_END}")
    print(f"Accounts: {len(AD_ACCOUNTS)}")
    print("=" * 50)

    all_campaigns = []
    all_insights = []
    all_daily_insights = []

    for account_id in AD_ACCOUNTS:
        campaigns, insights, daily = fetch_campaigns_with_insights(account_id)
        all_campaigns.extend(campaigns)
        all_insights.extend(insights)
        all_daily_insights.extend(daily)

    print(f"\nTotal: {len(all_campaigns)} campaigns, {len(all_insights)} insight rows")
    print("Processing data...")

    data = process_data(all_campaigns, all_insights, all_daily_insights)

    print("Generating dashboard...")
    html = generate_dashboard(data)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDashboard saved to: {output_path}")
    print(f"Total spend: ${data['grand_total']['spend']:,.2f}")
    print(f"Total campaigns with data: {len(data['campaign_totals'])}")


if __name__ == "__main__":
    main()
