import pytest
from PySide6.QtWidgets import QDialog

from tdc.config.settings import CombatSettings, PartySettings
from tdc.core.models import CreatureReading, FrameReading, HuntMode, Measurement, Priority
from tdc.core.events import Topic
from tdc.storage.repositories import HealingRule
from tdc.ui.main_window import MainWindow
from tdc.ui.rule_editor import RuleDialog
from tdc.ui.services import Services


@pytest.fixture
def app(qtbot, ctx):
    services = Services(ctx)
    w = MainWindow(ctx, services)
    qtbot.addWidget(w)
    qtbot.addWidget(services.hud.window)
    yield ctx, services, w
    services.shutdown()


class FakeDialog:
    """Stands in for RuleDialog.exec(): returns a preset rule."""
    next_rule = None

    def __init__(self, rule, targets, parent):
        self.rule = rule

    def exec(self):
        return QDialog.Accepted if FakeDialog.next_rule else QDialog.Rejected

    def result_rule(self):
        r = FakeDialog.next_rule(self.rule)
        return r


def test_rule_dialog_validates(qtbot):
    d = RuleDialog(HealingRule(None, 1, "self", "spell", "", "health", 50, 1), ("self", "partner"))
    qtbot.addWidget(d)
    d._accept()
    assert d.result() != QDialog.Accepted and "name" in d.error.text()
    d.name.setText("Exura Gran")
    d.threshold.setValue(72)
    d._accept()
    r = d.result_rule()
    assert d.result() == QDialog.Accepted and r.name == "Exura Gran" and r.threshold == 72
    d.target.setCurrentIndex(d.target.findData("partner"))
    assert d.result_rule().resource == "health" and not d.resource.isEnabled()


def test_add_edit_delete_reorder_rules(app):
    ctx, services, w = app
    page = w.pages["Healing Assistant"]
    page.select_profile(HuntMode.SOLO)
    ed = page.editor
    ed.dialog_factory = FakeDialog
    n = len(ed.rules)
    FakeDialog.next_rule = lambda r: HealingRule(r.id, r.profile_id, "self", "spell", "Exura", "health", 90, 0, True, r.sort_order)
    ed.add()
    assert len(ed.rules) == n + 1 and ed.rules[-1].name == "Exura"
    ed.table.selectRow(len(ed.rules) - 1)
    FakeDialog.next_rule = lambda r: HealingRule(r.id, r.profile_id, r.target, r.kind, "Exura Ico", r.resource, 88, 1, True, r.sort_order)
    ed.edit_selected()
    assert ed.rules[-1].name == "Exura Ico" and ed.rules[-1].threshold == 88
    ed.table.selectRow(len(ed.rules) - 1)
    ed.move_selected(-1)
    assert ed.rules[-2].name == "Exura Ico"
    ed.table.selectRow(len(ed.rules) - 2)
    assert ed.delete_selected()
    assert len(ed.rules) == n
    # cancelled dialog changes nothing
    FakeDialog.next_rule = None
    assert ed.add() is None and len(ed.rules) == n


def test_rule_changes_reach_live_engine(app):
    ctx, services, w = app
    page = w.pages["Healing Assistant"]
    page.select_profile(HuntMode.SOLO)
    services.rules.get()          # warm the cache
    item = page.editor.table.item(0, 0)                 # disable "Exura Gran"
    from PySide6.QtCore import Qt
    item.setCheckState(Qt.Unchecked)
    assert not [r for r in services.rules.get() if r.name == "Exura Gran" and r.enabled]
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(75, 0.95), Measurement(90, 0.95)))
    assert services.hub.last_healing == []              # 75 % no longer matches anything


def test_restore_example_rules(app):
    ctx, services, w = app
    page = w.pages["Healing Assistant"]
    page.select_profile(HuntMode.DUO)
    ed = page.editor
    for r in list(ed.rules):
        ctx.healing_rules.delete(r.id)
    ed.reload()
    assert ed.rules == []
    ed.restore_defaults(confirm=False)
    assert len(ed.rules) == 7 and {r.target for r in ed.rules} == {"self", "partner"}


