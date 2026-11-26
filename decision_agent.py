"""
Supply-chain exception decision agent (prototype).

When a disruption hits the network, the agent generates a resolution option
with a local LLM, scores it alongside two baseline options using a reward
function tuned to the business's current priority (margin vs. on-time-in-full),
explains which option wins and why, and asks a human to approve before
"executing" (execution is simulated).
"""

import json
import sys
import time

import questionary
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "phi3.5"

# Illustrative order economics (a real system would pull these from the ERP).
REVENUE, COGS, STANDARD_FREIGHT = 100_000, 80_000, 5_000

# Fallback used only if the local model is unreachable or returns bad JSON.
FALLBACK_OPTION = {
    "scenario": "Reallocate from remote hub",
    "exception_cost": 1000,
    "otif_score": 95,
    "penalty_risk": 5,
}

STRATEGIES = {
    "Focus on Cash Flow (heavily weight gross margin)": ("Cash Flow (margin)", 0.8, 0.2),
    "Balanced Strategy (equal weight margin and OTIF)": ("Balanced (margin & OTIF)", 0.5, 0.5),
    "Focus on Service (heavily weight OTIF & SLA compliance)": ("Service (OTIF)", 0.2, 0.8),
}

AGENT_PROMPT = """
You are a supply-chain decision agent. Network event: {event}.
Propose one resolution: fulfil Tier 1 orders from a remote hub.
Assume it incurs a $1000 exception cost, keeps OTIF at 95, and carries a penalty risk of 5.
Output JSON strictly in this format:
{{"scenario": "string", "exception_cost": int, "otif_score": int, "penalty_risk": int}}
"""


def slow_print(text, delay=0.02):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def query_agent(event):
    """Ask the local model for a resolution option; fall back visibly on failure."""
    payload = {
        "model": MODEL,
        "prompt": AGENT_PROMPT.format(event=event),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        option = json.loads(response.json()["response"])
        missing = set(FALLBACK_OPTION) - set(option)
        if missing:
            raise ValueError(f"model output missing fields: {sorted(missing)}")
        return option, True
    except (requests.RequestException, KeyError, ValueError) as err:
        print(f"[WARN] Local model unavailable or invalid output ({err}); using fallback option.")
        return dict(FALLBACK_OPTION), False


RISK_WEIGHT = 0.1  # penalty-risk deduction, applied on the same 0-1 scale


def gross_margin_pct(exception_cost):
    return round((REVENUE - (COGS + STANDARD_FREIGHT + exception_cost)) / REVENUE * 100, 2)


def normalize(values):
    """Min-max scale to 0-1 across the candidate options (all equal -> 0.5)."""
    lo, hi = min(values), max(values)
    return [0.5 if hi == lo else (v - lo) / (hi - lo) for v in values]


def score_options(options, margin_weight, otif_weight):
    """Score every option on a common 0-100 scale under the chosen strategy.

    Margin (~5-15%) and OTIF (~85-99%) live on different scales, so each metric
    is normalized across the candidates before weighting. Otherwise OTIF swamps
    margin and the strategy weights don't mean what they say.
    """
    margins = normalize([o["margin"] for o in options])
    otifs = normalize([o["otif"] for o in options])
    risks = normalize([o["risk"] for o in options])
    for o, m, t, r in zip(options, margins, otifs, risks):
        o["reward"] = round((m * margin_weight + t * otif_weight - r * RISK_WEIGHT) * 100, 1)


def explain(winner, options, priority_name):
    """Build the explanation from the computed scores rather than fixed text."""
    others = [o for o in options if o is not winner]
    runner_up = max(others, key=lambda o: o["reward"])
    return (
        f"With the priority set to {priority_name}, Option {winner['label']} "
        f"({winner['name']}) scores highest at {winner['reward']}, ahead of "
        f"Option {runner_up['label']} at {runner_up['reward']}.\n"
        f"    It keeps gross margin at {winner['margin']}% with {winner['otif']}% OTIF, "
        f"at an exception cost of ${winner['cost']:,}."
    )


def main():
    print("\n" + "=" * 66)
    print("       SUPPLY-CHAIN EXCEPTION DECISION AGENT - PROTOTYPE")
    print("=" * 66 + "\n")

    print(">>> PHASE 1: NETWORK OBSERVATION")
    event = questionary.select(
        "Select an incoming network signal:",
        choices=["Supplier shipment delayed (48 hours)", "Weather event: regional hub flooded"],
    ).ask()
    slow_print(f"\n[ALERT] '{event}' detected.\n")

    print(">>> PHASE 2: STRATEGIC ALIGNMENT")
    choice = questionary.select(
        "Set the current business priority for the evaluator:", choices=list(STRATEGIES)
    ).ask()
    priority_name, m_weight, o_weight = STRATEGIES[choice]
    slow_print(f"[SYSTEM] Reward function updated for {priority_name}.\n")

    print(">>> PHASE 3: AGENTIC SCENARIO GENERATION")
    slow_print("Loading order economics...")
    agent_option, from_model = query_agent(event)

    candidates = [
        ("A", "Wait for shipment", 0, 85, 25),
        ("B", "Expedite spot freight", 10_000, 99, 0),
        ("C", f"AI: {agent_option['scenario']}", agent_option["exception_cost"],
         agent_option["otif_score"], agent_option["penalty_risk"]),
    ]
    options = [
        {"label": label, "name": name, "cost": cost, "otif": otif, "risk": risk,
         "margin": gross_margin_pct(cost)}
        for label, name, cost, otif, risk in candidates
    ]
    score_options(options, m_weight, o_weight)

    print("\n" + "-" * 66)
    print("                    TRADE-OFF EVALUATION MATRIX")
    print("-" * 66)
    print(f" {'OPT':<4}| {'STRATEGY':<30}| {'MARGIN':>7} | {'OTIF':>4} | {'SCORE':>6}")  # score: 0-100
    print("-" * 66)
    for o in options:
        print(f"  {o['label']:<3}| {o['name'][:30]:<30}| {o['margin']:>6}% | {o['otif']:>3}% | {o['reward']:>6}")
    print("-" * 66)
    if not from_model:
        print("  (Option C used fallback values; start Ollama for live generation.)")

    winner = max(options, key=lambda o: o["reward"])
    print("\n>>> SYSTEM REASONING:")
    print("    " + explain(winner, options, priority_name) + "\n")

    print(">>> PHASE 4: HUMAN-IN-THE-LOOP DECISION")
    selection = questionary.select(
        "Select the execution path:",
        choices=[f"Option {o['label']}: {o['name']}" for o in options],
        default=f"Option {winner['label']}: {winner['name']}",
    ).ask()

    print("\n>>> PHASE 5: EXECUTION (SIMULATED)")
    slow_print(f"Initiating {selection.split(':')[0]}...")
    slow_print(">> Writing inventory reallocations to the warehouse management system (WMS)...")
    slow_print(">> Updating dock appointments and routing in the transportation management system (TMS)...")
    slow_print(">> Sending SLA notifications to impacted customers...")
    print("\n[SUCCESS] Network rebalanced. Dashboards synchronized.")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
