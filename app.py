import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
from PIL import Image as PILImage
import io
import re
import json

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Smart Pursuit | Performance Marketing Audit",
    page_icon="🚀",
    layout="wide"
)

# ============================================================
# BRAND COLORS
# ============================================================

NAVY = "#0F2942"
NAVY_2 = "#173B5E"
BLUE = "#2563EB"
BLUE_DARK = "#1D4ED8"
BLUE_LIGHT = "#EFF6FF"
GREEN = "#059669"
GREEN_LIGHT = "#ECFDF5"
RED = "#DC2626"
RED_LIGHT = "#FEF2F2"
PURPLE = "#7C3AED"
WHITE = "#FFFFFF"
OFF_WHITE = "#F8FAFC"
DARK = "#172B4D"
TEXT = "#334E68"
MUTED = "#627D98"
BORDER = "#D9E2EC"

MODEL_OPTIONS = [
    "gemini-3.6-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
]


# ============================================================
# STRUCTURED OUTPUT SCHEMA
# ------------------------------------------------------------
# This is the single most important fix in this file. Instead of
# asking Gemini for markdown and then regex-parsing it (fragile —
# one missing colon or merged line breaks the whole PDF), we ask
# Gemini to fill this exact schema. The API guarantees the shape
# of the JSON, so the PDF code below never has to "guess".
# ============================================================

class AuditContext(BaseModel):
    business_name: str = Field(description="The business/brand name visible in the screenshots.")
    industry: str = Field(description="Industry or niche, with country/region if identifiable.")
    offer: str = Field(description="The specific product or service being advertised.")
    target_audience: str = Field(description="Who the ad is clearly targeting.")


class ScoredItem(BaseModel):
    title: str = Field(description="A short (5-10 word) headline naming ONE specific point.")
    description: str = Field(description="1-3 sentences explaining this point in plain, client-friendly language.")


class LandingPageSection(BaseModel):
    heading: str = Field(description="e.g. 'The Problem', 'The Solution', 'How It Works', 'Trust / Proof', 'Final CTA'")
    body: str = Field(description="Ready-to-paste copy for this section, in the SAME language as the original ad.")


class LandingPageCopy(BaseModel):
    headline: str
    subheadline: str
    cta_button_text: str
    sections: List[LandingPageSection]
    form_fields: List[str] = Field(description="Short labels for recommended form fields, e.g. 'Full Name'.")


class AdVariation(BaseModel):
    hook: str
    body: str
    cta_line: str
    button_text: str


class CreativeFrame(BaseModel):
    timing: str = Field(description="e.g. 'First 3 seconds', 'Middle (3-7s)', 'Final frame (8-10s)'")
    visual_description: str
    on_screen_text: str


class CreativeDirection(BaseModel):
    format: str = Field(description="e.g. 'Vertical Video Reel (9:16)'")
    frames: List[CreativeFrame]


class AuditReport(BaseModel):
    context: AuditContext
    whats_working: List[ScoredItem] = Field(description="2-3 genuine strengths, most important first.")
    whats_costing_you_leads: List[ScoredItem] = Field(description="2-4 distinct, separate problems. Each item is ONE issue, never combine multiple issues into one item.")
    landing_page: LandingPageCopy
    ad_variations: List[AdVariation] = Field(description="Exactly 3 alternative ad copy variations.")
    creative_direction: CreativeDirection
    impact_statement: str = Field(description="1-2 sentences on the realistic business impact of fixing these issues.")
    next_step: str = Field(description="1-2 sentences proposing a concrete next step / call to action for the client.")


# ============================================================
# PROMPTS (embedded directly — no external .txt files to go missing)
# ============================================================