def test_preview(app):
    ctx, services, w = app
    page = w.pages["Healing Assistant"]
    page.select_profile(HuntMode.SOLO)
    page.sliders["health"].setValue(30)
    page.sliders["mana"].setValue(90)
    recs = page.update_preview()
    assert recs[0].text == "Cast Exura Vita" and recs[0].priority == Priority.CRITICAL
    assert not page.sliders["partner"].isEnabled()
    page.select_profile(HuntMode.DUO)
    page.sliders["partner"].setValue(20)
    assert any(r.key == "heal.partner" for r in page.update_preview())


def test_healing_page_follows_active_profile(app):
    ctx, services, w = app
    page = w.pages["Healing Assistant"]
    ctx.set_mode(HuntMode.DUO)
    assert page.selected == HuntMode.DUO


def test_combat_page_priorities_and_live(app):
    ctx, services, w = app
    page = w.pages["Combat Assistant"]
    page.name_edit.setText("Dragon Lord")
    page.prio_spin.setValue(8)
    assert page.add_priority()
    assert ctx.creatures.all() == {"Dragon Lord": 8}
    assert "Dragon Lord" in services.recognition.engine.config.matcher.names
    page.name_edit.setText("")
    assert not page.add_priority() and page.prio_error.text()
    creatures = tuple(CreatureReading(n, Measurement(hp, 0.95), 0.95, i) for i, (n, hp) in
                      enumerate((("Dragon", 90), ("Dragon Lord", 40))))
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(90, 0.95), Measurement(90, 0.95),
                                                          creatures=creatures, creatures_confidence=0.95))
    page.refresh_live()
    assert page.live_table.rowCount() == 2 and page.live_table.item(0, 0).text() == "Dragon Lord"
    assert "Priority creature: Dragon Lord" in page.combat_recs.text()
    page.prio_table.selectRow(0)
    page.remove_selected()
    assert ctx.creatures.all() == {}


def test_combat_settings_card(app):
    ctx, services, w = app
    card = w.pages["Combat Assistant"].settings_card
    card.form.editor("crowd_elevated").setValue(9)
    assert not card.save()          # critical (8) must be greater
    card.form.editor("crowd_critical").setValue(12)
    assert card.save() and ctx.config.get(CombatSettings).crowd_critical == 12


def test_party_page(app):
    ctx, services, w = app
    page = w.pages["Party Settings"]
    assert {r.target for r in page.editor.rules} == {"partner"}
    page.toggle_mode()
    assert ctx.mode == HuntMode.DUO and "Switch to Solo" == page.mode_btn.text()
    page.settings_card.form.editor("partner_name").setText("Knighty")
    assert page.settings_card.save() and ctx.config.get(PartySettings).partner_name == "Knighty"
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(90, 0.95), Measurement(90, 0.95),
                                                          Measurement(30, 0.95)))
    assert page.partner_bar.value == 30 and page.partner_bar.level == "critical"
    assert page.partner_bar.label == "Knighty"
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(90, 0.95), Measurement(90, 0.95),
                                                          Measurement(30, 0.4)))
    assert page.partner_bar.value is None


def test_hud_marks_priority_creatures(app):
    ctx, services, w = app
    ctx.creatures.set("Hydra", 4)
    ctx.bus.publish(Topic.CONFIG_CHANGED, "creatures")
    services.hud.show()
    creatures = (CreatureReading("Dragon", Measurement(90, 0.95), 0.95, 0),
                 CreatureReading("Hydra", Measurement(50, 0.95), 0.95, 1))
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(90, 0.95), Measurement(90, 0.95),
                                                          creatures=creatures, creatures_confidence=0.95))
    st = services.hud.vm.state()
    assert [c.name for c in st.creatures] == ["Hydra", "Dragon"] and st.creatures[0].priority == 4
    ctx.config.update(CombatSettings, sort_by_priority=False)
    assert [c.name for c in services.hud.vm.state().creatures] == ["Dragon", "Hydra"]


def test_notifications_are_logged(app):
    ctx, services, w = app
    ctx.bus.publish(Topic.READING_VALIDATED, FrameReading(Measurement(20, 0.95), Measurement(90, 0.95)))
    rows = services.recorder.recent()
    assert any("Exura Vita" in r["message"] and r["priority"] == 2 for r in rows)
