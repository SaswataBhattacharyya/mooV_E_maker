# Reasoning provider switch backup

- Created before website/backend implementation: 2026-09-26 UTC
- Archive: `/tmp/story-builder-provider-switch-backup-20260926.tar.gz`
- SHA-256: `964483154c04a9cf2479c82c0db3d6c874950ea2441edad8f9c74863e070ea03`
- Git revision: unavailable; this workspace does not expose a usable Git repository.

The archive contains the pre-change API and service source, frontend source,
frontend package manifest/lockfile/Vite config, and `run_story_builder.sh`.
It excludes local credentials, model weights, runtime storage, and dependency
directories.

Restore from the project directory only if rollback is needed:

```bash
tar -xzf /tmp/story-builder-provider-switch-backup-20260926.tar.gz -C /home/riki/web_dev/story_builder
```

This restores those archived paths to their pre-change contents. It does not
remove files created after the backup.
