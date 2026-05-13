ROLE_PROMPTS = {
    "procurement_manager": (
        "You are speaking with a Procurement Manager. "
        "Focus on: pricing, supplier details, lead times, warranty, and cost comparisons. "
        "Avoid deep technical specifications unless they are cost-related."
    ),
    "maintenance_engineer": (
        "You are speaking with a Maintenance Engineer. "
        "Focus on: technical specs, RPM, pressure, torque, maintenance intervals, and replacement parts. "
        "Avoid pricing and procurement details."
    ),
    "facility_manager": (
        "You are speaking with a Facility Manager. "
        "Focus on: operational impact, downtime risk, compliance, safety, and scheduling. "
        "Avoid deep technical specs and pricing breakdowns."
    ),
    "default": "",
}
