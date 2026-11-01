import threading

from tdc.core.events import EventBus, Topic


def test_publish_subscribe_and_unsubscribe():
    bus = EventBus()
    got = []
    unsub = bus.subscribe(Topic.SESSION_UPDATED, got.append)
    bus.publish(Topic.SESSION_UPDATED, 1)
    unsub()
    unsub()  # idempotent
    bus.publish(Topic.SESSION_UPDATED, 2)
    assert got == [1]
    assert bus.subscriber_count(Topic.SESSION_UPDATED) == 0


def test_faulty_handler_does_not_break_others():
    bus = EventBus()
    got = []
    bus.subscribe("x", lambda _p: 1 / 0)
    bus.subscribe("x", got.append)
    bus.publish("x", "ok")
    assert got == ["ok"]


def test_custom_dispatcher_receives_calls():
    queued = []
    bus = EventBus(dispatcher=queued.append)
    got = []
    bus.subscribe("x", got.append)
    bus.publish("x", 5)
    assert got == [] and len(queued) == 1
    queued[0]()
    assert got == [5]


def test_publish_from_many_threads():
    bus = EventBus()
    got = []
    lock = threading.Lock()

    def handler(p):
        with lock:
            got.append(p)

    bus.subscribe("x", handler)
    threads = [threading.Thread(target=lambda i=i: [bus.publish("x", i) for _ in range(100)]) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(got) == 800
