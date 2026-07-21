"""Presentation rendering support for M03 course-kit exports.

Phase 0-1 of docs/course-kit-presentation-architecture.md: the diagram renderer
and the measured layout primitives. The `PresentationGenerator` protocol and the
SlideSpec IR (phase 2) will land on top of these — they are the pieces that had
to be right first, because the IR should be designed against renderers that
work.
"""
from app.modules.m03_course_kit.presentation.theme import Palette, Theme, TypeScale

__all__ = ["Theme", "Palette", "TypeScale"]
