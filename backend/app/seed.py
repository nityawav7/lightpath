"""Reference topology: a national DWDM backbone across major Indian cities."""

from __future__ import annotations

from .topology import Network, Node

NODES: list[tuple[str, str, float, float]] = [
    ("DEL", "New Delhi", 28.61, 77.21),
    ("JAI", "Jaipur", 26.91, 75.79),
    ("LKO", "Lucknow", 26.85, 80.95),
    ("AMD", "Ahmedabad", 23.02, 72.57),
    ("BPL", "Bhopal", 23.26, 77.41),
    ("KOL", "Kolkata", 22.57, 88.36),
    ("NAG", "Nagpur", 21.15, 79.09),
    ("BBI", "Bhubaneswar", 20.30, 85.82),
    ("BOM", "Mumbai", 19.08, 72.88),
    ("PNQ", "Pune", 18.52, 73.86),
    ("HYD", "Hyderabad", 17.39, 78.49),
    ("BLR", "Bengaluru", 12.97, 77.59),
    ("MAA", "Chennai", 13.08, 80.27),
    ("COK", "Kochi", 9.93, 76.27),
]

LINKS: list[tuple[str, str]] = [
    ("DEL", "JAI"),
    ("DEL", "LKO"),
    ("DEL", "BPL"),
    ("JAI", "AMD"),
    ("JAI", "BPL"),
    ("LKO", "BPL"),
    ("LKO", "KOL"),
    ("AMD", "BOM"),
    ("AMD", "BPL"),
    ("BPL", "NAG"),
    ("KOL", "BBI"),
    ("KOL", "NAG"),
    ("NAG", "HYD"),
    ("NAG", "BOM"),
    ("BBI", "MAA"),
    ("BBI", "HYD"),
    ("BOM", "PNQ"),
    ("PNQ", "HYD"),
    ("PNQ", "BLR"),
    ("HYD", "BLR"),
    ("HYD", "MAA"),
    ("BLR", "MAA"),
    ("BLR", "COK"),
    ("MAA", "COK"),
]

# Demo services provisioned on startup / reset: (src, dst, rate_gbps, protected, name)
DEMO_SERVICES: list[tuple[str, str, int, bool, str]] = [
    ("DEL", "BOM", 400, True, "DC interconnect Delhi-Mumbai"),
    ("BOM", "MAA", 200, True, "Cable landing backhaul"),
    ("DEL", "KOL", 100, False, "Enterprise wave East"),
    ("BLR", "HYD", 400, False, "Cloud region link"),
    ("PNQ", "DEL", 100, False, "Mobile backhaul North"),
    ("COK", "BOM", 100, True, "Submarine cable extension"),
    ("JAI", "AMD", 400, False, "Metro aggregation West"),
]


def build_reference_network(num_channels: int) -> Network:
    net = Network(num_channels=num_channels)
    for node_id, name, lat, lon in NODES:
        net.add_node(Node(id=node_id, name=name, lat=lat, lon=lon))
    for a, b in LINKS:
        net.add_link(a, b)
    return net
