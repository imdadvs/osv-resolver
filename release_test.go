package main

import "testing"

// TestReleaseSubject pins which commit messages count as release paperwork.
func TestReleaseSubject(t *testing.T) {
	release := []string{
		"Version 1.0.1 (#3281)", "Bump to v4.0.2", "[skip-ci] Releasing 2.6.1",
		"Build: 3.4.11", "[maven-release-plugin] prepare release jenkins-2.44",
		"update ChangeLog", "chore: v4.1.6 release", ":rocket: Release 1.123.61 (#32926)",
		"Release v6.1.11", "prepare for release 5.9.0", "version bump to v2.19.1",
		"Bumped v10.1.1", "Bump version to 3.41.3", "chore(release): 2.3.0", "2.6.1",
	}
	fixes := []string{
		"Release memory in decoder", "fix: v2.0 parser overflow",
		"Fix OOB write in BuildHuffmanTable.", "fix: access control (#870)",
		"Merge commit from fork", "Prevent user supplied XSLTs from defining external entities",
		"1.2: escape metacharacters in search box",
	}
	for _, s := range release {
		if !releaseSubject.MatchString(s) {
			t.Errorf("should be a release commit: %q", s)
		}
	}
	for _, s := range fixes {
		if releaseSubject.MatchString(s) {
			t.Errorf("should not be a release commit: %q", s)
		}
	}
}
