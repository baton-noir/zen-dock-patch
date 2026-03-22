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

**Important:** Open Zen at least once before running the patch. macOS needs to approve the app through Gatekeeper first. If you patch a fresh download before opening it, macOS will flag it as "damaged" and refuse to launch it.

Quit Zen, then paste this into Terminal:

```sh
curl -sL https://raw.githubusercontent.com/baton-noir/zen-dock-patch/main/patch.py | python3 -
```

Or if you prefer to clone first:

```sh
git clone https://github.com/baton-noir/zen-dock-patch.git
cd zen-dock-patch
python3 patch.py
```

Other commands (run from inside the cloned repo):

```sh
python3 patch.py status    # check current patch status
python3 patch.py restore   # restore original omni.ja from backup
python3 patch.py --dry-run # preview without making changes
python3 patch.py --verbose # show technical details
```

The script will:
1. Check that Zen has been opened before (Gatekeeper-approved) and is not running
2. Back up the original `omni.ja` (first run only)
3. Apply the patch and verify it was written correctly
4. Re-sign the app bundle so macOS doesn't flag it as damaged
5. Clear the startup cache automatically

**You need to re-run this after every Zen update**, since updates replace `omni.ja`.

## Backups

Backups are stored in `~/Library/Application Support/zen-dock-patch/` with the Zen version and a hash prefix in the filename (e.g. `omni-1.19.3b-4887abe5.ja`). Use `patch.py status` to list them and `patch.py restore` to roll back.

## Upstream status

A proper fix has been proposed upstream:

- Zen: [#12676](https://github.com/zen-browser/desktop/issues/12676)
- Firefox: [Bug 1997246](https://bugzilla.mozilla.org/show_bug.cgi?id=1997246)

Once either ships a fix, this tool will be unnecessary.

## License

[MIT](LICENSE)
