# Report Verbosity Guide

## Overview

The validator now supports **3 verbosity levels** to control report output size:

- **brief**: Ultra-compact, shows only critical information (~20-30 lines)
- **standard**: Balanced detail with limits (~100-200 lines) **(DEFAULT)**
- **detailed**: Complete analysis, no limits (~500+ lines)

## Usage

### Command Line

```bash
# Brief mode (minimal output)
python3.11 cli.py workflow.yml --verbosity brief

# Standard mode (default, balanced)
python3.11 cli.py workflow.yml --verbosity standard
python3.11 cli.py workflow.yml  # same as above

# Detailed mode (full analysis)
python3.11 cli.py workflow.yml --verbosity detailed
python3.11 cli.py workflow.yml -v  # legacy flag, same as detailed
```

### Configuration File

Edit `validator_config.json`:

```json
{
  "output_config": {
    "verbosity": "brief",              // brief | standard | detailed
    "max_issues_shown": 10,            // Max issues in standard mode
    "max_recommendations": 5,          // Max recommendations in standard mode
    "show_validator_details": false,   // Show per-validator timing (standard/detailed only)
    "show_strengths": true             // Show workflow strengths
  }
}
```

## Verbosity Levels Compared

### Brief Mode (`--verbosity brief`)

**Use when**: Quick checks, CI/CD pipelines, dashboards

**Output**:
```
✅ PASSED | 0 errors, 2 warnings | 1.2s

🤖 LLM ANALYSIS
────────────────────────────────────────────────────────
✓ GOOD: Workflow is functional but has 2 warning(s) for improvement.

📊 Key Metrics:
   • Code Quality Scores: {'code_quality': 8, 'design': 7}
   • DAG: 5 jobs, max parallelism: 3

🔍 Main Issue Categories:
   • RESOURCES: 2 issue(s)

💡 TOP ACTIONS:
   1. Add memory specification to job 'analyze'
   2. Fix transformation catalog format
   3. Optimize job parallelization
   ... +3 more

────────────────────────────────────────────────────────
💡 Use --verbosity standard for detailed report
💡 Use --verbosity detailed for full analysis
```

**Features**:
- ✅ One-line status summary
- ✅ Executive summary from LLM
- ✅ Top 3 critical issues
- ✅ Top 3 recommendations
- ❌ No validator details
- ❌ No full issue list
- ❌ No strengths (unless critical)

**Size**: ~20-30 lines

---

### Standard Mode (`--verbosity standard`) **[DEFAULT]**

**Use when**: Interactive development, code reviews

**Output**:
```
═══════════════════════════════════════════════════════════════════
🔍  PEGASUS WORKFLOW VALIDATION REPORT
═══════════════════════════════════════════════════════════════════

Workflow: example_workflow.yml

Overall Status: ⚠️  WARNING

────────────────────────────────────────────────────────────────────
📊 SUMMARY
────────────────────────────────────────────────────────────────────
  Total Issues: 12
  ├─ Errors:    0
  └─ Warnings:  12

────────────────────────────────────────────────────────────────────
🤖 CONSOLIDATED LLM ANALYSIS
────────────────────────────────────────────────────────────────────

📋 EXECUTIVE SUMMARY
✓ GOOD: Workflow is functional but has 12 warning(s) for improvement.

📊 Key Metrics:
   • Code Quality Scores: {'code_quality': 8, 'design': 7, 'performance': 6}
   • DAG: 5 jobs, max parallelism: 3
   • Security Risk Level: low

💡 TOP RECOMMENDATIONS (Prioritized)
   1. Add memory specification to job 'analyze'
   2. Fix transformation catalog format for Pegasus 5.0+
   3. Optimize job parallelization
   4. Add error handling to jobs
   5. Document input file requirements
   ... and 7 more (use --verbosity detailed to see all)

💪 KEY STRENGTHS
   ✓ Clear job names
   ✓ Good documentation
   ✓ Proper use of Pegasus 5.0+ format

📊 ISSUES BY CATEGORY
   • STRUCTURE: 2 issue(s)
   • RESOURCES: 3 issue(s)
   • PERFORMANCE: 4 issue(s)
   • BEST_PRACTICES: 3 issue(s)

────────────────────────────────────────────────────────────────────
🚨 ISSUES FOUND
────────────────────────────────────────────────────────────────────

⚠️  WARNINGS (12)

🏗️ Job 'analyze' missing memory specification
   Location: job:analyze
   💡 Fix: Add 'request_memory' to profiles.condor

⚙️ Excessive resource allocation for small job
   Location: job:preprocess
   💡 Fix: Reduce memory from 128GB to 16GB

... (showing 10 of 12 issues)

💡 Showing 10 of 12 issues. Use --verbosity detailed to see all.

═══════════════════════════════════════════════════════════════════
⚠️  VALIDATION PASSED WITH WARNINGS
Consider addressing 12 warning(s) to improve reliability
═══════════════════════════════════════════════════════════════════
```

