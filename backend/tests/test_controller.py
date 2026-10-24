from __future__ import annotations

import pytest

from app.controller import (
    AlarmType,
    BlockedError,
    ConflictError,
    ControllerError,
    NetworkController,
    NotFoundError,
    Protection,
    ServiceStatus,
)


def active_alarm_types(ctl: NetworkController, resource: str) -> set[AlarmType]:
    return {a.type for a in ctl.active_alarms if a.resource == resource}


def test_provision_allocates_same_channel_on_every_link(ctl: NetworkController) -> None:
    svc = ctl.provision("DEL", "BOM", 100)
    leg = svc.legs["working"]
    assert leg is not None
    assert leg.path.nodes[0] == "DEL" and leg.path.nodes[-1] == "BOM"
    for lid in leg.path.links:
        assert ctl.network.links[lid].channels[leg.channel] == svc.id
    assert svc.status is ServiceStatus.UP


def test_second_service_gets_next_wavelength(ctl: NetworkController) -> None:
    a = ctl.provision("DEL", "JAI", 100)
    b = ctl.provision("DEL", "JAI", 100)
    assert a.legs["working"].channel == 0
    assert b.legs["working"].channel == 1


def test_validation_errors(ctl: NetworkController) -> None:
    with pytest.raises(NotFoundError):
        ctl.provision("DEL", "XXX", 100)
    with pytest.raises(ControllerError):
        ctl.provision("DEL", "DEL", 100)
    with pytest.raises(ControllerError):
        ctl.provision("DEL", "BOM", 300)


def test_reach_limit_blocks_long_400g(ctl: NetworkController) -> None:
    # Kochi -> Delhi is well beyond 2000 km on every route.
    with pytest.raises(BlockedError, match="optical reach"):
        ctl.provision("COK", "DEL", 400)
    assert ctl.blocked_total == 1
    # The same demand at 100G (5000 km reach) fits.
    assert ctl.provision("COK", "DEL", 100).status is ServiceStatus.UP


def test_wavelength_exhaustion_blocks(ctl: NetworkController) -> None:
    # Fill every channel on both fibers out of Kochi.
    for lid in ("BLR-COK", "COK-MAA"):
        ctl.network.links[lid].channels = ["X"] * ctl.network.num_channels
    with pytest.raises(BlockedError, match="wavelength blocking"):
        ctl.provision("COK", "BLR", 100)


def test_one_plus_one_paths_are_link_disjoint(ctl: NetworkController) -> None:
    svc = ctl.provision("DEL", "BOM", 400, Protection.ONE_PLUS_ONE)
    w, p = svc.legs["working"], svc.legs["protection"]
    assert w is not None and p is not None
    assert not set(w.path.links) & set(p.path.links)


def test_fiber_cut_triggers_protection_switch(ctl: NetworkController) -> None:
    svc = ctl.provision("DEL", "BOM", 100, Protection.ONE_PLUS_ONE)
    cut = svc.legs["working"].path.links[0]
    result = ctl.fail_link(cut)
    assert svc.id in result.switched
    assert svc.active == "protection"
    assert svc.switchovers == 1
    # 1+1+R: the lost leg is restored on a third, disjoint route if one exists.
    assert svc.status in (ServiceStatus.UP, ServiceStatus.DEGRADED)
    assert AlarmType.LOS in active_alarm_types(ctl, cut)
    for leg in svc.live_legs():
        assert cut not in leg.path.links


def test_fiber_cut_restores_unprotected_service(ctl: NetworkController) -> None:
    svc = ctl.provision("DEL", "BOM", 100)
    old = svc.legs["working"]
    cut = old.path.links[0]
    result = ctl.fail_link(cut)
    assert svc.id in result.restored
    new = svc.legs["working"]
    assert new is not None and cut not in new.path.links
    assert svc.status is ServiceStatus.UP
    # The old spectrum was released on links no longer used.
    for lid in set(old.path.links) - set(new.path.links):
        assert svc.id not in ctl.network.links[lid].channels