AUDIT_SYSTEM_PROMPT = """You are a senior performance marketing auditor. You will be shown two \
screenshots: (1) a paid social advertisement, and (2) the landing page / destination the ad \
sends traffic to.

Your job is to produce a sharp, highly specific audit — never generic marketing advice. \
Every observation must reference something actually visible in the screenshots (exact copy, \
exact visuals, exact buttons, exact destination).

Rules:
- Write all analysis labels, headings, and explanations in English.
- Write client-facing MARKETING COPY (headline, subheadline, landing page sections, ad hooks/body/CTAs) \
in the SAME language as the original advertisement's copy. If the ad is in Indonesian, write the new \
copy in Indonesian. If it's in English, write in English.
- "whats_costing_you_leads" must contain SEPARATE, DISTINCT items — never merge multiple problems \
into a single item.
- Every ad_variations entry must have a complete hook, body, cta_line and button_text — never leave \
any field blank.
- Be concrete and copy-paste ready. Assume this report will be shown directly to the business owner.
"""

OUTREACH_SYSTEM_PROMPT_TEMPLATE = """You are a B2B outreach specialist for "Smart Pursuit", a performance \
marketing agency. Below is a structured audit (as JSON) of a prospect's advertisement and landing page.

Using this audit, write a short, highly personalized outreach sequence to get this business to reply \
and book a call. Reference the SPECIFIC problems found in the audit (not generic pitches).

Output as clean markdown with two sections:

## SEQUENCE 1: 4 COLD EMAILS
For each email give a Subject and Body (short, 3-5 sentences max).

## SEQUENCE 2: 4 WHATSAPP MESSAGES
Short, casual, friendly. Message 3 should reference sending a PDF attachment.

Audit JSON:
{audit_json}
"""


# ============================================================
# STYLING
# ============================================================

