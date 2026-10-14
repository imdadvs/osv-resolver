package main

import (
	"encoding/json"
	"os"
	"testing"
)

// truthRecord is one hand-labelled advisory from tests/fix_truth.json.
type truthRecord struct {
	ID         string `json:"id"`
	FixInData  bool   `json:"fix_in_data"`
	Confidence string `json:"confidence"`
	Candidates []struct {
		URL   string `json:"url"`
		IsFix bool   `json:"is_fix"`
	} `json:"candidates"`
}

// TestFixTruth scores the fix picker against a labelled set. It downloads
// every advisory and patch, so it only runs when asked:
//
//	OSV_LIVE=1 go test -run TestFixTruth -v
//	OSV_LIVE=1 OSV_TRUTH=tests/fix_holdout.json go test -run TestFixTruth -v
//
// fix_truth.json is the set the rules were written against; fix_holdout.json
// was labelled afterwards and never used to tune them.
func TestFixTruth(t *testing.T) {
	if os.Getenv("OSV_LIVE") == "" {
		t.Skip("live test: set OSV_LIVE=1 to run")
	}
	file := os.Getenv("OSV_TRUTH")
	if file == "" {
		file = "tests/fix_truth.json"
	}
	raw, err := os.ReadFile(file)
	if err != nil {
		t.Fatal(err)
	}
	var truth []truthRecord
	if err := json.Unmarshal(raw, &truth); err != nil {
		t.Fatal(err)
	}

	right := 0
	for _, tr := range truth {
		record, err := fetch(tr.ID)
		if err != nil {
			t.Errorf("%s: fetch: %v", tr.ID, err)
			continue
		}
		cls := classify(record, fetch, 0, nil)
		picked, _ := cls["fix_commit"].(string)

		var ok bool
		if tr.FixInData {
			// Right when the pick is any of the commits labelled as the fix.
			_, _, pickedKey, _ := canonical(picked)
			for _, c := range tr.Candidates {
				if _, _, key, _ := canonical(c.URL); c.IsFix && key == pickedKey && key != "" {
					ok = true
				}
			}
		} else {
			// The fix isn't in the data: the only right answer is no commit.
			ok = picked == ""
		}
		mark := "WRONG"
		if ok {
			right++
			mark = "ok   "
		}
		t.Logf("%s %-22s %-12v %-10v %s", mark, tr.ID, cls["fix_status"], cls["fix_confidence"], picked)
	}
	t.Logf("score: %d of %d right", right, len(truth))
}
