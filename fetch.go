package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

const osvAPI = "https://api.osv.dev/v1/vulns/"

// normalizeID reduces an osv.dev URL (or a bare ID) to just the ID, because the
// API endpoint only accepts the ID. ".../vulnerability/CVE-x" -> "CVE-x".
func normalizeID(ref string) string {
	ref = strings.TrimSpace(ref)
	for _, marker := range []string{"/vulnerability/", "/vulns/"} {
		if i := strings.Index(ref, marker); i != -1 {
			rest := ref[i+len(marker):]
			for _, sep := range []string{"/", "?", "#"} {
				if j := strings.Index(rest, sep); j != -1 {
					rest = rest[:j]
				}
			}
			return rest
		}
	}
	return ref
}

// fetch gets an OSV record by URL or ID and decodes the whole response.
func fetch(ref string) (map[string]any, error) {
	id := normalizeID(ref)
	resp, err := http.Get(osvAPI + id)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("osv.dev returned %s for %s", resp.Status, id)
	}
	var record map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&record); err != nil {
		return nil, err
	}
	return record, nil
}
