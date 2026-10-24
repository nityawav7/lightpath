"""Network controller: service provisioning, fault handling and alarms.

The controller owns all mutable state. It is deliberately framework-free so the
business logic can be unit-tested without HTTP. Every public method takes a
re-entrant lock, so it is safe to call from request handlers and from the
background telemetry task at the same time.
"""

from __future__ import annotations

import functools
import logging
import math
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from .config import Settings
from .routing import (
    RATE_PROFILES,
    Path,
    channel_frequency_thz,
    first_fit_channel,
    k_shortest_paths,
)
from .seed import DEMO_SERVICES, build_reference_network
from .topology import Link, LinkStatus, Network

log = logging.getLogger("lightpath.controller")

WORKING = "working"
PROTECTION = "protection"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    WARNING = "WARNING"


class ServiceStatus(str, Enum):
    UP = "UP"
    DEGRADED = "DEGRADED"  # carrying traffic, but protection is lost
    DOWN = "DOWN"


class Protection(str, Enum):
    NONE = "NONE"
    ONE_PLUS_ONE = "1+1"


class AlarmType(str, Enum):
    LOS = "LOS"  # loss of signal on a fiber
    OSNR_DEGRADED = "OSNR_DEGRADED"
    HIGH_UTILIZATION = "HIGH_UTILIZATION"
    SERVICE_DOWN = "SERVICE_DOWN"
    PROTECTION_LOST = "PROTECTION_LOST"


ALARM_SEVERITY: dict[AlarmType, Severity] = {
    AlarmType.LOS: Severity.CRITICAL,
    AlarmType.SERVICE_DOWN: Severity.CRITICAL,
    AlarmType.OSNR_DEGRADED: Severity.MAJOR,
    AlarmType.PROTECTION_LOST: Severity.MAJOR,
    AlarmType.HIGH_UTILIZATION: Severity.MINOR,
}


class ControllerError(Exception):
    status_code = 400


class NotFoundError(ControllerError):
    status_code = 404


class ConflictError(ControllerError):
    status_code = 409


class BlockedError(ControllerError):
    """The request is valid but the network cannot carry it right now."""

    status_code = 409


@dataclass
class Leg:
    path: Path
    channel: int

    @property
    def frequency_thz(self) -> float:
        return channel_frequency_thz(self.channel)


@dataclass
class Service:
    id: str
    name: str
    src: str
    dst: str
    rate_gbps: int
    protection: Protection
    created_at: float
    legs: dict[str, Leg | None] = field(default_factory=dict)
    active: str = WORKING
    status: ServiceStatus = ServiceStatus.UP
    switchovers: int = 0
    restorations: int = 0

    @property
    def roles(self) -> list[str]:
        if self.protection is Protection.ONE_PLUS_ONE:
            return [WORKING, PROTECTION]
        return [WORKING]

    def live_legs(self) -> list[Leg]:
        return [leg for leg in self.legs.values() if leg is not None]

    def uses_link(self, link_id: str) -> bool:
        return any(link_id in leg.path.links for leg in self.live_legs())


@dataclass
class Alarm:
    id: int
    type: AlarmType
    severity: Severity
    resource: str
    message: str
    raised_at: float
    cleared_at: float | None = None
    acknowledged: bool = False

    @property
    def active(self) -> bool:
        return self.cleared_at is None


@dataclass
class Event:
    id: int
    ts: float
    level: str  # info | success | warning | critical
    kind: str
    message: str
    service_id: str | None = None
    link_id: str | None = None


@dataclass
class TelemetrySample:
    ts: float
    osnr_db: float
    rx_power_dbm: float
    utilization: float


@dataclass
class _Impairment:
    offset_db: float = 0.0
    ticks_left: int = 0


@dataclass
class OperationResult:
    affected: list[str] = field(default_factory=list)
    switched: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    down: list[str] = field(default_factory=list)


F = TypeVar("F", bound=Callable[..., Any])