st.markdown(
    f"""
    <style>
        .main {{ background: {OFF_WHITE}; }}
        #MainMenu, footer {{visibility: hidden;}}

        .sp-hero {{
            background: linear-gradient(120deg, {NAVY} 0%, {NAVY_2} 55%, {BLUE_DARK} 100%);
            border-radius: 18px;
            padding: 40px 44px;
            margin-bottom: 26px;
            box-shadow: 0 10px 30px rgba(15,41,66,0.25);
        }}
        .sp-hero-kicker {{
            display:inline-block;
            color: #BFDBFE;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.18);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.06em;
            margin-bottom: 14px;
        }}
        .sp-hero-title {{
            font-size: 40px;
            font-weight: 800;
            color: white;
            margin: 0 0 8px 0;
            line-height: 1.15;
        }}
        .sp-hero-subtitle {{
            font-size: 16.5px;
            color: #CBD5E1;
            max-width: 620px;
            margin-bottom: 18px;
        }}
        .sp-chip-row {{ display:flex; gap:10px; flex-wrap:wrap; }}
        .sp-chip {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.18);
            color: #E2E8F0;
            padding: 7px 14px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
        }}

        .section-title {{
            color: {NAVY};
            font-size: 21px;
            font-weight: 700;
            margin-bottom: 2px;
        }}
        .section-sub {{
            color: {MUTED};
            font-size: 13.5px;
            margin-bottom: 14px;
        }}

        .sp-card {{
            background: white;
            border: 1px solid {BORDER};
            border-radius: 14px;
            padding: 18px 20px;
            margin-bottom: 12px;
        }}
        .sp-card.working {{ border-left: 4px solid {GREEN}; }}
        .sp-card.costing {{ border-left: 4px solid {RED}; }}
        .sp-card-title {{ font-weight: 700; color: {DARK}; font-size: 14.5px; margin-bottom:4px; }}
        .sp-card-body {{ color: {TEXT}; font-size: 13.5px; line-height:1.5; }}

        .sp-step-card {{
            background: white;
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 26px 22px;
            text-align: left;
            height: 100%;
        }}
        .sp-step-num {{
            width: 30px; height: 30px;
            background: {BLUE}; color: white;
            border-radius: 8px;
            display:flex; align-items:center; justify-content:center;
            font-weight:700; margin-bottom: 12px;
        }}
        .sp-step-title {{ font-weight: 700; color: {NAVY}; font-size: 15.5px; margin-bottom: 6px;}}
        .sp-step-body {{ color: {MUTED}; font-size: 13px; line-height:1.5; }}

        div.stButton > button {{
            background: {BLUE};
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            padding: 0.65rem 1.2rem;
            transition: 0.15s;
        }}
        div.stButton > button:hover {{ background: {NAVY}; color: white; }}

        div[data-testid="stSidebar"] {{
            background: {WHITE};
            border-right: 1px solid {BORDER};
        }}
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HERO HEADER
# ============================================================

st.markdown(
    f"""
    <div class="sp-hero">
        <div class="sp-hero-kicker">AI-POWERED GROWTH AUDIT</div>
        <div class="sp-hero-title">Smart Pursuit</div>
        <div class="sp-hero-subtitle">
            Upload a prospect's advertisement and landing page. Get a client-ready
            audit PDF and a personalized outreach sequence — in under a minute.
        </div>
        <div class="sp-chip-row">
            <div class="sp-chip">📸 Vision-based ad analysis</div>
            <div class="sp-chip">📄 Client-ready PDF report</div>
            <div class="sp-chip">✉️ Personalized outreach copy</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown("### ⚙️ Audit Setup")

api_key = st.sidebar.text_input(
    "Gemini API Key",
    type="password",
    help="Your key is used only for this session and never stored."
)

st.sidebar.markdown("**1. Advertisement screenshot**")
ad_file = st.sidebar.file_uploader(
    "Upload ad screenshot", type=["png", "jpg", "jpeg"], label_visibility="collapsed"
)

st.sidebar.markdown("**2. Landing page screenshot**")
lp_file = st.sidebar.file_uploader(
    "Upload landing page screenshot", type=["png", "jpg", "jpeg"], label_visibility="collapsed"
)

st.sidebar.markdown("---")

model_name = st.sidebar.selectbox("Gemini Model", MODEL_OPTIONS, index=0)

st.sidebar.caption(
    "Tip: upload the exact ad creative the prospect is running, and the exact "
    "page/profile their ad clicks lead to."
)

run_clicked = st.sidebar.button(
    "🚀 Run Audit & Generate Campaigns", type="primary", use_container_width=True
)


# ============================================================
# SESSION STATE
# ============================================================

st.session_state.setdefault("report", None)          # dict (AuditReport.model_dump())
st.session_state.setdefault("outreach_data", "")
st.session_state.setdefault("pdf_data", None)
st.session_state.setdefault("client_filename", "Smart_Pursuit_Audit.pdf")


# ============================================================
# HELPERS
# ============================================================

def safe_filename(name: str) -> str:
    name = re.sub(r"\s*\(@[^)]*\)", "", name or "")
    name = re.sub(r"[^A-Za-z0-9\s_-]", "", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return f"{name or 'Client'}.pdf"


def call_gemini_structured(client, model, ad_img, lp_img) -> AuditReport:
    response = client.models.generate_content(
        model=model,
        contents=[
            ad_img,
            lp_img,
            "Analyze this advertisement and its landing page. Fill out the audit schema completely.",
        ],
        config=types.GenerateContentConfig(
            system_instruction=AUDIT_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=AuditReport,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, AuditReport):
        return parsed

    # Fallback: manually validate the raw JSON text if .parsed wasn't populated
    return AuditReport.model_validate(json.loads(response.text))


def call_gemini_outreach(client, model, report: AuditReport, ad_img, lp_img) -> str:
    prompt = OUTREACH_SYSTEM_PROMPT_TEMPLATE.format(
        audit_json=report.model_dump_json(indent=2)
    )
    response = client.models.generate_content(
        model=model,
        contents=[ad_img, lp_img, "Write the outreach sequence now."],
        config=types.GenerateContentConfig(system_instruction=prompt),
    )
    return response.text or ""


# ============================================================
# PDF STYLES
# ============================================================

def build_pdf_styles():
    base = getSampleStyleSheet()
    s = {}

    s["cover_kicker"] = ParagraphStyle("CoverKicker", parent=base["Normal"], fontName="Helvetica-Bold",
                                        fontSize=8, leading=10, textColor=colors.HexColor(BLUE), spaceAfter=6)
    s["cover_title"] = ParagraphStyle("CoverTitle", parent=base["Normal"], fontName="Helvetica-Bold",
                                       fontSize=29, leading=33, textColor=colors.HexColor(NAVY), spaceAfter=8)
    s["cover_client"] = ParagraphStyle("CoverClient", parent=base["Normal"], fontName="Helvetica-Bold",
                                        fontSize=17, leading=21, textColor=colors.HexColor(DARK), spaceAfter=8)
    s["cover_description"] = ParagraphStyle("CoverDescription", parent=base["Normal"], fontName="Helvetica",
                                             fontSize=10.5, leading=15, textColor=colors.HexColor(MUTED), spaceAfter=5)
    s["section_title"] = ParagraphStyle("SectionTitle", parent=base["Normal"], fontName="Helvetica-Bold",
                                         fontSize=17, leading=21, textColor=colors.HexColor(NAVY), spaceAfter=6)
    s["section_subtitle"] = ParagraphStyle("SectionSubtitle", parent=base["Normal"], fontName="Helvetica",
                                            fontSize=8.8, leading=12, textColor=colors.HexColor(MUTED), spaceAfter=8)
    s["body"] = ParagraphStyle("Body", parent=base["Normal"], fontName="Helvetica",
                                fontSize=9.2, leading=13.2, textColor=colors.HexColor(TEXT), spaceAfter=5)
    s["card_title"] = ParagraphStyle("CardTitle", parent=base["Normal"], fontName="Helvetica-Bold",
                                      fontSize=9.5, leading=12, textColor=colors.HexColor(NAVY), spaceAfter=4)
    s["card_body"] = ParagraphStyle("CardBody", parent=base["Normal"], fontName="Helvetica",
                                     fontSize=8.4, leading=11.8, textColor=colors.HexColor(TEXT), spaceAfter=2)
    s["label"] = ParagraphStyle("Label", parent=base["Normal"], fontName="Helvetica-Bold",
                                 fontSize=7.3, leading=9, textColor=colors.HexColor(BLUE), spaceAfter=3)
    s["white_title"] = ParagraphStyle("WhiteTitle", parent=base["Normal"], fontName="Helvetica-Bold",
                                       fontSize=12, leading=15, textColor=colors.white, spaceAfter=4)
    s["white_body"] = ParagraphStyle("WhiteBody", parent=base["Normal"], fontName="Helvetica",
                                      fontSize=8.5, leading=12, textColor=colors.HexColor("#E5E7EB"), spaceAfter=3)
    s["number"] = ParagraphStyle("Number", parent=base["Normal"], fontName="Helvetica-Bold",
                                  fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.white)
    return s


def draw_header_footer(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(colors.HexColor(BLUE))
    canvas.setLineWidth(1.2)
    canvas.line(45, height - 27, width - 45, height - 27)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(colors.HexColor(NAVY))
    canvas.drawString(45, height - 20, "SMART PURSUIT")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawRightString(width - 45, height - 20, "PERFORMANCE MARKETING AUDIT")
    canvas.setStrokeColor(colors.HexColor(BORDER))
    canvas.setLineWidth(0.5)
    canvas.line(45, 28, width - 45, 28)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(45, 17, "Confidential Growth Advisory")
    canvas.drawRightString(width - 45, 17, f"Page {doc.page}")
    canvas.restoreState()


def prepare_reportlab_image(uploaded_file, max_width=220, max_height=270):
    if uploaded_file is None:
        return None
    try:
        uploaded_file.seek(0)
        image = PILImage.open(uploaded_file).convert("RGB")
        w, h = image.size
        ratio = min(max_width / w, max_height / h, 1)
        nw, nh = int(w * ratio), int(h * ratio)
        image = image.resize((nw, nh))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return RLImage(buf, width=nw, height=nh)
    except Exception:
        return None


def info_card(label, value, styles):
    content = [
        Paragraph(label.upper(), styles["label"]),
        Paragraph(value or "Not identified", styles["card_body"]),
    ]
    t = Table([[content]], colWidths=[150])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def numbered_card(number, title, description, styles, accent=BLUE):
    """One clean card per distinct point — used for both 'costing you leads' and
    ad-variation numbering. This replaces the old regex-grouped card that merged
    multiple issues into a single card."""
    number_box = Table([[Paragraph(str(number), styles["number"])]], colWidths=[25])
    number_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(accent)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    content = [Paragraph(title, styles["card_title"]), Paragraph(description, styles["card_body"])]
    t = Table([[number_box, content]], colWidths=[32, 452])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def fix_card(label, title, body, styles, accent=BLUE):
    content = [
        Paragraph(label.upper(), ParagraphStyle(f"FixLabel{label}", parent=styles["label"], textColor=colors.HexColor(accent))),
        Paragraph(title, styles["card_title"]),
        Paragraph(body, styles["card_body"]),
    ]
    t = Table([[content]], colWidths=[484])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(BORDER)),
        ("LINEABOVE", (0, 0), (-1, 0), 3, colors.HexColor(accent)),
        ("LEFTPADDING", (0, 0), (-1, -1), 13), ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def variation_card(index, variation: AdVariation, styles):
    """Builds one complete ad-copy variation card. Because the data now comes from
    a validated schema, hook/body/cta/button can never be silently empty."""
    accent = [BLUE, PURPLE, GREEN][(index - 1) % 3]
    content = [
        Paragraph(f"Variation {index}", styles["card_title"]),
        Paragraph(f"<b>Hook</b><br/>{variation.hook}", styles["card_body"]),
        Paragraph(f"<b>Body</b><br/>{variation.body}", styles["card_body"]),
        Paragraph(f"<b>CTA</b><br/>{variation.cta_line}", styles["card_body"]),
        Paragraph(f"<b>Button:</b> {variation.button_text}", styles["card_body"]),
    ]
    t = Table([[content]], colWidths=[484])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(OFF_WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
        ("LINEABOVE", (0, 0), (-1, 0), 3, colors.HexColor(accent)),
        ("LEFTPADDING", (0, 0), (-1, -1), 13), ("RIGHTPADDING", (0, 0), (-1, -1), 13),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def section_block(number, title, subtitle, styles):
    number_box = Table([[Paragraph(str(number), styles["number"])]], colWidths=[29])
    number_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BLUE)),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    title_content = [Paragraph(title, styles["section_title"]), Paragraph(subtitle, styles["section_subtitle"])]
    t = Table([[number_box, title_content]], colWidths=[36, 448])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 9),
    ]))
    return t


