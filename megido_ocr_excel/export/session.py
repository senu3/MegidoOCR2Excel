"""Shared output ownership, change detection and image-level retry planning."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from pathlib import Path

from megido_ocr_excel.export.rows import ExportResult, ImageExportRecord, RowRecognizer
from megido_ocr_excel.operations import raise_if_cancelled


def file_digest(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def assert_unchanged(path: Path, expected: str) -> None:
    if file_digest(path) != expected:
        raise ValueError('出力ファイルが変更されています。別の出力先へ全画像を出力してください。')


def structure_signature(settings, fields, definition) -> tuple:
    return (
        tuple(asdict(settings).items()), repr(asdict(definition)),
        tuple((f.name, f.set_id, f.slot_key) for f in fields),
    )


def seal_result(result: ExportResult, path: Path, signature: tuple) -> ExportResult:
    result.output_digest = file_digest(path)
    result.output_path = str(path.resolve())
    result.output_signature = signature
    return result


def validate_retry(result: ExportResult, path: Path, signature: tuple) -> None:
    if (not result.output_digest or result.output_path != str(path.resolve())
            or result.output_signature != signature):
        raise ValueError('前回の出力情報と一致しません。全画像を出力し直してください。')
    assert_unchanged(path, result.output_digest)


def recognize_retry(recognizer: RowRecognizer, previous: ExportResult, fields, settings,
                    ocr_callback, definition, set_resolver=None, retry_files=None,
                    progress_callback=None, cancel_check=None) -> ExportResult:
    targets = set(retry_files) if retry_files is not None else None
    retries = [r for r in previous.failed_records if targets is None or r.image_path in targets]
    updated = {}
    for index, record in enumerate(retries, 1):
        raise_if_cancelled(cancel_check)
        rows, errors, notices = recognizer.recognize_image_rows(
            record.image_path, fields, settings, ocr_callback, definition, set_resolver, cancel_check,
        )
        updated[record.image_path] = ImageExportRecord(record.image_path, 0, len(rows), errors, notices, rows)
        if progress_callback:
            progress_callback(index, len(retries), record.image_path)
    raise_if_cancelled(cancel_check)
    cursor = previous.records[0].start_row if previous.records else 1
    records = []
    for old in previous.records:
        record = replace(updated.get(old.image_path, old), start_row=cursor)
        records.append(record)
        cursor += record.row_count
    return ExportResult(previous.total_images,
                        [error for r in records for error in r.errors], records,
                        [notice for r in records for notice in r.notices])
