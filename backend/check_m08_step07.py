"""STEP-07 smoke test — service layer structure and human gate contracts."""
from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

# Error class
err = ExamServiceError("TEST", "test message", 400)
assert err.code        == "TEST"
assert err.message     == "test message"
assert err.status_code == 400

# All public methods present
assert callable(ExamService.create)
assert callable(ExamService.get)
assert callable(ExamService.get_questions)
assert callable(ExamService.list_for_faculty)
assert callable(ExamService.list_board_pending)
assert callable(ExamService.list_all)
assert callable(ExamService.get_blooms_report)
assert callable(ExamService.update_question)
assert callable(ExamService.delete_question)
assert callable(ExamService.submit_for_review)   # GATE 1
assert callable(ExamService.board_decide)         # GATE 2
assert callable(ExamService.seal)                 # GATE 3
assert callable(ExamService.release)              # system auto-release

print("ExamService: all methods present. OK")

# Verify gate methods are separate functions (not the same accidentally)
import inspect
methods = [
    ExamService.submit_for_review,
    ExamService.board_decide,
    ExamService.seal,
    ExamService.release,
]
names = [m.__name__ for m in methods]
assert len(set(names)) == len(names), "Gate methods must be distinct"

print("Human gates: distinct static methods. OK")
print("All STEP-07 assertions passed.")
