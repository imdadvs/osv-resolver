package main

import (
	"encoding/json"
	"fmt"
	"os"
)

// main is the program's entry point: fetch an advisory, resolve it, check the
// output is valid OSV, and print it.
func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: osv-resolver <osv-url-or-id>")
		os.Exit(2)
	}

	record, err := fetch(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, "fetch failed:", err)
		os.Exit(1)
	}

	out := resolve(record, fetch) // pass fetch itself in, for upstream resolution

	if err := checkStandard(out); err != nil {
		fmt.Fprintln(os.Stderr, "emit failed:", err)
		os.Exit(1)
	}

	pretty, _ := json.MarshalIndent(out, "", "  ")
	fmt.Println(string(pretty))
}
