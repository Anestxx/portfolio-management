from __future__ import annotations

import pandas as pd
import streamlit as st

from backend import PortfolioRepository, get_config
from backend.database import ASSET_TYPES, CURRENCIES, RISK_PROFILES
from frontend.charts import (
    create_asset_allocation_chart,
    create_performance_chart,
    create_portfolio_breakdown_chart,
    create_sector_chart,
    create_top_holdings_chart,
)
from frontend.theme import configure_page, inject_styles


FLASH_KEY = "_flash_message"
SESSION_USER_ID_KEY = "current_user_id"
SESSION_LOGGED_IN_KEY = "logged_in"


@st.cache_resource(show_spinner=False)
def get_repository() -> PortfolioRepository:
    return PortfolioRepository(get_config())


def initialize_session_state() -> None:
    st.session_state.setdefault(SESSION_LOGGED_IN_KEY, False)
    st.session_state.setdefault(SESSION_USER_ID_KEY, None)


def queue_message(message: str, level: str = "success") -> None:
    st.session_state[FLASH_KEY] = {"message": message, "level": level}


def show_message() -> None:
    payload = st.session_state.pop(FLASH_KEY, None)
    if payload is None:
        return
    getattr(st, payload["level"], st.info)(payload["message"])


def login_user(user: dict) -> None:
    st.session_state[SESSION_LOGGED_IN_KEY] = True
    st.session_state[SESSION_USER_ID_KEY] = int(user["id"])


def logout_user() -> None:
    st.session_state[SESSION_LOGGED_IN_KEY] = False
    st.session_state[SESSION_USER_ID_KEY] = None


def get_current_user(repository: PortfolioRepository) -> dict | None:
    user_id = st.session_state.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None
    return repository.get_user_by_id(int(user_id))


def format_currency(value: float, currency: str = "USD") -> str:
    symbol = {"USD": "$", "INR": "Rs ", "EUR": "EUR ", "GBP": "GBP "}.get(currency, "")
    return f"{symbol}{value:,.2f}"


