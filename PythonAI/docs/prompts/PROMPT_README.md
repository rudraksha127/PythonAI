Runtime prompt & deployment notes

- Use `RUNTIME_SYSTEM_PROMPT.txt` as the `system` prompt for inference. Keep it short.
- Always run safety and toxicity checks (TruthfulQA / BBQ) on sampled outputs.
- For medical/legal answers: show a prominent disclaimer and recommend a qualified professional.
- Do not log raw user PII; redact before storage.

Quick deployment checklist

1. Inject `RUNTIME_SYSTEM_PROMPT.txt` into the model's system role.
2. Use inference defaults: temperature 0.7, top_p 0.95; reduce `code_temperature`/`math_temperature` for deterministic tasks.
3. Run small-batch evaluations (MMLU, GSM8K, IndicGLUE) and sample red-team prompts.
4. Soft launch to limited users; monitor for unsafe or incorrect outputs; enable human escalation.
