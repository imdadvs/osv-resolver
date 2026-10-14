package main

import (
	"regexp"
	"sort"
	"strings"
)

// candidate is one commit or pull request the advisory points at as a
// possible fix, with every place in the record that points at it. A struct is
// a small typed record: named fields we can carry around together.
type candidate struct {
	url     string
	repo    string   // repo URL, to match the project the advisory names
	sources []string // "range" (a GIT range's fixed event) or "ref_<TYPE>"
}

// checked is a candidate after we looked at its patch.
type checked struct {
	candidate
	patch    string // patch URL; "" when the forge isn't supported
	summary  diffSummary
	verified bool   // we downloaded and read its patch
	reject   string // why it is not the fix; "" when it may be
}

// maxCandidates bounds how many patches one advisory can make us download.
const maxCandidates = 10

var githubLink = regexp.MustCompile(`^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/(commit|pull)/([0-9a-fA-F]{7,40}|\d+)(?:/commits/([0-9a-fA-F]{7,40}))?`)

// canonical rewrites a GitHub commit or pull-request link to one standard
// form, so the same fix reached two ways is counted once. It returns the URL,
// the repo URL and a dedup key; ok is false for anything that isn't one.
func canonical(link string) (u, repo, key string, ok bool) {
	m := githubLink.FindStringSubmatch(strings.TrimSpace(link))
	if m == nil {
		return "", "", "", false
	}
	repo = "https://github.com/" + m[1] + "/" + m[2]
	kind, id := m[3], m[4]
	if kind == "pull" && m[5] != "" { // .../pull/12/commits/abc is commit abc
		kind, id = "commit", m[5]
	}
	short := id
	if kind == "commit" && len(short) > 7 {
		short = short[:7] // a reference may abbreviate the sha a range spells out
	}
	return repo + "/" + kind + "/" + id, repo, strings.ToLower(m[1] + "/" + m[2] + "/" + kind + "/" + short), true
}

// findCandidates collects every commit or pull request the record names as a
// fix: links in its references (any type) and GIT ranges' `fixed` events.
// References go first so they are inside the maxCandidates budget.
func findCandidates(record map[string]any) []candidate {
	var cands []candidate
	index := map[string]int{}
	add := func(link, repo, key, source string) {
		if i, seen := index[key]; seen {
			for _, s := range cands[i].sources {
				if s == source {
					return
				}
			}
			cands[i].sources = append(cands[i].sources, source)
			return
		}
		index[key] = len(cands)
		cands = append(cands, candidate{url: link, repo: repo, sources: []string{source}})
	}

	references, _ := record["references"].([]any)
	for _, ref := range references {
		rm, _ := ref.(map[string]any)
		link, _ := rm["url"].(string)
		kind, _ := rm["type"].(string)
		if u, repo, key, ok := canonical(link); ok {
			add(u, repo, key, "ref_"+kind)
		} else if kind == "FIX" && link != "" {
			// A fix link on another forge: kept, but we can't read its patch.
			add(link, "", strings.ToLower(link), "ref_FIX")
		}
	}

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
				fixed, ok := em["fixed"].(string)
				if !ok || repo == "" {
					continue
				}
				link := repo + "/commit/" + fixed
				if u, r, key, ok := canonical(link); ok {
					add(u, r, key, "range")
				} else {
					add(link, repo, strings.ToLower(link), "range")
				}
			}
		}
	}
	return cands
}

// checkCandidates downloads each candidate's patch and marks release commits.
// A candidate we can't download stays unverified rather than being dropped.
func checkCandidates(cands []candidate) []checked {
	if len(cands) > maxCandidates {
		cands = cands[:maxCandidates]
	}
	var out []checked
	for _, c := range cands {
		ch := checked{candidate: c}
		if p, ok := patchURL(c.url); ok {
			ch.patch = p
			if text, err := fetchPatch(p); err == nil {
				ch.summary = summarizeDiff(text)
				ch.verified = true
				ch.reject = releaseReason(ch.summary)
			}
		}
		out = append(out, ch)
	}
	return out
}

// referenced reports whether any reference link points at this candidate, as
// opposed to only a GIT range's `fixed` event.
func (c candidate) referenced() bool {
	for _, s := range c.sources {
		if strings.HasPrefix(s, "ref_") {
			return true
		}
	}
	return false
}

