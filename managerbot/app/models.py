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
    MINE = "mine"
    WAITING_ME = "waiting_me"
    WAITING_CUSTOMER = "waiting_customer"
    URGENT = "urgent"
    ESCALATED = "escalated"


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
    escalation_level: int
    last_customer_message_at: datetime | None


@dataclass(slots=True)
class ThreadEntry:
    direction: str
    body: str
    created_at: datetime


@dataclass(slots=True)
class CaseDetail:
    case_id: UUID
    case_display_number: int
    commercial_status: str
    operational_status: str
    waiting_state: str
    priority: str
    escalation_level: int
    assignment_label: str
    linked_order_display_number: int | None = None
    linked_quote_display_number: int | None = None
    thread_entries: list[ThreadEntry] = field(default_factory=list)
