import streamlit as st


def configure_page() -> None:
    st.set_page_config(
        page_title="Superstore Sales Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            .auth-shell {
                max-width: 980px;
                margin: 0 auto 1.5rem auto;
                padding-top: 0.5rem;
            }

            .main-header {
                font-size: 2.7rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin-bottom: 0.4rem;
                color: #12263a;
            }

            .sub-header {
                color: #51606f;
                margin-bottom: 1.2rem;
            }

            .metric-shell {
                padding: 0.2rem 0 0.4rem 0;
            }

            .stMetric {
                background: linear-gradient(180deg, #ffffff 0%, #f7fafc 100%);
                border: 1px solid #dbe5ef;
                border-radius: 16px;
                padding: 0.6rem;
                box-shadow: 0 8px 24px rgba(18, 38, 58, 0.06);
            }

            .insight-card {
                background: linear-gradient(135deg, #0f4c5c 0%, #1d7874 100%);
                color: white;
                border-radius: 18px;
                padding: 1rem 1.1rem;
                margin-bottom: 0.9rem;
                box-shadow: 0 10px 28px rgba(15, 76, 92, 0.22);
            }

            .insight-card h4 {
                margin: 0 0 0.3rem 0;
                font-size: 1rem;
            }

            .insight-card p {
                margin: 0;
                font-size: 0.92rem;
                line-height: 1.45;
            }

            .profile-card {
                background: linear-gradient(135deg, #ffffff 0%, #f6fbff 100%);
                border: 1px solid #dbe5ef;
                border-radius: 18px;
                padding: 1rem 1.1rem;
                margin-bottom: 1rem;
                box-shadow: 0 8px 24px rgba(18, 38, 58, 0.06);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
