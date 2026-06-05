import re

def extract_code_blocks(text: str) -> list[str]:
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    return blocks
