"""
Rock Solutions Limited — master inventory catalogue.

Used by seed_inventory_master management command and POST /api/v1/inventory/seed/master/.
"""

from decimal import Decimal

DEFAULT_REORDER = Decimal("10")
DEFAULT_MIN_STOCK = Decimal("5")
DEFAULT_MAX_STOCK = Decimal("100")
DEFAULT_SAFETY_STOCK = Decimal("5")

MASTER_CATEGORIES = [
    {"code": "RM", "name": "RAW MATERIALS INVENTORY", "description": "Raw materials for manufacturing and operations"},
    {"code": "WIP", "name": "WORK IN PROGRESS", "description": "Semi-finished production inventory"},
    {"code": "FG", "name": "FINISHED GOODS INVENTORY", "description": "Finished wire mesh and support products"},
    {"code": "RDT", "name": "ROCK DRILLING TOOLS", "description": "Drilling tools and consumables"},
    {"code": "USM", "name": "UNDERGROUND SUPPORT MATERIALS", "description": "Ground support and rock reinforcement"},
    {"code": "GEO", "name": "GEOLOGICAL CONSUMABLES", "description": "Geological sampling and survey consumables"},
    {"code": "UVE", "name": "UNDERGROUND VENTILATION EQUIPMENT", "description": "Mine ventilation fans and ducting"},
    {"code": "ELE", "name": "ELECTRICAL CONSUMABLES", "description": "Electrical cables, breakers, and lighting"},
    {"code": "PPE", "name": "SAFETY EQUIPMENT (PPE)", "description": "Personal protective equipment"},
    {"code": "LOG", "name": "TRANSPORT & LOGISTICS ITEMS", "description": "Cargo handling and transport consumables"},
    {"code": "MSP", "name": "MAINTENANCE SPARE PARTS", "description": "Plant and equipment spare parts"},
    {"code": "TLE", "name": "TOOLS & EQUIPMENT", "description": "Industrial tools and equipment assets"},
    {"code": "OIT", "name": "OFFICE & IT INVENTORY", "description": "Office furniture and IT assets"},
    {"code": "NSS", "name": "NON-STOCK SERVICES", "description": "Non-inventory services (no stock impact)"},
]

# Each item: code, name, category_code, item_type, unit_of_measure, flags...
# flags: serial, batch, expiry (optional kwargs)
def _item(code, name, cat, item_type, uom, **flags):
    return {
        "code": code,
        "name": name,
        "category_code": cat,
        "item_type": item_type,
        "unit_of_measure": uom,
        "has_serial_number": flags.get("serial", False),
        "has_batch_tracking": flags.get("batch", False),
        "has_expiry_date": flags.get("expiry", False),
    }


