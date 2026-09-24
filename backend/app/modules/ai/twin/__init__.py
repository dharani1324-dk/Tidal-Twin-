"""TidalTwin - Model-Observation Twin Intelligence Engine.

Reusable, data-transparent engine that compares numerical model
expectations against real in-situ observations for any location,
depth, time and ocean variable; scores confidence from meaningful
factors; explains anomalies; detects events; and produces
decision-support intelligence.

No value is ever fabricated: every result carries a ``data_status``
(``live`` / ``recent`` / ``cached`` / ``demo`` / ``derived`` /
``unavailable``) so the UI can be honest about what is real and what
is a clearly-labelled fallback.
"""