def render_auth_page(repository: PortfolioRepository) -> None:
    st.markdown("<div class='auth-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='main-header'>Personal Portfolio Manager</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-header'>Track your portfolios, holdings, and profile in one place. New accounts receive editable sample data as a starting point.</div>",
        unsafe_allow_html=True,
    )
    st.info("Demo account available: username `demo` and password `demo123`.")

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            identifier = st.text_input("Username or Email", placeholder="demo")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submit = st.form_submit_button("Login", use_container_width=True)
            if submit:
                if not identifier or not password:
                    st.error("Please fill in both fields.")
                else:
                    success, message, user = repository.authenticate_user(identifier, password)
                    if success and user is not None:
                        login_user(user)
                        queue_message(f"Welcome back, {user['full_name']}!")
                        st.rerun()
                    else:
                        st.error(message)

    with signup_tab:
        with st.form("signup_form"):
            full_name = st.text_input("Full Name", placeholder="Jane Doe")
            username = st.text_input("Username", placeholder="janedoe")
            email = st.text_input("Email", placeholder="jane@example.com")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submit = st.form_submit_button("Create Account", use_container_width=True)
            if submit:
                if not all([full_name, username, email, password, confirm_password]):
                    st.error("Please complete all fields.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    success, message, user = repository.register_user(username, email, password, full_name)
                    if success and user is not None:
                        login_user(user)
                        queue_message("Account created with starter portfolio examples.")
                        st.rerun()
                    else:
                        st.error(message)
    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar(repository: PortfolioRepository, current_user: dict) -> tuple[str, int | None]:
    portfolios = repository.get_user_portfolios(int(current_user["id"]))
    storage_summary = repository.get_storage_summary()

    with st.sidebar:
        st.markdown(f"### {current_user['full_name']}")
        st.caption(f"@{current_user['username']}")
        st.caption(current_user["email"])
        if int(current_user.get("is_demo", 0)) == 1:
            st.info("You are using the demo investor account with example data.")

        workspace = st.radio("Workspace", ["Dashboard", "Portfolios", "Profile"], index=0)

        selected_portfolio_id = None
        if not portfolios.empty:
            options = {"All Portfolios": None}
            for _, portfolio in portfolios.iterrows():
                options[portfolio["name"]] = int(portfolio["id"])
            selected_label = st.selectbox("Focus Portfolio", list(options.keys()))
            selected_portfolio_id = options[selected_label]

        st.markdown("---")
        if st.button("Load Example Data If Account Is Empty", use_container_width=True):
            repository.seed_sample_portfolio_for_user(int(current_user["id"]))
            queue_message("Example data is added only when the account has no portfolios yet.")
            st.rerun()

        if st.button("Logout", use_container_width=True):
            logout_user()
            queue_message("Signed out successfully.", "info")
            st.rerun()

        st.markdown("---")
        st.caption(f"Users: {storage_summary['users_count']}")
        st.caption(f"Portfolios: {storage_summary['portfolios_count']}")
        st.caption(f"Holdings: {storage_summary['holdings_count']}")
        st.caption(f"DB Size: {storage_summary['size_mb']} MB")
        return workspace, selected_portfolio_id


def render_header(current_user: dict) -> None:
    st.markdown("<div class='main-header'>Personal Portfolio Manager</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='sub-header'>Welcome, {current_user['full_name']}. Manage your personal investment portfolios, profile, and sample holdings from one dashboard.</div>",
        unsafe_allow_html=True,
    )


def render_dashboard(repository: PortfolioRepository, current_user: dict, selected_portfolio_id: int | None) -> None:
    user_id = int(current_user["id"])
    currency = str(current_user.get("preferred_currency", "USD"))
    metrics = repository.get_dashboard_metrics(user_id, selected_portfolio_id)
    asset_allocation = repository.get_asset_allocation(user_id, selected_portfolio_id)
    sector_allocation = repository.get_sector_allocation(user_id, selected_portfolio_id)
    portfolio_breakdown = repository.get_portfolio_breakdown(user_id)
    top_holdings = repository.get_top_holdings(user_id, selected_portfolio_id)
    performance = repository.get_performance_timeline(user_id, selected_portfolio_id)
    recent_activity = repository.get_recent_activity(user_id)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Current Value", format_currency(metrics["current_value"], currency))
    metric_cols[1].metric("Invested", format_currency(metrics["invested_value"], currency))
    metric_cols[2].metric("Unrealized P/L", format_currency(metrics["gain_loss"], currency))
    metric_cols[3].metric("Cash Balance", format_currency(metrics["cash_balance"], currency))
    metric_cols[4].metric("Portfolios", metrics["portfolios_count"])
    metric_cols[5].metric("Holdings", metrics["holdings_count"])

    top_left, top_right = st.columns([1.3, 1])
    with top_left:
        if performance.empty:
            st.info("Add holdings with purchase dates to see the growth timeline.")
        else:
            st.plotly_chart(create_performance_chart(performance), use_container_width=True)
    with top_right:
        if asset_allocation.empty:
            st.info("No holdings yet.")
        else:
            st.plotly_chart(create_asset_allocation_chart(asset_allocation), use_container_width=True)

    mid_left, mid_right = st.columns(2)
    with mid_left:
        if sector_allocation.empty:
            st.info("No sector data available.")
        else:
            st.plotly_chart(create_sector_chart(sector_allocation), use_container_width=True)
    with mid_right:
        if portfolio_breakdown.empty:
            st.info("No portfolio breakdown available.")
        else:
            st.plotly_chart(create_portfolio_breakdown_chart(portfolio_breakdown), use_container_width=True)

    bottom_left, bottom_right = st.columns([1.15, 0.85])
    with bottom_left:
        st.markdown("### Top Holdings")
        if top_holdings.empty:
            st.info("No holdings available.")
        else:
            st.plotly_chart(create_top_holdings_chart(top_holdings), use_container_width=True)
            st.dataframe(
                top_holdings.style.format(
                    {
                        "market_value": format_currency,
                        "gain_loss": format_currency,
                        "gain_loss_pct": "{:+.1f}%"
                    }
                ),
                use_container_width=True,
            )
    with bottom_right:
        st.markdown("### Recent Activity")
        if recent_activity.empty:
            st.info("Your activity feed will appear here after you create or edit portfolios and holdings.")
        else:
            for _, row in recent_activity.iterrows():
                event_time = row["event_time"].strftime("%d %b %Y") if pd.notna(row["event_time"]) else "Unknown"
                st.markdown(
                    f"""
                    <div class='profile-card'>
                        <strong>{row['event_type']}</strong><br/>
                        <span>{row['title']}</span><br/>
                        <small>{row['details']}</small><br/>
                        <small>{event_time}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def render_portfolio_manager(repository: PortfolioRepository, current_user: dict) -> None:
    st.markdown("## Portfolio Manager")
    st.caption("Create portfolios, edit cash balances and goals, and manage the holdings inside each portfolio.")

    user_id = int(current_user["id"])
    portfolios = repository.get_user_portfolios(user_id)
    holdings = repository.get_user_holdings(user_id)

    portfolio_tab, holdings_tab = st.tabs(["Portfolios", "Holdings"])

    with portfolio_tab:
        if portfolios.empty:
            st.info("No portfolios yet. Create your first one below.")
        else:
            for _, portfolio in portfolios.iterrows():
                with st.expander(portfolio["name"]):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Current Value", format_currency(portfolio["current_value"], current_user.get("preferred_currency", "USD")))
                    col2.metric("Cash", format_currency(portfolio["cash_balance"], current_user.get("preferred_currency", "USD")))
                    col3.metric("Target Progress", f"{portfolio['target_progress']:.1f}%")
                    st.write(f"Objective: {portfolio['objective'] or 'Not provided'}")
                    st.write(f"Risk Profile: {portfolio['risk_profile']}")
                    if portfolio["notes"]:
                        st.write(portfolio["notes"])

        mode = st.radio("Portfolio Mode", ["Create New", "Edit Existing"], horizontal=True)
        selected_portfolio = None
        if mode == "Edit Existing" and not portfolios.empty:
            mapping = {row["name"]: int(row["id"]) for _, row in portfolios.iterrows()}
            chosen_name = st.selectbox("Select Portfolio", list(mapping.keys()))
            selected_portfolio = portfolios[portfolios["id"] == mapping[chosen_name]].iloc[0]

        with st.form("portfolio_form"):
            name = st.text_input("Portfolio Name", value=str(selected_portfolio["name"]) if selected_portfolio is not None else "")
            objective = st.text_input("Objective", value=str(selected_portfolio["objective"]) if selected_portfolio is not None else "")
            risk_profile = st.selectbox(
                "Risk Profile",
                RISK_PROFILES,
                index=RISK_PROFILES.index(str(selected_portfolio["risk_profile"])) if selected_portfolio is not None else 1,
            )
            target_value = st.number_input(
                "Target Value",
                min_value=0.0,
                value=float(selected_portfolio["target_value"]) if selected_portfolio is not None else 100000.0,
                step=1000.0,
            )
            cash_balance = st.number_input(
                "Cash Balance",
                min_value=0.0,
                value=float(selected_portfolio["cash_balance"]) if selected_portfolio is not None else 0.0,
                step=500.0,
            )
            notes = st.text_area("Notes", value=str(selected_portfolio["notes"]) if selected_portfolio is not None else "")
            submit = st.form_submit_button("Save Portfolio", use_container_width=True)
            if submit:
                if not name:
                    st.error("Please enter a portfolio name.")
                else:
                    if selected_portfolio is None:
                        repository.create_portfolio(user_id, name, objective, risk_profile, target_value, cash_balance, notes)
                        queue_message("Portfolio created successfully.")
                    else:
                        repository.update_portfolio(
                            int(selected_portfolio["id"]),
                            user_id,
                            name,
                            objective,
                            risk_profile,
                            target_value,
                            cash_balance,
                            notes,
                        )
                        queue_message("Portfolio updated successfully.")
                    st.rerun()

        if selected_portfolio is not None and st.button("Delete Selected Portfolio", type="secondary", use_container_width=True):
            repository.delete_portfolio(int(selected_portfolio["id"]), user_id)
            queue_message("Portfolio deleted.", "info")
            st.rerun()

    with holdings_tab:
        if portfolios.empty:
            st.warning("Create a portfolio before adding holdings.")
            return

        st.dataframe(
            holdings.style.format(
                {
                    "units": "{:,.2f}",
                    "average_cost": format_currency,
                    "current_price": format_currency,
                    "invested_value": format_currency,
                    "market_value": format_currency,
                    "gain_loss": format_currency,
                    "gain_loss_pct": "{:+.1f}%"
                }
            ) if not holdings.empty else holdings,
            use_container_width=True,
            height=360,
        )

        mode = st.radio("Holding Mode", ["Create New", "Edit Existing"], horizontal=True, key="holding_mode")
        selected_holding = None
        if mode == "Edit Existing" and not holdings.empty:
            mapping = {
                f"{row['asset_name']} ({row['portfolio_name']})": int(row["id"])
                for _, row in holdings.iterrows()
            }
            chosen = st.selectbox("Select Holding", list(mapping.keys()))
            selected_holding = holdings[holdings["id"] == mapping[chosen]].iloc[0]

        portfolio_name_to_id = {row["name"]: int(row["id"]) for _, row in portfolios.iterrows()}
        holding_portfolio_name = (
            str(selected_holding["portfolio_name"]) if selected_holding is not None else list(portfolio_name_to_id.keys())[0]
        )

        with st.form("holding_form"):
            portfolio_name = st.selectbox(
                "Portfolio",
                list(portfolio_name_to_id.keys()),
                index=list(portfolio_name_to_id.keys()).index(holding_portfolio_name),
            )
            asset_name = st.text_input("Asset Name", value=str(selected_holding["asset_name"]) if selected_holding is not None else "")
            ticker = st.text_input("Ticker", value=str(selected_holding["ticker"]) if selected_holding is not None else "")
            asset_type = st.selectbox(
                "Asset Type",
                ASSET_TYPES,
                index=ASSET_TYPES.index(str(selected_holding["asset_type"])) if selected_holding is not None else 0,
            )
            sector = st.text_input("Sector", value=str(selected_holding["sector"]) if selected_holding is not None else "")
            units = st.number_input("Units", min_value=0.0, value=float(selected_holding["units"]) if selected_holding is not None else 1.0, step=1.0)
            average_cost = st.number_input(
                "Average Cost",
                min_value=0.0,
                value=float(selected_holding["average_cost"]) if selected_holding is not None else 100.0,
                step=1.0,
            )
            current_price = st.number_input(
                "Current Price",
                min_value=0.0,
                value=float(selected_holding["current_price"]) if selected_holding is not None else 100.0,
                step=1.0,
            )
            purchase_date = st.date_input(
                "Purchase Date",
                value=selected_holding["purchase_date"].date() if selected_holding is not None and pd.notna(selected_holding["purchase_date"]) else pd.Timestamp.today().date(),
            )
            notes = st.text_area("Notes", value=str(selected_holding["notes"]) if selected_holding is not None else "")
            submit = st.form_submit_button("Save Holding", use_container_width=True)

            if submit:
                if not asset_name:
                    st.error("Please enter an asset name.")
                else:
                    payload = {
                        "user_id": user_id,
                        "portfolio_id": portfolio_name_to_id[portfolio_name],
                        "asset_name": asset_name,
                        "ticker": ticker,
                        "asset_type": asset_type,
                        "sector": sector,
                        "units": units,
                        "average_cost": average_cost,
                        "current_price": current_price,
                        "purchase_date": purchase_date.strftime("%Y-%m-%d"),
                        "notes": notes,
                    }
                    if selected_holding is None:
                        repository.create_holding(**payload)
                        queue_message("Holding added successfully.")
                    else:
                        repository.update_holding(holding_id=int(selected_holding["id"]), **payload)
                        queue_message("Holding updated successfully.")
                    st.rerun()

        if selected_holding is not None and st.button("Delete Selected Holding", type="secondary", use_container_width=True):
            repository.delete_holding(int(selected_holding["id"]), user_id)
            queue_message("Holding deleted.", "info")
            st.rerun()


def render_profile_page(repository: PortfolioRepository, current_user: dict) -> None:
    st.markdown("## Profile")
    st.caption("Update your personal information, investor preferences, and keep your account aligned with your portfolio strategy.")

    user_id = int(current_user["id"])
    portfolios = repository.get_user_portfolios(user_id)
    holdings = repository.get_user_holdings(user_id)

    left, right = st.columns([1.15, 0.85])
    with left:
        st.markdown(
            f"""
            <div class='profile-card'>
                <strong>{current_user['full_name']}</strong><br/>
                <span>@{current_user['username']}</span><br/>
                <span>{current_user['email']}</span><br/><br/>
                <span>{current_user.get('job_title') or 'No job title added yet'}</span><br/>
                <span>{current_user.get('company') or 'No company added yet'}</span><br/>
                <span>Risk Appetite: {current_user.get('risk_appetite', 'Moderate')}</span><br/>
                <span>Preferred Currency: {current_user.get('preferred_currency', 'USD')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("profile_form"):
            full_name = st.text_input("Full Name", value=str(current_user.get("full_name", "")))
            email = st.text_input("Email", value=str(current_user.get("email", "")))
            job_title = st.text_input("Job Title", value=str(current_user.get("job_title", "")))
            company = st.text_input("Company", value=str(current_user.get("company", "")))
            risk_appetite = st.selectbox(
                "Risk Appetite",
                RISK_PROFILES,
                index=RISK_PROFILES.index(str(current_user.get("risk_appetite", "Moderate"))),
            )
            preferred_currency = st.selectbox(
                "Preferred Currency",
                CURRENCIES,
                index=CURRENCIES.index(str(current_user.get("preferred_currency", "USD"))),
            )
            bio = st.text_area("Bio", value=str(current_user.get("bio", "")), height=140)
            submit = st.form_submit_button("Update Profile", use_container_width=True)
            if submit:
                if not full_name or not email:
                    st.error("Full name and email are required.")
                else:
                    success, message = repository.update_user_profile(
                        user_id=user_id,
                        full_name=full_name,
                        email=email,
                        job_title=job_title,
                        company=company,
                        bio=bio,
                        risk_appetite=risk_appetite,
                        preferred_currency=preferred_currency,
                    )
                    if success:
                        queue_message(message)
                        st.rerun()
                    else:
                        st.error(message)

    with right:
        st.metric("Portfolios", len(portfolios))
        st.metric("Holdings", len(holdings))
        created_at = current_user.get("created_at")
        last_login = current_user.get("last_login")
        st.write(f"Account created: {created_at.strftime('%Y-%m-%d %H:%M') if isinstance(created_at, pd.Timestamp) else 'N/A'}")
        st.write(f"Last login: {last_login.strftime('%Y-%m-%d %H:%M') if isinstance(last_login, pd.Timestamp) else 'First login'}")
        if current_user.get("bio"):
            st.write("### Bio")
            st.write(current_user["bio"])


def main() -> None:
    configure_page()
    inject_styles()
    initialize_session_state()
    show_message()

    repository = get_repository()
    current_user = get_current_user(repository)

    if not st.session_state.get(SESSION_LOGGED_IN_KEY) or current_user is None:
        render_auth_page(repository)
        return

    workspace, selected_portfolio_id = render_sidebar(repository, current_user)
    render_header(current_user)

    if workspace == "Dashboard":
        render_dashboard(repository, current_user, selected_portfolio_id)
    elif workspace == "Portfolios":
        render_portfolio_manager(repository, current_user)
    else:
        render_profile_page(repository, current_user)
