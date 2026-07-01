# UI Build Preview

Use this when frontend changes are present in source but hard to see in the local ASGI app.

1. From the repo root, run:

```powershell
npm run build
```

This repo keeps the Vite config at the project root and points Vite at `frontend/`.

2. The `postbuild` step rewrites Vite hashes into deterministic content-hash assets. After a build, `public/index.html`, `public/legacy.html`, and `public/.vite/manifest.json` may change to reference the new asset files.

3. For local preview, do not immediately run `git restore public/index.html public/.vite/manifest.json public/legacy.html`. The ASGI static gateway serves those built files.

4. Restart the local app if needed, then open:

```powershell
http://127.0.0.1:8765
```

Hard refresh with `Ctrl+Shift+R`.

5. Check the board meta for the small `UI bundle loaded` stamp. It includes the loaded outlier asset name when the browser exposes it.

6. After preview, restore generated public files only if they are not intended to be committed.

Optional helper:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\preview_frontend_build.ps1
```
