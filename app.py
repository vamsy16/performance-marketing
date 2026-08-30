import streamlit as st
from google import genai
from PIL import Image
import os

# Page configuration for a clean layout
st.set_page_config(page_title="Smart Pursuit | Agency Engine", layout="wide")

st.markdown("<h1 style='color: #1E3A8A;'>Smart Pursuit 🚀</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #4B5563; font-size: 18px;'>AI-Powered Conversion Audit & Outreach Engine</p>", unsafe_allow_html=True)

# Sidebar configurations
st.sidebar.header("Setup & Assets")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))

ad_file = st.sidebar.file_uploader("1. Upload Meta/Google Ad Screenshot", type=["png", "jpg", "jpeg"])
lp_file = st.sidebar.file_uploader("2. Upload Landing Page Screenshot", type=["png", "jpg", "jpeg"])

# System configuration prompt rules
MASTER_SYSTEM_PROMPT = """
ROLE 1: SENIOR PERFORMANCE MARKETING CONSULTANT
You are sharp, specific, and allergic to vague advice — every recommendation you give is something the business owner could hand to someone and have them execute immediately.

ROLE 2: OUTREACH EXPERT
Your tone is confident, casual, and helpful — never salesy, never generic, never uses agency jargon (no "synergy," "leverage," "solutions," "reach out").

INPUT
You will receive two screenshots: a live ad and its corresponding landing page.

===========================================
PART 0: READ THE CONTEXT FROM THE SCREENSHOTS
===========================================
Extract directly from what's visible:
- Business name
- Industry/niche
- What they're selling / the offer
- Who the target customer likely is
- Visible pricing or financial terms (e.g., Crore pricing, payment plans, or hidden behind 'Enquire Now')

===========================================
PART 1: INTERNAL AUDIT (for our team)
===========================================
Score each of these Strong / Needs Work / Broken, with one line of reasoning:
- Message match
- Ad hook/headline strength
- Ad CTA clarity
- Landing page above-the-fold clarity
- Landing page structure and flow
- Trust signals present
- Form friction (number of fields)
- Mobile-friendliness signals
- Overall copy quality

Identify the TOP 2–3 problems hurting lead volume.

===========================================
PART 2: CLIENT-FACING SOLUTION DOCUMENT
===========================================
Ban these words: CTR, CRO, ROAS, message match, funnel, optimize, leverage, synergy. 
Structure:
1. WHAT'S WORKING: 1–2 genuine strengths.
2. WHAT'S COSTING YOU LEADS: The top 2–3 problems ("Here's what's happening -> here's why it's losing you leads").
3. THE FIX: Build a complete replacement landing page copy block (Headline, Subheadline, CTA, Property Highlights, 3-Step Process) or 3 full ad copy variations. Fully copy-paste ready.
4. WHAT THIS COULD MEAN FOR YOU: One honest, plain-English estimate of impact.
5. NEXT STEP: One line clear CTA for a short call.

===========================================
PART 3: OUTREACH SEQUENCES
===========================================
Write sequences based on the specific business data found above. Do not use generic brackets or placeholders.

SEQUENCE 1: 4 COLD EMAILS
Email 1 — Opener, references specific ad, offers a free breakdown. No pitch. Under 60 words.
Email 2 — 2 days later. Add one new, specific observation. Under 50 words.
Email 3 — 4 days later. Industry proof case. Under 60 words.
Email 4 — 7 days later. Polite breakup. Under 40 words.
Subject lines must be under 6 words.

SEQUENCE 2: 4 WHATSAPP MESSAGES
WhatsApp 1 — Casual opener, offer breakdown. Under 40 words, 1 emoji max.
WhatsApp 2 — 2 days later, short nudge. Under 25 words.
WhatsApp 3 — Value delivery: biggest finding + ask for 15-min call. Under 40 words.
WhatsApp 4 — Post-call follow-up. Under 30 words.
"""

if st.sidebar.button("Run Audit & Generate Campaigns", type="primary"):
    if not api_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not ad_file or not lp_file:
        st.error("Please upload both screenshots to execute the app.")
    else:
        with st.spinner("Analyzing assets and writing your custom outreach strategy..."):
            try:
                ad_img = Image.open(ad_file)
                lp_img = Image.open(lp_file)
                
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[ad_img, lp_img, "Analyze these two screenshots matching your system instructions."],
                    config=dict(system_instruction=MASTER_SYSTEM_PROMPT)
                )
                
                raw_text = response.text
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📋 Conversion Audit & Fixes")
                    if "PART 3" in raw_text:
                        st.write(raw_text.split("===========================================\nPART 3")[0])
                    else:
                        st.write(raw_text)
                        
                with col2:
                    st.subheader("✉️ High-Conversion Outreach Sequences")
                    if "PART 3" in raw_text:
                        st.write("### Outreach Sequences\n" + raw_text.split("===========================================\nPART 3")[1])
                    else:
                        st.info("Outreach copy appended inside the main report above.")
                        
            except Exception as e:
                st.error(f"Error: {str(e)}")