def test_isolated_node_goes_down_then_recovers_on_repair(ctl: NetworkController) -> None:
    svc = ctl.provision("COK", "BLR", 100)
    ctl.fail_link("BLR-COK")
    result = ctl.fail_link("COK-MAA")
    assert svc.status is ServiceStatus.DOWN
    assert svc.id in result.down
    assert AlarmType.SERVICE_DOWN in active_alarm_types(ctl, svc.id)
    assert not any(svc.id in link.channels for link in ctl.network.links.values())

    ctl.repair_link("COK-MAA")
    assert svc.status is ServiceStatus.UP
    assert AlarmType.SERVICE_DOWN not in active_alarm_types(ctl, svc.id)


def test_protected_service_degraded_when_no_disjoint_restoration(ctl: NetworkController) -> None:
    svc = ctl.provision("COK", "BLR", 100, Protection.ONE_PLUS_ONE)
    ctl.fail_link("BLR-COK")
    # Kochi has only two fibers, so after one cut a disjoint leg is impossible.
    assert svc.status is ServiceStatus.DEGRADED
    assert AlarmType.PROTECTION_LOST in active_alarm_types(ctl, svc.id)
    ctl.repair_link("BLR-COK")
    assert svc.status is ServiceStatus.UP
    assert not active_alarm_types(ctl, svc.id)


def test_double_fail_and_bad_repair_conflict(ctl: NetworkController) -> None:
    ctl.fail_link("DEL-JAI")
    with pytest.raises(ConflictError):
        ctl.fail_link("DEL-JAI")
    ctl.repair_link("DEL-JAI")
    with pytest.raises(ConflictError):
        ctl.repair_link("DEL-JAI")
    with pytest.raises(NotFoundError):
        ctl.fail_link("NOPE")


def test_delete_releases_spectrum(ctl: NetworkController) -> None:
    svc = ctl.provision("DEL", "MAA", 100, Protection.ONE_PLUS_ONE)
    ctl.delete_service(svc.id)
    assert all(svc.id not in link.channels for link in ctl.network.links.values())
    with pytest.raises(NotFoundError):
        ctl.get_service(svc.id)


def test_no_channel_is_ever_double_booked(ctl: NetworkController) -> None:
    ctl.generate_traffic(100)
    for lid in ("DEL-JAI", "BOM-PNQ", "HYD-NAG"):
        if ctl.network.links[lid].is_up:
            ctl.fail_link(lid)
    owners: dict[tuple[str, int], str] = {}
    for svc in ctl.services.values():
        for leg in svc.live_legs():
            for lid in leg.path.links:
                key = (lid, leg.channel)
                assert key not in owners, f"{key} used by {owners[key]} and {svc.id}"
                owners[key] = svc.id
                assert ctl.network.links[lid].channels[leg.channel] == svc.id
    allocated = sum(link.used_channels for link in ctl.network.links.values())
    assert allocated == len(owners)


def test_high_utilization_alarm(ctl: NetworkController) -> None:
    link = ctl.network.links["BOM-PNQ"]
    for _ in range(int(link.num_channels * 0.8)):
        ctl.provision("BOM", "PNQ", 100)
    assert AlarmType.HIGH_UTILIZATION in active_alarm_types(ctl, "BOM-PNQ")


def test_osnr_alarm_on_impairment(ctl: NetworkController) -> None:
    imp = ctl._impairments["BBI-MAA"]
    imp.offset_db, imp.ticks_left = 10.0, 5
    ctl.tick_telemetry()
    assert AlarmType.OSNR_DEGRADED in active_alarm_types(ctl, "BBI-MAA")


def test_stats_and_blocking_probability(ctl: NetworkController) -> None:
    ctl.provision("DEL", "JAI", 100)
    with pytest.raises(BlockedError):
        ctl.provision("COK", "DEL", 400)
    stats = ctl.stats()
    assert stats["requests_total"] == 2
    assert stats["blocking_probability"] == 0.5
    assert stats["services_by_status"]["UP"] == 1
