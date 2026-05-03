# Model Asset Netdisk Handoff

Last updated: 2026-05-03

Model files are not pushed to GitHub. Use the netdisk copy and restore the assets to these repository-relative paths before running any generation command.

## Required Model Assets

```text
assets/models/moxing2.blend
assets/models/moxing1_test.blend
assets/models/P101040.stl
assets/models/QC7-1336.stl
assets/models/QC7-1336-white.blend
assets/models/QC7-1336-black.blend
assets/models/QC7-5236.stl
assets/models/QL3-black.blend
```

## Repository Policy

The GitHub branch contains scripts, profiles, evaluation tools, handoff documents, and the approved showcase image set only. Large or proprietary model assets remain outside the repository.

The `.gitignore` excludes the local model asset formats used by this project:

```text
assets/models/*.blend
assets/models/*.blend1
assets/models/*.stl
```

After restoring assets from netdisk, keep the paths unchanged because the generation profiles and reference scripts resolve them directly.
