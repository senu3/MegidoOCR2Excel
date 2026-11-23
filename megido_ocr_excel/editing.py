"""Field identity, selection and recognition results owned by one editor state."""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Iterator, Sequence, overload
from uuid import uuid4

from megido_ocr_excel.models import TemplateField


@dataclass
class FieldEntry:
    field: TemplateField
    id: str = dataclass_field(default_factory=lambda: uuid4().hex)
    tested: bool = False
    raw_text: str = ''
    text: str = ''


class ResultValues:
    """Indexed view of entry results; never a separately synchronized array."""
    def __init__(self, state: EditorState, attribute: str) -> None:
        self.state = state
        self.attribute = attribute

    def __len__(self) -> int:
        return len(self.state.entries)

    @overload
    def __getitem__(self, index: int) -> str: ...
    @overload
    def __getitem__(self, index: slice) -> list[str]: ...
    def __getitem__(self, index):
        if isinstance(index, slice):
            return [getattr(entry, self.attribute) for entry in self.state.entries[index]]
        return getattr(self.state.entries[index], self.attribute)

    def __setitem__(self, index: int, value: str) -> None:
        setattr(self.state.entries[index], self.attribute, value)
        if self.attribute == "text":
            self.state.entries[index].tested = bool(value)

    def __iter__(self) -> Iterator[str]:
        return (getattr(entry, self.attribute) for entry in self.state.entries)

    def __eq__(self, other: object) -> bool:
        return list(self) == other

    def assign(self, values: Sequence[str]) -> None:
        for index, entry in enumerate(self.state.entries):
            self[index] = values[index] if index < len(values) else ''


class EditorState:
    def __init__(self) -> None:
        self.entries: list[FieldEntry] = []
        self.selected_id: str | None = None
        self.results = ResultValues(self, 'text')
        self.raw_results = ResultValues(self, 'raw_text')

    @property
    def fields(self) -> list[TemplateField]:
        return [entry.field for entry in self.entries]

    def reset(self, fields: list[TemplateField]) -> None:
        self.entries = [FieldEntry(item) for item in fields]
        self.selected_id = None

    def index_of(self, entry_id: str | None) -> int | None:
        return next((i for i, entry in enumerate(self.entries) if entry.id == entry_id), None)

    @property
    def selected_index(self) -> int | None:
        return self.index_of(self.selected_id)

    @selected_index.setter
    def selected_index(self, index: int | None) -> None:
        self.selected_id = self.entries[index].id if index is not None and 0 <= index < len(self.entries) else None

    def insert(self, index: int, item: TemplateField, *, entry_id: str | None = None,
               text: str = '', raw_text: str = '') -> None:
        entry = FieldEntry(item, text=text, raw_text=raw_text)
        if entry_id is not None:
            entry.id = entry_id
        self.entries.insert(index, entry)

    def remove(self, index: int) -> FieldEntry:
        entry = self.entries.pop(index)
        if self.selected_id == entry.id:
            self.selected_index = min(index, len(self.entries) - 1) if self.entries else None
        return entry

    def move(self, source: int, target: int) -> None:
        self.entries.insert(target, self.entries.pop(source))
