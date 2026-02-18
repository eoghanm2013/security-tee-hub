# GitHub Setup Instructions

## Step 1: Create Private Repository on GitHub

1. Go to https://github.com/new
2. Configure the repository:
   - **Repository name:** `security-tee-hub`
   - **Description:** "AI-powered investigation workspace for technical escalation engineering"
   - **Visibility:** ✅ **Private** (important!)
   - **Initialize:** Leave unchecked (we already have files)
3. Click "Create repository"

## Step 2: Verify Safe Files Only

```bash
cd /Users/eoghan.mellott/security-tee-hub

# Verify git status shows only safe files
git status

# Should NOT see:
# - docs/
# - reference/
# - archive/
# - investigations/SCRS-*
# - investigations/ZD-*
# - .env (real credentials)
# - .cursor/mcp.json (real tokens)
# - *.log files
```

## Step 3: Initialize and Push

```bash
# Initialize git repository
git init
git branch -M main

# Add all safe files
git add .

# Review what will be committed
git status

# Create initial commit
git commit -m "Initial commit: Security TEE Hub workspace

- Investigation workflow structure
- Cursor AI integration templates
- MCP configuration examples
- Utility scripts for JIRA/archive management
- Test service for reproduction environments
"

# Add remote (replace with YOUR repo URL from Step 1)
git remote add origin https://github.com/YOUR_USERNAME/security-tee-hub.git

# Push to private repository
git push -u origin main
```

## Step 4: Verify Upload

Go to your GitHub repo and verify:
- ✅ Repository shows "Private" badge
- ✅ Only template files are present
- ✅ No customer data visible
- ✅ No real credentials visible

## Step 5: Add README Disclaimer

After upload, you may want to add this to your README:

```markdown
> **Note:** This is a private workspace for technical escalation investigations. 
> It contains organization-specific configurations and should not be made public.
```

## Troubleshooting

### If you see sensitive files in `git status`:

```bash
# Remove them from staging
git reset HEAD <filename>

# Update .gitignore
echo "<filename>" >> .gitignore

# Try again
git add .
git status
```

### To double-check no secrets are staged:

```bash
# Check for potential secrets in staged files
git diff --cached | grep -i "token\|key\|password\|secret"

# Should return nothing or only template placeholders
```

### To verify .gitignore is working:

```bash
# This should be empty (no output)
git status | grep -E "SCRS-|ZD-|docs/|reference/|archive/"
```

## After Upload

Once pushed, you can:
1. Invite collaborators (Settings → Collaborators)
2. Set up branch protection (Settings → Branches)
3. Add labels for tracking (Issues → Labels)
4. Continue working locally - changes won't upload automatically

## Keeping It Private

**Remember:**
- This repo should stay PRIVATE due to:
  - Org-specific documentation references
  - Investigation patterns that may contain context
  - MCP configuration templates with org domains
  
**Never make this repo public without:**
- Removing all org-specific references
- Sanitizing all examples and templates
- Getting approval from your organization





