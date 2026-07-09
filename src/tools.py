"""
Tools for the BVRIT FAQ chatbot that handle computation and real-time data
not available in the grounding document. Each tool has a specific BVRIT-focused
description so the LLM only calls it at the right time.

Tools:
1. fee_calculator — compute total BVRIT fees across years with scholarships
2. date_checker — compare a BVRIT event date against today
3. percentage_calculator — compute BVRIT placement/scholarship rates
"""
from __future__ import annotations

import json
from datetime import date, datetime


# ---------------------------------------------------------------------------
# Tool 1: fee_calculator
# ---------------------------------------------------------------------------
def fee_calculator(
    tuition_per_year: float = 0,
    nba_fee_per_year: float = 0,
    jntuh_fee_per_year: float = 0,
    hostel_fee_per_year: float = 0,
    num_years: int = 4,
    scholarship_percent: float = 0,
) -> str:
    """
    Compute total BVRIT fees across multiple years including tuition, NBA fee,
    JNTUH fees, hostel charges, and scholarship discounts.
    """
    total_per_year = tuition_per_year + nba_fee_per_year + jntuh_fee_per_year + hostel_fee_per_year
    total_all_years = total_per_year * num_years
    discount = total_all_years * scholarship_percent
    final_total = total_all_years - discount

    parts = []
    if tuition_per_year > 0:
        parts.append(f"Tuition: ₹{tuition_per_year:,.0f}/year")
    if nba_fee_per_year > 0:
        parts.append(f"NBA fee: ₹{nba_fee_per_year:,.0f}/year")
    if jntuh_fee_per_year > 0:
        parts.append(f"JNTUH fee: ₹{jntuh_fee_per_year:,.0f}/year")
    if hostel_fee_per_year > 0:
        parts.append(f"Hostel: ₹{hostel_fee_per_year:,.0f}/year")
    parts.append(f"Total per year: ₹{total_per_year:,.0f}")
    parts.append(f"Total for {num_years} years: ₹{total_all_years:,.0f}")
    if scholarship_percent > 0:
        parts.append(f"Scholarship ({scholarship_percent*100:.0f}%): −₹{discount:,.0f}")
        parts.append(f"Final amount after discount: ₹{final_total:,.0f}")

    return "\n".join(parts)


FEE_CALCULATOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fee_calculator",
        "description": (
            "Compute total BVRIT fees across multiple years including tuition, NBA fee, "
            "JNTUH fees, hostel charges, and scholarship discounts. For questions about "
            "combined fee totals, multi-year costs, or fee + hostel + scholarship combinations "
            "specific to BVRIT Hyderabad. Read fee values from the BVRIT fee structure context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tuition_per_year": {
                    "type": "number",
                    "description": "Annual tuition fee in INR (e.g. 140000). Read from BVRIT fee structure context if available.",
                },
                "nba_fee_per_year": {
                    "type": "number",
                    "description": "Annual NBA accreditation fee in INR (e.g. 5000). Set to 0 for AI&ML branch per the document.",
                },
                "jntuh_fee_per_year": {
                    "type": "number",
                    "description": "Annual JNTUH miscellaneous fee in INR (e.g. 10000).",
                },
                "hostel_fee_per_year": {
                    "type": "number",
                    "description": "Annual hostel fee in INR (e.g. 60000). Only include if user asks about hostel.",
                },
                "num_years": {
                    "type": "integer",
                    "description": "Number of years for the program (default 4 for B.Tech., 2 for M.Tech.).",
                },
                "scholarship_percent": {
                    "type": "number",
                    "description": "Scholarship percentage as a decimal (e.g. 0.25 for 25% off). Only include if user mentions a scholarship.",
                },
            },
            "required": ["tuition_per_year", "num_years"],
        },
    },
}


# ---------------------------------------------------------------------------
# Tool 2: date_checker
# ---------------------------------------------------------------------------
def date_checker(event_date: str, event_description: str) -> str:
    """
    Compare a BVRIT-related event, deadline, or exam date against today's real date.
    Returns whether the date is past, upcoming, or how many days remain.
    """
    try:
        target = datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Could not parse date '{event_date}'. Expected format: YYYY-MM-DD."

    today = date.today()
    delta = (target - today).days

    if delta < 0:
        abs_delta = abs(delta)
        if abs_delta == 0:
            return f"{event_description} was today."
        elif abs_delta == 1:
            return f"{event_description} was yesterday (1 day ago)."
        else:
            return f"{event_description} was {abs_delta} days ago ({target.strftime('%d %B %Y')})."
    elif delta == 0:
        return f"{event_description} is today ({target.strftime('%d %B %Y')})!"
    elif delta == 1:
        return f"{event_description} is tomorrow (1 day from now, {target.strftime('%d %B %Y')})."
    else:
        return f"{event_description} is in {delta} days ({target.strftime('%d %B %Y')})."


