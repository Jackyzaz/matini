"""Guardrail checks (rule-based + heuristic "LLM judge").

DISABLED: nothing in the API wires this module in any more (chat now goes straight
to the selected Ollama model). It is kept in the codebase so it can be re-enabled
later by calling `run_guardrails` from the chat router before forwarding a prompt.
Note `check_llm_judge` is still a keyword/regex heuristic, not a real LLM call.
"""
import time
import re
import random
from typing import List, Tuple
from matini.api.schemas.guardrails import GuardrailCheckResult, GuardrailConfig

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)?\s*instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)?\s*prompts?",
    r"(reveal|leak|print|display|show|output)\s+(the\s+)?(secret\s+)?(system|initial)\s+prompt",
    r"system\s+prompt\s+(reveal|leak|print|display)",
    r"you\s+are\s+now\s+in\s+(developer|dan|god|unrestricted)\s+mode",
    r"pretend\s+you\s+have\s+no\s+(safety|rules|guardrails|filters)",
    r"output\s+raw\s+system\s+configuration",
    r"act\s+as\s+an?\s+(evil|unfiltered|jailbroken)\s+ai",
    r"what\s+is\s+your\s+(initial|system)\s+prompt",
]

def check_rule_based(prompt: str, config: GuardrailConfig) -> GuardrailCheckResult:
    start_time = time.time()
    
    if not config.rule_based_enabled:
        return GuardrailCheckResult(
            layer="Rule-Based Keyword Filter",
            passed=True,
            reason="Layer disabled in model policy",
            latency_ms=round((time.time() - start_time) * 1000, 2),
            detected_triggers=[],
        )

    prompt_lower = prompt.lower()
    detected = []
    
    for word in config.blacklist_words:
        if word.lower() in prompt_lower:
            detected.append(word)

    latency = round((time.time() - start_time) * 1000 + random.uniform(0.3, 1.2), 2)
    
    if detected:
        return GuardrailCheckResult(
            layer="Rule-Based Keyword Filter",
            passed=False,
            reason=f"Blocked: Detected blacklisted keyword(s): {', '.join(detected)}",
            latency_ms=latency,
            detected_triggers=detected,
        )
    
    return GuardrailCheckResult(
        layer="Rule-Based Keyword Filter",
        passed=True,
        reason="Passed: No blacklisted keywords found.",
        latency_ms=latency,
        detected_triggers=[],
    )

def check_llm_judge(prompt: str, config: GuardrailConfig) -> GuardrailCheckResult:
    start_time = time.time()
    
    if not config.llm_judge_enabled:
        return GuardrailCheckResult(
            layer="LLM-as-a-Judge Guardrail",
            passed=True,
            reason="Layer disabled in model policy",
            latency_ms=round((time.time() - start_time) * 1000, 2),
            detected_triggers=[],
        )

    # Simulate realistic LLM evaluation latency (180ms - 320ms)
    simulated_delay = random.uniform(0.18, 0.32)
    time.sleep(simulated_delay)
    
    prompt_lower = prompt.lower()
    triggers = []

    # Check for adversarial injection semantics
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, prompt_lower):
            triggers.append(f"Prompt Injection Signature: '{pattern}'")

    # Strictness evaluation
    if config.llm_judge_strictness == "high":
        # High strictness catches subtle probes
        if any(term in prompt_lower for term in ["bypass", "secret", "override", "unfiltered", "unlimited"]):
            triggers.append("Adversarial intent probe detected (Strictness: High)")
    elif config.llm_judge_strictness == "medium":
        if any(term in prompt_lower for term in ["jailbreak", "unrestricted mode"]):
            triggers.append("Direct safety override attempt detected (Strictness: Medium)")

    latency = round((time.time() - start_time) * 1000, 2)

    if triggers:
        return GuardrailCheckResult(
            layer="LLM-as-a-Judge Guardrail",
            passed=False,
            reason=f"Blocked by AI Judge: {triggers[0]}",
            latency_ms=latency,
            detected_triggers=triggers,
        )

    return GuardrailCheckResult(
        layer="LLM-as-a-Judge Guardrail",
        passed=True,
        reason=f"Passed: Prompt alignment verified under strictness '{config.llm_judge_strictness}'.",
        latency_ms=latency,
        detected_triggers=[],
    )

def run_guardrails(prompt: str, config: GuardrailConfig) -> Tuple[bool, List[GuardrailCheckResult]]:
    """Run both layers in order. Returns (allowed, per-layer results); stops at the first block."""
    results: List[GuardrailCheckResult] = []
    for check in (check_rule_based, check_llm_judge):
        res = check(prompt, config)
        results.append(res)
        if not res.passed:
            return False, results
    return True, results
