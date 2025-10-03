#!/bin/bash
# git-sync.sh
# Git helper: load .env, configure git, pull, commit, and push
# Usage:
#   ./git-sync.sh push           # Only push
#   ./git-sync.sh pull           # Only pull
#   ./git-sync.sh sync [message] # Pull + commit + push (default)

set -e  # Stop script on any error

# ==== Load environment variables from .env ====
if [ ! -f .env ]; then
  echo "❌ .env file not found! Please create it with GIT_USERNAME, GIT_EMAIL, GIT_TOKEN, DEFAULT_BRANCH, GIT_REPO"
  exit 1
fi

# Export variables from .env
export $(grep -v '^#' .env | xargs)

# Verify required variables
if [ -z "$GIT_USERNAME" ] || [ -z "$GIT_EMAIL" ] || [ -z "$GIT_TOKEN" ] || [ -z "$GIT_REPO" ] || [ -z "$DEFAULT_BRANCH" ]; then
  echo "❌ Missing required environment variables in .env!"
  exit 1
fi

# Ensure we're in a git repository
if [ ! -d .git ]; then
  echo "❌ Not a git repository!"
  exit 1
fi

# Configure Git
echo "⚙️ Configuring git..."
git config user.name "$GIT_USERNAME"
git config user.email "$GIT_EMAIL"
git config init.defaultBranch "$DEFAULT_BRANCH"

# Check if origin exists; add if missing
if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "$GIT_REPO"
fi

# Update remote URL with token
git remote set-url origin https://$GIT_USERNAME:$GIT_TOKEN@${GIT_REPO#https://}

# Determine action
ACTION="${1:-sync}"  # Default action is "sync"
COMMIT_MSG="${2:-update: $(date '+%Y-%m-%d %H:%M:%S')}"

case "$ACTION" in
  pull)
    echo "⬇️ Pulling latest changes from $DEFAULT_BRANCH..."
    git pull origin "$DEFAULT_BRANCH" || echo "⚠️ Pull failed"
    ;;
    
  push)
    echo "⬆️ Pushing to $DEFAULT_BRANCH..."
    git push origin "$DEFAULT_BRANCH" || echo "⚠️ Push failed"
    ;;
    
  sync)
    # Pull
    echo "⬇️ Pulling latest changes from $DEFAULT_BRANCH..."
    git pull origin "$DEFAULT_BRANCH" || echo "⚠️ Pull failed, continuing..."
    
    # Stage all changes
    echo "➕ Staging changes..."
    git add .
    
    # Commit
    echo "📝 Committing: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG" || echo "⚠️ Nothing to commit"
    
    # Push
    echo "⬆️ Pushing to $DEFAULT_BRANCH..."
    git push origin "$DEFAULT_BRANCH" || echo "⚠️ Push failed"
    ;;
    
  *)
    echo "❌ Unknown action: $ACTION"
    echo "Usage: $0 [pull|push|sync] [commit message]"
    exit 1
    ;;
esac

echo "✅ Done!"