**Features**:
- ✅ Full header and summary
- ✅ Consolidated LLM analysis
- ✅ Top 5 recommendations (configurable)
- ✅ Top 3 strengths
- ✅ Up to 10 issues shown (configurable)
- ✅ Category breakdown
- ❌ No per-validator details
- ❌ Limited issue details

**Size**: ~100-200 lines

**Configuration**:
```json
{
  "max_issues_shown": 10,        // Adjust how many issues to show
  "max_recommendations": 5,       // Adjust top recommendations
  "show_strengths": true          // Toggle strengths section
}
```

---

### Detailed Mode (`--verbosity detailed`)

**Use when**: Deep debugging, first-time validation, comprehensive audit

**Output**:
```
═══════════════════════════════════════════════════════════════════
🔍  PEGASUS WORKFLOW VALIDATION REPORT
═══════════════════════════════════════════════════════════════════

Workflow: example_workflow.yml
Validated: 2025-01-15 10:30:45
Duration: 2.34s

Overall Status: ⚠️  WARNING

────────────────────────────────────────────────────────────────────
📊 SUMMARY
────────────────────────────────────────────────────────────────────
  Total Issues: 12
  ├─ Errors:    0
  └─ Warnings:  12

────────────────────────────────────────────────────────────────────
🔧 VALIDATOR RESULTS
────────────────────────────────────────────────────────────────────

✅ SYNTAX (0.02s)
   Checks performed: 3
   Errors: 0, Warnings: 0

✅ STRUCTURE (0.05s)
   Checks performed: 8
   Errors: 0, Warnings: 2

⚠️  PATHS (0.10s)
   Checks performed: 12
   Errors: 0, Warnings: 3

... (all validators shown)

────────────────────────────────────────────────────────────────────
🤖 CONSOLIDATED LLM ANALYSIS
────────────────────────────────────────────────────────────────────

📋 EXECUTIVE SUMMARY
... (same as standard)

💡 TOP RECOMMENDATIONS (Prioritized)
   1. Add memory specification to job 'analyze'
   2. Fix transformation catalog format for Pegasus 5.0+
   3. Optimize job parallelization
   4. Add error handling to jobs
   5. Document input file requirements
   6. Add checksums to replica catalog
   7. Implement retry logic for network operations
   8. Use environment variables for paths
   9. Add workflow-level documentation
   10. Consider using containers for reproducibility

💪 KEY STRENGTHS
   ✓ Clear job names
   ✓ Good documentation
   ✓ Proper use of Pegasus 5.0+ format
   ✓ Consistent naming conventions
   ✓ Well-structured DAG

────────────────────────────────────────────────────────────────────
🚨 ISSUES FOUND
────────────────────────────────────────────────────────────────────

⚠️  WARNINGS (12)

🏗️ Job 'analyze' missing memory specification
   Location: job:analyze
   Reason: Memory specification is required for proper resource allocation
   Impact: May cause job failure or excessive resource usage
   💡 Fix: Add 'request_memory' to profiles.condor:
      profiles:
        condor:
          request_memory: "16GB"

... (ALL issues shown with full details)

────────────────────────────────────────────────────────────────────
📄 RAW LLM RESPONSES (Debug Mode) [if enabled]
────────────────────────────────────────────────────────────────────
... (complete LLM responses for debugging)

═══════════════════════════════════════════════════════════════════
```

