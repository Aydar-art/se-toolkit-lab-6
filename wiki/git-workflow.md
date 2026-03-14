# Git Workflow

## Creating a branch
Use `git checkout -b branch-name` to create and switch to a new branch.

## Committing changes
1. `git add <files>` - stage changes
2. `git commit -m "message"` - commit with message

## Resolving merge conflicts
When you have a merge conflict:
1. Edit the conflicting files to resolve differences
2. Remove the conflict markers (<<<<<<<, =======, >>>>>>>)
3. Stage the resolved files: `git add <file>`
4. Complete the merge: `git commit`

## Pushing changes
Use `git push origin branch-name` to push your branch.