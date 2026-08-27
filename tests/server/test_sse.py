import threading

from litreview.server.sse import EventBus


def test_replay_and_live_with_last_event_id():
    bus = EventBus()
    emitter = bus.emitter("s1")
    emitter.emit("log", message="one")
    emitter.emit("log", message="two")

    stream = bus.stream("s1", last_event_id=1)
    first = next(stream)
    assert "id: 2" in first and '"two"' in first and "event: log" in first

    # A live event arrives while subscribed.
    def later():
        emitter.emit("stage_done", stage="hunt")
    threading.Timer(0.05, later).start()
    second = next(stream)
    assert "event: stage_done" in second and '"hunt"' in second


def test_streams_are_isolated_per_survey():
    bus = EventBus()
    bus.emitter("a").emit("log", message="for-a")
    stream_b = bus.stream("b", last_event_id=0)
    bus.emitter("b").emit("log", message="for-b")
    event = next(stream_b)
    assert "for-b" in event and "for-a" not in event
