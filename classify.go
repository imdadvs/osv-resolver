package main

import "strings"

// findFixCommit returns a fixing-commit URL and where it came from, or "", "".
// A GIT range's `fixed` event is always a real commit, so it is preferred over
// a FIX reference, which OSV sometimes points at an advisory page.
// gitFix is one fixing commit and the repo it lives in. A struct is a small
// typed record: two named string fields we can carry around together.
type gitFix struct {
	repo   string
	commit string
}

func findFixCommit(record map[string]any) (url string, source string) {
	// Collect every GIT `fixed` commit in the record (a record may list
	// several projects, e.g. MySQL that bundles libpng).
	var fixes []gitFix
	affected, _ := record["affected"].([]any)
	for _, a := range affected {
		am, _ := a.(map[string]any)
		ranges, _ := am["ranges"].([]any)
		for _, r := range ranges {
			rm, _ := r.(map[string]any)
			if rm["type"] != "GIT" {
				continue
			}
			repo, _ := rm["repo"].(string)
			repo = strings.TrimRight(repo, "/")
			events, _ := rm["events"].([]any)
			for _, e := range events {
				em, _ := e.(map[string]any)
				if fixed, ok := em["fixed"].(string); ok && repo != "" {
					fixes = append(fixes, gitFix{repo: repo, commit: fixed})
				}
			}
		}
	}
	if len(fixes) > 0 {
		best := pickBestFix(fixes, record)
		return best.repo + "/commit/" + best.commit, "range"
	}

	// No GIT commit: fall back to a FIX reference.
	references, _ := record["references"].([]any)
	for _, ref := range references {
		rm, _ := ref.(map[string]any)
		if rm["type"] == "FIX" {
			u, _ := rm["url"].(string)
			return u, "references"
		}
	}
	return "", ""
}

// pickBestFix chooses the fix whose repo name appears in the advisory's
// summary/details, so a record listing several projects resolves to the one
// that is actually vulnerable. Falls back to the first fix when none matches.
func pickBestFix(fixes []gitFix, record map[string]any) gitFix {
	summary, _ := record["summary"].(string)
	details, _ := record["details"].(string)
	text := strings.ToLower(summary + " " + details)
	for _, f := range fixes {
		if name := repoName(f.repo); name != "" && strings.Contains(text, name) {
			return f
		}
	}
	return fixes[0]
}

// repoName is the last path segment of a repo URL, lowercased: the project name.
func repoName(repo string) string {
	parts := strings.Split(repo, "/")
	return strings.ToLower(parts[len(parts)-1])
}

// findFixedVersion reports whether a non-GIT range carries a `fixed` event:
// a fix exists as a version, even though no commit is named.
func findFixedVersion(record map[string]any) bool {
	affected, _ := record["affected"].([]any)
	for _, a := range affected {
		am, _ := a.(map[string]any)
		ranges, _ := am["ranges"].([]any)
		for _, r := range ranges {
			rm, _ := r.(map[string]any)
			if rm["type"] == "GIT" {
				continue
			}
			events, _ := rm["events"].([]any)
			for _, e := range events {
				if em, _ := e.(map[string]any); em["fixed"] != nil {
					return true
				}
			}
		}
	}
	return false
}

// upstreamIDs returns other records that may carry the fix (dedup, drop self).
func upstreamIDs(record map[string]any) []string {
	var ids []string
	seen := map[string]bool{}
	self, _ := record["id"].(string)
	for _, key := range []string{"upstream", "aliases"} {
		list, _ := record[key].([]any)
		for _, item := range list {
			id, _ := item.(string)
			if id != "" && id != self && !seen[id] {
				seen[id] = true
				ids = append(ids, id)
			}
		}
	}
	return ids
}

// fetchFn is the signature of a function that fetches a record by ID. Passing
// it in (rather than calling fetch directly) keeps classify testable offline.
type fetchFn func(string) (map[string]any, error)

// classify triages a record to a fix state: direct, indirect, version_only, none.
func classify(record map[string]any, fetch fetchFn, depth int, seen map[string]bool) map[string]any {
	if seen == nil {
		seen = map[string]bool{}
	}
	if id, ok := record["id"].(string); ok {
		seen[id] = true
	}

	// Rung 2+3: a fixing commit named in this record.
	if url, src := findFixCommit(record); url != "" {
		return map[string]any{"fix_status": "direct", "fix_commit": url, "fix_source": src}
	}

	// Rung 4: follow upstream/alias records; an upstream commit beats a local
	// package version, so this is tried before settling for version_only.
	if fetch != nil && depth < 3 {
		for _, uid := range upstreamIDs(record) {
			if seen[uid] {
				continue
			}
			upstream, err := fetch(uid)
			if err != nil {
				continue
			}
			result := classify(upstream, fetch, depth+1, seen)
			if s := result["fix_status"]; s == "direct" || s == "indirect" {
				result["fix_status"] = "indirect"
				result["resolved_via"] = uid
				return result
			}
		}
	}

	// Rung 5: a fixed version exists locally but no commit is linked.
	if findFixedVersion(record) {
		return map[string]any{"fix_status": "version_only"}
	}

	return map[string]any{"fix_status": "none"}
}
