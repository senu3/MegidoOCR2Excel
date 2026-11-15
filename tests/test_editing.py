import unittest
from unittest.mock import Mock

from megido_ocr_excel.editing import EditorState
from megido_ocr_excel.models import TemplateField
from megido_ocr_excel.application import ImageOcrExcelApp


class EditingTests(unittest.TestCase):
    def test_move_keeps_results_and_selection_with_identity(self):
        state = EditorState()
        state.reset([TemplateField('same', 0, 0, 10, 10), TemplateField('same', 0, 0, 10, 10)])
        state.results.assign(['first', 'second'])
        state.raw_results.assign(['raw1', 'raw2'])
        state.selected_index = 0
        selected = state.selected_id
        state.move(0, 1)
        self.assertEqual(state.selected_id, selected)
        self.assertEqual(state.selected_index, 1)
        self.assertEqual(list(state.results), ['second', 'first'])
        self.assertEqual(list(state.raw_results), ['raw2', 'raw1'])
        removed = state.remove(1)
        state.insert(0, removed.field, entry_id=removed.id, text=removed.text, raw_text=removed.raw_text)
        self.assertEqual(state.entries[0].id, selected)
        self.assertEqual(list(state.results), ['first', 'second'])

    def test_undo_range_after_reorder_targets_same_field(self):
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        original = TemplateField('a', 0, 0, 10, 10)
        app.fields = [TemplateField('a', 5, 5, 15, 15), TemplateField('b', 20, 20, 30, 30)]
        app.status_var = Mock()
        app._set_undo('update_rect', idx=0, field=original, result='before', raw_result='raw')
        app.editor.move(0, 1)
        app._undo_updated_rect(app.undo_action)
        self.assertEqual(app.fields[1].x1, 0)
        self.assertEqual(app.fields[0].x1, 20)
        self.assertEqual(app.current_results[1], 'before')

    def test_result_refresh_does_not_recreate_review_widgets(self):
        from megido_ocr_excel.application import MODE_REVIEW
        app = ImageOcrExcelApp.__new__(ImageOcrExcelApp)
        app.fields = [TemplateField('a', 0, 0, 10, 10)]
        app.mode_var = Mock()
        app.mode_var.get.return_value = MODE_REVIEW
        app._refresh_review_row = Mock()
        app._update_review_detail_values = Mock()
        app._render_side_body = Mock()
        app.redraw = Mock()
        app._refresh_recognition_results()
        app._render_side_body.assert_not_called()
        app._update_review_detail_values.assert_called_once()
