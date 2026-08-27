import time
import re
import random
from typing import Tuple, List, Optional
from matini.api.schemas.chat import GuardrailCheckResult, ChatResponse
from matini.api.schemas.models import GuardrailConfig, AIModel
from matini.api.services.registry import get_model_by_id

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

def generate_mock_response(model: AIModel, prompt: str) -> str:
    """Generate intelligent mock responses tailored to the model persona."""
    if "code" in model.category.lower() or "deepseek" in model.id:
        return f"""// Verified safe execution by {model.name}
def execute_task():
    # Prompt: {prompt[:40]}...
    print("Process executed safely inside sandbox container.")
    return {{"status": "success", "engine": "{model.id}", "version": "{model.version}"}}"""
        
    elif "finance" in model.category.lower():
        return f"""[FinGuard Advisory Response]
Based on current financial analysis standards regarding "{prompt[:50]}":
1. Market diversification and risk tolerance must always be assessed.
2. Past performance is not indicative of future returns.
(Generated compliant report via {model.name})"""

    elif "security" in model.category.lower() or "sentinel" in model.id:
        return f"""[Claude Sentinel Policy Report]
Your query has been analyzed against the internal alignment guidelines:
- Prompt Intent: Compliant and verified
- Sandbox Enclosure: Active
- Safe output generated for: "{prompt}"."""

    else:
        return f"""Hello! I am {model.name}.
I've processed your prompt: "{prompt}".
All guardrail verification gates passed smoothly. How else can I assist you with your project today?"""

def process_chat(model_id: str, prompt: str) -> ChatResponse:
    total_start = time.time()
    model = get_model_by_id(model_id)
    
    if not model:
        return ChatResponse(
            model_id=model_id,
            prompt=prompt,
            response=None,
            status="error",
            guardrail_results=[],
            total_latency_ms=0.0,
        )

    guardrail_results: List[GuardrailCheckResult] = []

    # Step 1: Rule-based Guardrail Check
    rule_res = check_rule_based(prompt, model.guardrails)
    guardrail_results.append(rule_res)
    
    if not rule_res.passed:
        total_latency = round((time.time() - total_start) * 1000, 2)
        return ChatResponse(
            model_id=model.id,
            prompt=prompt,
            response=None,
            status="blocked",
            guardrail_results=guardrail_results,
            total_latency_ms=total_latency,
        )

    # Step 2: LLM-as-a-Judge Guardrail Check
    judge_res = check_llm_judge(prompt, model.guardrails)
    guardrail_results.append(judge_res)
    
    if not judge_res.passed:
        total_latency = round((time.time() - total_start) * 1000, 2)
        return ChatResponse(
            model_id=model.id,
            prompt=prompt,
            response=None,
            status="blocked",
            guardrail_results=guardrail_results,
            total_latency_ms=total_latency,
        )

    # Step 3: Model Response Generation
    mock_reply = generate_mock_response(model, prompt)
    model.calls_count += 1
    total_latency = round((time.time() - total_start) * 1000, 2)

    return ChatResponse(
        model_id=model.id,
        prompt=prompt,
        response=mock_reply,
        status="allowed",
        guardrail_results=guardrail_results,
        total_latency_ms=total_latency,
    )
