package main

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"strings"
)

// maxDiffBytes caps how much of a patch we read. A fix is usually small; a
// commit that vendors a whole dependency can be huge, and we only need a summary.
const maxDiffBytes = 5 << 20 // 5 MiB

// diffSummary is what we keep from a patch: the commit subjects, which files
// changed, and how many lines went in and out. codeLines counts the changed
// lines that are neither bookkeeping files nor version-number edits; zero
// means the commit changed nothing but release paperwork.
type diffSummary struct {
	subjects  []string
	files     []string
	added     int
	removed   int
	codeLines int
}

// patchURL turns a commit or pull-request URL into the URL of its raw patch.
// This is the forge seam: only GitHub is supported today, and anything else
// returns "", false. The .patch form (not .diff) also carries each commit's
// message, which is how we spot release commits.
// "https://github.com/o/r/commit/abc"  -> ".../commit/abc.patch"
// "https://github.com/o/r/pull/12"     -> ".../pull/12.patch"
// "https://github.com/o/r/pull/12/commits/abc" -> ".../commit/abc.patch"
func patchURL(link string) (string, bool) {
	u, err := url.Parse(strings.TrimSpace(link))
	if err != nil || (u.Host != "github.com" && u.Host != "www.github.com") {
		return "", false
	}
	// Repo URLs in OSV sometimes end in ".git", which carries into the commit URL.
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) < 4 || parts[3] == "" {
		return "", false
	}
	owner, repo := parts[0], strings.TrimSuffix(parts[1], ".git")
	id := strings.TrimSuffix(strings.TrimSuffix(parts[3], ".diff"), ".patch")
	switch {
	case parts[2] == "commit" && len(parts) == 4:
		return fmt.Sprintf("https://github.com/%s/%s/commit/%s.patch", owner, repo, id), true
	case parts[2] == "pull" && len(parts) == 6 && parts[4] == "commits":
		return fmt.Sprintf("https://github.com/%s/%s/commit/%s.patch", owner, repo, parts[5]), true
	case parts[2] == "pull":
		return fmt.Sprintf("https://github.com/%s/%s/pull/%s.patch", owner, repo, id), true
	}
	return "", false
}

// diffBlock is the "diff" entry for database_specific, built from a summary.
func diffBlock(patch string, s diffSummary) map[string]any {
	return map[string]any{
		"available": true,
		"url":       patch,
		"files":     s.files,
		"added":     s.added,
		"removed":   s.removed,
	}
}

// diffInfo builds the "diff" block for a commit classify did not already
// check. It never fails the resolve: any reason we can't summarize becomes
// available=false plus a reason.
func diffInfo(commit string, hasCommit bool) map[string]any {
	if !hasCommit {
		return map[string]any{"available": false, "reason": "no fix commit"}
	}
	u, ok := patchURL(commit)
	if !ok {
		return map[string]any{"available": false, "reason": "forge not supported"}
	}
	patch, err := fetchPatch(u)
	if err != nil {
		return map[string]any{"available": false, "url": u, "reason": err.Error()}
	}
	return diffBlock(u, summarizeDiff(patch))
}

// fetchPatch is a variable, not a plain function, so tests can swap in canned
// patches and run offline. It defaults to the real download.
var fetchPatch = fetchDiff

// fetchDiff gets the raw patch text at url, reading at most maxDiffBytes.
func fetchDiff(url string) (string, error) {
	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("github returned %s for %s", resp.Status, url)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxDiffBytes))
	if err != nil {
		return "", err
	}
	return string(body), nil
}

// versionLike matches a line that carries a version number, e.g.
// `__version__ = "1.0.1"` or `<version>2.32.2</version>`.
var versionLike = regexp.MustCompile(`\d+\.\d+`)

