package main

import (
	"fmt"
	"sort"
)

// allowedTop is the set of top-level fields the OSV schema defines.
// Go has no built-in "set" type, so the idiom is a map whose values are bool:
// a key being present (and true) means "allowed".
var allowedTop = map[string]bool{
	"schema_version": true, "id": true, "modified": true, "published": true,
	"withdrawn": true, "aliases": true, "related": true, "upstream": true,
	"summary": true, "details": true, "severity": true, "affected": true,
	"references": true, "credits": true, "database_specific": true,
}

// checkStandard returns an error if the record carries any top-level field OSV
// does not define, or is missing a required one. A nil return means "valid".
func checkStandard(record map[string]any) error {
	var extra []string
	for key := range record {
		if !allowedTop[key] {
			extra = append(extra, key)
		}
	}
	if len(extra) > 0 {
		sort.Strings(extra)
		return fmt.Errorf("non-standard top-level fields: %v", extra)
	}
	if _, ok := record["id"]; !ok {
		return fmt.Errorf("OSV record missing required field: id")
	}
	if _, ok := record["modified"]; !ok {
		return fmt.Errorf("OSV record missing required field: modified")
	}
	return nil
}
