"""API request/response models and converters from domain objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .controller import (
    Alarm,
    Event,
    Leg,
    NetworkController,
    OperationResult,
    Protection,
    Service,
    TelemetrySample,
)
from .routing import RATE_PROFILES, Path

# ------------------------------------------------------------------ requests


class ServiceCreate(BaseModel):
    src: str = Field(min_length=2, max_length=8, examples=["DEL"])
    dst: str = Field(min_length=2, max_length=8, examples=["BOM"])
    rate_gbps: Literal[100, 200, 400] = 100
    protection: Protection = Protection.NONE
    name: str | None = Field(default=None, max_length=80)


class PathQuery(BaseModel):
    src: str = Field(min_length=2, max_length=8)
    dst: str = Field(min_length=2, max_length=8)
    rate_gbps: Literal[100, 200, 400] = 100


class TrafficRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=100)


# ----------------------------------------------------------------- responses


class NodeOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    degree: int


class LinkOut(BaseModel):
    id: str
    a: str
    b: str
    length_km: float
    latency_ms: float
    status: str
    utilization: float
    used_channels: int
    channels: list[str | None]
    osnr_db: float | None
    rx_power_dbm: float | None


class PathOut(BaseModel):
    nodes: list[str]
    links: list[str]
    length_km: float
    latency_ms: float
    hops: int


class LegOut(BaseModel):
    path: PathOut
    channel: int
    frequency_thz: float


class ServiceOut(BaseModel):
    id: str
    name: str
    src: str
    dst: str
    rate_gbps: int
    modulation: str
    protection: Protection
    status: str
    active: str
    working: LegOut | None
    protection_leg: LegOut | None
    switchovers: int
    restorations: int
    created_at: float


class AlarmOut(BaseModel):
    id: int
    type: str
    severity: str
    resource: str
    message: str
    raised_at: float
    cleared_at: float | None
    acknowledged: bool


class EventOut(BaseModel):
    id: int
    ts: float
    level: str
    kind: str
    message: str
    service_id: str | None
    link_id: str | None


class StatsOut(BaseModel):
    services_total: int
    services_by_status: dict[str, int]
    alarms_by_severity: dict[str, int]
    network_utilization: float
    requests_total: int
    blocked_total: int
    blocking_probability: float
    capacity_tbps: float
    links_down: int


class RateProfileOut(BaseModel):
    rate_gbps: int
    modulation: str
    max_reach_km: float


class SnapshotOut(BaseModel):
    version: int
    num_channels: int
    nodes: list[NodeOut]
    links: list[LinkOut]
    services: list[ServiceOut]
    alarms: list[AlarmOut]
    alarm_history: list[AlarmOut]
    events: list[EventOut]
    stats: StatsOut
    rate_profiles: list[RateProfileOut]


class PathCandidateOut(BaseModel):
    path: PathOut
    feasible: bool
    reason: str
    channel: int | None


class OperationOut(BaseModel):
    affected: list[str]
    switched: list[str]
    restored: list[str]
    down: list[str]


class TrafficOut(BaseModel):
    provisioned: int
    blocked: int
    reasons: dict[str, int]


class TelemetryOut(BaseModel):
    ts: float
    osnr_db: float
    rx_power_dbm: float
    utilization: float


# ---------------------------------------------------------------- converters


def path_out(p: Path) -> PathOut:
    return PathOut(
        nodes=list(p.nodes),
        links=list(p.links),
        length_km=p.length_km,
        latency_ms=round(p.latency_ms, 3),
        hops=p.hops,
    )


def leg_out(leg: Leg | None) -> LegOut | None:
    if leg is None:
        return None
    return LegOut(path=path_out(leg.path), channel=leg.channel, frequency_thz=leg.frequency_thz)


def service_out(s: Service) -> ServiceOut:
    return ServiceOut(
        id=s.id,
        name=s.name,
        src=s.src,
        dst=s.dst,
        rate_gbps=s.rate_gbps,
        modulation=RATE_PROFILES[s.rate_gbps].modulation,
        protection=s.protection,
        status=s.status.value,
        active=s.active,
        working=leg_out(s.legs.get("working")),
        protection_leg=leg_out(s.legs.get("protection")),
        switchovers=s.switchovers,
        restorations=s.restorations,
        created_at=s.created_at,
    )


def alarm_out(a: Alarm) -> AlarmOut:
    return AlarmOut(
        id=a.id,
        type=a.type.value,
        severity=a.severity.value,
        resource=a.resource,
        message=a.message,
        raised_at=a.raised_at,
        cleared_at=a.cleared_at,
        acknowledged=a.acknowledged,
    )


def event_out(e: Event) -> EventOut:
    return EventOut(**e.__dict__)


def operation_out(r: OperationResult) -> OperationOut:
    return OperationOut(**r.__dict__)


def telemetry_out(t: TelemetrySample) -> TelemetryOut:
    return TelemetryOut(**t.__dict__)


def snapshot(ctl: NetworkController) -> SnapshotOut:
    with ctl._lock:
        net = ctl.network
        links = []
        for link in net.links.values():
            last = ctl.telemetry[link.id][-1] if ctl.telemetry[link.id] else None
            links.append(
                LinkOut(
                    id=link.id,
                    a=link.a,
                    b=link.b,
                    length_km=link.length_km,
                    latency_ms=round(link.latency_ms, 3),
                    status=link.status.value,
                    utilization=round(link.utilization, 4),
                    used_channels=link.used_channels,
                    channels=list(link.channels),
                    osnr_db=last.osnr_db if last else None,
                    rx_power_dbm=last.rx_power_dbm if last else None,
                )
            )
        return SnapshotOut(
            version=ctl.version,
            num_channels=net.num_channels,
            nodes=[
                NodeOut(
                    id=n.id,
                    name=n.name,
                    lat=n.lat,
                    lon=n.lon,
                    degree=len(net.incident_links(n.id)),
                )
                for n in net.nodes.values()
            ],
            links=links,
            services=[service_out(s) for s in ctl.services.values()],
            alarms=[alarm_out(a) for a in ctl.active_alarms],
            alarm_history=[alarm_out(a) for a in ctl.alarm_history[:50]],
            events=[event_out(e) for e in list(ctl.events)[-100:]][::-1],
            stats=StatsOut(**ctl.stats()),
            rate_profiles=[RateProfileOut(**p.__dict__) for p in RATE_PROFILES.values()],
        )
