package main

import "testing"

func TestResidencyExcludesCloud(t *testing.T) {
	a := Annotation{BudgetMs: 1000, Residency: "region", ComputeMs: 1, MinHeadroom: 0.2}
	est := map[string]TierEstimate{
		"edge":  {P95RttMs: 500, Util: 0.95, Up: true},
		"fog":   {P95RttMs: 900, Util: 0.95, Up: true},
		"cloud": {P95RttMs: 1, Util: 0, Up: true},
	}
	if d := decide(a, est); d.Tier == "cloud" {
		t.Fatalf("residency violated: %+v", d)
	}
}

func TestPreferEdgeWhenBudgetMet(t *testing.T) {
	a := Annotation{BudgetMs: 30, Residency: "any", ComputeMs: 1, MinHeadroom: 0.2}
	est := map[string]TierEstimate{
		"edge": {P95RttMs: 5, Util: 0.3, Up: true}, "fog": {P95RttMs: 17, Util: 0.1, Up: true},
		"cloud": {P95RttMs: 50, Util: 0.1, Up: true},
	}
	if d := decide(a, est); d.Tier != "edge" {
		t.Fatalf("want edge, got %+v", d)
	}
}

func TestHeadroomFallback(t *testing.T) {
	a := Annotation{BudgetMs: 30, Residency: "any", ComputeMs: 1, MinHeadroom: 0.2}
	est := map[string]TierEstimate{
		"edge": {P95RttMs: 5, Util: 0.9, Up: true}, "fog": {P95RttMs: 17, Util: 0.1, Up: true},
		"cloud": {P95RttMs: 50, Util: 0.1, Up: true},
	}
	if d := decide(a, est); d.Tier != "fog" {
		t.Fatalf("want fog, got %+v", d)
	}
}

func TestColdStart(t *testing.T) {
	a := Annotation{BudgetMs: 120, Residency: "any", ComputeMs: 40}
	if d := decide(a, nil); d.Tier != "cloud" || d.Reason != "COLD_START" {
		t.Fatalf("got %+v", d)
	}
}

func TestDownTierSkipped(t *testing.T) {
	a := Annotation{BudgetMs: 30, Residency: "any", ComputeMs: 1, MinHeadroom: 0.2}
	est := map[string]TierEstimate{
		"edge": {Up: false}, "fog": {P95RttMs: 17, Util: 0.1, Up: true}, "cloud": {P95RttMs: 50, Up: true},
	}
	if d := decide(a, est); d.Tier != "fog" {
		t.Fatalf("got %+v", d)
	}
}

func TestParseTF(t *testing.T) {
	anns, err := parseTF("../iac/workloads.tf")
	if err != nil || len(anns) != 3 {
		t.Fatalf("parse: %v %d", err, len(anns))
	}
	if anns[1].Resource != "regional_compliance" || anns[1].Residency != "region" || anns[1].BudgetMs != 40 {
		t.Fatalf("bad parse %+v", anns[1])
	}
}