def _locked(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(self: NetworkController, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class NetworkController:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self._rng = rng or random.Random()
        self._clock = clock
        self._lock = threading.RLock()
        self.version = 0
        self._init_state()
        if settings.seed_demo_services:
            self._seed_demo()

    # ------------------------------------------------------------------ state

    def _init_state(self) -> None:
        self.network: Network = build_reference_network(self.settings.num_channels)
        self.services: dict[str, Service] = {}
        self._active_alarms: dict[tuple[AlarmType, str], Alarm] = {}
        self._alarm_history: deque[Alarm] = deque(maxlen=200)
        self.events: deque[Event] = deque(maxlen=300)
        self.telemetry: dict[str, deque[TelemetrySample]] = {
            lid: deque(maxlen=self.settings.telemetry_history) for lid in self.network.links
        }
        self._impairments: dict[str, _Impairment] = {
            lid: _Impairment() for lid in self.network.links
        }
        self._next_service = 1
        self._next_alarm = 1
        self._next_event = 1
        self.requests_total = 0
        self.blocked_total = 0
        self.block_reasons: dict[str, int] = {}
        self.tick_telemetry()

    def _seed_demo(self) -> None:
        for src, dst, rate, protected, name in DEMO_SERVICES:
            try:
                self.provision(
                    src,
                    dst,
                    rate,
                    Protection.ONE_PLUS_ONE if protected else Protection.NONE,
                    name,
                )
            except BlockedError as exc:  # pragma: no cover - topology is static
                log.warning("demo service %s-%s blocked: %s", src, dst, exc)

    @_locked
    def reset(self) -> None:
        self._init_state()
        if self.settings.seed_demo_services:
            self._seed_demo()
        self._event("info", "RESET", "Network reset to reference topology")
        self._touch()

    def _touch(self) -> None:
        self.version += 1

    # ----------------------------------------------------------- bookkeeping

    def _event(
        self,
        level: str,
        kind: str,
        message: str,
        service_id: str | None = None,
        link_id: str | None = None,
    ) -> None:
        ev = Event(self._next_event, self._clock(), level, kind, message, service_id, link_id)
        self._next_event += 1
        self.events.append(ev)
        log.info("[%s] %s", kind, message)

    def _raise_alarm(self, type_: AlarmType, resource: str, message: str) -> None:
        key = (type_, resource)
        if key in self._active_alarms:
            return
        alarm = Alarm(
            id=self._next_alarm,
            type=type_,
            severity=ALARM_SEVERITY[type_],
            resource=resource,
            message=message,
            raised_at=self._clock(),
        )
        self._next_alarm += 1
        self._active_alarms[key] = alarm
        self._touch()

    def _clear_alarm(self, type_: AlarmType, resource: str) -> None:
        alarm = self._active_alarms.pop((type_, resource), None)
        if alarm is None:
            return
        alarm.cleared_at = self._clock()
        self._alarm_history.appendleft(alarm)
        self._touch()

    def _clear_resource_alarms(self, resource: str) -> None:
        for type_, res in list(self._active_alarms):
            if res == resource:
                self._clear_alarm(type_, res)

    @property
    def active_alarms(self) -> list[Alarm]:
        order = list(Severity)
        return sorted(
            self._active_alarms.values(),
            key=lambda a: (order.index(a.severity), -a.raised_at),
        )

    @property
    def alarm_history(self) -> list[Alarm]:
        return list(self._alarm_history)

    def _update_utilization_alarms(self) -> None:
        threshold = self.settings.high_utilization_threshold
        for link in self.network.links.values():
            if link.is_up and link.utilization >= threshold:
                self._raise_alarm(
                    AlarmType.HIGH_UTILIZATION,
                    link.id,
                    f"Fiber {link.id} spectrum {link.utilization:.0%} occupied",
                )
            elif link.utilization < threshold - 0.05 or not link.is_up:
                self._clear_alarm(AlarmType.HIGH_UTILIZATION, link.id)

    # ----------------------------------------------------------- resources

    def _get_service(self, service_id: str) -> Service:
        svc = self.services.get(service_id)
        if svc is None:
            raise NotFoundError(f"service {service_id} not found")
        return svc

    def _get_link(self, link_id: str) -> Link:
        link = self.network.links.get(link_id)
        if link is None:
            raise NotFoundError(f"link {link_id} not found")
        return link

    def _allocate(self, service_id: str, leg: Leg) -> None:
        for lid in leg.path.links:
            link = self.network.links[lid]
            if not link.is_free(leg.channel):  # invariant, should never happen
                raise RuntimeError(f"channel {leg.channel} on {lid} already in use")
            link.channels[leg.channel] = service_id

    def _release(self, service_id: str, leg: Leg) -> None:
        for lid in leg.path.links:
            link = self.network.links[lid]
            if link.channels[leg.channel] == service_id:
                link.channels[leg.channel] = None

    def _leg_healthy(self, leg: Leg) -> bool:
        return all(self.network.links[lid].is_up for lid in leg.path.links)

    # ------------------------------------------------------- path computation

    def _validate_request(self, src: str, dst: str, rate_gbps: int) -> None:
        for node in (src, dst):
            if node not in self.network.nodes:
                raise NotFoundError(f"node {node} not found")
        if src == dst:
            raise ControllerError("source and destination must differ")
        if rate_gbps not in RATE_PROFILES:
            raise ControllerError(
                f"unsupported rate {rate_gbps}G; choose one of {sorted(RATE_PROFILES)}"
            )

    def _feasible_legs(
        self, src: str, dst: str, rate_gbps: int, excluded_links: set[str]
    ) -> tuple[list[Leg], str]:
        """All feasible legs over the K shortest routes, best first."""
        reach = RATE_PROFILES[rate_gbps].max_reach_km
        paths = k_shortest_paths(self.network, src, dst, self.settings.k_paths, excluded_links)
        if not paths:
            return [], "no physical route (fiber cut or no disjoint route)"
        in_reach = [p for p in paths if p.length_km <= reach]
        if not in_reach:
            return [], f"all routes exceed the {reach:.0f} km optical reach of {rate_gbps}G"
        legs: list[Leg] = []
        for path in in_reach:
            ch = first_fit_channel(self.network, path.links)
            if ch is not None:
                legs.append(Leg(path, ch))
        if not legs:
            return [], "wavelength blocking: no continuous free channel on any route"
        return legs, ""

    @_locked
    def compute_paths(self, src: str, dst: str, rate_gbps: int) -> list[dict[str, Any]]:
        """What-if analysis used by the UI before provisioning."""
        self._validate_request(src, dst, rate_gbps)
        reach = RATE_PROFILES[rate_gbps].max_reach_km
        result = []
        for path in k_shortest_paths(self.network, src, dst, self.settings.k_paths):
            ch = first_fit_channel(self.network, path.links)
            reason = ""
            if path.length_km > reach:
                reason = f"exceeds {reach:.0f} km reach"
            elif ch is None:
                reason = "no continuous free wavelength"
            result.append(
                {
                    "path": path,
                    "channel": ch if not reason else None,
                    "feasible": not reason,
                    "reason": reason,
                }
            )
        return result

    # ---------------------------------------------------------- provisioning

    @_locked
    def provision(
        self,
        src: str,
        dst: str,
        rate_gbps: int,
        protection: Protection = Protection.NONE,
        name: str | None = None,
    ) -> Service:
        self._validate_request(src, dst, rate_gbps)
        if len(self.services) >= self.settings.max_services:
            raise ConflictError(
                f"service limit of {self.settings.max_services} reached; delete some first"
            )
        self.requests_total += 1

        working, reason = self._feasible_legs(src, dst, rate_gbps, set())
        chosen: tuple[Leg, Leg | None] | None = None
        if working and protection is Protection.NONE:
            chosen = (working[0], None)
        elif working:
            for w in working:
                prot, prot_reason = self._feasible_legs(src, dst, rate_gbps, set(w.path.links))
                if prot:
                    chosen = (w, prot[0])
                    break
                reason = f"no disjoint protection route: {prot_reason}"

        if chosen is None:
            self.blocked_total += 1
            self.block_reasons[reason] = self.block_reasons.get(reason, 0) + 1
            self._event(
                "warning", "BLOCKED", f"Request {src}->{dst} {rate_gbps}G blocked: {reason}"
            )
            self._touch()
            raise BlockedError(reason)

        svc_id = f"SVC-{self._next_service:04d}"
        self._next_service += 1
        svc = Service(
            id=svc_id,
            name=(name or f"{src}-{dst} {rate_gbps}G").strip()[:80],
            src=src,
            dst=dst,
            rate_gbps=rate_gbps,
            protection=protection,
            created_at=self._clock(),
        )
        w_leg, p_leg = chosen
        self._allocate(svc_id, w_leg)
        svc.legs[WORKING] = w_leg
        if p_leg is not None:
            self._allocate(svc_id, p_leg)
            svc.legs[PROTECTION] = p_leg
        self.services[svc_id] = svc

        route = " > ".join(w_leg.path.nodes)
        kind = "1+1 protected" if p_leg else "unprotected"
        self._event(
            "success",
            "PROVISIONED",
            f"{svc_id} {rate_gbps}G {kind} up on λ{w_leg.channel + 1} via {route}",
            service_id=svc_id,
        )
        self._update_utilization_alarms()
        self._touch()
        return svc

    @_locked
    def delete_service(self, service_id: str) -> None:
        svc = self._get_service(service_id)
        for leg in svc.live_legs():
            self._release(svc.id, leg)
        del self.services[service_id]
        self._clear_resource_alarms(service_id)
        self._event("info", "DELETED", f"{service_id} decommissioned", service_id=service_id)
        self._update_utilization_alarms()
        self._touch()

    @_locked
    def get_service(self, service_id: str) -> Service:
        return self._get_service(service_id)

    # -------------------------------------------------------------- faults

    def _reconcile(self, svc: Service, result: OperationResult) -> None:
        """Bring a service back to its intended state after a topology change.

        1. Tear down legs that cross a failed fiber and free their spectrum.
        2. If the active leg died and the standby is healthy, switch over
           (1+1 protection: sub-50 ms, no path computation needed).
        3. Re-compute any missing leg (restoration), keeping protection
           link-disjoint from the surviving leg.
        """
        old_status = svc.status
        active_failed = False
        for role in svc.roles:
            leg = svc.legs.get(role)
            if leg is not None and not self._leg_healthy(leg):
                self._release(svc.id, leg)
                svc.legs[role] = None
                active_failed = active_failed or role == svc.active

        if active_failed:
            standby = next(
                (r for r in svc.roles if r != svc.active and svc.legs.get(r) is not None),
                None,
            )
            if standby is not None:
                svc.active = standby
                svc.switchovers += 1
                result.switched.append(svc.id)
                leg = svc.legs[standby]
                assert leg is not None
                self._event(
                    "warning",
                    "PROTECTION_SWITCH",
                    f"{svc.id} switched to {standby} path λ{leg.channel + 1} "
                    f"({' > '.join(leg.path.nodes)}) in <50 ms",
                    service_id=svc.id,
                )

        for role in svc.roles:
            if svc.legs.get(role) is not None:
                continue
            excluded = {lid for leg in svc.live_legs() for lid in leg.path.links}
            legs, _ = self._feasible_legs(svc.src, svc.dst, svc.rate_gbps, excluded)
            if not legs:
                continue
            leg = legs[0]
            self._allocate(svc.id, leg)
            svc.legs[role] = leg
            svc.restorations += 1
            result.restored.append(svc.id)
            self._event(
                "success",
                "RESTORED",
                f"{svc.id} {role} path restored on λ{leg.channel + 1} "
                f"via {' > '.join(leg.path.nodes)} ({leg.path.length_km:.0f} km)",
                service_id=svc.id,
            )

        if svc.legs.get(svc.active) is None:
            svc.active = next((r for r in svc.roles if svc.legs.get(r) is not None), WORKING)

        live = len(svc.live_legs())
        if live == 0:
            svc.status = ServiceStatus.DOWN
        elif live < len(svc.roles):
            svc.status = ServiceStatus.DEGRADED
        else:
            svc.status = ServiceStatus.UP

        if svc.status is ServiceStatus.DOWN:
            self._raise_alarm(
                AlarmType.SERVICE_DOWN,
                svc.id,
                f"{svc.id} ({svc.name}) is down: no restorable route",
            )
            self._clear_alarm(AlarmType.PROTECTION_LOST, svc.id)
            if old_status is not ServiceStatus.DOWN:
                result.down.append(svc.id)
                self._event("critical", "SERVICE_DOWN", f"{svc.id} is DOWN", service_id=svc.id)
        elif svc.status is ServiceStatus.DEGRADED:
            self._clear_alarm(AlarmType.SERVICE_DOWN, svc.id)
            self._raise_alarm(
                AlarmType.PROTECTION_LOST,
                svc.id,
                f"{svc.id} ({svc.name}) running unprotected",
            )
        else:
            self._clear_alarm(AlarmType.SERVICE_DOWN, svc.id)
            self._clear_alarm(AlarmType.PROTECTION_LOST, svc.id)

    @_locked
    def fail_link(self, link_id: str) -> OperationResult:
        link = self._get_link(link_id)
        if not link.is_up:
            raise ConflictError(f"fiber {link_id} is already down")
        link.status = LinkStatus.DOWN
        self._clear_resource_alarms(link_id)
        self._raise_alarm(AlarmType.LOS, link_id, f"Loss of signal on fiber {link_id}")
        self._event("critical", "FIBER_CUT", f"Fiber cut detected on {link_id}", link_id=link_id)

        result = OperationResult()
        for svc in sorted(self.services.values(), key=lambda s: s.id):
            if svc.uses_link(link_id):
                result.affected.append(svc.id)
                self._reconcile(svc, result)
        self._update_utilization_alarms()
        self._touch()
        return result

    @_locked
    def repair_link(self, link_id: str) -> OperationResult:
        link = self._get_link(link_id)
        if link.is_up:
            raise ConflictError(f"fiber {link_id} is not down")
        link.status = LinkStatus.UP
        self._clear_alarm(AlarmType.LOS, link_id)
        self._event("success", "FIBER_REPAIRED", f"Fiber {link_id} repaired", link_id=link_id)

        result = OperationResult()
        for svc in sorted(self.services.values(), key=lambda s: s.id):
            if svc.status is not ServiceStatus.UP:
                result.affected.append(svc.id)
                self._reconcile(svc, result)
        self._update_utilization_alarms()
        self._touch()
        return result

    @_locked
    def acknowledge_alarm(self, alarm_id: int) -> Alarm:
        for alarm in self._active_alarms.values():
            if alarm.id == alarm_id:
                alarm.acknowledged = True
                self._touch()
                return alarm
        raise NotFoundError(f"active alarm {alarm_id} not found")

    # ----------------------------------------------------------- simulation

    @_locked
    def generate_traffic(self, count: int) -> dict[str, Any]:
        """Offer random demands to the network (useful to study blocking)."""
        node_ids = sorted(self.network.nodes)
        provisioned, blocked = 0, 0
        reasons: dict[str, int] = {}
        for _ in range(count):
            if len(self.services) >= self.settings.max_services:
                break
            src, dst = self._rng.sample(node_ids, 2)
            rate = self._rng.choices([100, 200, 400], weights=[5, 3, 2])[0]
            prot = Protection.ONE_PLUS_ONE if self._rng.random() < 0.3 else Protection.NONE
            try:
                self.provision(src, dst, rate, prot)
                provisioned += 1
            except BlockedError as exc:
                blocked += 1
                reasons[str(exc)] = reasons.get(str(exc), 0) + 1
        return {"provisioned": provisioned, "blocked": blocked, "reasons": reasons}

    @_locked
    def tick_telemetry(self) -> None:
        """Sample optical performance monitoring (PM) counters for every fiber.

        OSNR falls with the number of amplified spans (~80 km each). Occasional
        impairments (dirty connector, amplifier drift) lower OSNR for a while
        and raise an alarm with hysteresis so it does not flap.
        """
        now = self._clock()
        threshold = self.settings.osnr_alarm_threshold_db
        for link in self.network.links.values():
            imp = self._impairments[link.id]
            if not link.is_up:
                sample = TelemetrySample(now, 0.0, -40.0, link.utilization)
            else:
                if imp.ticks_left > 0:
                    imp.ticks_left -= 1
                    if imp.ticks_left == 0:
                        imp.offset_db = 0.0
                elif self._rng.random() < self.settings.impairment_probability:
                    imp.offset_db = self._rng.uniform(7.0, 10.0)
                    imp.ticks_left = self._rng.randint(10, 30)
                    self._event(
                        "warning",
                        "IMPAIRMENT",
                        f"Optical impairment detected on {link.id} (-{imp.offset_db:.1f} dB OSNR)",
                        link_id=link.id,
                    )
                spans = max(1.0, link.length_km / 80.0)
                base_osnr = 33.0 - 10 * math.log10(spans)
                osnr = base_osnr - imp.offset_db + self._rng.gauss(0, 0.25)
                power = -12.0 - imp.offset_db * 0.4 + self._rng.gauss(0, 0.15)
                sample = TelemetrySample(now, round(osnr, 2), round(power, 2), link.utilization)
                if osnr < threshold:
                    self._raise_alarm(
                        AlarmType.OSNR_DEGRADED,
                        link.id,
                        f"OSNR on {link.id} below {threshold:.0f} dB",
                    )
                elif osnr > threshold + 0.5:
                    self._clear_alarm(AlarmType.OSNR_DEGRADED, link.id)
            self.telemetry[link.id].append(sample)

    @_locked
    def link_telemetry(self, link_id: str) -> list[TelemetrySample]:
        self._get_link(link_id)
        return list(self.telemetry[link_id])

    # -------------------------------------------------------------- reports

    @_locked
    def stats(self) -> dict[str, Any]:
        by_status = {s.value: 0 for s in ServiceStatus}
        for svc in self.services.values():
            by_status[svc.status.value] += 1
        by_severity = {s.value: 0 for s in Severity}
        for alarm in self._active_alarms.values():
            by_severity[alarm.severity.value] += 1
        carried_gbps = sum(
            s.rate_gbps for s in self.services.values() if s.status is not ServiceStatus.DOWN
        )
        return {
            "services_total": len(self.services),
            "services_by_status": by_status,
            "alarms_by_severity": by_severity,
            "network_utilization": round(self.network.utilization, 4),
            "requests_total": self.requests_total,
            "blocked_total": self.blocked_total,
            "blocking_probability": round(self.blocked_total / self.requests_total, 4)
            if self.requests_total
            else 0.0,
            "capacity_tbps": round(carried_gbps / 1000, 2),
            "links_down": sum(1 for link in self.network.links.values() if not link.is_up),
        }
