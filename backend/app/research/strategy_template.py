"""Strategy template generator for research notebooks or code."""

from __future__ import annotations

from textwrap import dedent


class StrategyTemplate:
    """Creates a starter strategy skeleton with hooks for signals and risk."""

    @staticmethod
    def generate(name: str = "sample_strategy") -> str:
        return dedent(
            f'''
            class {name}:
                def __init__(self, params=None):
                    self.params = params or {{}}

                def on_bar(self, bar):
                    # bar: dict with open/high/low/close/volume
                    signal = None  # return 'buy'/'sell'/None
                    return signal

                def position_size(self, capital, price):
                    return max(1, int((capital * 0.02) / max(price, 1)))
            '''
        ).strip()
