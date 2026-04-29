from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go


def create_performance_chart(dataframe):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dataframe["purchase_date"],
            y=dataframe["cumulative_invested"],
            mode="lines+markers",
            name="Invested Capital",
            line=dict(color="#1d4ed8", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dataframe["purchase_date"],
            y=dataframe["cumulative_market"],
            mode="lines+markers",
            name="Current Market Value",
            line=dict(color="#0f766e", width=3),
        )
    )
    fig.update_layout(
        title="Portfolio Growth Over Time",
        xaxis_title="Purchase Date",
        yaxis_title="Value",
        hovermode="x unified",
    )
    return fig


def create_asset_allocation_chart(dataframe):
    fig = px.pie(
        dataframe,
        names="asset_type",
        values="market_value",
        title="Allocation By Asset Type",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    return fig


def create_sector_chart(dataframe):
    fig = px.bar(
        dataframe,
        x="sector",
        y="market_value",
        color="market_value",
        color_continuous_scale="Tealgrn",
        title="Sector Exposure",
    )
    fig.update_layout(xaxis_title="Sector", yaxis_title="Market Value")
    return fig


def create_portfolio_breakdown_chart(dataframe):
    fig = px.bar(
        dataframe,
        x="name",
        y="current_value",
        color="gain_loss",
        color_continuous_scale="RdYlGn",
        text_auto=".2s",
        title="Portfolio Value Breakdown",
    )
    fig.update_layout(xaxis_title="Portfolio", yaxis_title="Current Value")
    return fig


def create_top_holdings_chart(dataframe):
    fig = px.bar(
        dataframe.sort_values("market_value"),
        x="market_value",
        y="asset_name",
        orientation="h",
        color="gain_loss_pct",
        color_continuous_scale="RdYlGn",
        title="Top Holdings By Value",
    )
    fig.update_layout(xaxis_title="Market Value", yaxis_title="Holding")
    return fig
