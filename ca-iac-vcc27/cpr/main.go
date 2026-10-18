// Continuum Placement Resolver (CPR).
//
// Reads continuum_placement annotations from a Terraform file and a telemetry
// snapshot (or a forecast) and selects a tier (edge, fog, cloud) per resource.
// Output is a JSON object keyed by resource name, written to stdout or -out.
//
// Decision rule (identical for reactive and predictive modes; only the
// network/headroom estimates differ):
//   1. Filter tiers by data_residency ("region" excludes cloud, "local" = edge only).
//   2. For each allowed tier in preference order edge -> fog -> cloud, estimate
//      latency = p95_rtt_ms + compute_ms * tier_multiplier.
//      Pick the first tier whose estimate <= latency_budget_ms and whose
//      headroom (1 - utilization) >= min_headroom.
//   3. If none qualifies, pick the allowed tier with the lowest estimate.
//   4. With no telemetry (cold start), fall back to the static nominal mapping.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
)

type Annotation struct {
	Resource    string  `json:"resource"`
	BudgetMs    float64 `json:"latency_budget_ms"`
	Residency   string  `json:"data_residency"`
	ComputeMs   float64 `json:"compute_ms"`
	MinHeadroom float64 `json:"min_headroom"`
}

// TierEstimate is either the observed window statistic (reactive) or a forecast (predictive).
type TierEstimate struct {
	P95RttMs float64 `json:"p95_rtt_ms"`
	Util     float64 `json:"util"`
	Up       bool    `json:"up"`
}

type Decision struct {
	Tier      string             `json:"tier"`
	Reason    string             `json:"reason"`
	Estimates map[string]float64 `json:"estimates_ms"`
}

var tiers = []string{"edge", "fog", "cloud"}

// Compute slowdown per tier relative to cloud hardware (testbed configuration, see testbed/config.py).
var mult = map[string]float64{"edge": 3.0, "fog": 1.5, "cloud": 1.0}

var (
	reRes   = regexp.MustCompile(`^resource\s+"[^"]+"\s+"([^"]+)"`)
	reBlock = regexp.MustCompile(`^continuum_placement\s*\{`)
	reKV    = regexp.MustCompile(`^(\w+)\s*=\s*"?([^"\s]+)"?`)
)

// parseTF extracts continuum_placement blocks with a minimal line parser
// (sufficient for the attribute-only block schema CA-IaC defines).
func parseTF(path string) ([]Annotation, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []Annotation
	var cur *Annotation
	inBlock := false
	res := ""
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		if m := reRes.FindStringSubmatch(line); m != nil {
			res = m[1]
			continue
		}
		if reBlock.MatchString(line) {
			cur = &Annotation{Resource: res, Residency: "any", MinHeadroom: 0.2}
			inBlock = true
			continue
		}
		if inBlock && line == "}" {
			out = append(out, *cur)
			inBlock = false
			continue
		}
		if inBlock {
			if m := reKV.FindStringSubmatch(line); m != nil {
				switch m[1] {
				case "latency_budget_ms":
					cur.BudgetMs, _ = strconv.ParseFloat(m[2], 64)
				case "data_residency":
					cur.Residency = m[2]
				case "compute_ms":
					cur.ComputeMs, _ = strconv.ParseFloat(m[2], 64)
				case "min_headroom":
					cur.MinHeadroom, _ = strconv.ParseFloat(m[2], 64)
				}
			}
		}
	}
	return out, sc.Err()
}

func allowed(res string) []string {
	switch res {
	case "local":
		return []string{"edge"}
	case "region":
		return []string{"edge", "fog"}
	default:
		return tiers
	}
}

func staticNominal(a Annotation) string {
	// Mapping an engineer would derive from documented nominal latencies.
	switch {
	case a.Residency == "region" || a.Residency == "local":
		if a.Residency == "local" {
			return "edge"
		}
		return "fog"
	case a.ComputeMs >= 20:
		return "cloud"
	default:
		return "edge"
	}
}

func decide(a Annotation, est map[string]TierEstimate) Decision {
	d := Decision{Estimates: map[string]float64{}}
	if len(est) == 0 {
		d.Tier, d.Reason = staticNominal(a), "COLD_START"
		return d
	}
	best, bestV := "", 1e18
	for _, t := range allowed(a.Residency) {
		e, ok := est[t]
		if !ok || !e.Up {
			continue
		}
		v := e.P95RttMs + a.ComputeMs*mult[t]
		d.Estimates[t] = v
		if v < bestV {
			best, bestV = t, v
		}
		if d.Tier == "" && v <= a.BudgetMs && (1-e.Util) >= a.MinHeadroom {
			d.Tier, d.Reason = t, "BUDGET_MET"
		}
	}
	if d.Tier == "" {
		if best == "" {
			d.Tier, d.Reason = staticNominal(a), "NO_TIER_UP"
		} else {
			d.Tier, d.Reason = best, "BEST_EFFORT"
		}
	}
	return d
}

func main() {
	tf := flag.String("tf", "", "Terraform file with continuum_placement blocks")
	tel := flag.String("estimates", "", "JSON map tier -> {p95_rtt_ms, util, up}")
	out := flag.String("out", "", "output JSON (default stdout)")
	flag.Parse()
	anns, err := parseTF(*tf)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	est := map[string]TierEstimate{}
	if *tel != "" {
		b, err := os.ReadFile(*tel)
		if err == nil {
			_ = json.Unmarshal(b, &est)
		}
	}
	res := map[string]Decision{}
	for _, a := range anns {
		res[a.Resource] = decide(a, est)
	}
	b, _ := json.MarshalIndent(res, "", "  ")
	if *out == "" {
		fmt.Println(string(b))
	} else {
		_ = os.WriteFile(*out, b, 0o644)
	}
}
