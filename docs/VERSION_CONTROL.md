# FatehPOS - Version Control System

This document explains the version control mechanism implemented in FatehPOS.

## Overview

FatehPOS uses a comprehensive version control system that tracks both application versions and build versions for effective cache busting and version management.

## Version Types

### 1. Application Version
- Defined in: `pos_next/__init__.py`
- Format: Semantic Versioning (MAJOR.MINOR.PATCH)
- Example: `1.0.0`
- Used for: Release tracking, compatibility checks

### 2. Build Version
- Generated during: Frontend build process
- Format: Timestamp (milliseconds since epoch)
- Example: `1730043123456`
- Stored in: `pos_next/public/pos/version.json`
- Used for: Cache busting, ensuring users get latest assets

## How It Works

### Build Process

1. **Vite Build Plugin** (`POS/vite.config.js`):
   ```javascript
   const buildVersion = process.env.POS_NEXT_BUILD_VERSION || Date.now().toString()
   ```
   - Generates unique build version
   - Writes to `version.json` after build completes
   - Includes version, timestamp, and build date

2. **Version File** (`pos_next/public/pos/version.json`):
   ```json
   {
     "version": "1730043123456",
     "timestamp": "2025-10-27T12:45:23.456Z",
     "buildDate": "October 27, 2025"
   }
   ```

3. **Backend Integration** (`pos_next/utils.py`):
   - `get_build_version()` - Returns current build version
   - `get_app_version()` - Returns application version
   - Fallback strategies for missing version files

4. **Hooks Integration** (`pos_next/hooks.py`):
   ```python
   _asset_version = get_build_version()
   # app_include_js = f"/assets/pos_next/js/app.js?v={_asset_version}"
   ```

## Version Bumping

### Manual Version Bump

Use the provided script to bump versions:

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next

# Bump patch version (1.0.0 → 1.0.1)
./scripts/version-bump.sh patch

# Bump minor version (1.0.1 → 1.1.0)
./scripts/version-bump.sh minor

# Bump major version (1.1.0 → 2.0.0)
./scripts/version-bump.sh major
```

The script will:
1. Update `pos_next/__init__.py`
2. Update `POS/package.json`
3. Display next steps for committing and tagging

### Build with Custom Version

You can specify a custom build version:

```bash
cd POS
POS_NEXT_BUILD_VERSION=1.2.3 yarn build
```

## Release Process

### Standard Release

1. **Bump Version**:
   ```bash
   ./scripts/version-bump.sh patch  # or minor/major
   ```

2. **Build Frontend**:
   ```bash
   cd POS
   yarn build
   ```

3. **Verify Build**:
   ```bash
   cat ../pos_next/public/pos/version.json
   ```

4. **Commit Changes**:
   ```bash
   git add .
   git commit -m "chore: bump version to 1.0.1"
   ```

5. **Tag Release**:
   ```bash
   git tag v1.0.1
   git tag -a v1.0.1 -m "Release version 1.0.1"  # annotated tag
   ```

6. **Push to Repository**:
   ```bash
   git push origin develop
   git push origin v1.0.1
   ```

### Semantic Versioning Guidelines

- **MAJOR** (X.0.0): Breaking changes, incompatible API changes
- **MINOR** (1.X.0): New features, backwards-compatible
- **PATCH** (1.0.X): Bug fixes, backwards-compatible

## Cache Busting

### How Cache Busting Works

1. Each build generates a unique build version (timestamp)
2. Assets are served with version query parameter: `?v=BUILD_VERSION`
3. When new build is deployed, version changes
4. Browser fetches new assets automatically

### Verification

Check current build version:

```bash
# Via bench console
cd /home/ubuntu/frappe-bench
bench --site nexus.local execute pos_next.utils.get_build_version

# Via Python
python3 -c "import sys; sys.path.insert(0, 'apps/pos_next'); from pos_next.utils import get_build_version; print(get_build_version())"
```

## File Structure

```
pos_next/
├── pos_next/
│   ├── __init__.py              # App version (__version__ = "1.0.0")
│   ├── hooks.py                 # Hooks with version integration
│   ├── utils.py                 # Version utility functions
│   └── public/
│       └── pos/
│           └── version.json     # Build version (generated)
├── POS/
│   ├── package.json             # Frontend version
│   └── vite.config.js           # Build version plugin
└── scripts/
    └── version-bump.sh          # Version bump utility
```

## Troubleshooting

### Version Not Updating

1. **Check version.json exists**:
   ```bash
   ls -la pos_next/public/pos/version.json
   ```

2. **Rebuild frontend**:
   ```bash
   cd POS
   yarn build
   ```

3. **Clear browser cache**:
   - Hard refresh (Ctrl+F5 / Cmd+Shift+R)
   - Clear site data in DevTools

### Build Version Shows Fallback

If `get_build_version()` returns format like `1.0.0-1730043123`:
- This means `version.json` is missing
- Frontend needs to be rebuilt
- Run: `cd POS && yarn build`

### Version Mismatch

If frontend and backend versions don't match:
1. Ensure both files are updated
2. Run version bump script
3. Rebuild frontend
4. Restart bench if necessary

## API Reference

### Python API

```python
from pos_next.utils import get_build_version, get_app_version

# Get current build version for cache busting
build_ver = get_build_version()  # Returns: "1730043123456"

# Get application version
app_ver = get_app_version()      # Returns: "1.0.0"
```

### JavaScript API

```javascript
// Build version is available as constant
console.log(__BUILD_VERSION__)  // "1730043123456"
```

## Best Practices

1. **Always build after version bump**: Ensure version.json is regenerated
2. **Use semantic versioning**: Follow MAJOR.MINOR.PATCH convention
3. **Tag releases**: Create git tags for each version
4. **Document changes**: Update CHANGELOG.md with each release
5. **Test locally**: Verify version changes before pushing

## Key Features

- Uses timestamp-based build versions
- Vite plugin generates version.json
- Backend utility functions for version retrieval
- Cache busting through query parameters
- **Location**: FatehPOS uses `public/pos/` for build assets
- **Fallback**: FatehPOS checks manifest.webmanifest mtime as additional fallback
- **Script**: FatehPOS includes automated version bump script
- **Documentation**: FatehPOS has comprehensive version management guide

## Future Enhancements

- [ ] Automated version bumping via CI/CD
- [ ] Changelog generation from git commits
- [ ] Version API endpoint for runtime checking
- [ ] Frontend version display in UI
- [ ] Version compatibility checks
