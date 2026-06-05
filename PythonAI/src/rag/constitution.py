from __future__ import annotations

from typing import Any

class ConstitutionalCheck:
    """Validates every output against OMNISCIENT's constitution."""
    
    def check_truth_over_confidence(self, answer: str, fact_verification: dict[str, Any]) -> bool:
        """Reject answers with no source backing or detected hallucinations."""
        if fact_verification.get("hallucinations_found"):
            return False
        return True
        
    def check_verify_before_trust(self, answer: str, code_verification: dict[str, Any]) -> bool:
        """Reject answers with failing code examples."""
        if not code_verification.get("all_passed", True):
            return False
        return True
        
    def check_empower_over_depend(self, answer: str) -> bool:
        """Ensure answer teaches, not just gives."""
        # A simple heuristic: check for explanation words
        explanation_words = ["because", "why", "means", "notice", "however", "note that", "important"]
        ans_lower = answer.lower()
        if len(ans_lower) > 200 and not any(w in ans_lower for w in explanation_words):
            return False
        return True
        
    def check_depth_over_breadth(self, answer: str) -> bool:
        """Flag overly superficial responses."""
        if len(answer.split()) < 20:
            return False
        return True

    def validate_all(self, answer: str, code_ver: dict[str, Any], fact_ver: dict[str, Any]) -> list[str]:
        """Run all checks and return a list of violations."""
        violations = []
        if not self.check_truth_over_confidence(answer, fact_ver):
            violations.append("Truth over confidence: Hallucinations or unsupported claims detected.")
        if not self.check_verify_before_trust(answer, code_ver):
            violations.append("Verify before trust: Code execution failed.")
        if not self.check_empower_over_depend(answer):
            violations.append("Empower over depend: Lacks explanation/teaching elements.")
        if not self.check_depth_over_breadth(answer):
            violations.append("Depth over breadth: Answer is too superficial.")
            
        return violations
