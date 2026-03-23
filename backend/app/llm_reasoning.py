"""
llm_reasoning.py
Claude AI integration for reasoning layer.
"""
import os
import requests

# Claude API endpoint and key (replace with your actual key)
CLAUDE_API_URL = os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "your-claude-api-key")

class ClaudeReasoner:
    def __init__(self, api_url=CLAUDE_API_URL, api_key=CLAUDE_API_KEY):
        self.api_url = api_url
        self.api_key = api_key

    def reason(self, ml_outputs, technical_signals):
        """
        Send ML outputs and technical signals to Claude, get decision and explanation.
        Args:
            ml_outputs (dict): ML model predictions
            technical_signals (dict): Technical indicators
        Returns:
            dict: { 'decision': str, 'confidence': float, 'explanation': str }
        """
        prompt = self._build_prompt(ml_outputs, technical_signals)
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        data = {
            "model": "claude-2.1",
            "max_tokens": 512,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return self._parse_response(result)

    def _build_prompt(self, ml_outputs, technical_signals):
        return (
            "You are an expert trading assistant.\n"
            "Review the following ML model outputs and technical signals.\n"
            "Decide whether to place a trade, your confidence level (0-1), and explain your reasoning in plain English.\n"
            f"ML Outputs: {ml_outputs}\n"
            f"Technical Signals: {technical_signals}\n"
        )

    def _parse_response(self, result):
        # Parse Claude's response for decision, confidence, and explanation
        content = result['choices'][0]['message']['content']
        # Simple parsing, can be improved with structured output
        return {
            'decision': content,
            'confidence': None,
            'explanation': content
        }
