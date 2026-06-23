from src.chat_guardrails import is_safetrace_question, safetrace_refusal


def test_safetrace_questions_are_allowed():
    assert is_safetrace_question("Which frames support Missing Helmet?")
    assert is_safetrace_question("Why is the backend queue stale?")
    assert is_safetrace_question("How do I download the technical JSON?")
    assert is_safetrace_question("Why is the packaged GGUF runtime missing?")
    assert is_safetrace_question("Where is batch upload implemented?")
    assert is_safetrace_question("Which API endpoint downloads the technical report?")


def test_out_of_scope_questions_are_rejected():
    assert not is_safetrace_question("What is the weather tomorrow?")
    assert not is_safetrace_question("Write me unrelated code")
    assert "SafeTrace" in safetrace_refusal()
