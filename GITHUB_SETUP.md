# Push this project to a temporary GitHub repository

1. Extract the ZIP, then enter the extracted project directory.
2. Review the files and confirm that no private config/API keys have been added.
3. Create an empty repository on GitHub (do not initialize it with a README/license, because these files are already included).
4. Run:

```bash
git init
git add .
git status --short
git commit -m "Release AZZX v10.3.0: queue reliability and scheduler"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Replace `YOUR_USERNAME` and `YOUR_REPOSITORY` with the repository details. If Git asks you to authenticate, use GitHub's supported authentication flow; do not put a personal access token into the remote URL or source files.

The `.gitignore` excludes local caches, virtual environments, `.env`, local AZZX state, encrypted files and key files. Always inspect `git status` before the first push.