**Features**:
- ✅ Full header with timestamps
- ✅ Per-validator timing details
- ✅ ALL recommendations (no limit)
- ✅ ALL strengths (no limit)
- ✅ ALL issues with full details
- ✅ Complete explanations and code examples
- ✅ Optional raw LLM responses (if `show_raw_llm_responses: true`)

**Size**: ~500-1000+ lines depending on workflow complexity

---

## Quick Reference Table

| Feature | Brief | Standard | Detailed |
|---------|-------|----------|----------|
| Status line | ✅ | ✅ | ✅ |
| Timestamp | ❌ | ❌ | ✅ |
| Executive summary | ✅ | ✅ | ✅ |
| Validator timing | ❌ | ❌ | ✅ |
| Recommendations | Top 3 | Top 5 | All |
| Strengths | ❌ | Top 3 | All |
| Issues shown | Top 3 critical | Up to 10 | All |
| Issue details | Minimal | Standard | Full with code |
| Category breakdown | ✅ | ✅ | ✅ |
| Raw LLM responses | ❌ | ❌ | Optional |
| Typical size | ~30 lines | ~200 lines | ~1000+ lines |
| Use case | Quick check | Development | Deep audit |

## Advanced Configuration

### Custom Limits (Standard Mode)

```json
{
  "output_config": {
    "verbosity": "standard",
    "max_issues_shown": 20,            // Show more issues
    "max_recommendations": 10,         // Show more recommendations
    "show_validator_details": true,    // Show timing even in standard
    "show_strengths": false            // Hide strengths to save space
  }
}
```

### Debug Mode (Detailed + Raw Responses)

```json
{
  "output_config": {
    "verbosity": "detailed",
    "show_raw_llm_responses": true     // Show complete LLM JSON responses
  }
}
```

## Best Practices

### CI/CD Pipelines
```bash
# Use brief mode for fast feedback
python3.11 cli.py workflow.yml --verbosity brief --format json > results.json
```

### Development
```bash
# Use standard mode (default) for balanced output
python3.11 cli.py workflow.yml
```

### Code Reviews
```bash
# Use detailed mode with HTML output
python3.11 cli.py workflow.yml --verbosity detailed --format html -o report.html
```

### Debugging
```bash
# Use detailed + raw responses
# First enable in config: "show_raw_llm_responses": true
python3.11 cli.py workflow.yml --verbosity detailed
```

## Migration from Old Version

If you're upgrading:

1. **Old `--verbose` flag** → Now maps to `--verbosity detailed`
2. **Default behavior** → Now uses `brief` mode (was full output)
3. **To get old full output** → Use `--verbosity detailed`

```bash
# Old way
python3.11 cli.py workflow.yml -v

# New way (equivalent)
python3.11 cli.py workflow.yml --verbosity detailed
```

## Tips

1. **Start with brief** to get quick overview
2. **Use standard for development** (default is already set)
3. **Use detailed for final review** before production
4. **Adjust limits** in config if standard is too verbose/brief
5. **Enable raw responses** only when debugging prompts

## Examples

### Example 1: Quick CI Check
```bash
#!/bin/bash
# ci-validate.sh
python3.11 cli.py workflow.yml --verbosity brief
if [ $? -eq 0 ]; then
  echo "✅ Validation passed"
else
  echo "❌ Validation failed - run with --verbosity standard for details"
  exit 1
fi
```

### Example 2: Development Workflow
```bash
# Quick check during development
python3.11 cli.py workflow.yml --verbosity brief

# If issues found, get more details
python3.11 cli.py workflow.yml --verbosity standard

# Before commit, full audit
python3.11 cli.py workflow.yml --verbosity detailed -o full-report.txt
```

### Example 3: Team Review
```bash
# Generate HTML report for team
python3.11 cli.py workflow.yml --verbosity standard --format html -o review.html

# Open in browser
open review.html
```

## Summary

- **Brief** = Fast overview (~30 lines)
- **Standard** = Development mode (~200 lines) **[DEFAULT]**
- **Detailed** = Complete audit (~1000+ lines)

Choose based on your needs! The default `brief` mode is optimized for quick feedback while `detailed` gives you everything.
