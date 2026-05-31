from yuki.backend.routers.route import _heuristic_route


def test_heuristic_action_verbs_go_control():
    assert _heuristic_route("open whatsapp and message saran") == "control"
    assert _heuristic_route("click the submit button") == "control"


def test_heuristic_questions_go_chat():
    assert _heuristic_route("what is the capital of france") == "chat"
    assert _heuristic_route("explain how tcp works") == "chat"
