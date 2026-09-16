/**
 * Example custom cases. Copy to evals/custom-cases.ts and add YOUR OWN 5+.
 *
 * These run as an extra suite (`make eval-dev` picks them up automatically).
 * Write cases for edges YOU found while building: ambiguous users, injection
 * attempts, missing data, multi-turn follow-ups, pagination, sandbox abuse.
 *
 * Grading: we read these. Good custom cases signal product judgment — they show
 * you thought about what could go wrong, not just what the public suite checks.
 */
import type { EvalCase } from "../src/eval-cases";

export const CUSTOM_CASES: EvalCase[] = [
  {
    name: "custom: ambiguous user clarification",
    turns: ["What plan is Alex on?"],
    expectedAnswer: "Ask which Alex (Alex Chen C234 vs Alexandra Chen C235).",
    expectedWhy: "Example custom case: agent should clarify, not guess.",
    category: "custom",
    responseFactGroups: [["C234", "Alex Chen"], ["C235", "Alexandra"]],
  },
  // TODO (candidate): add 4+ more of your own. Delete this example if you want.
];
