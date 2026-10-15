"""Offline translation-only worker package boundary.

This package owns the one loopback client for the pinned TranslateGemma runtime, the
deterministic selector of missing representative teaching-text cells, and the resumable
output worker.
"""