// chooseFix splits checked candidates into accepted fixes (best first) and
// rejected ones. The rules, measured on tests/fix_truth.json:
//  1. A release commit is never the fix.
//  2. A range `fixed` commit is often the release that shipped the fix, so
//     when a referenced fix survives, a range commit nothing references is
//     dropped.
//  3. Best first: verified, referenced, in the project the advisory names,
//     linked as FIX, then the smallest change (the most focused).
func chooseFix(checks []checked, record map[string]any) (accepted, rejected []checked) {
	// Only a referenced fix we actually read counts: a FIX link we can't read
	// is often an advisory web page, not a commit.
	anyReferenced := false
	for _, c := range checks {
		if c.reject == "" && c.verified && c.referenced() {
			anyReferenced = true
		}
	}
	for _, c := range checks {
		if c.reject == "" && anyReferenced && !c.referenced() {
			c.reject = "range commit not backed by any reference, while a referenced fix exists"
		}
		if c.reject != "" {
			rejected = append(rejected, c)
		} else {
			accepted = append(accepted, c)
		}
	}

	summary, _ := record["summary"].(string)
	details, _ := record["details"].(string)
	text := strings.ToLower(summary + " " + details)
	named := func(c checked) bool {
		name := repoName(c.repo)
		return name != "" && strings.Contains(text, name)
	}
	isFixRef := func(c checked) bool {
		for _, s := range c.sources {
			if s == "ref_FIX" {
				return true
			}
		}
		return false
	}
	// better reports whether a should rank above b: the first rule that tells
	// them apart decides.
	better := func(a, b checked) bool {
		for _, rule := range []func(checked) bool{
			func(c checked) bool { return c.verified },
			checked.referenced,
			named,
			isFixRef,
		} {
			if rule(a) != rule(b) {
				return rule(a)
			}
		}
		return a.summary.added+a.summary.removed < b.summary.added+b.summary.removed
	}
	sort.SliceStable(accepted, func(i, j int) bool { return better(accepted[i], accepted[j]) })
	return accepted, rejected
}

// confidence grades the chosen fix: high when we read its patch and the
// advisory links it directly, low when only a range commit backs it, and
// unverified when we couldn't read its patch at all.
func confidence(c checked) string {
	switch {
	case !c.verified:
		return "unverified"
	case c.referenced():
		return "high"
	default:
		return "low"
	}
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

	// Rung 2+3: a fixing commit named in this record, after release commits
	// and unbacked range commits are ruled out.
	var rejected []any
	if cands := findCandidates(record); len(cands) > 0 {
		accepted, dropped := chooseFix(checkCandidates(cands), record)
		rejected = rejectedList(dropped)
		if len(accepted) > 0 {
			return fixResult(accepted, rejected)
		}
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
			if more, ok := result["rejected"].([]any); ok {
				rejected = append(rejected, more...)
			}
		}
	}

	// Rung 5: a fix shipped in a version, but no commit we found is the fix:
	// either none is linked, or every linked one was release paperwork.
	if findFixedVersion(record) || len(rejected) > 0 {
		result := map[string]any{"fix_status": "version_only"}
		if len(rejected) > 0 {
			result["rejected"] = rejected
		}
		return result
	}

	return map[string]any{"fix_status": "none"}
}

// fixResult turns the accepted candidates (best first) into classify's answer.
func fixResult(accepted []checked, rejected []any) map[string]any {
	best := accepted[0]
	var all []any
	for _, c := range accepted {
		all = append(all, c.url)
	}
	result := map[string]any{
		"fix_status":     "direct",
		"fix_commit":     best.url,
		"fix_commits":    all,
		"fix_source":     strings.Join(best.sources, ","),
		"fix_confidence": confidence(best),
	}
	if best.verified {
		result["diff"] = diffBlock(best.patch, best.summary)
	}
	if len(rejected) > 0 {
		result["rejected"] = rejected
	}
	return result
}

// rejectedList records each ruled-out candidate and why, so the output shows
// its working instead of silently skipping commits.
func rejectedList(dropped []checked) []any {
	var out []any
	for _, c := range dropped {
		out = append(out, map[string]any{"url": c.url, "reason": c.reject})
	}
	return out
}
