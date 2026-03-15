"""Pydantic models for request / response validation."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CommunityBootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    community_name: str = Field(min_length=1)
    community_type: str = "family"
    location: str = ""
    description: str = ""
    motto: str = ""


class InviteRegistrationRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    invite_code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    credential: str


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordRecoveryVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=8)


class AccountDeleteRequest(BaseModel):
    password: str = ""


class OwnershipTransferRequest(BaseModel):
    new_owner_user_id: str


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1)
    nickname: str = ""
    phone_number: str = ""
    profile_image_url: str = ""


class GoogleOnboardingRequest(BaseModel):
    full_name: str = ""
    nickname: str = ""
    phone_number: str = ""
    profile_image_url: str = ""
    community_name: str = Field(min_length=1)
    community_type: str = "family"
    location: str = ""
    description: str = ""
    motto: str = ""


class CommunityPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    community_type: str = "family"
    location: str = ""
    description: str = ""
    motto: str = ""
    owner_user_id: str = ""
    member_count: int = 0
    created_at: str = ""


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str = ""
    full_name: str = ""
    nickname: str = ""
    phone_number: str = ""
    community_id: str = ""
    role: str = "member"
    profile_image_url: str = ""
    google_picture: str = ""
    auth_provider: str = "email"
    onboarding_completed: bool = False
    created_at: str = ""


class AuthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    token: str
    user: UserPublic
    community: CommunityPublic | None = None


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: str = "member"
    subyard_id: str = ""


class InvitePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    community_id: str
    email: str
    role: str
    status: str
    code: str
    subyard_id: str = ""
    invited_by_name: str = ""
    created_at: str = ""


class AgendaItemRequest(BaseModel):
    time_label: str = ""
    title: str = Field(min_length=1)
    notes: str = ""


class VolunteerSlotRequest(BaseModel):
    title: str = Field(min_length=1)
    needed_count: int = 5


class VolunteerSignupRequest(BaseModel):
    slot_id: str


class PotluckItemRequest(BaseModel):
    item_name: str = Field(min_length=1)


class PotluckClaimRequest(BaseModel):
    item_id: str


class RSVPRequest(BaseModel):
    status: Literal["going", "maybe", "not-going"]
    user_email: str = ""
    user_name: str = ""
    guests: int = 0


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    start_at: str = Field(min_length=1)
    end_at: str = ""
    location: str = ""
    event_template: str = "custom"
    gathering_format: str = "in-person"
    max_attendees: int = 50
    recurrence_frequency: Literal["none", "daily", "weekly", "monthly", "yearly"] = "none"
    recurrence_count: int = 4
    subyard_id: str = ""
    assigned_roles: list[str] = Field(default_factory=list)
    map_url: str = ""
    special_focus: str = ""
    travel_coordination_notes: str = ""
    suggested_contribution: float = 0.0
    zoom_link: str = ""


class ChecklistItemRequest(BaseModel):
    category: str = ""
    title: str = Field(min_length=1)


class ChecklistToggleRequest(BaseModel):
    item_id: str


class EventInviteCreateRequest(BaseModel):
    member_ids: list[str] = Field(default_factory=list)
    guest_emails: list[str] = Field(default_factory=list)
    note: str = ""


class EventRoleAssignmentRequest(BaseModel):
    role_name: str = ""
    assignees: list[str] = Field(default_factory=list)


class EventMeetingLinkRequest(BaseModel):
    meeting_link: str = ""


class EventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    community_id: str
    title: str
    description: str = ""
    start_at: str
    end_at: str = ""
    location: str = ""
    event_template: str = "custom"
    gathering_format: str = "in-person"
    max_attendees: int | None = 50
    created_by_name: str = ""
    created_by_id: str = ""
    created_by: str = ""
    countdown_label: str = ""
    attendees: list[dict[str, Any]] = Field(default_factory=list)
    role_assignments: list[dict[str, Any]] = Field(default_factory=list)
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    agenda: list[dict[str, Any]] = Field(default_factory=list)
    volunteer_slots: list[dict[str, Any]] = Field(default_factory=list)
    potluck_items: list[dict[str, Any]] = Field(default_factory=list)
    meeting_link: str = ""
    zoom_link: str = ""
    event_invites: list[dict[str, Any]] = Field(default_factory=list)
    event_role_assignments: list[dict[str, Any]] = Field(default_factory=list)
    rsvp_records: list[dict[str, Any]] = Field(default_factory=list)
    planning_checklist: list[dict[str, Any]] = Field(default_factory=list)
    recurrence_frequency: str = "none"
    recurrence_count: int = 0
    recurrence_parent_id: str = ""
    recurrence_index: int = 0
    series_id: str = ""
    is_recurring_instance: bool = False
    parent_event_id: str = ""
    subyard_id: str = ""
    subyard_name: str = ""
    map_url: str = ""
    special_focus: str = ""
    assigned_roles: list[str] = Field(default_factory=list)
    travel_coordination_notes: str = ""
    suggested_contribution: float = 0.0
    created_at: str = ""


class MemoryCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    memory_type: str = "photo"
    file_data: str = ""
    file_name: str = ""
    tags: list[str] = Field(default_factory=list)
    event_id: str = ""
    category: str = "photo"
    image_data_url: str = ""
    voice_note_data_url: str = ""


class CommentRequest(BaseModel):
    text: str = Field(min_length=1)
    author_name: str = ""


class MemoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    community_id: str
    title: str
    description: str = ""
    memory_type: str = "photo"
    file_url: str = ""
    tags: list[str] = Field(default_factory=list)
    ai_summary: str = ""
    sentiment: str = "neutral"
    mood: str = "warm"
    event_id: str = ""
    event_title: str = ""
    category: str = ""
    image_data_url: str = ""
    voice_note_data_url: str = ""
    created_by: str = ""
    created_by_name: str = ""
    created_by_id: str = ""
    comments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""


class ThreadCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    body: str = ""
    category: str = "oral-history"
    elder_name: str = ""
    voice_note_data_url: str = ""
    tags: list[str] = Field(default_factory=list)


class ThreadPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    community_id: str
    title: str
    body: str = ""
    category: str = "oral-history"
    elder_name: str = ""
    voice_note_data_url: str = ""
    author_name: str = ""
    tags: list[str] = Field(default_factory=list)
    created_by_name: str = ""
    created_by_id: str = ""
    comments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""


class PaymentCheckoutRequest(BaseModel):
    package_id: str
    origin_url: str


class DashboardOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    community: dict[str, Any] = Field(default_factory=dict)
    members: list[dict[str, Any]] = Field(default_factory=list)
    subyards: list[dict[str, Any]] = Field(default_factory=list)
    kinship_entries: list[dict[str, Any]] = Field(default_factory=list)
    upcoming_events: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class SubyardCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    icon: str = ""
    privacy: str = "open"
    inherited_roles: bool = True
    role_focus: list[str] = Field(default_factory=list)
    visibility: str = "shared"
    custom_roles: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)


class KinshipCreateRequest(BaseModel):
    person_name: str = Field(min_length=1)
    relationship_type: str = "cousin"
    related_to_name: str = ""
    relationship_scope: str = ""
    linked_user_id: str = ""
    birth_date: str = ""
    anniversary_date: str = ""
    last_seen_at: str = ""
    notes: str = ""


class TravelPlanCreateRequest(BaseModel):
    event_id: str = ""
    title: str = ""
    travel_type: str = "driving"
    details: str = ""
    coordinator_name: str = ""
    amount_estimate: float = 0.0
    payment_status: Literal["pending", "partially-funded", "funded"] = "pending"
    seats_available: int = 4
    traveler_name: str = ""
    mode: str = "driving"
    origin: str = ""
    departure_at: str = ""
    arrival_at: str = ""
    notes: str = ""
    estimated_cost: float = 0.0


class BudgetCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    target_amount: float = 0.0
    current_amount: float = 0.0
    suggested_contribution: float = 0.0
    budget_type: str = "event"
    event_id: str = ""
    notes: str = ""
    line_items: list[dict[str, Any]] = Field(default_factory=list)


class LegacyTableConfigRequest(BaseModel):
    base_url: str = ""
    auth_type: str = "api-key"
    sync_members: bool = True
    sync_stories: bool = True
    sync_events: bool = True
    sync_relationships: bool = True


class FileAttachmentPayload(BaseModel):
    file_data: str = ""
    file_name: str = ""
    mime_type: str = ""


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    body: str = ""
    scope: str = "courtyard"
    subyard_id: str = ""
    attachments: list[FileAttachmentPayload] = Field(default_factory=list)


class ChatMessageCreateRequest(BaseModel):
    text: str = ""
    attachments: list[FileAttachmentPayload] = Field(default_factory=list)


class CommunicationUnreadSummary(BaseModel):
    announcements_unread: int
    chat_unread: int
    total_unread: int


class NotificationPreferencesUpdateRequest(BaseModel):
    reminder_notifications: bool = True
    announcement_notifications: bool = True
    chat_notifications: bool = True
    invite_notifications: bool = True
    rsvp_notifications: bool = True
    muted_room_ids: list[str] = Field(default_factory=list)
    muted_announcement_scopes: list[str] = Field(default_factory=list)


class PollOptionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class PollCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    options: list[PollOptionRequest] = Field(min_length=2, max_length=10)
    allow_multiple: bool = False
    closes_at: str = ""


class PollVoteRequest(BaseModel):
    option_ids: list[str] = Field(min_length=1)


class EventUpdateRequest(BaseModel):
    title: str = ""
    description: str = ""
    start_at: str = ""
    location: str = ""
    gathering_format: str = ""
    max_attendees: int | None = None
    zoom_link: str = ""
    special_focus: str = ""
    map_url: str = ""


class MemoryUpdateRequest(BaseModel):
    title: str = ""
    description: str = ""


class SubscriptionCheckoutRequest(BaseModel):
    plan_id: str
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    origin_url: str