# ============================================================
# BUILD PDF (now reads directly from AuditReport — no regex)
# ============================================================

def generate_client_pdf(report: AuditReport, ad_file=None, lp_file=None) -> bytes:
    styles = build_pdf_styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=54, rightMargin=54, topMargin=45, bottomMargin=40,
        title=f"Smart Pursuit Performance Audit - {report.context.business_name}",
        author="Smart Pursuit", subject="Performance Marketing Growth Audit",
        allowSplitting=True,
    )
    story = []

    # ---------------- PAGE 1: COVER ----------------
    story.append(Spacer(1, 20))

    brand_row = Table([[
        Paragraph("SMART PURSUIT", ParagraphStyle("BrandCover", parent=styles["label"], fontSize=9)),
        Paragraph("CONFIDENTIAL CLIENT REPORT",
                   ParagraphStyle("ConfCover", parent=styles["label"], fontSize=7, alignment=TA_RIGHT,
                                  textColor=colors.HexColor(MUTED))),
    ]], colWidths=[280, 204])
    brand_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                    ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(brand_row)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor(BLUE), spaceBefore=0, spaceAfter=25))

    story.append(Paragraph("PERFORMANCE MARKETING", styles["cover_kicker"]))
    story.append(Paragraph("Growth Audit", styles["cover_title"]))
    story.append(Paragraph(report.context.business_name, styles["cover_client"]))
    story.append(Paragraph(
        "A clear review of what happens between the moment someone sees your "
        "advertisement and the moment they decide whether to enquire.",
        styles["cover_description"]))
    story.append(Spacer(1, 18))

    ad_preview = prepare_reportlab_image(ad_file, 210, 245)
    lp_preview = prepare_reportlab_image(lp_file, 210, 245)
    ad_cell = [Paragraph("ADVERTISEMENT", styles["label"]),
               ad_preview or Paragraph("Screenshot supplied for analysis.", styles["card_body"])]
    lp_cell = [Paragraph("LANDING PAGE", styles["label"]),
               lp_preview or Paragraph("Screenshot supplied for analysis.", styles["card_body"])]
    screenshots = Table([[ad_cell, lp_cell]], colWidths=[238, 238])
    screenshots.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(OFF_WHITE)),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(screenshots)
    story.append(Spacer(1, 14))

    context_row = Table([[
        info_card("Business", report.context.business_name, styles),
        info_card("Industry", report.context.industry, styles),
        info_card("Offer", report.context.offer, styles),
    ]], colWidths=[160, 160, 164])
    context_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    story.append(context_row)
    story.append(Spacer(1, 15))

    cover_footer = Table([[
        Paragraph("Prepared by Smart Pursuit", styles["card_body"]),
        Paragraph("Practical. Specific. Actionable.",
                   ParagraphStyle("CoverFooterRight", parent=styles["card_body"], alignment=TA_RIGHT)),
    ]], colWidths=[250, 234])
    cover_footer.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor(BORDER)),
                                       ("TOPPADDING", (0, 0), (-1, -1), 7),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(cover_footer)
    story.append(PageBreak())

    # ---------------- PAGE 2: EXECUTIVE DIAGNOSIS ----------------
    story.append(section_block("01", "Executive Diagnosis",
                                "The few things most likely affecting enquiry volume.", styles))
    story.append(Spacer(1, 8))
    story.append(Paragraph("WHAT'S WORKING", styles["label"]))
    for item in report.whats_working[:3]:
        story.append(fix_card("Strength", item.title, item.description, styles, GREEN))
        story.append(Spacer(1, 7))

    story.append(Spacer(1, 5))
    story.append(Paragraph("WHAT'S COSTING YOU LEADS", styles["label"]))
    for idx, item in enumerate(report.whats_costing_you_leads[:4], start=1):
        story.append(numbered_card(idx, item.title, item.description, styles, RED))
        story.append(Spacer(1, 7))
    story.append(PageBreak())

    # ---------------- PAGE 3: THE FIX ----------------
    story.append(section_block("02", "The Fix",
                                "What we would change first — with the actual copy and structure.", styles))
    story.append(Spacer(1, 7))
    lp = report.landing_page
    story.append(fix_card("Headline", "Headline", lp.headline, styles, PURPLE))
    story.append(Spacer(1, 6))
    story.append(fix_card("Subheadline", "Subheadline", lp.subheadline, styles, PURPLE))
    story.append(Spacer(1, 6))
    story.append(fix_card("Hero CTA button", "Hero CTA Button Text", lp.cta_button_text, styles, GREEN))
    story.append(Spacer(1, 6))
    for sec in lp.sections:
        story.append(fix_card(sec.heading, sec.heading, sec.body, styles, BLUE))
        story.append(Spacer(1, 6))
    if lp.form_fields:
        story.append(fix_card("Recommended form fields", "Recommended Form Fields",
                               " • ".join(lp.form_fields), styles, BLUE))
    story.append(PageBreak())

    # ---------------- PAGE 4: AD CREATIVE & COPY ----------------
    story.append(section_block("03", "Ad Creative & Copy",
                                "Three practical ways to make the advertisement clearer and more compelling.", styles))
    story.append(Spacer(1, 8))
    for idx, variation in enumerate(report.ad_variations[:3], start=1):
        story.append(variation_card(idx, variation, styles))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 5))
    story.append(Paragraph("CREATIVE DIRECTION", styles["label"]))
    story.append(Paragraph(f"<b>Format:</b> {report.creative_direction.format}", styles["body"]))
    for frame in report.creative_direction.frames:
        story.append(Paragraph(
            f"• <b>{frame.timing}:</b> {frame.visual_description} "
            f"<i>(On-screen text: \u201c{frame.on_screen_text}\u201d)</i>",
            styles["body"]))
    story.append(PageBreak())

    # ---------------- PAGE 5: BUSINESS IMPACT ----------------
    story.append(section_block("04", "What This Could Mean For You",
                                "The practical business impact of fixing the weak points above.", styles))
    story.append(Spacer(1, 10))
    impact_card = Table([[[
        Paragraph("THE OPPORTUNITY", styles["label"]),
        Paragraph(report.impact_statement,
                  ParagraphStyle("ImpactLarge", parent=styles["body"], fontSize=11, leading=17,
                                 textColor=colors.HexColor(NAVY))),
    ]]], colWidths=[484])
    impact_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BLUE_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#BFDBFE")),
        ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(impact_card)
    story.append(Spacer(1, 20))

    story.append(Paragraph("NEXT STEP", styles["label"]))
    next_card = Table([[[
        Paragraph("A SIMPLE NEXT MOVE", styles["white_title"]),
        Paragraph(report.next_step, styles["white_body"]),
    ]]], colWidths=[484])
    next_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(NAVY)),
        ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 15), ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(next_card)
    story.append(Spacer(1, 25))

    final_brand = Table([[Paragraph("SMART PURSUIT",
                                     ParagraphStyle("FinalBrand", parent=styles["white_title"],
                                                    textColor=colors.HexColor(NAVY)))]], colWidths=[484])
    final_brand.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(final_brand)

    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# STREAMLIT RENDER HELPERS
