"""Minimal persistent SQLite datastore for GOA Creative Commerce.

Stores validated JSON documents for merchants, products, creative briefs,
compositions, demand gaps, quote enquiries and LLM call receipts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from goa.config import DATA_DIR
from goa.schemas import (
    Composition,
    CreativeBrief,
    DemandGap,
    GapSourceType,
    Merchant,
    Product,
    QuoteEnquiry,
)


class GoaStore:
    def __init__(self, db_path: str | Path = ":memory:", *, seed_from_data_dir: bool = True):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        if seed_from_data_dir:
            self.seed_catalogue_from_disk()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS merchants (
                    merchant_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    merchant_id TEXT NOT NULL,
                    part_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS briefs (
                    brief_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compositions (
                    composition_id TEXT PRIMARY KEY,
                    brief_id TEXT NOT NULL,
                    saved INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS demand_gaps (
                    gap_id TEXT PRIMARY KEY,
                    brief_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enquiries (
                    enquiry_id TEXT PRIMARY KEY,
                    composition_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def seed_catalogue_from_disk(self, data_dir: Path = DATA_DIR) -> None:
        merchants_file = data_dir / "merchants.json"
        products_file = data_dir / "products.json"
        if merchants_file.exists():
            raw_merchants = json.loads(merchants_file.read_text(encoding="utf-8"))
            for m in raw_merchants:
                self.upsert_merchant(Merchant.model_validate(m))
        if products_file.exists():
            raw_products = json.loads(products_file.read_text(encoding="utf-8"))
            for p in raw_products:
                self.upsert_product(Product.model_validate(p))

    # --- merchants & products
    def upsert_merchant(self, merchant: Merchant) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO merchants (merchant_id, payload) VALUES (?, ?)",
                (merchant.merchant_id, merchant.model_dump_json()),
            )

    def list_merchants(self) -> list[Merchant]:
        rows = self._conn.execute("SELECT payload FROM merchants ORDER BY merchant_id").fetchall()
        return [Merchant.model_validate_json(r["payload"]) for r in rows]

    def upsert_product(self, product: Product) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO products (product_id, merchant_id, part_type, payload) VALUES (?, ?, ?, ?)",
                (
                    product.product_id,
                    product.merchant_id,
                    product.part_type.value,
                    product.model_dump_json(),
                ),
            )

    def list_products(self) -> list[Product]:
        rows = self._conn.execute("SELECT payload FROM products ORDER BY product_id").fetchall()
        return [Product.model_validate_json(r["payload"]) for r in rows]

    def products_by_id(self) -> dict[str, Product]:
        return {p.product_id: p for p in self.list_products()}

    # --- briefs
    def save_brief(self, brief: CreativeBrief) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO briefs (brief_id, session_id, payload) VALUES (?, ?, ?)",
                (brief.brief_id, brief.session_id, brief.model_dump_json()),
            )

    def get_brief(self, brief_id: str) -> CreativeBrief | None:
        row = self._conn.execute("SELECT payload FROM briefs WHERE brief_id = ?", (brief_id,)).fetchone()
        return CreativeBrief.model_validate_json(row["payload"]) if row else None

    def count_briefs_by_source(self, source_value: str) -> int:
        rows = self._conn.execute("SELECT payload FROM briefs").fetchall()
        return sum(1 for r in rows if json.loads(r["payload"]).get("interpretation_source") == source_value)

    # --- compositions
    def save_composition(self, composition: Composition) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO compositions (composition_id, brief_id, saved, payload) VALUES (?, ?, ?, ?)",
                (
                    composition.composition_id,
                    composition.brief_id,
                    1 if composition.saved else 0,
                    composition.model_dump_json(),
                ),
            )

    def get_composition(self, composition_id: str) -> Composition | None:
        row = self._conn.execute(
            "SELECT payload FROM compositions WHERE composition_id = ?", (composition_id,)
        ).fetchone()
        return Composition.model_validate_json(row["payload"]) if row else None

    def list_compositions(self, *, saved_only: bool = False) -> list[Composition]:
        sql = "SELECT payload FROM compositions" + (" WHERE saved = 1" if saved_only else "")
        rows = self._conn.execute(sql).fetchall()
        return [Composition.model_validate_json(r["payload"]) for r in rows]

    # --- demand gaps
    def save_demand_gaps(self, gaps: Iterable[DemandGap]) -> None:
        with self._conn:
            for g in gaps:
                self._conn.execute(
                    "INSERT OR REPLACE INTO demand_gaps (gap_id, brief_id, source_type, payload) VALUES (?, ?, ?, ?)",
                    (g.gap_id, g.brief_id, g.source_type.value, g.model_dump_json()),
                )

    def list_demand_gaps(self, *, source_type: GapSourceType | None = None) -> list[DemandGap]:
        if source_type is None:
            rows = self._conn.execute("SELECT payload FROM demand_gaps ORDER BY gap_id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM demand_gaps WHERE source_type = ? ORDER BY gap_id",
                (source_type.value,),
            ).fetchall()
        return [DemandGap.model_validate_json(r["payload"]) for r in rows]

    # --- quote enquiries
    def save_enquiry(self, enquiry: QuoteEnquiry) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO enquiries (enquiry_id, composition_id, merchant_id, payload) VALUES (?, ?, ?, ?)",
                (
                    enquiry.enquiry_id,
                    enquiry.composition_id,
                    enquiry.merchant_id,
                    enquiry.model_dump_json(),
                ),
            )

    def list_enquiries(self, *, merchant_id: str | None = None) -> list[QuoteEnquiry]:
        if merchant_id is None:
            rows = self._conn.execute("SELECT payload FROM enquiries ORDER BY enquiry_id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM enquiries WHERE merchant_id = ? ORDER BY enquiry_id",
                (merchant_id,),
            ).fetchall()
        return [QuoteEnquiry.model_validate_json(r["payload"]) for r in rows]
