from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class SystemRole(str, Enum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


class PresenceStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"


class QueueKey(str, Enum):
    NEW = "new"
    NEW_INCOMING = "new_incoming"
    MINE = "mine"
    WAITING_ME = "waiting_me"
    WAITING_CUSTOMER = "waiting_customer"
    URGENT = "urgent"
    ESCALATED = "escalated"
    SLA_RISK = "sla_risk"
    FAILED_DELIVERY = "failed_delivery"
    URGENT_ESCALATED = "urgent_escalated"
    ARCHIVE = "archive"


class HotTaskBucketKey(str, Enum):
    NEEDS_REPLY_NOW = "needs_reply_now"
    NEW_BUSINESS = "new_business"
    SLA_AT_RISK = "sla_at_risk"
    URGENT_ESCALATED = "urgent_escalated"
    FAILED_DELIVERY = "failed_delivery"


@dataclass(slots=True)
class ManagerActor:
    actor_id: UUID
    telegram_user_id: int
    display_name: str
    role: SystemRole


@dataclass(slots=True)
class QueueItem:
    case_id: UUID
    case_display_number: int
    customer_label: str | None
    operational_status: str
    waiting_state: str
    assigned_manager_actor_id: UUID | None
    priority: str
    escalation_level: str
    last_customer_message_at: datetime | None
    sla_due_at: datetime | None = None
    is_archived: bool = False


@dataclass(slots=True)
class HotTaskItem:
    case_id: UUID
    case_display_number: int
    customer_label: str | None
    reason: str
    priority: str
    escalation_level: str
    waiting_state: str
    sla_due_at: datetime | None
    last_customer_message_at: datetime | None
    last_event_at: datetime | None
    linked_order_display_number: int | None = None


@dataclass(slots=True)
class HotTaskBucket:
    key: HotTaskBucketKey
    title: str
    queue_key: str
    items: list[HotTaskItem] = field(default_factory=list)


@dataclass(slots=True)
class ThreadEntry:
    direction: str
    body: str
    created_at: datetime
    delivery_status: str = "not_applicable"
    author_side: str | None = None


@dataclass(slots=True)
class InternalNote:
    body: str
    author_label: str
    created_at: datetime


@dataclass(slots=True)
class DeliverySnapshot:
    status: str
    attempted_at: datetime | None
    error_message: str | None = None


@dataclass(slots=True)
class ManagerItemDetail:
    title: str | None = None
    brand: str | None = None
    sku_code: str | None = None
    selling_unit: str | None = None
    min_order: str | None = None
    increment: str | None = None
    packaging_context: str | None = None
    shelf_life: str | None = None
    origin: str | None = None
    weight: str | None = None
    piece_weight: str | None = None
    description: str | None = None
    is_active: bool | None = None
    in_draft: bool | None = None


@dataclass(slots=True)
class CustomerCard:
    label: str | None
    actor_id: str | None = None
    telegram_chat_id: int | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    phone_number: str | None = None


@dataclass(slots=True)
class NotificationEvent:
    event_key: str
    kind: str
    case_id: UUID
    case_display_number: int
    assigned_manager_actor_id: UUID | None
    assigned_manager_presence: PresenceStatus | None = None
    summary: str | None = None


@dataclass(slots=True)
class CaseDetail:
    case_id: UUID
    case_display_number: int
    commercial_status: str
    operational_status: str
    waiting_state: str
    priority: str
    escalation_level: str
    assignment_label: str
    sla_due_at: datetime | None = None
    linked_order_display_number: int | None = None
    linked_order_status: str | None = None
    linked_order_summary: str | None = None
    linked_order_pdf_url: str | None = None
    linked_order_document_label: str | None = None
    linked_quote_display_number: int | None = None
    customer_label: str | None = None
    customer_card: CustomerCard | None = None
    thread_entries: list[ThreadEntry] = field(default_factory=list)
    internal_notes: list[InternalNote] = field(default_factory=list)
    last_delivery: DeliverySnapshot | None = None
    item_detail: ManagerItemDetail | None = None


@dataclass(slots=True)
class QueueFilters:
    assignment_scope: str = "any"  # any | mine | unassigned
    waiting_scope: str = "any"  # any | waiting_manager | waiting_customer
    priority_scope: str = "any"  # any | high_or_urgent | urgent_or_vip | vip
    sla_scope: str = "any"  # any | at_risk
    escalation_scope: str = "any"  # any | escalated
    lifecycle_scope: str = "active"  # active | archive | all


@dataclass(slots=True)
class SearchResultItem:
    case_id: UUID
    case_display_number: int
    linked_order_display_number: int | None
    customer_label: str | None
    operational_status: str
    waiting_state: str
    priority: str
    escalation_level: str
    is_archived: bool
    customer_actor_id: str | None = None
    customer_telegram_chat_id: int | None = None
