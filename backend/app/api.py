"""REST API routes (mounted under /api)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from . import schemas as s
from .controller import NetworkController
from .realtime import SnapshotHub

router = APIRouter(prefix="/api")


def _ctl(request: Request) -> NetworkController:
    return request.app.state.controller


def _hub(request: Request) -> SnapshotHub:
    return request.app.state.hub


@router.get("/health", tags=["ops"])
async def health(request: Request) -> dict[str, object]:
    return {"status": "ok", "version": _ctl(request).version, "clients": _hub(request).client_count}


@router.get("/snapshot", response_model=s.SnapshotOut, tags=["network"])
async def get_snapshot(request: Request) -> s.SnapshotOut:
    """Full network state: topology, spectrum, services, alarms, events, KPIs."""
    return s.snapshot(_ctl(request))


@router.get("/services", response_model=list[s.ServiceOut], tags=["services"])
async def list_services(request: Request) -> list[s.ServiceOut]:
    return [s.service_out(svc) for svc in _ctl(request).services.values()]


@router.post("/services", response_model=s.ServiceOut, status_code=201, tags=["services"])
async def create_service(body: s.ServiceCreate, request: Request) -> s.ServiceOut:
    """Provision a wavelength service. Returns 409 with a reason if blocked."""
    svc = _ctl(request).provision(
        body.src.upper(), body.dst.upper(), body.rate_gbps, body.protection, body.name
    )
    await _hub(request).publish()
    return s.service_out(svc)


@router.get("/services/{service_id}", response_model=s.ServiceOut, tags=["services"])
async def get_service(service_id: str, request: Request) -> s.ServiceOut:
    return s.service_out(_ctl(request).get_service(service_id))


@router.delete(
    "/services/{service_id}", status_code=204, response_class=Response, tags=["services"]
)
async def delete_service(service_id: str, request: Request) -> Response:
    _ctl(request).delete_service(service_id)
    await _hub(request).publish()
    return Response(status_code=204)


@router.post("/paths/compute", response_model=list[s.PathCandidateOut], tags=["services"])
async def compute_paths(body: s.PathQuery, request: Request) -> list[s.PathCandidateOut]:
    """What-if: K shortest routes with reach and wavelength feasibility."""
    result = _ctl(request).compute_paths(body.src.upper(), body.dst.upper(), body.rate_gbps)
    return [
        s.PathCandidateOut(
            path=s.path_out(c["path"]),
            feasible=c["feasible"],
            reason=c["reason"],
            channel=c["channel"],
        )
        for c in result
    ]


@router.post("/links/{link_id}/fail", response_model=s.OperationOut, tags=["faults"])
async def fail_link(link_id: str, request: Request) -> s.OperationOut:
    """Simulate a fiber cut; protected services switch, others are restored."""
    result = _ctl(request).fail_link(link_id.upper())
    await _hub(request).publish()
    return s.operation_out(result)


@router.post("/links/{link_id}/repair", response_model=s.OperationOut, tags=["faults"])
async def repair_link(link_id: str, request: Request) -> s.OperationOut:
    result = _ctl(request).repair_link(link_id.upper())
    await _hub(request).publish()
    return s.operation_out(result)


@router.get("/links/{link_id}/telemetry", response_model=list[s.TelemetryOut], tags=["telemetry"])
async def link_telemetry(link_id: str, request: Request) -> list[s.TelemetryOut]:
    return [s.telemetry_out(t) for t in _ctl(request).link_telemetry(link_id.upper())]


@router.post("/alarms/{alarm_id}/ack", response_model=s.AlarmOut, tags=["alarms"])
async def ack_alarm(alarm_id: int, request: Request) -> s.AlarmOut:
    alarm = _ctl(request).acknowledge_alarm(alarm_id)
    await _hub(request).publish()
    return s.alarm_out(alarm)


@router.post("/simulate/traffic", response_model=s.TrafficOut, tags=["simulation"])
async def simulate_traffic(body: s.TrafficRequest, request: Request) -> s.TrafficOut:
    """Offer N random demands to the network."""
    result = _ctl(request).generate_traffic(body.count)
    await _hub(request).publish()
    return s.TrafficOut(**result)


@router.post("/reset", status_code=204, response_class=Response, tags=["simulation"])
async def reset(request: Request) -> Response:
    _ctl(request).reset()
    await _hub(request).publish()
    return Response(status_code=204)