// summarizeDiff reads a patch and counts changed files and lines.
// A "+++"/"---" line is a file header only before the first "@@" hunk of a
// file; inside a hunk it is a real added/removed line whose text starts with
// "++" or "--", so we track which part of the file we are in. A pull-request
// patch is several commits back to back, each starting with "From <sha>".
func summarizeDiff(patch string) diffSummary {
	var s diffSummary
	inHunk, paperwork := false, false
	for _, line := range strings.Split(patch, "\n") {
		switch {
		case strings.HasPrefix(line, "From ") && len(line) > 45 && isHex(line[5:45]):
			inHunk = false // next commit in a pull-request patch
		case !inHunk && strings.HasPrefix(line, "Subject: "):
			s.subjects = append(s.subjects, cleanSubject(line[len("Subject: "):]))
		case strings.HasPrefix(line, "diff --git "):
			inHunk = false
			// "diff --git a/path b/path" -> "path" (the new name, after b/).
			if i := strings.LastIndex(line, " b/"); i != -1 {
				name := line[i+len(" b/"):]
				s.files = append(s.files, name)
				paperwork = isPaperwork(name)
			}
		case strings.HasPrefix(line, "@@"):
			inHunk = true
		case !inHunk:
			// Header lines (message, index, ---, +++, mode changes): not content.
		case strings.HasPrefix(line, "+"), strings.HasPrefix(line, "-"):
			if line[0] == '+' {
				s.added++
			} else {
				s.removed++
			}
			text := strings.TrimSpace(line[1:])
			if !paperwork && text != "" && !versionLike.MatchString(text) {
				s.codeLines++
			}
		}
	}
	return s
}

// cleanSubject drops the "[PATCH 1/3] " prefix git adds to each subject.
func cleanSubject(subject string) string {
	if strings.HasPrefix(subject, "[PATCH") {
		if i := strings.Index(subject, "] "); i != -1 {
			subject = subject[i+2:]
		}
	}
	return strings.TrimSpace(subject)
}

func isHex(s string) bool {
	for _, r := range s {
		if !strings.ContainsRune("0123456789abcdef", r) {
			return false
		}
	}
	return true
}

// isPaperwork reports whether a file is release paperwork rather than code:
// changelogs and release notes, documentation, and dependency lock files.
func isPaperwork(name string) bool {
	lower := strings.ToLower(name)
	base := path.Base(lower)
	for _, word := range []string{"changelog", "changes", "news", "history", "release-notes", "release_notes", "releasenotes"} {
		if strings.HasPrefix(base, word) {
			return true
		}
	}
	switch path.Ext(base) {
	case ".md", ".rst", ".adoc", ".txt":
		return true
	}
	switch base {
	case "package-lock.json", "yarn.lock", "cargo.lock", "go.sum", "composer.lock", "gemfile.lock", "poetry.lock":
		return true
	}
	return strings.HasPrefix(lower, "docs/") || strings.HasPrefix(lower, "doc/") ||
		strings.Contains(lower, "/docs/") || strings.HasPrefix(lower, ".changeset/")
}

// releaseSubject matches commit messages that announce a release instead of a
// change: "Version 1.0.1", "Bump to v4.0.2", "Releasing 2.6.1", "Build: 3.4.11",
// "chore: v4.1.6 release", ":rocket: Release 1.123.61". A leading "[skip-ci]",
// conventional-commit "chore(release):" or ":emoji:" is skipped. Not "Release
// memory in decoder", which is a fix, so a version must follow "release".
// "[maven-release-plugin] prepare release jenkins-2.44", "update ChangeLog".
var releaseSubject = regexp.MustCompile(`(?i)^(` +
	`\[maven-release-plugin\]|` +
	`(\[[^\]]*\]\s*)*(\w+(\([^)]*\))?!?:\s*)?(:\w+:\s*)?(releas(e|ing):? v?\d|release\s*$|prepar(e|ing) (for )?(the )?release|` +
	`bump(ed)?( the)? (version|to)|bump(ed)? v?\d|version bump|version:? v?\d|v?\d+\.\d+(\.\d+)*( release)?\s*(\(#\d+\))?$|` +
	`build:? v?\d|update (the )?(changelog|news|release notes|version))` +
	`)`)

// releaseReason says why a checked commit is release paperwork and not a fix,
// or returns "" when it looks like a real change. It needs no CVE IDs or
// advisory text: only the commit's own message and what it touched.
func releaseReason(s diffSummary) string {
	if len(s.files) == 0 {
		return "empty patch"
	}
	// Every commit in it must be a release commit; one real change is enough
	// to keep a pull request.
	release := len(s.subjects) > 0
	for _, subj := range s.subjects {
		if !releaseSubject.MatchString(subj) {
			release = false
		}
	}
	if release {
		return "release commit: " + s.subjects[0]
	}
	if s.codeLines == 0 {
		return "only changelog, docs or version numbers changed"
	}
	return ""
}
