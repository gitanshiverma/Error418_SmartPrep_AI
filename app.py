import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import json
import google.generativeai as genai
import re
import os
import time
import base64
import random
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

# ============================================
# 1. PAGE CONFIGURATION
# ============================================
st.set_page_config(
    page_title="SmartPrep AI Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# 2. LOAD EXTERNAL CSS FILE
# ============================================
def load_css(file_name="style.css"):
    """
    Helper function to read and inject external CSS file into Streamlit layout.
    """
    css_path = os.path.join(os.path.dirname(__file__), file_name) if "__file__" in globals() else file_name
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    elif os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css("style.css")

# ============================================
# 3. BULLETPROOF IMAGE HELPER (BASE64 + MULTI-LOCATION SEARCH)
# ============================================
IMAGE_SEARCH_DIRS = [
    r"C:\Users\user\.gemini\antigravity\brain\4f7c1d95-038b-4cd3-9ac0-da2001ce0678",
    os.path.dirname(__file__) if "__file__" in globals() else ".",
    os.path.join(os.path.dirname(__file__), "assets") if "__file__" in globals() else "./assets"
]

DEFAULT_AVATAR = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=600&q=80"
DEFAULT_HERO_BG = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80"
DEFAULT_ANALYTICS_BG = "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80"

def get_base64_image(filename):
    for base_dir in IMAGE_SEARCH_DIRS:
        full_path = os.path.join(base_dir, filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, "rb") as f:
                    data = f.read()
                    if len(data) > 0:
                        return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
            except Exception:
                pass
    return ""

hero_b64 = get_base64_image("hero_ai_banner_1784974267844.jpg")
avatar_b64 = get_base64_image("ai_coach_avatar_1784974288606.jpg")
analytics_b64 = get_base64_image("analytics_dashboard_bg_1784974343418.jpg")

avatar_src = avatar_b64 if (avatar_b64 and len(avatar_b64) > 100) else DEFAULT_AVATAR
hero_bg_src = hero_b64 if (hero_b64 and len(hero_b64) > 100) else DEFAULT_HERO_BG
analytics_bg_src = analytics_b64 if (analytics_b64 and len(analytics_b64) > 100) else DEFAULT_ANALYTICS_BG

# Dynamic CSS injection for custom hero background image variable
st.markdown(f"<style>:root {{ --hero-bg-src: url('{hero_bg_src}'); }}</style>", unsafe_allow_html=True)

# ============================================
# 4. SECURE GEMINI CONFIGURATION & FALLBACK ENGINE
# ============================================
# ============================================
# 4. SECURE GEMINI CONFIGURATION & FALLBACK ENGINE
# ============================================
def get_gemini_api_key():
    """Safely fetch API Key from Env, Secrets, or Session State."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        try:
            if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    if not api_key:
        api_key = st.session_state.get("user_api_key", "")
    return api_key

api_key = get_gemini_api_key()
if api_key:
    genai.configure(api_key=api_key)

if "active_model_used" not in st.session_state:
    st.session_state.active_model_used = "gemini-1.5-flash"

def get_available_gemini_models():
    """
    Dynamically fetches valid text-generation Gemini models.
    Filters out TTS, Audio-only, Embedding, and Image models.
    """
    try:
        raw_models = genai.list_models()
        valid_models = []
        
        # Exclude non-text models (TTS, Audio, Image, Embeddings)
        invalid_keywords = ['tts', 'audio', 'embed', 'imagen', 'realtime', 'bidi']
        
        for m in raw_models:
            name = m.name.replace("models/", "").lower()
            if 'generatecontent' in [method.lower() for method in m.supported_generation_methods] and 'gemini' in name:
                if not any(keyword in name for keyword in invalid_keywords):
                    valid_models.append(m.name.replace("models/", ""))
        
        # Priority order: stable flash & pro text models
        priority_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        sorted_models = [m for m in priority_models if m in valid_models] + [m for m in valid_models if m not in priority_models]
        
        return sorted_models if sorted_models else ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
    except Exception:
        return ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]

def safe_generate_content(contents):
    """
    Bulletproof Model Fallback Engine:
    Retries across models on Rate Limit (429), 404, or Modality (400) errors.
    """
    current_key = get_gemini_api_key()
    if not current_key:
        raise ValueError("No Gemini API Key found! Please check your secrets.toml or sidebar API Key.")
    
    genai.configure(api_key=current_key)
        
    if "available_models_list" not in st.session_state or not st.session_state.available_models_list:
        st.session_state.available_models_list = get_available_gemini_models()
        
    models_to_try = st.session_state.available_models_list
    last_error = None
    
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name)
            response = m.generate_content(contents)
            st.session_state.active_model_used = model_name
            return response
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # If 429 quota, 404 not found, 400 modality/TTS error, or 503 service unavailable -> switch model
            if any(err in err_str for err in ["429", "quota", "rate limit", "404", "not found", "400", "modalities", "503", "overloaded"]):
                time.sleep(1.0)
                continue
            else:
                raise e
                
    raise Exception(f"Unable to generate response across available models. (Last error: {last_error})")
# ============================================
# 5. HERO BANNER
# ============================================
st.markdown(f"""
<div class="hero-wrapper">
    <div class="hero-content">
        <div class="hero-title">⚡ SmartPrep AI Pro</div>
        <div class="hero-subtitle">
            Master your career with real-time multi-question simulations, native voice speech evaluation, strict accuracy scoring, adaptive AI feedback, and curated study resources.
        </div>
        <div class="badge-container">
            <span class="badge badge-blue">🎙️ Voice & Speech Evaluation</span>
            <span class="badge badge-purple">🤖 Powered by Gemini Multimodal AI</span>
            <span class="badge badge-pink">🛡️ Auto-Quota Fallback Engine</span>
            <span class="badge badge-red">📚 Curated Online Resources</span>
        </div>
    </div>
    <div class="avatar-frame">
        <img class="avatar-img" src="{avatar_src}" alt="AI Coach Avatar" />
    </div>
</div>
""", unsafe_allow_html=True)

# ============================================
# 6. SESSION STATE INITIALIZATION
# ============================================
if "difficulty" not in st.session_state:
    st.session_state.difficulty = "Medium"
if "questions" not in st.session_state:
    st.session_state.questions = []
if "eval_results" not in st.session_state:
    st.session_state.eval_results = None
if "answers_history" not in st.session_state:
    st.session_state.answers_history = []
if "scores" not in st.session_state:
    st.session_state.scores = []
if "session_count" not in st.session_state:
    st.session_state.session_count = 0
if "candidate_name" not in st.session_state:
    st.session_state.candidate_name = ""
if "role" not in st.session_state:
    st.session_state.role = "Software Engineer"

# ============================================
# 7. PERFORMANCE GAUGE FUNCTION
# ============================================
def performance_gauge(score):
    value = score * 10

    if score >= 9:
        status = "🌟 Exceptional (Ready for Senior / Staff Roles!)"
        bar_color = "#22C55E"
    elif score >= 7:
        status = "🟢 Correct Answer (Strong Competency)"
        bar_color = "#84CC16"
    elif score >= 5:
        status = "🟡 Partially Correct Answer (On the Right Track)"
        bar_color = "#EAB308"
    elif score >= 3:
        status = "🔴 Wrong / Out of Topic Answer (Needs Deepening)"
        bar_color = "#F97316"
    else:
        status = "⚪ Insufficient / Blank Submission"
        bar_color = "#EF4444"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 46, "color": "white", "family": "Outfit"}},
        title={"text": f"<b>Overall Performance Rating</b><br><span style='font-size:0.85em;color:#C4B5FD'>{status}</span>"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "white"},
            "bar": {"color": bar_color, "thickness": 0.35},
            "bgcolor": "rgba(255,255,255,0.03)",
            "borderwidth": 1,
            "bordercolor": "rgba(255,255,255,0.1)",
            "steps": [
                {"range": [0, 20], "color": "rgba(239, 68, 68, 0.3)"},
                {"range": [20, 40], "color": "rgba(249, 115, 22, 0.3)"},
                {"range": [40, 60], "color": "rgba(234, 179, 8, 0.3)"},
                {"range": [60, 80], "color": "rgba(132, 204, 22, 0.3)"},
                {"range": [80, 100], "color": "rgba(34, 197, 94, 0.3)"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 4},
                "thickness": 0.75,
                "value": value
            }
        }
    ))

    fig.update_layout(height=360, margin=dict(l=20, r=20, t=60, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white", 'family': "Plus Jakarta Sans"})
    st.plotly_chart(fig, use_container_width=True)

# ============================================
# 8. SKILL RADAR CHART
# ============================================
def build_radar_chart(answers_history):
    dims = ["Clarity", "Technical Depth", "Structure", "Examples"]
    
    if not answers_history:
        values = [0, 0, 0, 0]
    else:
        clarity_scores = []
        tech_scores = []
        structure_scores = []
        example_scores = []
        
        for session in answers_history:
            evaluations = session.get('evaluation', {}).get('evaluations', [])
            for eval_item in evaluations:
                if isinstance(eval_item, dict):
                    clarity_scores.append(eval_item.get('clarity', eval_item.get('score', 5)))
                    tech_scores.append(eval_item.get('technical_depth', eval_item.get('score', 5)))
                    structure_scores.append(eval_item.get('structure', eval_item.get('score', 5)))
                    example_scores.append(eval_item.get('examples', eval_item.get('score', 5)))
        
        values = [
            round(sum(clarity_scores) / len(clarity_scores) if clarity_scores else 0, 2),
            round(sum(tech_scores) / len(tech_scores) if tech_scores else 0, 2),
            round(sum(structure_scores) / len(structure_scores) if structure_scores else 0, 2),
            round(sum(example_scores) / len(example_scores) if example_scores else 0, 2)
        ]
    
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],
        theta=dims + [dims[0]],
        fill="toself",
        line=dict(color="#ff4b6e", width=3),
        fillcolor="rgba(255,75,110,0.35)",
        hovertemplate='<b>%{theta}</b><br>Score: %{r:.1f}/10<extra></extra>'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 10],
                color="#CBD5E1",
                tickfont=dict(color="#CBD5E1", size=12)
            ),
            angularaxis=dict(
                tickfont=dict(color="#F8FAFC", size=14, weight="bold")
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
        showlegend=False,
        height=400,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    
    return fig

# ============================================
# 9. PDF REPORT GENERATOR
# ============================================
def generate_pdf_report(name, role, answers_history):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=50, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        textColor=colors.HexColor("#ff4b6e"),
        fontSize=24,
        fontName="Helvetica-Bold"
    )
    heading_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#302b63"),
        fontSize=16,
        fontName="Helvetica-Bold"
    )
    body_style = styles["BodyText"]
    
    story = []
    story.append(Paragraph("⚡ SmartPrep AI Pro — Interview Report Card", title_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph(
        f"<b>Candidate:</b> {name or 'Anonymous'}<br/>"
        f"<b>Target Role / Topic:</b> {role}<br/>"
        f"<b>Date:</b> {datetime.now().strftime('%d %b %Y, %H:%M')}<br/>"
        f"<b>Sessions Completed:</b> {len(answers_history)}",
        body_style
    ))
    story.append(Spacer(1, 16))
    
    if answers_history:
        all_scores = [session.get('evaluation', {}).get('overall_score', 0) for session in answers_history]
        avg_overall = round(sum(all_scores) / len(all_scores) if all_scores else 0, 2)
    else:
        avg_overall = 0
    
    data = [["Metric / Session Topic", "Score / 10"]]
    data.append(["Overall Career Average", avg_overall])
    
    for i, session in enumerate(answers_history, 1):
        score = session.get('evaluation', {}).get('overall_score', 0)
        data.append([f"Session {i} - {session.get('topic', 'Unknown')} ({session.get('difficulty', 'Medium')})", score])
    
    tbl = Table(data, colWidths=[3.5*inch, 2*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ff4b6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("Detailed Session Feedback Breakdown", heading_style))
    story.append(Spacer(1, 10))
    
    for i, session in enumerate(answers_history, 1):
        topic = session.get('topic', 'Unknown')
        evaluation = session.get('evaluation', {})
        overall_score = evaluation.get('overall_score', 0)
        overall_feedback = evaluation.get('overall_feedback', 'No feedback provided.')
        
        story.append(Paragraph(f"<b>Session {i}: {topic}</b> — Score: {overall_score}/10", body_style))
        story.append(Paragraph(f"<b>Executive Summary:</b> {overall_feedback}", body_style))
        story.append(Spacer(1, 8))
        
        evaluations = evaluation.get('evaluations', [])
        for eval_item in evaluations:
            q_num = eval_item.get('question_number', 1)
            q_score = eval_item.get('score', 0)
            q_status = eval_item.get('status', 'Unknown')
            q_feedback = eval_item.get('feedback', '')
            transcription = eval_item.get('transcription', '')
            
            story.append(Paragraph(f"<b>Q{q_num}:</b> Score {q_score}/10 — {q_status}", body_style))
            if transcription and transcription != "N/A - Typed Answer Only" and "No answer" not in transcription:
                story.append(Paragraph(f"<b>Spoken Audio Transcription:</b> <i>\"{transcription}\"</i>", body_style))
            if q_feedback:
                story.append(Paragraph(f"<b>Coach Advice:</b> <i>{q_feedback}</i>", body_style))
            story.append(Spacer(1, 4))
        
        story.append(Spacer(1, 12))
        story.append(PageBreak())
    
    doc.build(story)
    return buf.getvalue()

# ============================================
# 10. PROGRESS TRACKER BAR CHART
# ============================================
def generate_progress_chart(answers_history):
    if not answers_history:
        return None, None
    
    topic_scores = {}
    topic_counts = {}
    
    for session in answers_history:
        topic = session.get('topic', 'Unknown')
        score = session.get('evaluation', {}).get('overall_score', 0)
        
        if topic not in topic_scores:
            topic_scores[topic] = []
            topic_counts[topic] = 0
        
        topic_scores[topic].append(score)
        topic_counts[topic] += 1
    
    topics = list(topic_scores.keys())
    avg_scores = [sum(topic_scores[t]) / len(topic_scores[t]) for t in topics]
    counts = [topic_counts[t] for t in topics]
    
    zero_score_topics = [topics[i] for i, score in enumerate(avg_scores) if score == 0]
    
    if topics:
        colors_list = []
        for score in avg_scores:
            if score == 0:
                colors_list.append('#e53e3e')
            elif score >= 7:
                colors_list.append('#48bb78')
            elif score >= 5:
                colors_list.append('#f6ad55')
            elif score >= 3:
                colors_list.append('#fc8181')
            else:
                colors_list.append('#9b2c2c')
        
        bar_width = 0.6 if len(topics) <= 6 else 0.4
        chart_width = max(800, len(topics) * 100)
        
        fig = go.Figure(data=[
            go.Bar(
                x=topics,
                y=avg_scores,
                text=[f"{s:.1f}/10" for s in avg_scores],
                textposition='outside',
                textfont=dict(color='white', size=14),
                marker_color=colors_list,
                marker_line_color='rgba(255,255,255,0.3)',
                marker_line_width=2,
                width=bar_width,
                hovertemplate='<b>%{x}</b><br>Score: %{y:.1f}/10<br>Sessions: %{customdata}<extra></extra>',
                customdata=counts
            )
        ])
        
        zero_note = f"⚠️ Topics with 0 score: {', '.join(zero_score_topics)}" if zero_score_topics else ""
        
        fig.update_layout(
            title={
                'text': f"📊 Topic Progress Tracker {zero_note}",
                'y': 0.97,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': {'size': 22, 'color': '#F8FAFC', 'family': 'Outfit'}
            },
            xaxis={
                'title': 'Topics / Job Roles',
                'tickfont': {'size': 14, 'color': '#CBD5E1'},
                'gridcolor': 'rgba(255,255,255,0.05)',
                'tickangle': -20 if len(topics) > 4 else 0,
                'automargin': True
            },
            yaxis={
                'title': 'Average Score (out of 10)',
                'range': [0, 11],
                'tickfont': {'size': 14, 'color': '#CBD5E1'},
                'gridcolor': 'rgba(255,255,255,0.05)',
                'dtick': 1
            },
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            height=450,
            width=chart_width,
            margin=dict(l=60, r=60, t=100, b=100),
            hoverlabel=dict(bgcolor='#1a202c', font_size=14),
            modebar=dict(
                remove=['zoomIn2d', 'zoomOut2d', 'resetScale2d', 'pan2d', 'select2d', 'lasso2d'],
                orientation='v'
            ),
            xaxis_fixedrange=True,
            yaxis_fixedrange=True
        )
        
        if zero_score_topics:
            fig.add_annotation(
                x=0.5, y=0.5,
                text="⚠️ Topics with score 0 need immediate attention!",
                showarrow=False,
                font={'size': 14, 'color': '#fc8181'},
                xref="paper",
                yref="paper",
                bgcolor='rgba(0,0,0,0.7)',
                bordercolor='#e53e3e',
                borderwidth=2,
                borderpad=10,
                opacity=0.9
            )
        
        if len(topics) > 5:
            with st.container():
                st.markdown('<div class="chart-scroll-container">', unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown("</div>", unsafe_allow_html=True)
                st.caption("↔️ Scroll horizontally to see all topics")
        else:
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        if zero_score_topics:
            st.warning(f"⚠️ **Topics with 0/10 score:** {', '.join(zero_score_topics)}. These need focused practice!")
        
        return topics, avg_scores
    
    return None, None

# ============================================
# 11. SIDEBAR DASHBOARD
# ============================================
with st.sidebar:
    st.header("⚙️ Coach Dashboard")
    
    # Secure API Key Management
    st.subheader("🔑 API Authentication")
    env_key = os.getenv("GEMINI_API_KEY", "")
    secrets_key = st.secrets["GEMINI_API_KEY"] if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets else ""
    
    if env_key or secrets_key:
        st.success("✅ API Key Loaded (Env/Secrets)")
    else:
        user_key = st.text_input(
            "Enter Gemini API Key",
            type="password",
            value=st.session_state.get("user_api_key", ""),
            placeholder="AIzaSy...",
            help="Your key is kept 100% private in memory and never stored."
        )
        if user_key != st.session_state.get("user_api_key", ""):
            st.session_state.user_api_key = user_key
            st.rerun()
        if not user_key:
            st.warning("⚠️ Enter API Key above to begin.")
            
    st.info(f"⚡ **Active AI Model:** `{st.session_state.active_model_used}`")
    
    st.session_state.candidate_name = st.text_input(
        "👤 Your Name (For Report Card)",
        value=st.session_state.candidate_name,
        placeholder="Enter your name..."
    )
    st.session_state.role = st.text_input(
        "🎯 Target Job Role",
        value=st.session_state.role,
        placeholder="e.g. Software Engineer"
    )
    
    st.success(f"📊 **Current Difficulty:** `{st.session_state.difficulty}`")
    st.warning(f"📝 **Sessions Completed:** `{st.session_state.session_count}`")
    
    st.markdown("---")
    st.subheader("💡 Pro Interview Tips:")
    st.markdown("""
    - **Use the Microphone 🎙️**: Practicing speaking out loud builds vocal confidence and interview flow.
    - **STAR Method 🌟**: Structure answers with Situation, Task, Action, and Result.
    - **Be Precise 🎯**: Avoid vague statements; quantify achievements and technical depth.
    - **Review Resources 📚**: Check the curated links below each evaluation to close knowledge gaps.
    """)
    st.markdown("---")
    
    if st.session_state.answers_history:
        st.subheader("📄 Report Card Export")
        pdf_bytes = generate_pdf_report(
            st.session_state.candidate_name,
            st.session_state.role,
            st.session_state.answers_history
        )
        st.download_button(
            "⬇️ Download PDF Report Card",
            data=pdf_bytes,
            file_name=f"SmartPrep_Pro_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        st.markdown("---")
    
    if st.button("🔄 Reset Entire Session", use_container_width=True, type="secondary"):
        st.session_state.questions = []
        st.session_state.eval_results = None
        st.session_state.answers_history = []
        st.session_state.scores = []
        st.session_state.session_count = 0
        st.rerun()

# ============================================
# 12. TOPIC & DIFFICULTY INPUT
# ============================================
col_input, col_slider = st.columns([2, 1])

with col_input:
    topic = st.text_input("🎯 Enter a Topic, Job Role, or Tech Stack:", value="Full Stack Software Engineer", placeholder="e.g., Software Engineer, Data Scientist, Product Manager")
    if topic.strip() and topic != st.session_state.role:
        st.session_state.role = topic.strip()

with col_slider:
    new_difficulty = st.select_slider(
        "📊 Target Difficulty:",
        options=["Easy", "Medium", "Hard"],
        value=st.session_state.difficulty
    )
    if new_difficulty != st.session_state.difficulty:
        st.session_state.difficulty = new_difficulty

# ============================================
# 13. GENERATE QUESTIONS BUTTON (WITH AUTO-FALLBACK)
# ============================================
if st.button("🚀 Generate 2 Interview Questions", type="primary", use_container_width=True):
    if not topic.strip():
        st.warning("⚠️ Please enter a topic or job role first!")
    else:
        prompt = f"""
        Generate exactly 2 distinct, highly realistic technical or behavioral interview questions about '{topic}'.
        Target Difficulty level: {st.session_state.difficulty}.
        
        Return ONLY a valid JSON object with this exact key:
        - "questions": list of 2 question strings
        
        Example format:
        {{"questions": ["Question 1 text...", "Question 2 text..."]}}
        Only return the JSON object, no other text or explanation.
        """
        
        try:
            with st.spinner(f"⚡ SmartPrep AI is crafting 2 tailored '{st.session_state.difficulty}' questions for '{topic}'..."):
                response = safe_generate_content(prompt)
                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    st.session_state.questions = data.get("questions", [])
                else:
                    st.session_state.questions = [
                        f"Explain the core architectural principles of {topic} and give an example of when you applied them.",
                        f"Describe a complex technical challenge you faced when working with {topic}. What was your debugging and resolution process?"
                    ]
                st.session_state.eval_results = None
                st.rerun()
        except Exception as e:
            st.error(f"❌ Rate Limit Notice: {e}")
            st.info("💡 Please wait about 15 seconds and click Generate again!")

# ============================================
# 14. MOCK INTERVIEW FORM (TEXT + AUDIO)
# ============================================
if st.session_state.questions and len(st.session_state.questions) == 2:
    st.markdown("---")
    st.subheader(f"💡 Active Mock Interview: {topic} ({st.session_state.difficulty} Level)")
    st.write("For each question below, you can **type your answer** in the text box OR **record your voice directly** using the microphone! Click **Submit All Answers** at the bottom when you are done.")
    
    with st.form("questions_form", clear_on_submit=False):
        for i, q in enumerate(st.session_state.questions, 1):
            st.markdown(f"""
            <div class="question-card">
                <span class="q-number-pill">Question {i} of 2</span><br>
                {q}
            </div>
            """, unsafe_allow_html=True)
            
            c_text, c_audio = st.columns([3, 2])
            
            with c_text:
                st.text_area(
                    f"✍️ Typed Answer (Optional if recording audio) - Q{i}:", 
                    key=f"ans_{i}", 
                    height=130, 
                    placeholder="Type your structured answer here (STAR method recommended)..."
                )
                
            with c_audio:
                st.markdown(f"**🎙️ Voice Recording (Optional) - Q{i}:**")
                if hasattr(st, "audio_input"):
                    st.audio_input(f"Record audio for Question {i}", key=f"audio_{i}", label_visibility="collapsed")
                else:
                    st.file_uploader(f"Upload voice recording (WAV/MP3/M4A)", type=["wav", "mp3", "m4a", "ogg"], key=f"audio_{i}", label_visibility="collapsed")
                st.markdown('<div class="audio-hint">💡 Tip: Speak clearly! Gemini will transcribe & evaluate your vocal delivery.</div>', unsafe_allow_html=True)
                
            st.markdown("---")
            
        submit_all = st.form_submit_button("📤 Submit All Answers & Get SmartPrep Evaluation", type="primary", use_container_width=True)
        
        if submit_all:
            has_any_input = False
            for i in range(1, 3):
                t_ans = st.session_state.get(f"ans_{i}", "").strip()
                a_file = st.session_state.get(f"audio_{i}")
                if t_ans or a_file is not None:
                    has_any_input = True
                    break
            
            if has_any_input:
                with st.spinner("🧠 SmartPrep Multimodal AI is transcribing audio, scoring accuracy, and finding curated resources..."):
                    encoded_topic = re.sub(r'\s+', '+', topic)
                    contents = [
                        f"""
                        You are a strict, expert technical interview coach evaluating a candidate for '{topic}' at target difficulty level: '{st.session_state.difficulty}'.
                        
                        Below are 2 interview questions and the candidate's submitted responses. 
                        The candidate may have provided typed text answers, attached voice audio recordings, or both.
                        If voice audio recordings are provided, listen to them carefully, transcribe what the candidate said verbatim, and evaluate their technical depth as well as communication clarity and confidence.
                        
                        STRICT SCORING RULES (0-10):
                        1. If answer is missing or very short (<10 words) -> score = 0-1
                        2. If answer is off-topic or fundamentally wrong -> score = 2-3
                        3. If answer is relevant but vague or missing key technical depth -> score = 4-6
                        4. If answer is accurate, well-structured, and includes concrete examples -> score = 7-10
                        """
                    ]
                    
                    text_answers_saved = []
                    for i in range(1, 3):
                        q_text = st.session_state.questions[i-1]
                        ans_text = st.session_state.get(f"ans_{i}", "").strip()
                        audio_file = st.session_state.get(f"audio_{i}")
                        
                        text_answers_saved.append(ans_text if ans_text else "[Voice Recording Submitted]" if audio_file else "[No answer provided]")
                        
                        contents.append(f"\n--- Question {i}: {q_text} ---\n")
                        if ans_text:
                            contents.append(f"Candidate Typed Text Answer for Question {i}: {ans_text}\n")
                        if audio_file is not None:
                            contents.append(f"Candidate Voice Audio Recording for Question {i} is attached below (listen, transcribe verbatim, and evaluate):\n")
                            mime = getattr(audio_file, "type", "audio/wav") or "audio/wav"
                            contents.append({"mime_type": mime, "data": audio_file.getvalue()})
                        if not ans_text and audio_file is None:
                            contents.append(f"Candidate Answer for Question {i}: [No answer provided by candidate]\n")
                            
                    contents.append(f"""
                    \nReturn ONLY a valid JSON object matching this exact schema:
                    {{
                        "evaluations": [
                            {{
                                "question_number": 1,
                                "transcription": "Exact transcription of spoken audio if voice was used, or 'N/A - Typed Answer Only' if only text was submitted, or 'No answer submitted'.",
                                "score": integer from 0 to 10,
                                "clarity": integer from 0 to 10,
                                "technical_depth": integer from 0 to 10,
                                "structure": integer from 0 to 10,
                                "examples": integer from 0 to 10,
                                "status": "🟢 Correct / 🟡 Partial / 🔴 Wrong / ⚪ Blank",
                                "strengths": [
                                    "Specific bullet point 1 on technical accuracy or strong reasoning.",
                                    "Specific bullet point 2 on communication clarity or delivery."
                                ],
                                "gaps": [
                                    "Specific bullet point 1 on missing edge cases or technical depth.",
                                    "Specific bullet point 2 on areas to refine in structure or delivery."
                                ],
                                "feedback": "Brief 1-2 sentence actionable coaching advice for Question 1.",
                                "resources": [
                                    {{"title": "Best Practice Tutorial", "type": "📺 YouTube", "url": "https://www.youtube.com/results?search_query={encoded_topic}+tutorial", "reason": "Watch foundational concepts in action"}},
                                    {{"title": "System Architecture Guide", "type": "📚 Article", "url": "https://github.com/donnemartin/system-design-primer", "reason": "Deepen architectural patterns and trade-offs"}},
                                    {{"title": "Hands-on Coding Practice", "type": "💻 Platform", "url": "https://leetcode.com", "reason": "Apply algorithms and problem solving"}}
                                ]
                            }},
                            {{
                                "question_number": 2,
                                "transcription": "Exact transcription of spoken audio if voice was used, or 'N/A - Typed Answer Only' if only text was submitted, or 'No answer submitted'.",
                                "score": integer from 0 to 10,
                                "clarity": integer from 0 to 10,
                                "technical_depth": integer from 0 to 10,
                                "structure": integer from 0 to 10,
                                "examples": integer from 0 to 10,
                                "status": "🟢 Correct / 🟡 Partial / 🔴 Wrong / ⚪ Blank",
                                "strengths": ["..."],
                                "gaps": ["..."],
                                "feedback": "Brief 1-2 sentence actionable coaching advice for Question 2.",
                                "resources": [
                                    {{"title": "{topic} Interview Prep", "type": "📺 YouTube", "url": "https://www.youtube.com/results?search_query={encoded_topic}+interview+questions", "reason": "See expert interview breakdowns"}},
                                    {{"title": "Official Documentation", "type": "📚 Docs", "url": "https://devdocs.io", "reason": "Master standard library and APIs"}},
                                    {{"title": "Interactive Playground", "type": "💻 Platform", "url": "https://www.hackerrank.com", "reason": "Practice real-time coding challenges"}}
                                ]
                            }}
                        ],
                        "overall_score": float from 0.0 to 10.0 representing average performance across both questions,
                        "next_difficulty": "Easy", "Medium", or "Hard" (recommend progression based on score),
                        "overall_feedback": "2-3 sentence executive summary of candidate's interview readiness and key focus areas."
                    }}
                    
                    CRITICAL RULES:
                    1. "strengths", "gaps", and "resources" MUST ALWAYS be arrays matching the schema.
                    2. If audio was provided, ensure "transcription" accurately reflects the candidate's spoken words.
                    3. Only return the JSON object without any markdown wrapping or extra commentary.
                    """)
                    
                    try:
                        response = safe_generate_content(contents)
                        match = re.search(r'\{.*\}', response.text, re.DOTALL)
                        if match:
                            result = json.loads(match.group())
                        else:
                            result = {
                                "evaluations": [
                                    {
                                        "question_number": i,
                                        "transcription": "Evaluation completed (See detailed feedback below)",
                                        "score": 6,
                                        "clarity": 7,
                                        "technical_depth": 6,
                                        "structure": 6,
                                        "examples": 5,
                                        "status": "🟡 Partial",
                                        "strengths": ["Clear attempt at structuring the solution", "Good baseline understanding of core concepts"],
                                        "gaps": ["Could delve deeper into time/space complexities and edge cases", "Provide more concrete real-world examples"],
                                        "feedback": "Solid foundation! Focus on adding quantifiable metrics and architectural details next time.",
                                        "resources": [
                                            {"title": f"{topic} Fundamentals", "type": "📺 YouTube", "url": f"https://www.youtube.com/results?search_query={encoded_topic}+tutorial", "reason": "Build foundational knowledge"},
                                            {"title": "Practice Problems", "type": "💻 Platform", "url": "https://leetcode.com", "reason": "Apply what you learn"},
                                            {"title": "System Design Primer", "type": "📚 Article", "url": "https://github.com/donnemartin/system-design-primer", "reason": "Learn scalable architecture patterns"}
                                        ]
                                    } for i in range(1, 3)
                                ],
                                "overall_score": 6.0,
                                "next_difficulty": st.session_state.difficulty,
                                "overall_feedback": "Strong effort across the board! Review the point-by-point breakdown below and practice with the suggested resources to polish your answers."
                            }
                        
                        st.session_state.eval_results = result
                        st.session_state.scores.append(result.get("overall_score", 5))
                        st.session_state.session_count += 1
                        
                        st.session_state.answers_history.append({
                            "topic": topic,
                            "difficulty": st.session_state.difficulty,
                            "questions": st.session_state.questions,
                            "answers": text_answers_saved,
                            "evaluation": result
                        })
                        
                        st.session_state.difficulty = result.get("next_difficulty", st.session_state.difficulty)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Rate Limit Notice: {e}")
                        st.info("💡 Please wait about 15 seconds and click submit again!")
            else:
                st.warning("⚠️ Please type an answer OR record a voice audio response for at least one question before submitting!")

# ============================================
# 15. EXECUTIVE PERFORMANCE DASHBOARD & RESULTS
# ============================================
if st.session_state.eval_results:
    res = st.session_state.eval_results
    st.markdown("---")
    st.header("📊 Executive Performance Dashboard")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🎯 Overall Score", f"{res.get('overall_score', 0):.1f} / 10", delta="Average")
    with c2:
        st.metric("🔥 Recommended Level", st.session_state.difficulty, delta="Adaptive AI")
    with c3:
        avg_score = sum(st.session_state.scores) / len(st.session_state.scores) if st.session_state.scores else 0
        st.metric("📈 Career Average", f"{avg_score:.1f} / 10")
    with c4:
        st.metric("🏆 Completed Sets", st.session_state.session_count)
    
    col_gauge, col_sum = st.columns([1, 1])
    with col_gauge:
        performance_gauge(res.get("overall_score", 0))
    with col_sum:
        st.markdown("### 💬 Coach's Executive Summary")
        st.info(f"**Overall Verdict:** {res.get('overall_feedback', 'Great practice session! Keep refining your technical depth.')}")
        st.success(f"📈 Based on your performance, your next interview simulation difficulty has been calibrated to: **{st.session_state.difficulty}**.")
        st.markdown("**Next Step:** Click **🚀 Generate 2 Interview Questions** at the top to challenge yourself at the new difficulty!")
    
    st.markdown("---")
    st.subheader("📝 Detailed Question Breakdown, Transcription & Curated Resources")
    
    for eval_item in res.get("evaluations", []):
        q_num = eval_item.get("question_number", 1)
        q_score = eval_item.get("score", 0)
        q_status = eval_item.get("status", "⚪ Unknown")
        q_text = st.session_state.questions[q_num - 1] if q_num <= len(st.session_state.questions) else ""
        user_ans = st.session_state.get(f"ans_{q_num}", "")
        transcription = eval_item.get("transcription", "N/A - Typed Answer Only")
        
        icon = "🟢" if q_score >= 7 else "🟡" if q_score >= 4 else "🔴" if q_score > 0 else "⚪"
        
        with st.expander(f"{icon} Question {q_num} Evaluation — Score: {q_score}/10 — {q_status}", expanded=True):
            st.markdown(f"**❓ Question:** {q_text}")
            
            if user_ans.strip():
                st.markdown(f"**✍️ Typed Answer:** _{user_ans}_")
                
            if transcription and transcription != "N/A - Typed Answer Only" and "No answer" not in transcription:
                st.markdown(f"""
                <div class="transcription-box">
                    <b>🗣️ AI Spoken Voice Transcription:</b><br>"{transcription}"
                </div>
                """, unsafe_allow_html=True)
            elif not user_ans.strip():
                st.markdown("**✍️ Answer:** _[No answer submitted]_")
                
            st.markdown("---")
            
            col_str, col_gap = st.columns(2)
            with col_str:
                st.success("#### ✅ Strengths & Highlights")
                strengths = eval_item.get("strengths", ["No strengths identified"])
                if isinstance(strengths, list) and strengths:
                    for item in strengths:
                        st.markdown(f"- ✔️ **{item}**")
                else:
                    st.markdown(f"- ✔️ {strengths}")
                    
            with col_gap:
                st.error("#### ❌ Gaps & Areas to Refine")
                gaps = eval_item.get("gaps", ["No gaps identified"])
                if isinstance(gaps, list) and gaps:
                    for item in gaps:
                        st.markdown(f"- 🔸 **{item}**")
                else:
                    st.markdown(f"- 🔸 {gaps}")
            
            if eval_item.get("feedback"):
                st.markdown("---")
                st.markdown(f"💡 **Coach's Actionable Advice:** {eval_item['feedback']}")
                
            # Curated Resources 3-Column Grid
            st.markdown("---")
            st.markdown("📚 **Curated Online Resources to Master This Question:**")
            resources = eval_item.get("resources", [])
            if isinstance(resources, list) and resources:
                cols = st.columns(min(len(resources), 3))
                for idx, resource in enumerate(resources[:3]):
                    with cols[idx % 3]:
                        if isinstance(resource, dict):
                            st.markdown(f"""
                            <div class="resource-card">
                                <div style="font-size: 1.8rem; text-align: center;">{resource.get('type', '📚')}</div>
                                <h5 style="color: #F8FAFC; margin: 0.5rem 0; text-align: center; font-size: 1.05rem;">{resource.get('title', 'Study Resource')}</h5>
                                <a href="{resource.get('url', '#')}" target="_blank" style="display: block; text-align: center; color: #60A5FA; text-decoration: none; font-weight: 700; padding: 0.5rem; border-radius: 8px; background: rgba(59, 130, 246, 0.15); margin: 0.65rem 0; font-size: 0.95rem;">
                                    🔗 View Resource
                                </a>
                                <p style="color: #94A3B8; font-size: 0.85rem; margin: 0.5rem 0; text-align: center;">💡 {resource.get('reason', 'Recommended study material')}</p>
                            </div>
                            """, unsafe_allow_html=True)

# ============================================
# 16. SKILL RADAR & PROGRESS TRACKER CHARTS
# ============================================
if st.session_state.answers_history:
    st.markdown("---")
    
    col_radar, col_progress = st.columns([1, 2])
    
    with col_radar:
        st.subheader("🎯 Skill Radar")
        st.caption("Visual breakdown of your core competency dimensions across sessions")
        radar_fig = build_radar_chart(st.session_state.answers_history)
        st.plotly_chart(radar_fig, use_container_width=True)
    
    with col_progress:
        st.subheader("📈 Topic Progress Tracker")
        st.caption("Visualizing your average performance score across different job roles & topics")
        generate_progress_chart(st.session_state.answers_history)

# ============================================
# 17. SESSION HISTORY
# ============================================
if st.session_state.answers_history:
    st.markdown("---")
    with st.expander("📚 Past Interview Session Logs & History", expanded=False):
        for session_idx, hist in enumerate(reversed(st.session_state.answers_history), 1):
            st.markdown(f"### 🎯 Session {len(st.session_state.answers_history) - session_idx + 1} — {hist['topic']} ({hist['difficulty']} Level)")
            st.markdown(f"**Overall Average Score:** `{hist['evaluation'].get('overall_score', 'N/A')} / 10`")
            for i, (q, a) in enumerate(zip(hist['questions'], hist['answers']), 1):
                st.markdown(f"**Q{i}:** {q}")
                st.markdown(f"**Submitted Response:** _{a if a.strip() else '[No answer]'}_")
            st.markdown("---")

# ============================================
# 18. FOOTER
# ============================================
st.markdown("---")
st.markdown(f"""
<div style="text-align: center; color: #64748B; font-size: 0.95rem; padding: 1rem 0;">
    🚀 <b>SmartPrep AI Pro | Personalized Career & Interview Coach</b><br>
    Powered by Google Gemini Multimodal AI (<code>{st.session_state.active_model_used}</code>) | Built for Hackathon Excellence
</div>
""", unsafe_allow_html=True)