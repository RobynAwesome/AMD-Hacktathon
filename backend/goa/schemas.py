"""Canonical, versioned public contracts for GOA Creative Commerce.

Fixed invariants (Y) encoded here:
- All money is integer ZAR cents (StrictInt; floats are rejected).
- Stock is variant-specific.
- Verification checks are tri-state (PASS / FAIL / UNKNOWN); UNKNOWN never passes.
- Customer-visible part outcomes are AVAILABLE or NOT_ON_OFFER_YET. A part that has
  not yet been verified is PENDING_VERIFICATION and is never shown as available.
- Quote enquiries are demo-only, require explicit customer authorization and are not
  payments, orders or reservations.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

SCHEMA_VERSION = "1.0.0"

ID_PATTERN = r"^[a-z]+_[A-Za-z0-9_-]+$"


class _Contract(BaseModel):
    """Base for every public contract: strict, versioned, no unknown fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION


class _Part(BaseModel):
    """Base for nested value objects (not independently versioned)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- enums


class PartType(StrEnum):
    DRESS_OR_SUIT = "DRESS_OR_SUIT"
    SHOES = "SHOES"
    OUTER_LAYER = "OUTER_LAYER"
    ACCESSORY = "ACCESSORY"


class Formality(StrEnum):
    CASUAL = "CASUAL"
    SMART_CASUAL = "SMART_CASUAL"
    SEMI_FORMAL = "SEMI_FORMAL"
    FORMAL = "FORMAL"


class CatalogueStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class ProductSourceType(StrEnum):
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"


class CheckState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class PartStatus(StrEnum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    AVAILABLE = "AVAILABLE"
    NOT_ON_OFFER_YET = "NOT_ON_OFFER_YET"


class PartOrigin(StrEnum):
    EXPLICIT = "EXPLICIT"  # customer named this part
    INFERRED_DEFAULT = "INFERRED_DEFAULT"  # added by decomposition of "outfit"
    CUSTOMER_ADDED = "CUSTOMER_ADDED"  # added during remix


class MatchMethod(StrEnum):
    KEYWORD_BASELINE = "KEYWORD_BASELINE"
    TAG_OVERLAP = "TAG_OVERLAP"
    EMBEDDING = "EMBEDDING"


class InterpretationSource(StrEnum):
    GEMMA_AMD_TOKEN_FACTORY = "GEMMA_AMD_TOKEN_FACTORY"
    RULE_BASED_FALLBACK = "RULE_BASED_FALLBACK"
    SCRIPTED_EVALUATION = "SCRIPTED_EVALUATION"


class UnmetReason(StrEnum):
    NO_MATCHING_PRODUCT = "NO_MATCHING_PRODUCT"
    SIZE_UNAVAILABLE = "SIZE_UNAVAILABLE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    DELIVERY_TOO_LATE = "DELIVERY_TOO_LATE"
    PRICE_UNKNOWN = "PRICE_UNKNOWN"
    OVER_BUDGET = "OVER_BUDGET"
    BUDGET_EXHAUSTED_BY_OTHER_PARTS = "BUDGET_EXHAUSTED_BY_OTHER_PARTS"
    # Customer-input reasons: the part fails closed, but these are NOT demand gaps.
    CUSTOMER_SIZE_REQUIRED = "CUSTOMER_SIZE_REQUIRED"
    EVENT_DATE_REQUIRED = "EVENT_DATE_REQUIRED"
    BUDGET_REQUIRED = "BUDGET_REQUIRED"


CUSTOMER_INPUT_REASONS = frozenset(
    {UnmetReason.CUSTOMER_SIZE_REQUIRED, UnmetReason.EVENT_DATE_REQUIRED, UnmetReason.BUDGET_REQUIRED}
)


class CompositionStatus(StrEnum):
    VERIFIED_COMPLETE = "VERIFIED_COMPLETE"
    VERIFIED_PARTIAL = "VERIFIED_PARTIAL"
    EMPTY = "EMPTY"
    INVALID = "INVALID"


class SelectedBy(StrEnum):
    CUSTOMER = "CUSTOMER"
    SYSTEM_SUGGESTION = "SYSTEM_SUGGESTION"


class GapSourceType(StrEnum):
    SCRIPTED_EVALUATION = "SCRIPTED_EVALUATION"
    DEMO_SESSION = "DEMO_SESSION"


class EnquiryStatus(StrEnum):
    SENT_TO_DEMO_INBOX = "SENT_TO_DEMO_INBOX"


# ------------------------------------------------------------------ A. Merchant


class Merchant(_Contract):
    merchant_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str
    is_fictional: bool
    location: str
    catalogue_status: CatalogueStatus
    created_at: datetime


# --------------------------------------------------- B. Product and ProductVariant


class ProductVariant(_Part):
    variant_id: str = Field(pattern=ID_PATTERN)
    size: str = Field(min_length=1)
    stock_quantity: StrictInt = Field(ge=0)


class Product(_Contract):
    product_id: str = Field(pattern=ID_PATTERN)
    merchant_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str
    part_type: PartType
    colour: str
    material: str
    style_tags: list[str] = Field(default_factory=list)
    formality: Formality
    image_url: str
    image_licence: str
    image_attribution: str = Field(description="Source attribution for the image.")
    # Nullable on purpose: a catalogue entry may genuinely lack a price ("price on
    # request"). Verification then reports price_known = FAIL; it never guesses.
    price_cents: StrictInt | None = Field(default=None, ge=1)
    currency: str = "ZAR"
    delivery_lead_days: StrictInt | None = Field(default=None, ge=0)
    active: bool = True
    source_type: ProductSourceType
    variants: list[ProductVariant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_variant_ids(self) -> "Product":
        ids = [v.variant_id for v in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("variant_id values must be unique within a product")
        return self


# ---------------------------------------------------------- D. RequestedPart


class DesiredAttributes(_Part):
    colours: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    formality: Formality | None = None
    garment_keywords: list[str] = Field(
        default_factory=list, description="e.g. 'jacket', 'jumpsuit', 'sandals'."
    )
    free_text: str | None = None


class MandatoryConstraints(_Part):
    size: str | None = Field(default=None, description="None means unknown; never guessed.")
    must_arrive_by: date | None = None
    max_price_cents: StrictInt | None = Field(default=None, ge=1)
    required_colours: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    required_garment_keywords: list[str] = Field(default_factory=list)


class RequestedPart(_Contract):
    part_id: str = Field(pattern=ID_PATTERN)
    brief_id: str = Field(pattern=ID_PATTERN)
    part_type: PartType
    origin: PartOrigin = PartOrigin.EXPLICIT
    desired_attributes: DesiredAttributes = Field(default_factory=DesiredAttributes)
    mandatory_constraints: MandatoryConstraints = Field(default_factory=MandatoryConstraints)
    optional_preferences: list[str] = Field(default_factory=list)
    status: PartStatus = PartStatus.PENDING_VERIFICATION


# ---------------------------------------------------------- C. CreativeBrief


class CreativeBrief(_Contract):
    brief_id: str = Field(pattern=ID_PATTERN)
    session_id: str = Field(pattern=ID_PATTERN)
    raw_prompt: str = Field(min_length=1)
    occasion: str | None = None
    event_date: date | None = None
    location: str | None = None
    budget_cents: StrictInt | None = Field(default=None, ge=1)
    preferred_colours: list[str] = Field(default_factory=list)
    formality: Formality | None = None
    style_preferences: list[str] = Field(default_factory=list)
    sustainability_or_reuse_preferences: list[str] = Field(default_factory=list)
    sizes: dict[PartType, str] = Field(
        default_factory=dict, description="Only sizes the customer actually supplied."
    )
    constraints: list[str] = Field(default_factory=list)
    requested_parts: list[RequestedPart] = Field(default_factory=list)
    uncertainties: list[str] = Field(
        default_factory=list, description="Explicitly preserved unknowns and inferences."
    )
    interpretation_source: InterpretationSource
    created_at: datetime

    @model_validator(mode="after")
    def _parts_reference_brief(self) -> "CreativeBrief":
        for part in self.requested_parts:
            if part.brief_id != self.brief_id:
                raise ValueError(f"requested part {part.part_id} references another brief")
        ids = [p.part_id for p in self.requested_parts]
        if len(ids) != len(set(ids)):
            raise ValueError("part_id values must be unique within a brief")
        return self


# ------------------------------------------- E. MatchCandidate / VerificationResult


class CheckResult(_Part):
    state: CheckState
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(_Contract):
    exists_in_catalogue: CheckResult
    correct_part_type: CheckResult
    size_available: CheckResult
    stock_available: CheckResult
    delivery_feasible: CheckResult
    price_known: CheckResult
    budget_feasible: CheckResult
    overall: CheckState
    engine_version: str
    evaluated_on: date = Field(description="Reference date used for delivery calculations.")

    CHECK_NAMES: ClassVar[tuple[str, ...]] = (
        "exists_in_catalogue",
        "correct_part_type",
        "size_available",
        "stock_available",
        "delivery_feasible",
        "price_known",
        "budget_feasible",
    )

    @model_validator(mode="after")
    def _overall_is_consistent(self) -> "VerificationResult":
        states = [getattr(self, n).state for n in self.CHECK_NAMES]
        if CheckState.FAIL in states:
            expected = CheckState.FAIL
        elif CheckState.UNKNOWN in states:
            expected = CheckState.UNKNOWN
        else:
            expected = CheckState.PASS
        if self.overall != expected:
            raise ValueError(f"overall must be {expected} given individual checks")
        return self


class MatchCandidate(_Contract):
    part_id: str = Field(pattern=ID_PATTERN)
    product_id: str = Field(pattern=ID_PATTERN)
    variant_id: str | None = None
    merchant_id: str | None = None
    semantic_score: float = Field(ge=0.0, le=1.0)
    match_method: MatchMethod
    matched_attributes: list[str] = Field(default_factory=list)
    verification_result: VerificationResult
    rejection_reasons: list[str] = Field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.verification_result.overall == CheckState.PASS and not self.rejection_reasons


# ------------------------------------------------------------ F. Composition


class SelectedPart(_Part):
    part_id: str = Field(pattern=ID_PATTERN)
    part_type: PartType
    product_id: str = Field(pattern=ID_PATTERN)
    variant_id: str = Field(pattern=ID_PATTERN)
    merchant_id: str = Field(pattern=ID_PATTERN)
    product_name: str
    size: str
    unit_price_cents: StrictInt = Field(ge=1)
    selected_by: SelectedBy
    semantic_score: float = Field(ge=0.0, le=1.0)
    matched_attributes: list[str] = Field(default_factory=list)
    verification_result: VerificationResult

    @model_validator(mode="after")
    def _must_be_verified(self) -> "SelectedPart":
        if self.verification_result.overall != CheckState.PASS:
            raise ValueError("a selected (available) part must have passed verification")
        return self


class UnmetPart(_Part):
    part_id: str = Field(pattern=ID_PATTERN)
    part_type: PartType
    desired_attributes: DesiredAttributes
    reasons: list[UnmetReason] = Field(min_length=1)
    explanation: str


class Composition(_Contract):
    composition_id: str = Field(pattern=ID_PATTERN)
    brief_id: str = Field(pattern=ID_PATTERN)
    parent_composition_id: str | None = None
    selected_parts: list[SelectedPart] = Field(default_factory=list)
    unmet_parts: list[UnmetPart] = Field(default_factory=list)
    total_price_cents: StrictInt = Field(ge=0)
    budget_cents: StrictInt | None = Field(default=None, ge=1)
    validation_status: CompositionStatus
    merchant_scope: list[str] = Field(default_factory=list)
    saved: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def _integrity(self) -> "Composition":
        total = sum(p.unit_price_cents for p in self.selected_parts)
        if total != self.total_price_cents:
            raise ValueError("total_price_cents must equal the sum of selected part prices")
        sel = {p.part_id for p in self.selected_parts}
        unmet = {p.part_id for p in self.unmet_parts}
        if sel & unmet:
            raise ValueError("a part cannot be both selected and unmet")
        if self.validation_status == CompositionStatus.VERIFIED_COMPLETE and self.unmet_parts:
            raise ValueError("a composition with unmet parts cannot be VERIFIED_COMPLETE")
        if (
            self.validation_status in (CompositionStatus.VERIFIED_COMPLETE, CompositionStatus.VERIFIED_PARTIAL)
            and self.budget_cents is not None
            and self.total_price_cents > self.budget_cents
        ):
            raise ValueError("a verified composition cannot exceed the customer's budget")
        if sorted(set(p.merchant_id for p in self.selected_parts)) != sorted(self.merchant_scope):
            raise ValueError("merchant_scope must list exactly the merchants of selected parts")
        return self


# -------------------------------------------------------------- G. DemandGap


class DemandGap(_Contract):
    gap_id: str = Field(pattern=ID_PATTERN)
    brief_id: str = Field(pattern=ID_PATTERN)
    part_type: PartType
    desired_attributes: DesiredAttributes
    reason: UnmetReason
    merchant_scope: list[str] = Field(
        description="Merchants whose catalogues were searched when the gap was recorded."
    )
    source_type: GapSourceType
    created_at: datetime
    disclaimer: Literal[
        "Recorded from GOA demo/scripted briefs. Not a measure of live market demand."
    ] = "Recorded from GOA demo/scripted briefs. Not a measure of live market demand."

    @model_validator(mode="after")
    def _not_customer_input(self) -> "DemandGap":
        if self.reason in CUSTOMER_INPUT_REASONS:
            raise ValueError("missing customer input is not a demand gap")
        return self


# ----------------------------------------------------------- H. QuoteEnquiry


class LineItem(_Part):
    part_id: str = Field(pattern=ID_PATTERN)
    product_id: str = Field(pattern=ID_PATTERN)
    variant_id: str = Field(pattern=ID_PATTERN)
    merchant_id: str = Field(pattern=ID_PATTERN)
    product_name: str
    size: str
    quantity: StrictInt = Field(default=1, ge=1)
    unit_price_cents: StrictInt = Field(ge=1)


class CustomerRequirements(_Part):
    sizes: dict[PartType, str] = Field(default_factory=dict)
    notes: str | None = None
    location: str | None = None


class ItemRevalidation(_Part):
    part_id: str
    product_id: str
    variant_id: str
    belongs_to_addressed_merchant: bool
    verification_result: VerificationResult


class ValidationReceipt(_Part):
    revalidated_at: datetime
    engine_version: str
    items: list[ItemRevalidation]
    all_items_pass: bool
    excluded_parts_other_merchants: list[str] = Field(
        default_factory=list,
        description="Selected parts that belong to other merchants and were NOT sent here.",
    )


class QuoteEnquiry(_Contract):
    enquiry_id: str = Field(pattern=ID_PATTERN)
    composition_id: str = Field(pattern=ID_PATTERN)
    merchant_id: str = Field(pattern=ID_PATTERN)
    customer_requirements: CustomerRequirements
    line_items: list[LineItem] = Field(min_length=1)
    event_date: date
    known_total_cents: StrictInt = Field(ge=1)
    customer_authorized: Literal[True]
    status: EnquiryStatus
    created_at: datetime
    validation_receipt: ValidationReceipt
    is_demo: Literal[True] = True
    disclaimer: Literal[
        "DEMO quote enquiry to a fictional merchant. Not a payment, order or confirmed reservation."
    ] = "DEMO quote enquiry to a fictional merchant. Not a payment, order or confirmed reservation."

    @model_validator(mode="after")
    def _integrity(self) -> "QuoteEnquiry":
        for item in self.line_items:
            if item.merchant_id != self.merchant_id:
                raise ValueError(f"line item {item.product_id} belongs to another merchant")
        if sum(i.unit_price_cents * i.quantity for i in self.line_items) != self.known_total_cents:
            raise ValueError("known_total_cents must equal the sum of line items")
        if not self.validation_receipt.all_items_pass:
            raise ValueError("an enquiry can only be sent after successful revalidation")
        return self


PUBLIC_CONTRACTS: dict[str, type[BaseModel]] = {
    "merchant": Merchant,
    "product": Product,
    "creative_brief": CreativeBrief,
    "requested_part": RequestedPart,
    "verification_result": VerificationResult,
    "match_candidate": MatchCandidate,
    "composition": Composition,
    "demand_gap": DemandGap,
    "quote_enquiry": QuoteEnquiry,
}
