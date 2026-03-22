#!/usr/bin/env python3
"""
Patch Zen Browser's omni.ja to disable macOS dock download progress indicator.

Workaround for a macOS Tahoe issue where the dock icon reverts from the
"Clear" icon style to full colour when a download starts. The root cause is
Firefox's nsMacDockSupport replacing the OS-managed dock tile with a static
bitmap that macOS can't apply icon styling to.

Upstream references:
  - Zen: https://github.com/zen-browser/desktop/issues/12676
  - Firefox: https://bugzilla.mozilla.org/show_bug.cgi?id=1997246

Mozilla's omni.ja stores files uncompressed. This script does a same-size
byte replacement directly in the archive, updating CRCs but not changing
any offsets. This preserves the optimised JAR structure.
"""

import argparse
import hashlib
import plistlib
import struct
import subprocess
import sys
import zlib
from pathlib import Path

OMNI_PATH = Path("/Applications/Zen.app/Contents/Resources/omni.ja")
INFO_PLIST = Path("/Applications/Zen.app/Contents/Info.plist")
DEFAULT_BACKUP_DIR = Path.home() / ".zen-dock-patch"

# The exact bytes we're replacing (must be unique in the archive)
ORIGINAL = b"this.#taskbarProgresses.add(gInterfaces.macTaskbarProgress);"
# Same length replacement - returns early before registering the progress target
REPLACEMENT = b"return;/* dock progress disabled for Tahoe icon fix      */;"

assert len(ORIGINAL) == len(REPLACEMENT), (
    f"Size mismatch: original={len(ORIGINAL)}, replacement={len(REPLACEMENT)}"
)


def get_zen_version():
    """Read the installed Zen version from Info.plist."""
    if not INFO_PLIST.exists():
        return None
    with open(INFO_PLIST, "rb") as f:
        plist = plistlib.load(f)
    return plist.get("CFBundleShortVersionString")


def get_omni_hash():
    """SHA-256 of the current omni.ja."""
    if not OMNI_PATH.exists():
        return None
    h = hashlib.sha256()
    with open(OMNI_PATH, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_status():
    """Check whether omni.ja is currently patched."""
    if not OMNI_PATH.exists():
        return "not_installed"
    with open(OMNI_PATH, "rb") as f:
        data = f.read()
    if data.find(REPLACEMENT) != -1:
        return "patched"
    if data.find(ORIGINAL) != -1:
        return "unpatched"
    return "unknown"


def backup_path_for_version(backup_dir, version, omni_hash):
    """Return the backup path, including version and hash prefix for safety."""
    hash_prefix = omni_hash[:8] if omni_hash else "unknown"
    name = f"omni-{version}-{hash_prefix}.ja" if version else f"omni-{hash_prefix}.ja"
    return backup_dir / name


def find_backup(backup_dir, omni_hash):
    """Find an existing backup matching the current omni.ja hash."""
    if not backup_dir.exists():
        return None
    for p in backup_dir.glob("omni-*.ja"):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() == omni_hash:
            return p
    return None


def find_any_backup(backup_dir):
    """Find any backup with the original (unpatched) bytes."""
    if not backup_dir.exists():
        return None
    for p in sorted(backup_dir.glob("omni-*.ja"), key=lambda x: x.stat().st_mtime, reverse=True):
        with open(p, "rb") as f:
            data = f.read()
        if data.find(ORIGINAL) != -1:
            return p
    return None


def find_local_header_for_offset(data, content_offset):
    """Scan backwards to find the ZIP local file header containing this data."""
    pos = content_offset - 1
    while pos >= 0:
        if data[pos : pos + 4] == b"PK\x03\x04":
            name_len = struct.unpack_from("<H", data, pos + 26)[0]
            extra_len = struct.unpack_from("<H", data, pos + 28)[0]
            data_start = pos + 30 + name_len + extra_len
            if data_start <= content_offset:
                return pos
        pos -= 1
    return None


def do_patch(data):
    """Apply the byte replacement and update CRCs. Returns patched data or None."""
    pos = data.find(ORIGINAL)
    if pos == -1:
        print("  ERROR: Target bytes not found in archive")
        return None

    if data.find(ORIGINAL, pos + 1) != -1:
        print("  ERROR: Target bytes found multiple times - not safe to patch")
        return None

    print(f"  Found target at byte offset {pos}")
    data[pos : pos + len(ORIGINAL)] = REPLACEMENT
    print(f"  Applied replacement ({len(REPLACEMENT)} bytes)")

    local_header = find_local_header_for_offset(data, pos)
    if local_header is None:
        print("  WARNING: Could not find local file header, skipping CRC update")
        return data

    name_len = struct.unpack_from("<H", data, local_header + 26)[0]
    extra_len = struct.unpack_from("<H", data, local_header + 28)[0]
    comp_size = struct.unpack_from("<I", data, local_header + 18)[0]
    entry_name = data[local_header + 30 : local_header + 30 + name_len].decode(
        "utf-8", errors="replace"
    )
    data_start = local_header + 30 + name_len + extra_len
    file_data = data[data_start : data_start + comp_size]

    print(f"  Entry: {entry_name}")

    new_crc = zlib.crc32(bytes(file_data)) & 0xFFFFFFFF
    old_crc = struct.unpack_from("<I", data, local_header + 14)[0]
    print(f"  CRC: 0x{old_crc:08x} -> 0x{new_crc:08x}")

    struct.pack_into("<I", data, local_header + 14, new_crc)

    eocd_pos = bytes(data).rfind(b"PK\x05\x06")
    if eocd_pos != -1:
        cd_offset = struct.unpack_from("<I", data, eocd_pos + 16)[0]
        total_entries = struct.unpack_from("<H", data, eocd_pos + 10)[0]

        cpos = cd_offset
        for i in range(total_entries):
            if data[cpos : cpos + 4] != b"PK\x01\x02":
                break
            cd_name_len = struct.unpack_from("<H", data, cpos + 28)[0]
            cd_extra_len = struct.unpack_from("<H", data, cpos + 30)[0]
            cd_comment_len = struct.unpack_from("<H", data, cpos + 32)[0]
            cd_local_offset = struct.unpack_from("<I", data, cpos + 42)[0]

            if cd_local_offset == local_header:
                struct.pack_into("<I", data, cpos + 16, new_crc)
                print(f"  Updated CRC in central directory")
                break

            cpos += 46 + cd_name_len + cd_extra_len + cd_comment_len

    return data


def cmd_status(args):
    """Show current patch status."""
    version = get_zen_version()
    status = check_status()
    print(f"Zen Browser: {version or 'not found'}")
    print(f"Patch status: {status}")
    if args.backup_dir.exists():
        backups = sorted(args.backup_dir.glob("omni-*.ja"))
        if backups:
            print(f"Backups ({len(backups)}):")
            for b in backups:
                size_mb = b.stat().st_size / (1024 * 1024)
                print(f"  {b.name} ({size_mb:.1f} MB)")


def cmd_patch(args):
    """Apply the patch."""
    if not OMNI_PATH.exists():
        print("ERROR: Zen Browser not found at /Applications/Zen.app")
        return 1

    version = get_zen_version()
    status = check_status()
    print(f"Zen Browser {version or 'unknown'}")

    if status == "patched":
        print("Already patched. Nothing to do.")
        return 0

    if status == "unknown":
        print("ERROR: omni.ja does not contain the expected bytes.")
        print("This Zen version may have changed DownloadsTaskbar.sys.mjs.")
        print("The patch script may need updating for this version.")
        return 1

    # Create backup
    omni_hash = get_omni_hash()
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_path_for_version(args.backup_dir, version, omni_hash)

    existing = find_backup(args.backup_dir, omni_hash)
    if existing:
        print(f"  Backup already exists: {existing.name}")
    else:
        import shutil

        shutil.copy2(OMNI_PATH, backup)
        print(f"  Backed up to {backup}")

    if args.dry_run:
        print("  Dry run - no changes made.")
        return 0

    # Patch
    print("Patching omni.ja...")
    with open(OMNI_PATH, "rb") as f:
        data = bytearray(f.read())

    result = do_patch(data)
    if result is None:
        return 1

    with open(OMNI_PATH, "wb") as f:
        f.write(result)

    print(f"  Written: {OMNI_PATH} ({len(result)} bytes)")
    print()
    print("Patch applied. Next steps:")
    print("  1. Quit Zen Browser completely")
    print("  2. Clear the startup cache:")
    print("     /Applications/Zen.app/Contents/MacOS/zen -purgecaches")
    print("  3. Reopen Zen normally")
    return 0


def cmd_restore(args):
    """Restore from backup."""
    if not OMNI_PATH.exists():
        print("ERROR: Zen Browser not found")
        return 1

    omni_hash = get_omni_hash()
    backup = find_any_backup(args.backup_dir)
    if not backup:
        print(f"ERROR: No unpatched backup found in {args.backup_dir}")
        return 1

    if args.dry_run:
        print(f"  Would restore from: {backup.name}")
        return 0

    import shutil

    shutil.copy2(backup, OMNI_PATH)
    print(f"  Restored from {backup.name}")
    print("  Quit Zen and run with -purgecaches to complete.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Patch Zen Browser to disable macOS dock download progress indicator.",
        epilog=(
            "Workaround for macOS Tahoe Clear icon style issue. "
            "See: https://github.com/zen-browser/desktop/issues/12676"
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"directory for backups (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be done without making changes",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("patch", help="apply the patch (default if no command given)")
    sub.add_parser("restore", help="restore omni.ja from backup")
    sub.add_parser("status", help="show current patch status and backups")

    args = parser.parse_args()

    if not args.command:
        args.command = "patch"

    if args.command == "status":
        cmd_status(args)
        return 0
    elif args.command == "patch":
        return cmd_patch(args)
    elif args.command == "restore":
        return cmd_restore(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
