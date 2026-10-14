package main

// computeMissing lists core fields we wanted but the record did not supply.
func computeMissing(record, cls map[string]any) []string {
	var missing []string
	ds, _ := record["database_specific"].(map[string]any)
	if ds == nil || ds["cwe_ids"] == nil {
		missing = append(missing, "cwe_ids")
	}
	hasFixed := false
	affected, _ := record["affected"].([]any)
	for _, a := range affected {
		am, _ := a.(map[string]any)
		ranges, _ := am["ranges"].([]any)
		for _, r := range ranges {
			rm, _ := r.(map[string]any)
			events, _ := rm["events"].([]any)
			for _, e := range events {
				if em, _ := e.(map[string]any); em["fixed"] != nil {
					hasFixed = true
				}
			}
		}
	}
	if !hasFixed && cls["fix_status"] != "direct" {
		missing = append(missing, "fixed_version")
	}
	return missing
}

// resolve enriches the record under database_specific and returns it.
func resolve(record map[string]any, fetch fetchFn) map[string]any {
	cls := classify(record, fetch, 0, nil)
	status, _ := cls["fix_status"].(string)

	ds, _ := record["database_specific"].(map[string]any)
	if ds == nil {
		ds = map[string]any{}
	}
	ds["fix_status"] = status
	if status == "direct" || status == "indirect" || status == "version_only" {
		ds["decision"] = "process"
	} else {
		ds["decision"] = "skip"
	}
	commit, hasCommit := cls["fix_commit"].(string)
	if d, checked := cls["diff"].(map[string]any); checked {
		ds["diff"] = d // classify already read this patch
	} else {
		ds["diff"] = diffInfo(commit, hasCommit)
	}
	if hasCommit {
		ds["fix_commit"] = commit
	}
	for _, key := range []string{"fix_commits", "fix_confidence", "rejected"} {
		if v, ok := cls[key]; ok {
			ds[key] = v
		}
	}
	if via, ok := cls["resolved_via"].(string); ok {
		ds["resolved_via"] = via
	}
	if missing := computeMissing(record, cls); len(missing) > 0 {
		ds["missing"] = missing
	}
	record["database_specific"] = ds

	// Surface the resolved commit as a standard FIX reference if absent.
	if hasCommit {
		refs, _ := record["references"].([]any)
		hasFixRef := false
		for _, ref := range refs {
			if rm, _ := ref.(map[string]any); rm["type"] == "FIX" {
				hasFixRef = true
			}
		}
		if !hasFixRef {
			refs = append(refs, map[string]any{"type": "FIX", "url": commit})
			record["references"] = refs
		}
	}
	return record
}