MASTER_ITEMS = [
    # RAW MATERIALS (RM)
    _item("RM-001", "High Tensile Steel Wire Coils", "RM", "RAW_MATERIAL", "coils"),
    _item("RM-002", "Galvanized Steel Wire", "RM", "RAW_MATERIAL", "coils"),
    _item("RM-003", "Binding Wire", "RM", "RAW_MATERIAL", "kg"),
    _item("RM-004", "Steel Rods", "RM", "RAW_MATERIAL", "pieces"),
    _item("RM-005", "Welding Electrodes", "RM", "RAW_MATERIAL", "boxes"),
    _item("RM-006", "Welding Gas Cylinders", "RM", "RAW_MATERIAL", "cylinders"),
    _item("RM-007", "Cutting Discs", "RM", "RAW_MATERIAL", "pieces"),
    _item("RM-008", "Grinding Discs", "RM", "RAW_MATERIAL", "pieces"),
    _item("RM-009", "Industrial Lubricants", "RM", "RAW_MATERIAL", "liters"),
    _item("RM-010", "Industrial Paints & Coatings", "RM", "RAW_MATERIAL", "liters"),
    # WORK IN PROGRESS (WIP)
    _item("WIP-001", "Wire Mesh Under Production", "WIP", "WORK_IN_PROGRESS", "panels"),
    _item("WIP-002", "Semi-Finished Support Panels", "WIP", "WORK_IN_PROGRESS", "panels"),
    _item("WIP-003", "Fabricated Steel Components", "WIP", "WORK_IN_PROGRESS", "units"),
    _item("WIP-004", "Quality Inspection Batch", "WIP", "WORK_IN_PROGRESS", "batches"),
    # FINISHED GOODS (FG)
    _item("FG-001", "Underground Safety Wire Mesh Panels", "FG", "FINISHED_GOODS", "panels"),
    _item("FG-002", "Welded Wire Mesh Rolls", "FG", "FINISHED_GOODS", "rolls"),
    _item("FG-003", "Mine Support Mesh Heavy Duty", "FG", "FINISHED_GOODS", "panels"),
    _item("FG-004", "Reinforcement Mesh Panels", "FG", "FINISHED_GOODS", "panels"),
    _item("FG-005", "Customized Mine Support Products", "FG", "FINISHED_GOODS", "units"),
    # ROCK DRILLING TOOLS (RDT)
    _item("RDT-001", "Drill Bits", "RDT", "TRADED", "pieces"),
    _item("RDT-002", "Button Bits", "RDT", "TRADED", "pieces"),
    _item("RDT-003", "DTH Hammers", "RDT", "TRADED", "pieces"),
    _item("RDT-004", "Drill Rods", "RDT", "TRADED", "pieces"),
    _item("RDT-005", "Shank Adapters", "RDT", "TRADED", "pieces"),
    _item("RDT-006", "Coupling Sleeves", "RDT", "TRADED", "pieces"),
    _item("RDT-007", "Extension Rods", "RDT", "TRADED", "pieces"),
    # UNDERGROUND SUPPORT MATERIALS (USM)
    _item("USM-001", "Rock Bolts", "USM", "TRADED", "pieces"),
    _item("USM-002", "Friction Bolts", "USM", "TRADED", "pieces"),
    _item("USM-003", "Split Sets", "USM", "TRADED", "pieces"),
    _item("USM-004", "Bearing Plates", "USM", "TRADED", "pieces"),
    _item("USM-005", "Cable Bolts", "USM", "TRADED", "pieces"),
    _item("USM-006", "Resin Capsules", "USM", "TRADED", "boxes"),
    _item("USM-007", "Mesh Fasteners", "USM", "TRADED", "pieces"),
    _item("USM-008", "Ground Support Accessories", "USM", "TRADED", "sets"),
    # GEOLOGICAL CONSUMABLES (GEO)
    _item("GEO-001", "Sample Bags", "GEO", "TRADED", "pieces"),
    _item("GEO-002", "Core Trays", "GEO", "TRADED", "pieces"),
    _item("GEO-003", "Core Boxes", "GEO", "TRADED", "pieces"),
    _item("GEO-004", "Geological Markers", "GEO", "TRADED", "pieces"),
    _item("GEO-005", "Sampling Tags", "GEO", "TRADED", "pieces"),
    _item("GEO-006", "Survey Consumables", "GEO", "TRADED", "sets"),
    # UNDERGROUND VENTILATION EQUIPMENT (UVE) — serial tracked
    _item("UVE-001", "Ventilation Fans", "UVE", "TRADED", "units", serial=True),
    _item("UVE-002", "Auxiliary Fans", "UVE", "TRADED", "units", serial=True),
    _item("UVE-003", "Ventilation Ducts", "UVE", "TRADED", "meters"),
    _item("UVE-004", "Flexible Ducting", "UVE", "TRADED", "meters"),
    _item("UVE-005", "Duct Clamps", "UVE", "TRADED", "pieces"),
    _item("UVE-006", "Airflow Controllers", "UVE", "TRADED", "units", serial=True),
    # ELECTRICAL CONSUMABLES (ELE)
    _item("ELE-001", "Power Cables", "ELE", "TRADED", "meters"),
    _item("ELE-002", "Control Cables", "ELE", "TRADED", "meters"),
    _item("ELE-003", "Circuit Breakers", "ELE", "TRADED", "pieces"),
    _item("ELE-004", "Cable Glands", "ELE", "TRADED", "pieces"),
    _item("ELE-005", "Electrical Connectors", "ELE", "TRADED", "pieces"),
    _item("ELE-006", "Industrial Switches", "ELE", "TRADED", "pieces"),
    _item("ELE-007", "LED Industrial Lighting", "ELE", "TRADED", "pieces"),
    _item("ELE-008", "Distribution Boards", "ELE", "TRADED", "units"),
    # SAFETY EQUIPMENT (PPE) — batch tracked
    _item("PPE-001", "Safety Helmets", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-002", "Safety Boots", "PPE", "PPE", "pairs", batch=True),
    _item("PPE-003", "Reflective Vests", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-004", "Safety Goggles", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-005", "Ear Protection", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-006", "Respirators", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-007", "Hand Gloves", "PPE", "PPE", "pairs", batch=True),
    _item("PPE-008", "Face Shields", "PPE", "PPE", "pieces", batch=True),
    _item("PPE-009", "Fall Protection Harnesses", "PPE", "PPE", "units", batch=True),
    _item("PPE-010", "Protective Overalls", "PPE", "PPE", "pieces", batch=True),
    # TRANSPORT & LOGISTICS (LOG)
    _item("LOG-001", "Cargo Straps", "LOG", "TRADED", "pieces"),
    _item("LOG-002", "Tarpaulins", "LOG", "TRADED", "pieces"),
    _item("LOG-003", "Pallets", "LOG", "TRADED", "pieces"),
    _item("LOG-004", "Loading Chains", "LOG", "TRADED", "pieces"),
    _item("LOG-005", "Lifting Slings", "LOG", "TRADED", "pieces"),
    # MAINTENANCE SPARE PARTS (MSP)
    _item("MSP-001", "Bearings", "MSP", "SPARE_PART", "pieces"),
    _item("MSP-002", "Belts", "MSP", "SPARE_PART", "pieces"),
    _item("MSP-003", "Motors", "MSP", "SPARE_PART", "units"),
    _item("MSP-004", "Hydraulic Hoses", "MSP", "SPARE_PART", "meters"),
    _item("MSP-005", "Pumps", "MSP", "SPARE_PART", "units"),
    _item("MSP-006", "Gearboxes", "MSP", "SPARE_PART", "units"),
    _item("MSP-007", "Industrial Sensors", "MSP", "SPARE_PART", "pieces"),
    _item("MSP-008", "Pneumatic Components", "MSP", "SPARE_PART", "sets"),
    # TOOLS & EQUIPMENT (TLE) — serial tracked
    _item("TLE-001", "Welding Machines", "TLE", "ASSET", "units", serial=True),
    _item("TLE-002", "Angle Grinders", "TLE", "ASSET", "units", serial=True),
    _item("TLE-003", "Hand Drills", "TLE", "ASSET", "units", serial=True),
    _item("TLE-004", "Measuring Instruments", "TLE", "ASSET", "units", serial=True),
    _item("TLE-005", "Cutting Machines", "TLE", "ASSET", "units", serial=True),
    _item("TLE-006", "Hydraulic Tools", "TLE", "ASSET", "units", serial=True),
    # OFFICE & IT (OIT) — serial tracked
    _item("OIT-001", "Laptops", "OIT", "ASSET", "units", serial=True),
    _item("OIT-002", "Desktop Computers", "OIT", "ASSET", "units", serial=True),
    _item("OIT-003", "Printers", "OIT", "ASSET", "units", serial=True),
    _item("OIT-004", "Routers", "OIT", "ASSET", "units", serial=True),
    _item("OIT-005", "Office Furniture", "OIT", "ASSET", "sets"),
    _item("OIT-006", "Projectors", "OIT", "ASSET", "units", serial=True),
    # NON-STOCK SERVICES (NSS)
    _item("NSS-001", "Freight Services", "NSS", "SERVICE", "service"),
    _item("NSS-002", "Equipment Rental", "NSS", "SERVICE", "service"),
    _item("NSS-003", "Technical Consultancy", "NSS", "SERVICE", "service"),
    _item("NSS-004", "Installation Services", "NSS", "SERVICE", "service"),
    _item("NSS-005", "Training Services", "NSS", "SERVICE", "service"),
]
