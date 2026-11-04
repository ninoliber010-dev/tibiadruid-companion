from tdc.core.events import EventBus, Topic
from tdc.core.models import Notification, Priority
from tdc.notifications.recorder import EventRecorder


def test_notifications_are_recorded(mem_db):
    bus = EventBus()
    rec = EventRecorder(mem_db, bus, session_id=lambda: None)
    bus.publish(Topic.NOTIFICATION, Notification("heal.self", Priority.CRITICAL, "Critical", "Cast Exura Vita — Health 30% < 35%", "healing"))
    bus.publish(Topic.NOTIFICATION, Notification("combat.crowd", Priority.ELEVATED, "Warning", "6 creatures", "combat"))
    rows = rec.recent()
    assert [r["category"] for r in rows] == ["combat", "healing"]
    assert rows[1]["priority"] == 2 and "Exura Vita" in rows[1]["message"]


def test_prune_keeps_newest(mem_db):
    rec = EventRecorder(mem_db, EventBus())
    for i in range(30):
        rec.record(Notification(f"k{i}", Priority.NORMAL, "Info", f"m{i}", "session"))
    rec.prune(keep=10)
    rows = rec.recent(100)
    assert len(rows) == 10 and rows[0]["message"] == "m29" and rows[-1]["message"] == "m20"


def test_recording_errors_do_not_raise(mem_db):
    rec = EventRecorder(mem_db, EventBus())
    mem_db.close()
    rec.record(Notification("x", Priority.NORMAL, "Info", "m", "session"))   # logged, not raised
