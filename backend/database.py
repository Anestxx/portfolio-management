from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import json
import os
import sqlite3

import pandas as pd

from backend.config import AppConfig, get_config


ASSET_TYPES = [
    "Stock",
    "ETF",
    "Bond",
    "Mutual Fund",
    "Crypto",
    "Cash Equivalent",
    "Commodity",
    "Real Estate",
]
RISK_PROFILES = ["Conservative", "Moderate", "Aggressive"]
CURRENCIES = ["USD", "INR", "EUR", "GBP"]


class PortfolioRepository:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or get_config()
        self.initialize_database()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.config.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _execute(self, query: str, params: list | tuple | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(query, params or [])
            connection.commit()
            return cursor.lastrowid

    def _execute_many(self, query: str, values: list[tuple]) -> None:
        with self.connect() as connection:
            connection.executemany(query, values)
            connection.commit()

    def _read_sql(self, query: str, params: list | None = None) -> pd.DataFrame:
        with self.connect() as connection:
            dataframe = pd.read_sql_query(query, connection, params=params or [])
        for column in ["created_at", "updated_at", "last_login", "purchase_date"]:
            if column in dataframe.columns:
                dataframe[column] = pd.to_datetime(dataframe[column], errors="coerce")
        return dataframe

    def initialize_database(self) -> None:
        schema_sql = self.config.schema_path.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema_sql)
        self.ensure_demo_account()

    def _hash_password(self, password: str) -> str:
        salt = os.urandom(16).hex()
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
        return f"{salt}${digest}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            salt, digest = stored_hash.split("$", 1)
        except ValueError:
            return False
        comparison = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()
        return hmac.compare_digest(comparison, digest)

    def _create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str,
        job_title: str = "",
        company: str = "",
        bio: str = "",
        risk_appetite: str = "Moderate",
        preferred_currency: str = "USD",
        is_demo: int = 0,
    ) -> int:
        return self._execute(
            """
            INSERT INTO users (
                username, email, password_hash, full_name, job_title,
                company, bio, risk_appetite, preferred_currency, is_demo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                username,
                email,
                self._hash_password(password),
                full_name,
                job_title,
                company,
                bio,
                risk_appetite,
                preferred_currency,
                is_demo,
            ],
        )

    def ensure_demo_account(self) -> None:
        existing = self._read_sql("SELECT id FROM users WHERE username = 'demo' LIMIT 1")
        if not existing.empty:
            return

        demo_user_id = self._create_user(
            username="demo",
            email="demo@portfolio.local",
            password="demo123",
            full_name="Demo Investor",
            job_title="Individual Investor",
            company="Personal Wealth Lab",
            bio="This demo profile includes sample portfolios and holdings so new users can see how the app works before editing their own data.",
            risk_appetite="Moderate",
            preferred_currency="USD",
            is_demo=1,
        )
        self.seed_sample_portfolio_for_user(demo_user_id)

    def register_user(self, username: str, email: str, password: str, full_name: str) -> tuple[bool, str, dict | None]:
        try:
            user_id = self._create_user(username, email, password, full_name)
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "users.username" in message:
                return False, "Username already exists.", None
            if "users.email" in message:
                return False, "Email already exists.", None
            return False, "Unable to create account.", None

        self.seed_sample_portfolio_for_user(user_id)
        return True, "Account created successfully.", self.get_user_by_id(user_id)

    def authenticate_user(self, identifier: str, password: str) -> tuple[bool, str, dict | None]:
        users = self._read_sql(
            """
            SELECT *
            FROM users
            WHERE lower(username) = lower(?) OR lower(email) = lower(?)
            LIMIT 1
            """,
            [identifier, identifier],
        )
        if users.empty:
            return False, "Invalid username/email or password.", None

        user = users.iloc[0].to_dict()
        if not self._verify_password(password, str(user["password_hash"])):
            return False, "Invalid username/email or password.", None

        self._execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", [int(user["id"])])
        return True, "Login successful.", self.get_user_by_id(int(user["id"]))

    def get_user_by_id(self, user_id: int) -> dict | None:
        users = self._read_sql("SELECT * FROM users WHERE id = ? LIMIT 1", [user_id])
        if users.empty:
            return None
        user = users.iloc[0].to_dict()
        for column in ["created_at", "last_login"]:
            if pd.notna(user.get(column)):
                user[column] = pd.Timestamp(user[column])
        return user

    def update_user_profile(
        self,
        user_id: int,
        full_name: str,
        email: str,
        job_title: str,
        company: str,
        bio: str,
        risk_appetite: str,
        preferred_currency: str,
    ) -> tuple[bool, str]:
        try:
            self._execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, job_title = ?, company = ?, bio = ?,
                    risk_appetite = ?, preferred_currency = ?
                WHERE id = ?
                """,
                [full_name, email, job_title, company, bio, risk_appetite, preferred_currency, user_id],
            )
        except sqlite3.IntegrityError:
            return False, "That email is already being used by another account."
        return True, "Profile updated successfully."

    def seed_sample_portfolio_for_user(self, user_id: int) -> None:
        existing = self._read_sql("SELECT id FROM portfolios WHERE user_id = ? LIMIT 1", [user_id])
        if not existing.empty:
            return

        sample_payload = json.loads(self.config.sample_data_path.read_text(encoding="utf-8"))
        portfolio_id_map: dict[str, int] = {}

        for portfolio in sample_payload["portfolios"]:
            portfolio_id = self.create_portfolio(
                user_id=user_id,
                name=portfolio["name"],
                objective=portfolio["objective"],
                risk_profile=portfolio["risk_profile"],
                target_value=float(portfolio["target_value"]),
                cash_balance=float(portfolio["cash_balance"]),
                notes=portfolio.get("notes", ""),
            )
            portfolio_id_map[portfolio["name"]] = portfolio_id

        for holding in sample_payload["holdings"]:
            self.create_holding(
                user_id=user_id,
                portfolio_id=portfolio_id_map[holding["portfolio_name"]],
                asset_name=holding["asset_name"],
                ticker=holding.get("ticker", ""),
                asset_type=holding["asset_type"],
                sector=holding.get("sector", ""),
                units=float(holding["units"]),
                average_cost=float(holding["average_cost"]),
                current_price=float(holding["current_price"]),
                purchase_date=holding.get("purchase_date", ""),
                notes=holding.get("notes", ""),
            )

    def get_user_portfolios(self, user_id: int) -> pd.DataFrame:
        portfolios = self._read_sql(
            """
            SELECT
                p.*,
                COALESCE(SUM(h.units * h.current_price), 0) AS holdings_value,
                COALESCE(SUM(h.units * h.average_cost), 0) AS invested_value,
                COALESCE(SUM((h.current_price - h.average_cost) * h.units), 0) AS gain_loss,
                COALESCE(COUNT(h.id), 0) AS holdings_count
            FROM portfolios p
            LEFT JOIN holdings h ON h.portfolio_id = p.id
            WHERE p.user_id = ?
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.created_at DESC
            """,
            [user_id],
        )
        if portfolios.empty:
            return portfolios

        portfolios["current_value"] = portfolios["holdings_value"] + portfolios["cash_balance"]
        portfolios["target_progress"] = portfolios.apply(
            lambda row: (row["current_value"] / row["target_value"] * 100) if row["target_value"] else 0,
            axis=1,
        )
        return portfolios

    def create_portfolio(
        self,
        user_id: int,
        name: str,
        objective: str,
        risk_profile: str,
        target_value: float,
        cash_balance: float,
        notes: str,
    ) -> int:
        return self._execute(
            """
            INSERT INTO portfolios (
                user_id, name, objective, risk_profile, target_value, cash_balance, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [user_id, name, objective, risk_profile, target_value, cash_balance, notes],
        )

    def update_portfolio(
        self,
        portfolio_id: int,
        user_id: int,
        name: str,
        objective: str,
        risk_profile: str,
        target_value: float,
        cash_balance: float,
        notes: str,
    ) -> None:
        self._execute(
            """
            UPDATE portfolios
            SET name = ?, objective = ?, risk_profile = ?, target_value = ?, cash_balance = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            [name, objective, risk_profile, target_value, cash_balance, notes, portfolio_id, user_id],
        )

    def delete_portfolio(self, portfolio_id: int, user_id: int) -> None:
        self._execute("DELETE FROM portfolios WHERE id = ? AND user_id = ?", [portfolio_id, user_id])

    def get_user_holdings(self, user_id: int, portfolio_id: int | None = None) -> pd.DataFrame:
        query = """
            SELECT
                h.*,
                p.name AS portfolio_name,
                p.user_id,
                (h.units * h.average_cost) AS invested_value,
                (h.units * h.current_price) AS market_value,
                ((h.current_price - h.average_cost) * h.units) AS gain_loss
            FROM holdings h
            INNER JOIN portfolios p ON p.id = h.portfolio_id
            WHERE p.user_id = ?
        """
        params: list = [user_id]
        if portfolio_id is not None:
            query += " AND p.id = ?"
            params.append(portfolio_id)
        query += " ORDER BY h.updated_at DESC, h.created_at DESC"
        holdings = self._read_sql(query, params)
        if holdings.empty:
            return holdings
        holdings["gain_loss_pct"] = holdings.apply(
            lambda row: (row["gain_loss"] / row["invested_value"] * 100) if row["invested_value"] else 0,
            axis=1,
        )
        return holdings

    def create_holding(
        self,
        user_id: int,
        portfolio_id: int,
        asset_name: str,
        ticker: str,
        asset_type: str,
        sector: str,
        units: float,
        average_cost: float,
        current_price: float,
        purchase_date: str,
        notes: str,
    ) -> int:
        owner_check = self._read_sql("SELECT id FROM portfolios WHERE id = ? AND user_id = ?", [portfolio_id, user_id])
        if owner_check.empty:
            raise ValueError("Portfolio does not belong to this user.")
        return self._execute(
            """
            INSERT INTO holdings (
                portfolio_id, asset_name, ticker, asset_type, sector, units,
                average_cost, current_price, purchase_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [portfolio_id, asset_name, ticker, asset_type, sector, units, average_cost, current_price, purchase_date, notes],
        )

    def update_holding(
        self,
        holding_id: int,
        user_id: int,
        portfolio_id: int,
        asset_name: str,
        ticker: str,
        asset_type: str,
        sector: str,
        units: float,
        average_cost: float,
        current_price: float,
        purchase_date: str,
        notes: str,
    ) -> None:
        owner_check = self._read_sql("SELECT id FROM portfolios WHERE id = ? AND user_id = ?", [portfolio_id, user_id])
        if owner_check.empty:
            raise ValueError("Portfolio does not belong to this user.")
        self._execute(
            """
            UPDATE holdings
            SET portfolio_id = ?, asset_name = ?, ticker = ?, asset_type = ?, sector = ?, units = ?,
                average_cost = ?, current_price = ?, purchase_date = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND portfolio_id IN (SELECT id FROM portfolios WHERE user_id = ?)
            """,
            [
                portfolio_id,
                asset_name,
                ticker,
                asset_type,
                sector,
                units,
                average_cost,
                current_price,
                purchase_date,
                notes,
                holding_id,
                user_id,
            ],
        )

    def delete_holding(self, holding_id: int, user_id: int) -> None:
        self._execute(
            """
            DELETE FROM holdings
            WHERE id = ? AND portfolio_id IN (SELECT id FROM portfolios WHERE user_id = ?)
            """,
            [holding_id, user_id],
        )

    def _portfolio_context(self, user_id: int, portfolio_id: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        portfolios = self.get_user_portfolios(user_id)
        if portfolio_id is not None and not portfolios.empty:
            portfolios = portfolios[portfolios["id"] == portfolio_id]
        holdings = self.get_user_holdings(user_id, portfolio_id)
        return portfolios, holdings

    def get_dashboard_metrics(self, user_id: int, portfolio_id: int | None = None) -> dict[str, float]:
        portfolios, holdings = self._portfolio_context(user_id, portfolio_id)
        total_cash = float(portfolios["cash_balance"].sum()) if not portfolios.empty else 0.0
        invested_value = float(holdings["invested_value"].sum()) if not holdings.empty else 0.0
        holdings_value = float(holdings["market_value"].sum()) if not holdings.empty else 0.0
        current_value = holdings_value + total_cash
        gain_loss = holdings_value - invested_value
        target_total = float(portfolios["target_value"].sum()) if not portfolios.empty else 0.0
        return {
            "current_value": current_value,
            "invested_value": invested_value,
            "gain_loss": gain_loss,
            "cash_balance": total_cash,
            "holdings_count": int(len(holdings)),
            "portfolios_count": int(len(portfolios)),
            "target_progress": (current_value / target_total * 100) if target_total else 0.0,
        }

    def get_asset_allocation(self, user_id: int, portfolio_id: int | None = None) -> pd.DataFrame:
        _, holdings = self._portfolio_context(user_id, portfolio_id)
        if holdings.empty:
            return pd.DataFrame(columns=["asset_type", "market_value"])
        return (
            holdings.groupby("asset_type", as_index=False)
            .agg(market_value=("market_value", "sum"))
            .sort_values("market_value", ascending=False)
        )

    def get_sector_allocation(self, user_id: int, portfolio_id: int | None = None) -> pd.DataFrame:
        _, holdings = self._portfolio_context(user_id, portfolio_id)
        if holdings.empty:
            return pd.DataFrame(columns=["sector", "market_value"])
        sector_df = holdings.copy()
        sector_df["sector"] = sector_df["sector"].replace("", "Unspecified")
        return (
            sector_df.groupby("sector", as_index=False)
            .agg(market_value=("market_value", "sum"))
            .sort_values("market_value", ascending=False)
        )

    def get_portfolio_breakdown(self, user_id: int) -> pd.DataFrame:
        portfolios = self.get_user_portfolios(user_id)
        if portfolios.empty:
            return pd.DataFrame(columns=["name", "current_value", "gain_loss", "target_progress"])
        return portfolios[["name", "current_value", "gain_loss", "target_progress"]].sort_values(
            "current_value", ascending=False
        )

    def get_top_holdings(self, user_id: int, portfolio_id: int | None = None, top_n: int = 10) -> pd.DataFrame:
        _, holdings = self._portfolio_context(user_id, portfolio_id)
        if holdings.empty:
            return pd.DataFrame(
                columns=["asset_name", "ticker", "portfolio_name", "market_value", "gain_loss", "gain_loss_pct"]
            )
        return holdings.sort_values("market_value", ascending=False).head(top_n)[
            ["asset_name", "ticker", "portfolio_name", "market_value", "gain_loss", "gain_loss_pct"]
        ]

    def get_performance_timeline(self, user_id: int, portfolio_id: int | None = None) -> pd.DataFrame:
        _, holdings = self._portfolio_context(user_id, portfolio_id)
        if holdings.empty:
            return pd.DataFrame(columns=["purchase_date", "cumulative_invested", "cumulative_market"])
        timeline = holdings.copy()
        timeline["purchase_date"] = pd.to_datetime(timeline["purchase_date"], errors="coerce")
        timeline = timeline.dropna(subset=["purchase_date"]).sort_values("purchase_date")
        if timeline.empty:
            return pd.DataFrame(columns=["purchase_date", "cumulative_invested", "cumulative_market"])
        timeline["cumulative_invested"] = timeline["invested_value"].cumsum()
        timeline["cumulative_market"] = timeline["market_value"].cumsum()
        return timeline[["purchase_date", "cumulative_invested", "cumulative_market"]]

    def get_recent_activity(self, user_id: int, limit: int = 8) -> pd.DataFrame:
        portfolios = self.get_user_portfolios(user_id)
        holdings = self.get_user_holdings(user_id)

        frames = []
        if not portfolios.empty:
            frames.append(
                pd.DataFrame(
                    {
                        "event_time": portfolios["updated_at"].fillna(portfolios["created_at"]),
                        "event_type": "Portfolio",
                        "title": portfolios["name"],
                        "details": portfolios["objective"].replace("", "Portfolio updated"),
                    }
                )
            )
        if not holdings.empty:
            frames.append(
                pd.DataFrame(
                    {
                        "event_time": holdings["updated_at"].fillna(holdings["created_at"]),
                        "event_type": "Holding",
                        "title": holdings["asset_name"],
                        "details": holdings["portfolio_name"],
                    }
                )
            )
        if not frames:
            return pd.DataFrame(columns=["event_time", "event_type", "title", "details"])
        activity = pd.concat(frames, ignore_index=True).dropna(subset=["event_time"])
        return activity.sort_values("event_time", ascending=False).head(limit)

    def get_storage_summary(self) -> dict[str, str | int | float]:
        users = self._read_sql("SELECT COUNT(*) AS count FROM users")
        portfolios = self._read_sql("SELECT COUNT(*) AS count FROM portfolios")
        holdings = self._read_sql("SELECT COUNT(*) AS count FROM holdings")
        size_bytes = self.config.database_path.stat().st_size if self.config.database_path.exists() else 0
        return {
            "database_path": str(self.config.database_path),
            "sample_data_path": str(self.config.sample_data_path),
            "users_count": int(users.loc[0, "count"]),
            "portfolios_count": int(portfolios.loc[0, "count"]),
            "holdings_count": int(holdings.loc[0, "count"]),
            "size_mb": round(size_bytes / (1024 * 1024), 2),
        }
