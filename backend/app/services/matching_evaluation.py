"""Evaluate the actual discovery decision against versioned labeled examples."""
from app.models.user import WorkPreferences
from app.services.discovery import _evaluate
from app.services.job_matching import MIN_TITLE_MATCH, build_profile


def evaluate_dataset(dataset):
    outcomes = []
    for case in dataset["cases"]:
        prefs = WorkPreferences.model_validate({**dataset["preferences"], **case.get("preferences", {})})
        profile = build_profile(dataset["resume"], prefs)
        fit, flags = _evaluate(prefs, profile, "India", ats="greenhouse", company="Evaluation Company", title=case["title"],
            description=case["description"], location=case["location"], remote=case["remote"])
        eligibility = fit.details["eligibility"]["status"]
        predicted = eligibility == "eligible" and not flags and fit.title_match >= MIN_TITLE_MATCH and fit.score >= prefs.min_match_score
        outcomes.append({"id": case["id"], "expected_eligibility": case["eligibility"], "actual_eligibility": eligibility,
            "expected_relevant": case["relevant"], "actual_relevant": predicted, "score": fit.score,
            "title_match": fit.title_match, "semantic_model": fit.details["semantic_model"],
            "passed": eligibility == case["eligibility"] and predicted == case["relevant"]})
    tp = sum(r["expected_relevant"] and r["actual_relevant"] for r in outcomes)
    fp = sum(not r["expected_relevant"] and r["actual_relevant"] for r in outcomes)
    fn = sum(r["expected_relevant"] and not r["actual_relevant"] for r in outcomes)
    return {"dataset_version": dataset["version"], "dataset_source": dataset["source"], "cases": len(outcomes),
        "eligibility_accuracy": round(sum(r["expected_eligibility"] == r["actual_eligibility"] for r in outcomes)/len(outcomes),4),
        "precision": round(tp/(tp+fp),4) if tp+fp else 0, "recall": round(tp/(tp+fn),4) if tp+fn else 0,
        "false_positives": fp, "false_negatives": fn,
        "semantic_cases": sum(r["semantic_model"] == "all-MiniLM-L6-v2" for r in outcomes),
        "outcomes": outcomes}
