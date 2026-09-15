from src.gradio_app import StreamState, apply_event, build_demo, build_payload, parse_sse_text, render_output


def test_gradio_payload_matches_stream_contract():
    assert build_payload("What is RAG?", 4, False, "llama3.2:1b", ["cs.CL"]) == {
        "query": "What is RAG?",
        "top_k": 4,
        "use_hybrid": False,
        "model": "llama3.2:1b",
        "categories": ["cs.CL"],
    }


def test_sse_parser_preserves_named_events_and_json_payloads():
    text = (
        'event: sources\ndata: {"sources":[],"citations":[]}\n\n'
        'event: delta\ndata: {"delta":"hello"}\n\n'
        'event: done\ndata: {"answer":"hello"}\n\n'
    )

    assert parse_sse_text(text) == [
        ("sources", {"sources": [], "citations": []}),
        ("delta", {"delta": "hello"}),
        ("done", {"answer": "hello"}),
    ]


def test_error_event_discards_accumulated_answer():
    state = StreamState(answer="partial answer")

    apply_event(state, "error", {"error": "failed"})

    assert state.answer == ""
    assert state.error == "failed"


def test_render_output_shows_ordered_traceability_and_sanitizes_untrusted_text():
    state = StreamState(
        answer="Finding <script>alert(1)</script> [1.1]",
        metadata={
            "citations": [
                {
                    "marker": "[1.1]",
                    "arxiv_id": "2601.00001v2",
                    "title": "Paper <img src=x onerror=alert(1)>",
                    "section_title": "Methods",
                    "section_index": 3,
                    "chunk_index": 1,
                    "evidence": "Exact <b>passage</b>",
                }
            ]
        },
    )

    rendered = render_output(state)

    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "https://arxiv.org/pdf/2601.00001.pdf" in rendered
    assert "section_index=3, chunk_index=1" in rendered
    assert "Exact &lt;b&gt;passage&lt;/b&gt;" in rendered


def test_gradio_interface_constructs_with_configured_controls(settings):
    demo = build_demo(settings)

    assert demo is not None