DATE_CHECKER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "date_checker",
        "description": (
            "Compare a BVRIT-related event, deadline, or exam date against today's real date. "
            "Returns whether the date is past, upcoming, or how many days remain. "
            "Only for BVRIT-specific dates like admission deadlines, exam dates, fest dates, "
            "or application windows mentioned in the college document."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_date": {
                    "type": "string",
                    "description": "The date to check in YYYY-MM-DD format (e.g. '2026-03-31'). Read from the BVRIT document context.",
                },
                "event_description": {
                    "type": "string",
                    "description": "Short label for the event (e.g. 'Synergia 2026 fest', 'M.Tech application deadline'). Used in the response message.",
                },
            },
            "required": ["event_date", "event_description"],
        },
    },
}


# ---------------------------------------------------------------------------
# Tool 3: percentage_calculator
# ---------------------------------------------------------------------------
def percentage_calculator(
    operation: str,
    value: float,
    total: float,
    label: str,
) -> str:
    """
    Compute BVRIT-specific rates and percentages: placement rates, scholarship
    discounts, or admission cutoff conversions. Input values must come from
    the BVRIT document context.
    """
    if total == 0:
        return "Cannot compute: total is zero."

    if operation == "percentage_of_total":
        result = (value / 100.0) * total
        return f"{value}% of {total:,.0f} {label} = {result:,.0f}"
    elif operation == "percent_off":
        discount = (value / 100.0) * total
        final = total - discount
        return f"{value}% off ₹{total:,.0f} = ₹{discount:,.0f} discount, final: ₹{final:,.0f}"
    elif operation == "ratio_to_percent":
        pct = (value / total) * 100.0
        return f"{value:,.0f} out of {total:,.0f} {label} = {pct:.1f}%"
    elif operation == "apply_discount":
        discounted = total * (1.0 - value)
        return f"Applying {value*100:.0f}% discount to {label} (₹{total:,.0f}) = ₹{discounted:,.0f}"
    else:
        return f"Unknown operation '{operation}'. Supported: percentage_of_total, percent_off, ratio_to_percent, apply_discount."


PERCENTAGE_CALCULATOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "percentage_calculator",
        "description": (
            "Compute BVRIT-specific rates and percentages: placement rates "
            "(e.g. '75% of 614 students'), scholarship discounts (e.g. '10% off tuition'), "
            "or admission cutoff conversions. NOT for general math or fee totals "
            "(use fee_calculator for fee totals). Input values must come from the "
            "BVRIT document context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["percentage_of_total", "percent_off", "ratio_to_percent", "apply_discount"],
                    "description": (
                        "Type of calculation: "
                        "'percentage_of_total' (e.g. '75% of 614'), "
                        "'percent_off' (e.g. '10% off 140000'), "
                        "'ratio_to_percent' (e.g. '460 out of 614 = ?%'), "
                        "'apply_discount' (e.g. 'apply 25% scholarship to 140000')."
                    ),
                },
                "value": {
                    "type": "number",
                    "description": "The percentage value (e.g. 75 for 75%). For 'ratio_to_percent', this is the numerator.",
                },
                "total": {
                    "type": "number",
                    "description": "The total/base value (e.g. 614 students, 140000 fee). For 'ratio_to_percent', this is the denominator.",
                },
                "label": {
                    "type": "string",
                    "description": "Label describing what's being calculated (e.g. 'placed students', 'tuition fee'). Used in the response message.",
                },
            },
            "required": ["operation", "value", "total", "label"],
        },
    },
}


# ---------------------------------------------------------------------------
# Registry: map function names to (callable, schema)
# ---------------------------------------------------------------------------
AVAILABLE_TOOLS: dict[str, tuple] = {
    "fee_calculator": (fee_calculator, FEE_CALCULATOR_SCHEMA),
    "date_checker": (date_checker, DATE_CHECKER_SCHEMA),
    "percentage_calculator": (percentage_calculator, PERCENTAGE_CALCULATOR_SCHEMA),
}


def get_tool_schemas() -> list[dict]:
    """Return all tool schemas for the OpenAI tools API."""
    return [schema for _, schema in AVAILABLE_TOOLS.values()]


def execute_tool_call(tool_call: dict) -> str:
    """
    Execute a tool call from the LLM.
    `tool_call` has keys: name, arguments (JSON string).
    Returns the result string to feed back to the LLM.
    """
    name = tool_call.get("name", "")
    args = json.loads(tool_call.get("arguments", "{}"))

    if name not in AVAILABLE_TOOLS:
        return f"Error: unknown tool '{name}'"

    func, _ = AVAILABLE_TOOLS[name]
    try:
        result = func(**args)
        return str(result)
    except Exception as e:
        return f"Error executing {name}: {e}"