from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


USER_GUIDE_IMAGES = (
    Path("docs/images/user-guide/basic-settings.png"),
    Path("docs/images/user-guide/excel-output.png"),
    Path("docs/images/user-guide/range-and-columns.png"),
    Path("docs/images/user-guide/recognition-test-result.png"),
    Path("docs/images/user-guide/start-method.png"),
)


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
    *USER_GUIDE_IMAGES,
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
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True)
class ReleaseArtifact:
    version: str
    archive_path: Path
    checksum_path: Path
    sha256: str
    files: tuple[Path, ...]


def _version_tuple(version: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(
            "バージョンは 0.2.0 のような major.minor.patch 形式で指定してください。"
        )
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _version_texts(project_root: Path) -> tuple[str, str]:
    pyproject = (project_root / "pyproject.toml").read_bytes().decode("utf-8")
    package_init = (project_root / PACKAGE_DIR / "__init__.py").read_bytes().decode(
        "utf-8"
    )
    return pyproject, package_init


def _versions_from_texts(pyproject: str, package_init: str) -> tuple[str, str]:
    project_match = re.search(
        r"(?ms)^\[project\].*?^version\s*=\s*[\"']([^\"']+)[\"']",
        pyproject,
    )
    if project_match is None:
        raise ValueError("pyproject.toml の [project] version を取得できません。")

    package_match = re.search(
        r"(?m)^__version__\s*=\s*[\"']([^\"']+)[\"']", package_init
    )
    if package_match is None:
        raise ValueError("megido_ocr_excel.__version__ を取得できません。")

    return project_match.group(1), package_match.group(1)


def project_version(project_root: Path) -> str:
    project_version, package_version = _versions_from_texts(
        *_version_texts(project_root)
    )
    if project_version != package_version:
        raise ValueError(
            "バージョンが一致しません: "
            f"pyproject.toml={project_version}, package={package_version}"
        )
    _version_tuple(project_version)
    return project_version


def _replace_version(text: str, pattern: str, version: str, source: str) -> str:
    updated, count = re.subn(pattern, rf"\g<1>{version}\g<3>", text, count=1)
    if count != 1:
        raise ValueError(f"{source} のバージョンを書き換えられません。")
    return updated


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def update_project_version(project_root: Path, version: str) -> tuple[str, str]:
    project_root = project_root.resolve()
    requested = _version_tuple(version)
    pyproject_path = project_root / "pyproject.toml"
    package_path = project_root / PACKAGE_DIR / "__init__.py"
    pyproject, package_init = _version_texts(project_root)
    current_project, current_package = _versions_from_texts(
        pyproject, package_init
    )
    if current_project != current_package:
        raise ValueError(
            "バージョンが一致しません: "
            f"pyproject.toml={current_project}, package={current_package}"
        )
    current = _version_tuple(current_project)
    if requested < current:
        raise ValueError(
            f"現在の {current_project} より古いバージョン {version} は指定できません。"
        )
    if requested == current:
        return current_project, current_project

    updated_pyproject = _replace_version(
        pyproject,
        r'(?ms)(^\[project\].*?^version\s*=\s*[\"\'])([^\"\']+)([\"\'])',
        version,
        "pyproject.toml",
    )
    updated_package = _replace_version(
        package_init,
        r'(?m)(^__version__\s*=\s*[\"\'])([^\"\']+)([\"\'])',
        version,
        "megido_ocr_excel/__init__.py",
    )
    originals = {
        pyproject_path: pyproject.encode("utf-8"),
        package_path: package_init.encode("utf-8"),
    }
    try:
        _atomic_write_bytes(pyproject_path, updated_pyproject.encode("utf-8"))
        _atomic_write_bytes(package_path, updated_package.encode("utf-8"))
        if project_version(project_root) != version:
            raise ValueError("更新後のバージョン確認に失敗しました。")
    except Exception:
        for path, data in originals.items():
            _atomic_write_bytes(path, data)
        raise
    return current_project, version


def _refresh_uv_lock(project_root: Path) -> None:
    subprocess.run(
        ("uv", "lock"),
        cwd=project_root,
        check=True,
    )


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


def build_release(
    project_root: Path,
    output_dir: Path,
    *,
    version: str | None = None,
) -> ReleaseArtifact:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    version_paths = (
        project_root / "pyproject.toml",
        project_root / PACKAGE_DIR / "__init__.py",
        project_root / "uv.lock",
    )
    originals = (
        {path: path.read_bytes() for path in version_paths}
        if version is not None
        else None
    )
    try:
        if version is not None:
            update_project_version(project_root, version)
            _refresh_uv_lock(project_root)
        version = project_version(project_root)
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
    except Exception:
        if originals is not None:
            for path, data in originals.items():
                _atomic_write_bytes(path, data)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub Releases用のWindows配布ZIPを生成します。"
    )
    parser.add_argument(
        "--version",
        help=(
            "公開するバージョン。指定時はpyproject.toml、パッケージ、"
            "uv.lockのバージョンを一括更新します。"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="生成先（既定: dist）",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    before = project_version(project_root)
    artifact = build_release(
        project_root,
        args.output_dir,
        version=args.version,
    )

    if args.version is not None:
        print(f"Version: {before} -> {artifact.version}")
    print(f"Created: {artifact.archive_path}")
    print(f"Created: {artifact.checksum_path}")
    print(f"SHA256:  {artifact.sha256}")
    print(f"Files:   {len(artifact.files)}")
    if not any((project_root / path).is_file() for path in OPTIONAL_PUBLIC_FILES):
        print("Warning: LICENSEまたは利用条件を公開前に確認してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
