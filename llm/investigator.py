from jinja2 import Template


class LLMInvestigator:
    def __init__(self, model: str = "llama3.1:8b", temperature: float = 0.1):
        self.model = model
        self.temperature = temperature
        self._load_prompt_template()

    def _load_prompt_template(self):
        with open("llm/prompts/fraud_narrative.txt") as f:
            self.template = Template(f.read())

    def investigate(self, evidence: dict) -> dict:
        pass
