# supply-chain-decision-agent

A prototype decision-support agent for supply-chain exceptions. When a
disruption hits a distribution network (a delayed supplier shipment, a
flooded regional hub), the agent generates a resolution option with a local
LLM, scores it against baseline options using a reward function tuned to the
business's current priority, explains the trade-off, and asks a human to
approve before execution.

The scenario is a consumer-goods distributor balancing two metrics that pull
against each other: **gross margin** and **OTIF** (on-time-in-full delivery,
which drives retailer SLA penalties).

## How it works

1. **Observe** — pick an incoming network signal.
2. **Align** — pick the business priority (cash flow, balanced, or service).
   This sets the weights in the reward function.
3. **Generate and score** — a local model (via [Ollama](https://ollama.com))
   proposes a resolution as structured JSON. It's scored alongside two
   baselines (wait for the shipment; expedite with spot freight):

   ```
   score = 100 × (norm_margin × margin_weight + norm_OTIF × otif_weight − 0.1 × norm_risk)
   ```

   Each metric is min-max normalized across the candidate options first, so
   margin (~5–15%) and OTIF (~85–99%) are weighted on the same 0–1 scale.

4. **Explain** — the agent shows a trade-off matrix and explains, from the
   computed scores, why the top option wins.
5. **Human-in-the-loop** — a person approves the execution path (the top
   option is preselected).
6. **Execute (simulated)** — prints the writes a real system would make to
   the warehouse and transportation management systems and customer
   notifications.

## Running it

```bash
pip install -r requirements.txt
ollama pull phi3.5
python decision_agent.py
```

If Ollama isn't running, the agent says so and uses a fallback option, so
the flow can still be demoed.

## Design decisions

- **The model proposes; deterministic code decides.** The LLM generates a
  candidate in a strict JSON schema, and scoring is plain arithmetic. That
  keeps the recommendation auditable, which matters when it moves inventory
  and money.
- **Strategy as a tunable reward.** The same disruption has different right
  answers depending on whether the business is protecting cash or service
  levels, so priority is an explicit input rather than buried in a prompt.
- **Explanations come from the numbers.** The reasoning text is built from
  the scores, so it can't contradict the matrix.
- **A human approves every action.** The agent recommends; a person commits.

## Known limitations and next steps

- **Normalization is relative to the candidates.** Min-max scaling ranks
  options against each other, so adding or removing a candidate can shift
  scores. A production version would normalize against business targets
  (e.g., a margin floor and an OTIF commitment) instead.
- **The model's proposal is constrained.** For a repeatable demo, the prompt
  fixes the cost and OTIF values the model returns. A real agent would derive
  them from live inventory, lanes and contracts via tool calls.
- **Order economics are hardcoded** where a real system would query the ERP.
- **Execution is simulated.** Next step: tool calls into WMS/TMS sandboxes,
  plus an eval set of historical disruptions to measure recommendation
  quality against what planners actually chose.

## Changelog

- **v2** — Normalized metrics before weighting. In v1, margin and OTIF were
  summed on their raw scales, so OTIF swamped margin and the strategy weights
  didn't mean what they said. Explanations are now generated from the
  computed scores (v1 used fixed text that could contradict the matrix), and
  the agent now flags when it falls back from the local model instead of
  failing silently.
- **v1** — Initial prototype.

## Author

Built by [Balaji Kamakoti](https://www.linkedin.com/in/balaji-k-2291ab71/).
