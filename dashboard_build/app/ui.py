"""Shared visual styling: theme CSS, status pills, campaign banner. No DB/business logic here."""

import streamlit as st

STATUS_COLORS = {
    "DISCOVERED": ("#EEF2F6", "#475467"),
    "DRAFT": ("#EEF2F6", "#475467"),
    "READY_FOR_REVIEW": ("#FEF3C7", "#92400E"),
    "COMPLETED": ("#DCFCE7", "#166534"),
    "REOPENED": ("#F3E8FF", "#6B21A8"),
}

WORKFLOW_STEPS = ["DRAFT", "READY_FOR_REVIEW", "COMPLETED", "REOPENED"]


def inject_theme():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.5rem; max-width: 1400px;}
        .padm-pill {display:inline-flex;align-items:center;padding:4px 14px;border-radius:999px;
                    font-size:12px;font-weight:700;letter-spacing:.02em;white-space:nowrap;}
        .padm-card {background:#fff;border:1px solid #E4E8EF;border-radius:12px;padding:20px 24px;
                    margin-bottom:14px;box-shadow:0 1px 2px rgba(16,24,40,.04);}
        .padm-chip {background:#F4F6F9;border-radius:8px;padding:4px 10px;font-size:12px;
                    color:#475467;font-weight:600;margin-right:8px;display:inline-block;}
        .padm-section-title {font-weight:800;font-size:15px;color:#0B1F3A;margin:4px 0 10px 0;}
        .padm-muted {font-size:12px;color:#98A2B3;}
        .padm-step-wrap {display:flex;align-items:flex-start;gap:0;position:relative;}
        .padm-step {display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;flex:1;}
        .padm-step .circ {width:32px;height:32px;border-radius:999px;display:flex;align-items:center;
                           justify-content:center;font-weight:800;font-size:13px;z-index:1;}
        .padm-step .circ.done {background:#2563EB;color:#fff;}
        .padm-step .circ.current {background:#166534;color:#fff;box-shadow:0 0 0 4px #DCFCE7;}
        .padm-step .circ.pending {background:#F2F4F7;color:#98A2B3;border:2px dashed #D0D5DD;}
        .padm-step .lbl {font-size:11px;font-weight:700;color:#344054;text-align:center;}
        .padm-step-line {position:absolute;top:16px;left:-50%;width:100%;height:2px;background:#2563EB;z-index:0;}
        .padm-step-line.pending {background:#E4E8EF;}
        [data-testid="stMetricValue"] {font-weight:800;color:#0B1F3A;}
        [data-testid="stMetricLabel"] {font-weight:600;text-transform:uppercase;letter-spacing:.03em;font-size:11px;color:#667085;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_pill_html(status):
    bg, fg = STATUS_COLORS.get(status, ("#EEF2F6", "#475467"))
    return f'<span class="padm-pill" style="background:{bg};color:{fg}">{status or "UNKNOWN"}</span>'


def campaign_banner(display_name, status, subtitle=""):
    st.markdown(
        f"""
        <div class="padm-card" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
            <div>
                <div style="font-size:20px;font-weight:800;color:#0B1F3A">{display_name}</div>
                <div style="font-size:13px;color:#667085;margin-top:4px">{subtitle}</div>
            </div>
            {status_pill_html(status)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def workflow_stepper(current_status):
    """Renders DRAFT -> READY_FOR_REVIEW -> COMPLETED -> REOPENED as a stepper, current step highlighted."""
    try:
        current_idx = WORKFLOW_STEPS.index(current_status)
    except ValueError:
        current_idx = 0

    cells = []
    for i, step in enumerate(WORKFLOW_STEPS):
        if i < current_idx:
            circ_class, glyph = "done", "✓"
        elif i == current_idx:
            circ_class, glyph = "current", "✓"
        else:
            circ_class, glyph = "pending", str(i + 1)
        line_html = ""
        if i > 0:
            line_class = "padm-step-line" if i <= current_idx else "padm-step-line pending"
            line_html = f'<div class="{line_class}"></div>'
        label = step.replace("_", " ").title()
        cells.append(
            f'<div class="padm-step">{line_html}<div class="circ {circ_class}">{glyph}</div>'
            f'<div class="lbl">{label}</div></div>'
        )
    st.markdown(f'<div class="padm-card"><div class="padm-step-wrap">{"".join(cells)}</div></div>', unsafe_allow_html=True)


def chips(*labels):
    st.markdown("".join(f'<span class="padm-chip">{label}</span>' for label in labels), unsafe_allow_html=True)


def section_title(text):
    st.markdown(f'<div class="padm-section-title">{text}</div>', unsafe_allow_html=True)
