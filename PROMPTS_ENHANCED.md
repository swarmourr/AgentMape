# Enhanced LLM Prompts

All prompts have been upgraded to be more mature and interactive!

## Location
`validators/llm_enhanced/llm_multi_prompt_validator.py`

## What's Enhanced

### ✅ Expert Personas
Each prompt now has a specific expert role:
- **Prompt 1**: Pegasus Workflow Management System validator
- **Prompt 2**: DAG analysis expert
- **Prompt 3**: Filesystem & path validation expert
- **Prompt 4**: HPC resource allocation expert
- **Prompt 5**: Data integrity & quality assurance specialist
- **Prompt 6**: Cybersecurity expert
- **Prompt 7**: Workflow architect & best practices expert

### ✅ Comprehensive Analysis
Each prompt now includes:
- Multiple analysis dimensions (3-7 categories each)
- Detailed evaluation criteria
- Context-aware recommendations
- Real-world impact assessment

### ✅ Interactive Clarification
LLM can now ASK FOR MORE DETAILS:
```json
{
  "needs_clarification": true,
  "questions": [
    "What is the expected execution environment?",
    "What are the budget constraints?",
    "Are there specific compliance requirements?"
  ]
}
```

### ✅ Rich Response Format
Enhanced JSON responses include:
- **analysis_summary**: High-level overview
- **metrics**: Quantitative measurements
- **issues**: Detailed problems with solutions
- **recommendations**: Actionable improvements
- **strengths**: Positive feedback
- **questions**: Requests for clarification

## Example Enhanced Output

```json
{
  "analysis_summary": "Workflow structure is well-formed with minor optimization opportunities",
  "quality_score": {
    "code_quality": 8,
    "design": 7,
    "performance": 6,
    "maintainability": 8,
    "documentation": 5
  },
  "issues": [
    {
      "severity": "warning",
      "category": "performance",
      "message": "Job parallelization could be improved",
      "location": "jobs:2-5",
      "explanation": "Jobs 2-5 have no dependencies but execute sequentially",
      "impact": "30% longer execution time",
      "suggestion": "Remove unnecessary parent dependencies to enable parallel execution"
    }
  ],
  "strengths": [
    "Clear naming conventions",
    "Proper use of Pegasus 5.0+ format",
    "Good separation of catalogs"
  ],
  "quick_wins": [
    "Add workflow documentation",
    "Include resource estimates"
  ],
  "needs_clarification": true,
  "questions": [
    "What is the target execution environment (cluster type)?",
    "Are there budget constraints for resource allocation?"
  ]
}
```

## Run Enhanced Validation

```bash
python3.11 cli.py workflow.yml -l full -v
```

You'll now see:
- 🤖 Expert analysis from 7 specialized validators
- 📊 Detailed metrics and scores
- 💡 Actionable recommendations
- ❓ Smart questions when LLM needs more context
- ✨ Positive reinforcement for good practices

## Benefits

1. **More Intelligent**: LLM understands context deeply
2. **Interactive**: LLM asks questions instead of guessing
3. **Actionable**: Specific fixes with code examples
4. **Comprehensive**: Multi-dimensional analysis
5. **Professional**: Expert-level validation
6. **Educational**: Learn best practices through feedback