# ============================================================

def render_report_inline(report: AuditReport):
    ctx = report.context
    st.markdown(f"**{ctx.business_name}** · {ctx.industry}")
    st.caption(f"Offer: {ctx.offer}  |  Audience: {ctx.target_audience}")

    st.markdown("###### ✅ What's working")
    for item in report.whats_working:
        st.markdown(
            f'<div class="sp-card working"><div class="sp-card-title">{item.title}</div>'
            f'<div class="sp-card-body">{item.description}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("###### ⚠️ What's costing you leads")
    for item in report.whats_costing_you_leads:
        st.markdown(
            f'<div class="sp-card costing"><div class="sp-card-title">{item.title}</div>'
            f'<div class="sp-card-body">{item.description}</div></div>',
            unsafe_allow_html=True,
        )

    with st.expander("📝 Landing page copy (copy-paste ready)"):
        lp = report.landing_page
        st.markdown(f"**Headline:** {lp.headline}")
        st.markdown(f"**Subheadline:** {lp.subheadline}")
        st.markdown(f"**CTA button:** {lp.cta_button_text}")
        for sec in lp.sections:
            st.markdown(f"**{sec.heading}**")
            st.write(sec.body)
        if lp.form_fields:
            st.markdown("**Form fields:** " + ", ".join(lp.form_fields))

    with st.expander("🎯 Ad copy variations"):
        for i, v in enumerate(report.ad_variations, start=1):
            st.markdown(f"**Variation {i}**")
            st.markdown(f"- Hook: {v.hook}\n- Body: {v.body}\n- CTA: {v.cta_line}\n- Button: {v.button_text}")

    with st.expander("🎬 Creative direction"):
        st.markdown(f"**Format:** {report.creative_direction.format}")
        for f in report.creative_direction.frames:
            st.markdown(f"- **{f.timing}:** {f.visual_description}  \n  _On-screen text: \"{f.on_screen_text}\"_")

    st.markdown("###### 💡 What this could mean for you")
    st.info(report.impact_statement)

    st.markdown("###### 📞 Next step")
    st.success(report.next_step)


# ============================================================
# RUN AUDIT
# ============================================================

if run_clicked:
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
    elif not ad_file or not lp_file:
        st.error("Please upload both the ad screenshot and the landing page screenshot.")
    else:
        try:
            ad_img = PILImage.open(ad_file)
            lp_img = PILImage.open(lp_file)
            client = genai.Client(api_key=api_key)

            st.session_state.report = None
            st.session_state.outreach_data = ""
            st.session_state.pdf_data = None

            with st.spinner("Analyzing advertisement and landing page..."):
                report = call_gemini_structured(client, model_name, ad_img, lp_img)
                st.session_state.report = report.model_dump()

            with st.spinner("Creating personalized outreach..."):
                st.session_state.outreach_data = call_gemini_outreach(client, model_name, report, ad_img, lp_img)

            with st.spinner("Designing professional client report..."):
                st.session_state.client_filename = safe_filename(report.context.business_name)
                st.session_state.pdf_data = generate_client_pdf(report, ad_file, lp_file)

        except Exception as e:
            st.error(f"Audit generation failed: {e}")


# ============================================================
# RESULTS
# ============================================================

if st.session_state.report:
    report_obj = AuditReport.model_validate(st.session_state.report)

    st.markdown("---")
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown('<div class="section-title">Performance Audit</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">Ready to send as a client PDF</div>', unsafe_allow_html=True)
        render_report_inline(report_obj)
        if st.session_state.pdf_data:
            st.download_button(
                "⬇️ Download Client PDF",
                data=st.session_state.pdf_data,
                file_name=st.session_state.client_filename,
                mime="application/pdf",
                use_container_width=True,
            )

    with col2:
        st.markdown('<div class="section-title">Outreach Sequences</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">Personalized emails & WhatsApp messages</div>', unsafe_allow_html=True)
        if st.session_state.outreach_data:
            st.markdown(st.session_state.outreach_data)


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state.report:
    st.write("")
    c1, c2, c3 = st.columns(3, gap="medium")
    steps = [
        ("1", "Upload two screenshots", "The paid ad creative and the exact page or profile its clicks land on."),
        ("2", "AI audits both", "Gemini compares message match, CTA clarity, trust signals, and booking friction."),
        ("3", "Get client-ready assets", "A polished PDF audit plus a personalized cold email & WhatsApp sequence."),
    ]
    for col, (num, title, body) in zip([c1, c2, c3], steps):
        with col:
            st.markdown(
                f'<div class="sp-step-card"><div class="sp-step-num">{num}</div>'
                f'<div class="sp-step-title">{title}</div>'
                f'<div class="sp-step-body">{body}</div></div>',
                unsafe_allow_html=True,
            )
    st.write("")
    st.markdown(
        f"""
        <div style="background:white;border:1px solid {BORDER};border-radius:16px;
                    padding:40px;text-align:center;margin-top:10px;">
            <div style="font-size:38px;margin-bottom:10px;">📊</div>
            <div style="font-size:21px;font-weight:700;color:{NAVY};">Ready to audit your next business</div>
            <div style="font-size:14.5px;color:{MUTED};margin-top:6px;">
                Upload the advertisement and landing page screenshots from the sidebar to begin.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )