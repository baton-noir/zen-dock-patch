# zen-dock-patch

Patches [Zen Browser](https://zen-browser.app) on macOS to disable the dock download progress indicator, preserving the Tahoe "Clear" icon style.

## The problem

On macOS Tahoe (26), System Settings lets you choose a "Clear" (monochrome/transparent) icon style. Zen's dock icon renders correctly in Clear style - until you download a file. Firefox's `nsMacDockSupport` replaces the OS-managed dock tile with a custom `NSView` containing a static bitmap and a progress bar. macOS can't apply Clear styling to this bitmap, so the icon reverts to full colour and stays that way until you restart the Dock.

There's no `about:config` preference to disable this. The progress indicator is registered unconditionally in `DownloadsTaskbar.sys.mjs`.

This also affects stock Firefox (tracked as [Bug 1997246](https://bugzilla.mozilla.org/show_bug.cgi?id=1997246)).

## What this does

The script patches `omni.ja` (the main resource archive in Zen's app bundle) to skip the macOS dock progress registration. It does a same-size byte replacement directly in the archive and updates the ZIP CRC checksums. Downloads still work normally - only the dock progress bar is suppressed.

## Usage

Requires Python 3.6+ (ships with macOS).

```sh
# Apply the patch (auto-backs up omni.ja first)
python3 patch.py

# Check status
python3 patch.py status

# Restore the original omni.ja from backup
python3 patch.py restore

# Preview without making changes
python3 patch.py --dry-run
```

After patching, quit Zen completely and clear the startup cache:

```sh
/Applications/Zen.app/Contents/MacOS/zen -purgecaches
```

Then reopen Zen normally.

**You need to re-run this after every Zen update**, since updates replace `omni.ja`.

## Backups

Backups are stored in `~/.zen-dock-patch/` with the Zen version and a hash prefix in the filename (e.g. `omni-1.19.3b-4887abe5.ja`). Use `patch.py status` to list them and `patch.py restore` to roll back.

## Upstream status

A proper fix has been proposed upstream:

- Zen: [#12676](https://github.com/zen-browser/desktop/issues/12676)
- Firefox: [Bug 1997246](https://bugzilla.mozilla.org/show_bug.cgi?id=1997246)

Once either ships a fix, this tool will be unnecessary.

## License

[MIT](LICENSE)
