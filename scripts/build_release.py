from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PUBLIC_FILES = (
    Path(".python-version"),
    Path("MegidoOCR2Excel.cmd"),
    Path("README.md"),
    Path("docs/USER_GUIDE.md"),
    Path("launcher.py"),
    Path("main.py"),
    Path("pyproject.toml"),
    Path("run_app.ps1"),
    Path("uv.lock"),
)
OPTIONAL_PUBLIC_FILES = (
    Path("LICENSE"),
    Path("LICENSE.md"),
    Path("LICENSE.txt"),
    Path("NOTICE"),
    Path("THIRD_PARTY_NOTICES.md"),
)
PACKAGE_DIR = Path("megido_ocr_excel")
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReleaseArtifact:
    version: str
    archive_path: Path
    checksum_path: Path
    sha256: str
    files: tuple[Path, ...]


def _project_version(project_root: Path) -> str:
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    project_match = re.search(
        r"(?ms)^\[project\].*?^version\s*=\s*[\"']([^\"']+)[\"']",
        pyproject,
    )
    if project_match is None:
        raise ValueError("pyproject.toml の [project] version を取得できません。")

    package_init = (project_root / PACKAGE_DIR / "__init__.py").read_text(
        encoding="utf-8"
    )
    package_match = re.search(
        r"(?m)^__version__\s*=\s*[\"']([^\"']+)[\"']", package_init
    )
    if package_match is None:
        raise ValueError("megido_ocr_excel.__version__ を取得できません。")

    project_version = project_match.group(1)
    package_version = package_match.group(1)
    if project_version != package_version:
        raise ValueError(
            "バージョンが一致しません: "
            f"pyproject.toml={project_version}, package={package_version}"
        )
    return project_version


def collect_release_files(project_root: Path) -> tuple[Path, ...]:
    missing = [path for path in PUBLIC_FILES if not (project_root / path).is_file()]
    if missing:
        joined = ", ".join(path.as_posix() for path in missing)
        raise FileNotFoundError(f"配布に必要なファイルがありません: {joined}")

    package_root = project_root / PACKAGE_DIR
    if not package_root.is_dir():
        raise FileNotFoundError(f"配布に必要なフォルダーがありません: {PACKAGE_DIR}")

    files = set(PUBLIC_FILES)
    files.update(
        path.relative_to(project_root)
        for path in package_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
    )
    files.update(
        path for path in OPTIONAL_PUBLIC_FILES if (project_root / path).is_file()
    )
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


def _archive_member(root_name: str, relative_path: Path) -> str:
    return str(PurePosixPath(root_name, *relative_path.parts))


def _write_archive(
    project_root: Path,
    archive_path: Path,
    root_name: str,
    files: tuple[Path, ...],
) -> None:
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative_path in files:
            member = _archive_member(root_name, relative_path)
            info = zipfile.ZipInfo(member, date_time=ARCHIVE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                (project_root / relative_path).read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def validate_release_archive(
    archive_path: Path,
    root_name: str,
    expected_files: tuple[Path, ...],
) -> None:
    expected = {
        _archive_member(root_name, relative_path) for relative_path in expected_files
    }
    with zipfile.ZipFile(archive_path) as archive:
        actual = set(archive.namelist())
        bad_paths = [
            name
            for name in actual
            if PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "__pycache__" in PurePosixPath(name).parts
            or PurePosixPath(name).suffix.lower() in {".pyc", ".pyo"}
        ]
        if bad_paths:
            raise ValueError(f"ZIP内に不正なパスがあります: {bad_paths}")
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            raise ValueError(
                f"ZIP内容が一致しません。missing={missing}, unexpected={unexpected}"
            )
        bad_file = archive.testzip()
        if bad_file is not None:
            raise ValueError(f"ZIPのCRC検査に失敗しました: {bad_file}")


def build_release(project_root: Path, output_dir: Path) -> ReleaseArtifact:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    version = _project_version(project_root)
    files = collect_release_files(project_root)
    root_name = f"MegidoOCR2Excel-v{version}-Windows"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{root_name}.zip"
    checksum_path = output_dir / f"{root_name}.sha256"

    _write_archive(project_root, archive_path, root_name, files)
    validate_release_archive(archive_path, root_name, files)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii", newline="\n"
    )
    return ReleaseArtifact(version, archive_path, checksum_path, digest, files)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub Releases用のWindows配布ZIPを生成します。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="生成先（既定: dist）",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    artifact = build_release(project_root, args.output_dir)

    print(f"Created: {artifact.archive_path}")
    print(f"Created: {artifact.checksum_path}")
    print(f"SHA256:  {artifact.sha256}")
    print(f"Files:   {len(artifact.files)}")
    if not any((project_root / path).is_file() for path in OPTIONAL_PUBLIC_FILES):
        print("Warning: LICENSEまたは利用条件を公開前に確認してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
