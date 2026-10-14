package main

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// maxDiffBytes caps how much of a patch we read. A fix is usually small; a
// commit that vendors a whole dependency can be huge, and we only need a summary.
const maxDiffBytes = 5 << 20 // 5 MiB

// diffSummary is what we keep from a patch: which files changed and how many
// lines went in and out. The raw patch is not stored; it is fetched on demand.
type diffSummary struct {
	files   []string
	added   int
	removed int
}

// patchURL turns a commit URL into the URL of its raw patch. This is the forge
// seam: only GitHub is supported today, and anything else returns "", false.
// "https://github.com/o/r/commit/abc" -> "https://github.com/o/r/commit/abc.diff"
func patchURL(commit string) (string, bool) {
	u, err := url.Parse(strings.TrimSpace(commit))
	if err != nil || u.Host != "github.com" {
		return "", false
	}
	// Expect /owner/repo/commit/sha. Repo URLs in OSV sometimes end in ".git",
	// which classify carries into the commit URL, so strip it here.
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) != 4 || parts[2] != "commit" || parts[3] == "" {
		return "", false
	}
	repo := strings.TrimSuffix(parts[1], ".git")
	sha := strings.TrimSuffix(parts[3], ".diff")
	return fmt.Sprintf("https://github.com/%s/%s/commit/%s.diff", parts[0], repo, sha), true
}

// diffInfo builds the "diff" block for database_specific. It never fails the
// resolve: any reason we can't summarize becomes available=false plus a reason.
func diffInfo(commit string, hasCommit bool) map[string]any {
	if !hasCommit {
		return map[string]any{"available": false, "reason": "no fix commit"}
	}
	u, ok := patchURL(commit)
	if !ok {
		return map[string]any{"available": false, "reason": "forge not supported"}
	}
	patch, err := fetchDiff(u)
	if err != nil {
		return map[string]any{"available": false, "url": u, "reason": err.Error()}
	}
	s := summarizeDiff(patch)
	return map[string]any{
		"available": true,
		"url":       u,
		"files":     s.files,
		"added":     s.added,
		"removed":   s.removed,
	}
}

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

// summarizeDiff reads a unified diff and counts changed files and lines.
// A "+++"/"---" line is a file header only before the first "@@" hunk of a
// file; inside a hunk it is a real added/removed line whose text starts with
// "++" or "--", so we track which part of the file we are in.
func summarizeDiff(patch string) diffSummary {
	var s diffSummary
	inHunk := false
	for _, line := range strings.Split(patch, "\n") {
		switch {
		case strings.HasPrefix(line, "diff --git "):
			inHunk = false
			// "diff --git a/path b/path" -> "path" (the new name, after b/).
			if i := strings.LastIndex(line, " b/"); i != -1 {
				s.files = append(s.files, line[i+len(" b/"):])
			}
		case strings.HasPrefix(line, "@@"):
			inHunk = true
		case !inHunk:
			// File header lines (index, ---, +++, mode changes): not content.
		case strings.HasPrefix(line, "+"):
			s.added++
		case strings.HasPrefix(line, "-"):
			s.removed++
		}
	}
	return s
}
