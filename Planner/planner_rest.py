#!/usr/bin/env python3
"""
LLM-Powered Planner Agent for MAPE-K Pegasus Workflow System
Generates executable repair plans using AI with catalog awareness
Save as: Planner/planner_rest.py
Run with: python planner_rest.py
"""

import asyncio
import json
import logging
import os
import requests
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from tinydb import TinyDB, Query
from enum import Enum
from aiohttp import web, ClientSession
import aiohttp

# Configuration
HTTP_PORT = int(os.getenv("HTTP_PORT", "8082"))
MCP_PORT = int(os.getenv("MCP_PORT", "8767"))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize TinyDB
db = TinyDB("planner_db.json")
plans_table = db.table("plans")
execution_requests_table = db.table("execution_requests")
agents_table = db.table("agents")

class TerminalColor(Enum):
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'
    WHITE = '\033[97m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_MAGENTA = '\033[95m'
    RESET = '\033[0m'

    def apply(self, text):
        return f"{self.value}{text}{TerminalColor.RESET.value}"


class OllamaManager:
    """Manages Ollama LLM connection for plan generation"""

    def __init__(self, config: Dict[str, Any]):
        self.ollama_url = config.get("ollama_url")
        self.ollama_api_base = config.get("ollama_api_base")
        self.ollama_model = config.get("ollama_model", "llama3:latest")
        self.connection_timeout = config.get("connection_timeout", 120)
        self.is_healthy = False
        self.last_check = 0
        self.check_interval = config.get("ollama_check_interval", 30)

    def check_health(self) -> bool:
        """Check if Ollama is available"""
        try:
            tags_url = f"{self.ollama_api_base}/api/tags"
            response = requests.get(tags_url, timeout=10)
            self.is_healthy = response.status_code == 200
            return self.is_healthy
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            self.is_healthy = False
            return False

    def call_llm(self, prompt: str, system_prompt: str = "") -> Optional[Dict[str, Any]]:
        """Call Ollama LLM for plan generation"""
        if not self.is_healthy:
            self.check_health()

        if not self.is_healthy:
            logger.warning("Ollama not available, using fallback planning")
            return None

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 3000
            }
        }

        try:
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.connection_timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return None


class PromptBuilder:
    """Builds LLM prompts for plan generation with catalog awareness"""

    SYSTEM_PROMPT = """You are an expert Pegasus Workflow Management System planner agent.
Your role is to generate executable repair plans based on workflow failure analysis.

PEGASUS ARCHITECTURE UNDERSTANDING:
- Workflows are defined by: workflow.yml (descriptor) + workflow generator Python script
- Catalogs can be: embedded in workflow.yml OR separate files (replica, transformation, site)
- Resources are defined in: site catalog (condor profiles, memory, cores, disk)
- Data locations are in: replica catalog (LFN → PFN mappings)
- Executables are in: transformation catalog (programs/scripts to run)

⚠️  CRITICAL: TRANSFORMATION SCRIPTS ARE TEMPORARY!
- Scripts like /srv/./FineTuneLLM are TEMPORARY execution scripts created by Pegasus
- The ACTUAL SOURCE is in: workflow generator script (permanent) OR workflow YAML (temporary)
- If transformation has syntax error: Fix the SOURCE, not the temporary execution script!
- Workflow files provided include: generator script content + workflow YAML content
- Use these to find and fix transformation definitions

TYPES OF REPAIRS:
1. RESOURCE ISSUES (memory, disk, cores):
   - Modify site catalog condor profiles
   - If embedded: use 'yq' to edit workflow.yml sites section
   - If separate: edit sites.yml or regenerate workflow with updated resources
   - Consider: May need to update workflow GENERATOR script for permanent fix

2. DATA/FILE ISSUES (missing files, wrong paths):
   - Add/update replica catalog entries
   - Verify file actually exists before adding
   - Update LFN→PFN mappings
   - Consider: May need to update workflow GENERATOR to produce correct paths

3. TRANSFORMATION ISSUES (missing executables, wrong versions):
   - Update transformation catalog
   - Verify executable exists and is correct version
   - Check container/environment requirements

4. WORKFLOW REGENERATION (when catalog changes aren't enough):
   - Modify workflow generator Python script
   - Re-run: pegasus-plan workflow.yml
   - This creates fresh workflow with updated settings

5. UNKNOWN/COMPLEX ERRORS (when error doesn't match common patterns):
   - Provide diagnostic commands to investigate the issue
   - Commands: pegasus-analyzer -v, condor_q -analyze, condor_q -better-analyze
   - Check job logs: cat <submit-dir>/*/jobstate.log
   - Check Condor logs: condor_q -l <job-id>
   - Suggest manual investigation steps with clear guidance
   - Recommend checking Pegasus documentation or support
   - If unsure about fix: Mark as "requires_manual_intervention: true"
   - Provide troubleshooting workflow rather than potentially wrong fix
   - Include commands to gather more information for debugging

WORKFLOW REPAIR STRATEGY - NEW SUBMISSION (NOT REPLAN):
After modifying the workflow descriptor (YAML), you MUST submit as a NEW workflow:

🚨 IMPORTANT: DO NOT use --cleanup inplace for failed/held workflows
Instead, create a NEW submission to keep the old run for debugging

1. FIX THE WORKFLOW FILE:
   - Modify the YAML file (update memory, fix paths, etc.)
   - Example: yq eval '.transformationCatalog.transformations[0].profiles.pegasus.memory = 15000' -i <workflow.yml>

2. SUBMIT AS NEW WORKFLOW (NOT replan old one):
   pegasus-plan --dir <workflow.yml> --output-sites <site> --submit

   This will create a NEW run directory (run0049, run0050, etc.)
   The old failed run (run0048) is preserved for debugging

3. VALIDATION AFTER NEW SUBMISSION:
   - Wait for new workflow to start
   - Check status: pegasus-status <new-submit-dir>
   - Monitor: pegasus-analyzer <new-submit-dir>

COMPLETE REPAIR WORKFLOW:
Step 1: Fix the issue (modify YAML/catalog)
Step 2: Submit NEW workflow (pegasus-plan --dir <workflow.yml> --submit)
Step 3: Validate new submission (pegasus-status)
Step 4: Monitor execution

You must provide:
1. Specific bash/Pegasus commands to fix issues
2. NEW SUBMISSION commands (pegasus-plan --dir <workflow.yml> --submit) - NO --cleanup inplace!
3. Validation steps (pegasus-status on NEW workflow)
4. Rollback commands if needed
5. Risk assessment (low/medium/high)
6. Whether workflow regeneration is needed

Output format: JSON with executable commands.

CRITICAL: READ THE ANALYSIS CAREFULLY BEFORE GENERATING PLAN!

🔥 PARENT ERROR PRIORITIZATION (ROOT CAUSE ANALYSIS):
When multiple errors are present, the analysis may identify a "parent error" (root cause):
- Parent errors CAUSE cascade errors - fix the parent first!
- Example: SyntaxError in script → causes POST_SCRIPT_FAILED → causes Transfer failure
- Example: Missing input file → causes multiple job failures

IF PARENT ERROR IS IDENTIFIED:
1. ✅ Focus your plan on fixing the PARENT ERROR ONLY
2. ✅ Cascade errors will resolve automatically when parent is fixed
3. ✅ Do NOT create separate steps for cascade errors
4. ✅ Mention in plan summary: "Fixing root cause - cascade errors will auto-resolve"

PARENT ERROR WILL BE PROVIDED IN:
- workflow_context['parent_error_analysis']['parent_error'] - The root cause to fix
- workflow_context['parent_error_analysis']['cascade_errors'] - Will auto-resolve (ignore these)
- workflow_context['parent_error_analysis']['confidence'] - How confident we are

ERROR TYPE MATCHING:
1. If analysis mentions "SyntaxError" or "Python error" → Fix Python script, NOT catalog
2. If analysis mentions "memory exceeded" or "out of memory" → Fix memory in catalog
3. If analysis mentions "missing file" or "file not found" → Fix replica catalog
4. If analysis mentions "permission denied" → Fix permissions, NOT catalog
5. If analysis mentions "syntax error in script" → Manual code review needed
6. If error doesn't match known patterns → Use diagnostic commands

IMPORTANT RULES:
- 🚨 READ THE ERROR MESSAGE - Don't assume it's a memory issue!
- Match your solution to the ACTUAL error type from the analysis
- If analysis says "SyntaxError in script" → DO NOT fix memory!
- ALWAYS include NEW submission step after modifying workflow YAML
- DO NOT use --cleanup inplace (we want a new run, not replan the old failed one)
- ALWAYS consider if the fix should be in the GENERATOR script (for permanent fix)
- For resource problems: update transformation/site catalog AND suggest generator changes
- Only generate commands you are confident will work
- Always include validation after modifications
- Provide rollback strategy for file modifications
- Mark risky operations clearly
- If unsure or error is complex/unknown: Set "requires_manual_intervention": true
- For unknown errors: Provide diagnostic commands instead of guessing a fix
- For embedded catalogs, use 'yq' YAML editor
- For text catalogs, use 'echo' or 'sed'
- Include working directory context (from braindump submit_dir)
- Better to suggest investigation steps than a potentially wrong fix
"""

    @staticmethod
    def build_planner_prompt(analysis_result: Dict[str, Any], catalogs: Dict[str, Any], workflow_context: Dict[str, Any]) -> str:
        """Build comprehensive prompt with catalog awareness"""

        # Build catalog information section
        catalog_info = PromptBuilder._build_catalog_section(catalogs)

        # Build analysis section
        analysis_section = json.dumps(analysis_result, indent=2)

        # Get workflow files info from context (sent by Monitor via Analyzer)
        workflow_files_info = PromptBuilder._discover_workflow_files(workflow_context)

        # Extract braindump metadata for paths
        workflow_files = workflow_context.get('workflow_files', {})
        braindump_metadata = workflow_files.get('braindump_metadata', {})
        submit_dir = braindump_metadata.get('submit_dir', workflow_context.get('workflow_dir'))
        dax_path = braindump_metadata.get('dax', 'workflow.yml')

        prompt = f"""
Given the following workflow failure analysis, generate a detailed executable repair plan.

=== WORKFLOW INFORMATION ===
Workflow ID: {workflow_context.get('workflow_id')}
Workflow Directory: {workflow_context.get('workflow_dir')}
Submit Directory: {submit_dir}
Workflow Descriptor (DAX): {dax_path}
Current State: {workflow_context.get('state', 'unknown')}

🚨 CRITICAL: USE THESE EXACT PATHS IN ALL COMMANDS 🚨
NEVER use placeholders like /path/to/workflow.yml or <workflow.yml>
ALWAYS use the EXACT paths provided below:

MANDATORY PATHS TO USE IN COMMANDS:
- Submit Dir: {submit_dir}
  → Use in: pegasus-status {submit_dir}
  → Use in: pegasus-analyzer {submit_dir}
  → Use in: cd {submit_dir}

- Workflow YAML: {dax_path}
  → Use in: yq eval '...' -i {dax_path}
  → Use in: pegasus-plan --dir {dax_path} ...

- Working Dir: {workflow_context.get('workflow_dir')}

EXAMPLE CORRECT COMMAND:
  yq eval '.transformationCatalog.transformations[0].profiles.pegasus.memory = 15000' -i {dax_path}

EXAMPLE WRONG COMMAND (DO NOT DO THIS):
  yq eval '...' -i /path/to/workflow.yml  ❌ WRONG - This is a placeholder!

=== WORKFLOW FILES ===
{workflow_files_info}

=== CATALOG INFORMATION ===
{catalog_info}

=== FAILURE ANALYSIS ===
{analysis_section}
"""

        # ENHANCED: Add parent error analysis if available
        parent_error_analysis = workflow_context.get('parent_error_analysis')
        if parent_error_analysis and parent_error_analysis.get('parent_error'):
            parent = parent_error_analysis['parent_error']
            cascade_count = parent_error_analysis.get('cascade_count', 0)
            confidence = parent_error_analysis.get('confidence', 'unknown')
            method = parent_error_analysis.get('analysis_method', 'unknown')

            parent_section = f"""

🔥 ROOT CAUSE ANALYSIS (PARENT ERROR DETECTED):
================================================================================
IMPORTANT: Multiple errors detected, but ONE is the root cause!

Parent Error (ROOT CAUSE - FIX THIS FIRST):
  Problem: {parent.get('problem', 'Unknown')}
  Solution: {parent.get('solution', 'Unknown')}
  Error Level: {parent.get('error_level', 'unknown')}
  Priority: {parent.get('priority', 'unknown')}

Cascade Errors (will auto-resolve when parent is fixed): {cascade_count}
Confidence: {confidence}
Analysis Method: {method}

⚠️  CRITICAL INSTRUCTIONS:
1. Your repair plan should ONLY fix the parent error above
2. Do NOT create separate steps for cascade errors - they will resolve automatically
3. Cascade errors are symptoms of the parent error
4. Example: If parent is "SyntaxError in script", fixing the script will resolve:
   - POST_SCRIPT_FAILED errors
   - Transfer output failures
   - Job execution failures
   All these are just symptoms of the syntax error!

5. In your plan_summary, mention: "Fixing root cause: [parent error]. Cascade errors will auto-resolve."
================================================================================
"""
            prompt += parent_section

        prompt += """

=== YOUR TASK ===
Generate a repair plan with the following JSON structure:

{{
  "plan_summary": "Brief description of the fix",
  "repair_strategy": "automatic|semi-automatic|manual",
  "estimated_time": "time estimate",
  "risk_level": "low|medium|high",
  "risk_explanation": "why this risk level",

  "repair_steps": [
    {{
      "step_number": 1,
      "description": "What this step does",
      "action_type": "modify_file|run_command|validate",
      "target": "file or command target",
      "commands": [
        "specific bash command 1",
        "specific bash command 2"
      ],
      "validation_command": "command to verify this worked",
      "expected_result": "what success looks like",
      "rollback_commands": ["commands to undo this step"]
    }}
  ],

  "preconditions": [
    "List conditions that must be true before executing"
  ],

  "success_criteria": [
    "How to know the fix worked"
  ],

  "fallback_plan": "What to do if this plan fails",

  "confidence_score": {{
    "score": 0.85,
    "explanation": "Why you are confident in this plan"
  }},

  "requires_approval": true/false,
  "approval_reason": "Why human approval is needed (if applicable)",

  "requires_manual_intervention": true/false,
  "manual_intervention_reason": "Why this issue needs manual investigation (if applicable - for unknown/complex errors)",
  "diagnostic_commands": [
    "List of diagnostic commands to run for troubleshooting",
    "Example: pegasus-analyzer -v <submit-dir>",
    "Example: condor_q -better-analyze <job-id>"
  ],

  "generator_script_review_needed": true/false,
  "generator_modifications_suggested": [
    "Description of changes needed in generator script for permanent fix",
    "Example: Update request_memory from 2GB to 8GB in Site() configuration"
  ],

  "workflow_regeneration_needed": true/false,
  "regeneration_reason": "Why workflow needs to be regenerated (if applicable)"
}}

EXAMPLES OF PEGASUS-SPECIFIC REPAIRS (USING ACTUAL PATHS FOR THIS WORKFLOW):

Example 1 - MEMORY ISSUE (Transformation Catalog - EMBEDDED):
  Problem: Job exceeded memory limit (10GB requested, needs 15GB)

  Step 1: Update transformation memory in workflow YAML
    yq eval '.transformationCatalog.transformations[0].profiles.pegasus.memory = 15000' -i {dax_path}

  Step 2: Submit NEW workflow (NOT replan old one)
    pegasus-plan --dir {dax_path} --output-sites local --submit

  Step 3: Validate NEW submission (new run will be created)
    # New run directory will be created automatically (e.g., run0049)
    # Wait a moment, then check status of the new run

  Step 4: Monitor new workflow execution
    # Find new run: ls -lt {workflow_context.get('workflow_dir')}/run* | head -1
    # Then: pegasus-status <new-run-dir>

  Note: Old run ({submit_dir}) is preserved for debugging
  Note: For permanent fix, update memory in generator script and regenerate

Example 2 - MEMORY ISSUE (Site Catalog - EMBEDDED):
  Step 1: Update site catalog memory
    yq eval '.siteCatalog.sites[] | select(.name == "condorpool") | .profiles.condor.request_memory = "8GB"' -i {dax_path}

  Step 2: Submit NEW workflow
    pegasus-plan --dir {dax_path} --output-sites local --submit

  Step 3: Validate new submission
    # New run created automatically, old run preserved

Example 3 - MISSING FILE (Replica Catalog - EMBEDDED):
  Step 1: Verify file exists
    test -f /data/input.csv || echo "ERROR: File not found"

  Step 2: Add to replica catalog in workflow YAML
    yq eval '.replicaCatalog.replicas += [{{"lfn": "input.csv", "pfn": "file:///data/input.csv", "site": "local"}}]' -i {dax_path}

  Step 3: Submit NEW workflow
    pegasus-plan --dir {dax_path} --output-sites local --submit

  Step 4: Validate
    # New run will be created, check its status

Example 4 - DISK SPACE ISSUE:
  Step 1: Update disk requirement in site catalog
    yq eval '.sites[0].profiles.condor.request_disk = "10GB"' -i workflow.yml
  Step 2: Update generator for permanent fix
    # Add note to modify generator script disk settings

Example 5 - SYNTAX ERROR IN TRANSFORMATION SCRIPT (Code issue, CAN be auto-fixed!):
  Problem: SyntaxError in FineTuneLLM script: invalid syntax. Perhaps you forgot a comma?

  IMPORTANT: Transformation scripts are provided in workflow_files.transformation_scripts!
  The script content is available - LLM can analyze and suggest fixes!

  Step 1: Get transformation script path from YAML
    yq eval '.transformationCatalog.transformations[] | select(.name == "FineTuneLLM") | .pfn' {dax_path}
    # Returns: /srv/FineTuneLLM (actual script path)

  Step 2: Review the script content (provided in workflow_files)
    # Script content is in: workflow_files['transformation_scripts']['FineTuneLLM']['content']
    # Analyze the script for syntax errors
    # Identify the missing comma or syntax issue

  Step 3: Fix the syntax error in the script
    # Example fix for missing comma in function call:
    sed -i 's/arg1 arg2/arg1, arg2/' /srv/FineTuneLLM
    # OR use a more specific fix based on the actual error

  Step 4: Validate the fix
    python -m py_compile /srv/FineTuneLLM

  Step 5: Submit NEW workflow
    pegasus-plan --dir {dax_path} --output-sites local --submit

  Note: If transformation_scripts is available, LLM CAN suggest specific fix!
  Note: If script content not available, mark requires_manual_intervention: true

Example 6 - UNKNOWN/COMPLEX ERROR (Error pattern not recognized):
  Problem: Unfamiliar error or complex multi-factor issue

  Step 1: Run diagnostic commands to gather information
    pegasus-analyzer -v {submit_dir}
    condor_q -better-analyze <job-id>

  Step 2: Check detailed logs
    cat {submit_dir}/*/jobstate.log
    condor_q -l <job-id> | grep -i hold

  Step 3: Provide troubleshooting guidance
    # Check Pegasus logs: {submit_dir}/*.log
    # Check job stderr: {submit_dir}/*/*.err
    # Review Pegasus documentation: https://pegasus.isi.edu/documentation/

  Step 4: Mark for manual intervention
    requires_manual_intervention: true
    approval_reason: "Complex error requiring expert analysis"

  Note: When unsure, provide diagnostic steps rather than risky fixes

COMMAND SYNTAX GUIDE:
- Add to replica catalog (text): echo 'lfn pfn site' >> /path/rc.txt
- Add to replica catalog (YAML): yq eval '.replicaCatalog.replicas += [{{"lfn": "data.csv", "pfn": "file:///path", "site": "local"}}]' -i /path/workflow.yml
- Update site memory (YAML): yq eval '.sites[0].profiles.condor.request_memory = "4GB"' -i /path/sites.yml
- Update site cores (YAML): yq eval '.sites[0].profiles.condor.request_cpus = "4"' -i /path/sites.yml
- Update site disk (YAML): yq eval '.sites[0].profiles.condor.request_disk = "10GB"' -i /path/sites.yml
- Check file exists: test -f /path/to/file && echo "exists"
- Resubmit workflow: cd /workflow/submit-dir && pegasus-run .
- Release held job: condor_release <job_id>
- Check workflow status: pegasus-status /workflow/submit-dir
- Regenerate workflow: cd /workflow && python generate_workflow.py && pegasus-plan workflow.yml

REPAIR STRATEGY DECISION:
- Use QUICK FIX (modify workflow.yml) if: One-time issue, need immediate resolution
- Use PERMANENT FIX (modify generator) if: Recurring issue, need long-term solution
- Use WORKFLOW REGENERATION if: Major changes needed, multiple catalog updates
- ALWAYS mention both quick and permanent fix options in the plan

🚨 CRITICAL REMINDERS BEFORE GENERATING PLAN 🚨:

1. ALWAYS use the exact paths provided above:
   - Workflow YAML: {dax_path}
   - Old Submit Dir (for reference): {submit_dir}

2. ALWAYS include BOTH steps for workflow modifications:
   Step 1: Modify the file (yq/sed/echo command)
   Step 2: Submit NEW workflow (pegasus-plan --dir {dax_path} --submit)

   ⚠️ DO NOT use --cleanup inplace! We want a NEW run, not replan the old failed one!

3. DO NOT use placeholders like:
   ❌ /path/to/workflow.yml
   ❌ <workflow.yml>
   ❌ /workflow/submit-dir
   ✅ Use: {dax_path}

4. Memory issues REQUIRE:
   - Step 1: Update memory value with yq in {dax_path}
   - Step 2: Submit NEW workflow: pegasus-plan --dir {dax_path} --output-sites local --submit
   - Step 3: Note that new run will be created (e.g., run0049)
   - Step 4: Old run {submit_dir} is preserved for debugging

5. VALIDATION commands should note:
   - "New run directory will be created automatically"
   - "Wait for new workflow to start, then check status"
   - "Old failed run is preserved"

🔥 FINAL CHECK BEFORE GENERATING PLAN 🔥:

1. What is the ACTUAL error from the analysis?
   - SyntaxError in transformation script? → Check if script content is in transformation_scripts
   - Memory error? → Fix memory in catalog
   - Missing file? → Fix replica catalog
   - Other? → Diagnostic commands

2. Is transformation script content available?
   - If workflow_files.transformation_scripts has the script → LLM CAN analyze and fix it!
   - Script content shows the exact code → Identify the syntax error
   - Generate sed/awk command to fix the specific error
   - If script not available → Mark requires_manual_intervention: true

3. Does your solution match the error type?
   - If analysis says "SyntaxError in FineTuneLLM" AND script content available → Fix the script!
   - If analysis says "SyntaxError" but NO script content → Diagnostic commands only
   - If analysis says "exceeded memory" → Fix memory in catalog

4. Are you confident in the fix?
   - Script content visible + clear syntax error → Provide sed/awk fix command
   - No script content OR complex error → Set requires_manual_intervention: true

Generate the plan now with EXACT paths, NEW submission (NOT replan), and use transformation_scripts content if available:
"""
        return prompt

    @staticmethod
    def _discover_workflow_files(workflow_context: Dict[str, Any]) -> str:
        """Use workflow files from context (sent by Monitor) to build prompt section"""
        import os

        info = []
        workflow_files = workflow_context.get('workflow_files', {})
        workflow_dir = workflow_context.get('workflow_dir', '')

        # Use workflow YAML from context
        if workflow_files.get('workflow_yaml'):
            wf = workflow_files['workflow_yaml']
            info.append(f"Workflow Descriptor: {wf.get('path', 'N/A')}")
            info.append("  → This file defines the workflow structure and catalogs")
            info.append("  → Can be regenerated if needed")

            # Include parsed structure first for quick reference
            parsed = wf.get('parsed_structure', {})
            if parsed:
                info.append("\n=== PARSED WORKFLOW STRUCTURE (JSON) ===")
                info.append("This structured data can be used to extract and modify specific elements:")

                if parsed.get('jobs'):
                    info.append(f"\nJOBS ({len(parsed['jobs'])} total):")
                    import json
                    info.append(json.dumps(parsed['jobs'], indent=2))

                if parsed.get('transformations'):
                    info.append(f"\nTRANSFORMATIONS ({len(parsed['transformations'])} total - EMBEDDED):")
                    info.append(json.dumps(parsed['transformations'], indent=2))
                    info.append("  → To modify: Use 'yq' on workflow.yml at path: .pegasus.transformations")

                if parsed.get('replicas'):
                    info.append(f"\nREPLICAS ({len(parsed['replicas'])} total - EMBEDDED):")
                    info.append(json.dumps(parsed['replicas'], indent=2))
                    info.append("  → To modify: Use 'yq' on workflow.yml at path: .pegasus.replicas")

                if parsed.get('sites'):
                    info.append(f"\nSITES ({len(parsed['sites'])} total - EMBEDDED):")
                    info.append(json.dumps(parsed['sites'], indent=2))
                    info.append("  → To modify: Use 'yq' on workflow.yml at path: .pegasus.sites[INDEX]")

                info.append("=== END PARSED STRUCTURE ===\n")

            # Include the YAML content that Monitor already read
            yaml_content = wf.get('content', '')
            if yaml_content:
                info.append("\n=== CURRENT WORKFLOW YAML CONTENT ===")
                info.append(yaml_content)
                info.append("=== END YAML CONTENT ===\n")
            else:
                info.append("  → WARNING: YAML content not available")

        # ENHANCED: Include transformation scripts content
        if workflow_files.get('transformation_scripts'):
            trans_scripts = workflow_files['transformation_scripts']
            info.append(f"\n=== TRANSFORMATION SCRIPTS ({len(trans_scripts)} available) ===")
            info.append("These are the actual executable scripts from the workflow:")

            for script_name, script_data in trans_scripts.items():
                info.append(f"\n--- Script: {script_name} ---")
                info.append(f"Path: {script_data.get('path')}")
                info.append(f"Type: {script_data.get('type')}")

                if 'content' in script_data:
                    info.append(f"\n=== SCRIPT CONTENT ({script_name}) ===")
                    info.append(script_data['content'])
                    info.append(f"=== END SCRIPT CONTENT ({script_name}) ===")
                    info.append("\n🔧 THIS SCRIPT CAN BE MODIFIED:")
                    info.append(f"   - Use sed/awk to fix syntax errors")
                    info.append(f"   - Path: {script_data.get('path')}")
                    info.append(f"   - Validate with: python -m py_compile {script_data.get('path')}")
                elif 'error' in script_data:
                    info.append(f"ERROR: Could not read script - {script_data.get('error')}")

            info.append("\n=== END TRANSFORMATION SCRIPTS ===\n")

        # Use generator script from context
        if workflow_files.get('generator_script'):
            gs = workflow_files['generator_script']
            info.append(f"\nWorkflow Generator Script: {gs.get('path', 'N/A')}")
            info.append("  → This script generates the workflow descriptor")
            info.append("  → Modify this for PERMANENT fixes to resources/paths")
            info.append(f"  → Re-run with: python {gs.get('filename', 'generator.py')} to regenerate workflow.yml")

            # Provide info about generator availability
            info.append("\n  ℹ️  GENERATOR SCRIPT AVAILABLE:")
            info.append("     If you need to see the generator script content to suggest")
            info.append("     permanent fixes, include in your plan:")
            info.append("     'generator_script_review_needed': true")
            info.append("     The Executor agent can read and analyze it for modifications.")

        # Look for submit directory (planned workflow) - this still needs filesystem access
        if workflow_dir and os.path.exists(workflow_dir):
            try:
                submit_dirs = [d for d in os.listdir(workflow_dir) if os.path.isdir(os.path.join(workflow_dir, d))
                              and d.startswith(os.path.basename(workflow_dir))]

                if submit_dirs:
                    info.append(f"\nSubmit Directory: {submit_dirs[0]}/")
                    info.append("  → Contains the planned/submitted workflow")
                    info.append("  → Use: pegasus-run {submit_dirs[0]} to resubmit")
                    info.append("  → Use: pegasus-status {submit_dirs[0]} to check status")
            except Exception as e:
                pass  # Directory listing may fail, not critical

        return "\n".join(info) if info else "No workflow files received from Monitor"

    @staticmethod
    def _build_catalog_section(catalogs: Dict[str, Any]) -> str:
        """Build catalog information section for prompt"""
        sections = []

        if catalogs.get('replica_catalog'):
            rc = catalogs['replica_catalog']
            if rc.get('embedded'):
                sections.append(f"""
Replica Catalog: EMBEDDED in workflow YAML
  - Location: {rc.get('parent_file')}
  - YAML Path: {rc.get('path')}
  - Format: {rc.get('format')}
  - To modify: Use 'yq' to edit YAML at path '{rc.get('path')}'
  - Example: yq eval '.replicaCatalog.replicas += [{{"lfn": "data.csv", "pfn": "file:///data/input.csv", "site": "local"}}]' -i {rc.get('parent_file')}
""")
            else:
                sections.append(f"""
Replica Catalog: Separate file
  - Location: {rc.get('path')}
  - Format: {rc.get('format')}
  - Writable: {rc.get('writable', False)}
  - To modify: Use 'echo' to append or 'sed' to edit
  - Example: echo 'data.csv file:///data/input.csv local' >> {rc.get('path')}
""")

        if catalogs.get('transformation_catalog'):
            tc = catalogs['transformation_catalog']
            if tc.get('embedded'):
                sections.append(f"""
Transformation Catalog: EMBEDDED in workflow YAML
  - Location: {tc.get('parent_file')}
  - YAML Path: {tc.get('path')}
  - Format: {tc.get('format')}
  - To modify: Use 'yq' to edit YAML
""")
            else:
                sections.append(f"""
Transformation Catalog: Separate file
  - Location: {tc.get('path')}
  - Format: {tc.get('format')}
""")

        if catalogs.get('site_catalog'):
            sc = catalogs['site_catalog']
            if sc.get('embedded'):
                sections.append(f"""
Site Catalog: EMBEDDED in workflow YAML
  - Location: {sc.get('parent_file')}
  - YAML Path: {sc.get('path')}
  - Format: {sc.get('format')}
  - To modify: Use 'yq' to edit YAML
  - Example: yq eval '.sites[0].profiles.condor.request_memory = "4GB"' -i {sc.get('parent_file')}
""")
            else:
                sections.append(f"""
Site Catalog: Separate file
  - Location: {sc.get('path')}
  - Format: {sc.get('format')}
""")

        return "\n".join(sections) if sections else "No catalog files found"


class PlanValidator:
    """Validates and assesses risk of generated plans"""

    @staticmethod
    def validate_plan(plan: Dict[str, Any], workflow_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plan and assess risk"""
        issues = []

        # Check 1: Plan has required fields
        required_fields = ["plan_summary", "repair_steps", "confidence_score"]
        for field in required_fields:
            if field not in plan:
                issues.append(f"Missing required field: {field}")

        # Check 2: Commands are not empty
        for step in plan.get("repair_steps", []):
            if not step.get("commands"):
                issues.append(f"Step {step.get('step_number')} has no commands")

        # Check 3: Dangerous commands (more specific patterns)
        dangerous_patterns = [
            "rm -rf /",           # Delete root
            "dd if=/dev/zero",    # Overwrite disk
            "> /dev/sd",          # Write to disk device
            "mkfs.",              # Format disk
            "fdisk",              # Partition disk
            "chmod 777 /",        # Chmod root
            "chown root /",       # Chown root
        ]
        for step in plan.get("repair_steps", []):
            for cmd in step.get("commands", []):
                # Only flag truly dangerous commands, not yq/pegasus commands
                if any(pattern in cmd for pattern in dangerous_patterns):
                    issues.append(f"Dangerous command detected: {cmd}")
                    plan["risk_level"] = "high"
                    plan["requires_approval"] = True

        # Check 4: Confidence score
        confidence = plan.get("confidence_score", {}).get("score", 0)
        if confidence < 0.6:
            issues.append("Low confidence score - requires approval")
            plan["requires_approval"] = True

        # Check 5: Risk level assessment
        if plan.get("risk_level") not in ["low", "medium", "high"]:
            plan["risk_level"] = "medium"

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "risk_assessment": {
                "risk_level": plan.get("risk_level", "medium"),
                "requires_approval": plan.get("requires_approval", False),
                "auto_execute": len(issues) == 0 and not plan.get("requires_approval", False) and confidence >= 0.75
            }
        }


class LLMPlanner:
    """Main LLM-powered planner agent"""

    def __init__(self, config_file: str = "planner_config.json"):
        self.config = self.load_config(config_file)
        self.ollama_manager = OllamaManager(self.config)
        self.prompt_builder = PromptBuilder()
        self.validator = PlanValidator()

        # Database
        self.plans_table = plans_table
        self.execution_requests_table = execution_requests_table

        # Check Ollama health
        self.ollama_manager.check_health()

    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Config file {config_file} not found, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    async def generate_plan_with_llm(
        self,
        analysis_result: Dict[str, Any],
        catalogs: Dict[str, Any],
        workflow_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate repair plan using LLM"""

        logger.info(f"Generating plan for workflow {workflow_context.get('workflow_id')}")

        # Build prompt
        prompt = self.prompt_builder.build_planner_prompt(analysis_result, catalogs, workflow_context)

        # Call LLM
        llm_response = self.ollama_manager.call_llm(prompt, self.prompt_builder.SYSTEM_PROMPT)

        if llm_response:
            try:
                # Parse LLM output
                plan = self.parse_llm_response(llm_response)

                # Validate plan
                validation_result = self.validator.validate_plan(plan, workflow_context)

                # Add metadata
                plan["plan_id"] = str(uuid.uuid4())
                plan["workflow_id"] = workflow_context.get("workflow_id")
                plan["created_at"] = datetime.now().isoformat()
                plan["validation_result"] = validation_result
                plan["llm_used"] = True

                # Store plan
                self.plans_table.insert(plan)

                # Print plan summary
                self.print_plan_summary(plan)

                return plan

            except Exception as e:
                logger.error(f"Error parsing LLM response: {e}")
                return self.generate_fallback_plan(analysis_result, workflow_context)
        else:
            logger.warning("LLM not available, using fallback planning")
            return self.generate_fallback_plan(analysis_result, workflow_context)

    def parse_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM JSON response"""
        response_text = llm_response.get("response", "")

        # Clean up markdown if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.rfind("```")
            if end > start:
                response_text = response_text[start:end].strip()

        # Parse JSON
        plan = json.loads(response_text)
        return plan

    def generate_fallback_plan(self, analysis_result: Dict[str, Any], workflow_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic fallback plan without LLM"""
        logger.info("Generating fallback plan")

        plan = {
            "plan_id": str(uuid.uuid4()),
            "workflow_id": workflow_context.get("workflow_id"),
            "created_at": datetime.now().isoformat(),
            "plan_summary": "Manual intervention required - LLM unavailable",
            "repair_strategy": "manual",
            "risk_level": "high",
            "risk_explanation": "Automated planning unavailable",
            "repair_steps": [
                {
                    "step_number": 1,
                    "description": "Review analysis and determine fix manually",
                    "action_type": "manual_review",
                    "target": "workflow",
                    "commands": ["echo 'Manual review required'"],
                    "validation_command": "echo 'Manual validation required'",
                    "expected_result": "Human review completed"
                }
            ],
            "confidence_score": {"score": 0.3, "explanation": "Fallback mode - manual intervention needed"},
            "requires_approval": True,
            "approval_reason": "LLM unavailable, automated planning not possible",
            "llm_used": False,
            "fallback_mode": True,
            "validation_result": {
                "valid": True,
                "issues": [],
                "risk_assessment": {
                    "risk_level": "high",
                    "requires_approval": True,
                    "auto_execute": False
                }
            }
        }

        self.plans_table.insert(plan)
        return plan

    def print_plan_summary(self, plan: Dict[str, Any]):
        """Print colorful plan summary to console"""
        print(f"\n{'='*80}")
        print(f"{TerminalColor.BRIGHT_GREEN.apply('📋 REPAIR PLAN GENERATED')}")
        print(f"{'='*80}")
        print(f"{TerminalColor.CYAN.apply('Plan ID:')} {plan.get('plan_id')}")
        print(f"{TerminalColor.CYAN.apply('Workflow ID:')} {plan.get('workflow_id')}")
        print(f"{TerminalColor.CYAN.apply('Summary:')} {plan.get('plan_summary')}")
        print(f"{TerminalColor.CYAN.apply('Strategy:')} {plan.get('repair_strategy')}")
        print(f"{TerminalColor.CYAN.apply('Risk Level:')} {plan.get('risk_level')}")
        print(f"{TerminalColor.CYAN.apply('LLM Used:')} {plan.get('llm_used', False)}")

        validation = plan.get('validation_result', {})
        auto_exec = validation.get('risk_assessment', {}).get('auto_execute', False)
        print(f"{TerminalColor.CYAN.apply('Auto Execute:')} {auto_exec}")

        print(f"\n{TerminalColor.BRIGHT_YELLOW.apply('🔧 Repair Steps:')}")
        for step in plan.get("repair_steps", []):
            step_num = step.get("step_number")
            step_desc = step.get("description")
            print(f"\n  {TerminalColor.WHITE.apply(f'Step {step_num}:')} {step_desc}")
            for cmd in step.get("commands", []):
                print(f"    {TerminalColor.GREEN.apply('$')} {cmd}")

        confidence = plan.get("confidence_score", {})
        print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('📊 Confidence:')} {confidence.get('score', 'N/A')}")
        print(f"  {confidence.get('explanation', 'N/A')}")

        # Display generator script review info if applicable
        if plan.get("generator_script_review_needed"):
            print(f"\n{TerminalColor.BRIGHT_YELLOW.apply('⚠️  GENERATOR SCRIPT REVIEW NEEDED')}")
            print(f"  {TerminalColor.YELLOW.apply('For permanent fix, the workflow generator script needs modification:')}")
            for suggestion in plan.get("generator_modifications_suggested", []):
                print(f"    • {suggestion}")

        # Display workflow regeneration info if applicable
        if plan.get("workflow_regeneration_needed"):
            print(f"\n{TerminalColor.BRIGHT_CYAN.apply('🔄 WORKFLOW REGENERATION RECOMMENDED')}")
            print(f"  {TerminalColor.CYAN.apply('Reason:')} {plan.get('regeneration_reason', 'Major changes required')}")

        print(f"{'='*80}\n")

    def convert_plan_to_execution_request(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Convert plan to executor-friendly format"""
        execution_steps = []

        for step in plan.get("repair_steps", []):
            execution_step = {
                "step_id": step.get("step_number"),
                "description": step.get("description"),
                "commands": step.get("commands", []),
                "validation": {
                    "command": step.get("validation_command", "echo 'No validation'"),
                    "expected_result": step.get("expected_result")
                },
                "rollback_commands": step.get("rollback_commands", []),
                "timeout_seconds": 60,
                "continue_on_failure": False
            }
            execution_steps.append(execution_step)

        execution_request = {
            "execution_request_id": str(uuid.uuid4()),
            "workflow_id": plan.get("workflow_id"),
            "plan_id": plan.get("plan_id"),
            "plan_summary": plan.get("plan_summary"),
            "execution_mode": plan.get("repair_strategy", "manual"),
            "requires_approval": plan.get("requires_approval", True),
            "execution_steps": execution_steps,
            "rollback_strategy": {
                "enabled": True,
                "auto_rollback_on_failure": True
            },
            "monitoring": {
                "report_progress": True,
                "webhook_url": f"http://localhost:{HTTP_PORT}/webhooks/execution-status"
            }
        }

        self.execution_requests_table.insert(execution_request)
        return execution_request


class PlannerHTTPServer:
    """HTTP server for Planner agent"""

    def __init__(self, planner: LLMPlanner, config: Dict[str, Any]):
        self.planner = planner
        self.config = config
        self.app = web.Application()
        self.setup_routes()

    def write_workflow_step(self, workflow_id: str, agent: str, step: str, message: str, status: str = "INFO"):
        """Write workflow processing step to shared log file"""
        try:
            log_file = f"logs/workflow_{workflow_id}_steps.log"

            # Create logs directory if it doesn't exist
            if not os.path.exists("logs"):
                os.makedirs("logs")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Create colored status indicators
            status_color = {
                "INFO": TerminalColor.CYAN,
                "SUCCESS": TerminalColor.GREEN,
                "ERROR": TerminalColor.RED,
                "WARNING": TerminalColor.YELLOW
            }.get(status, TerminalColor.WHITE)

            log_entry = f"\n{'='*80}\n"
            log_entry += f"[{timestamp}] [{status_color.apply(status)}] {agent.upper()}\n"
            log_entry += f"{'='*80}\n"
            log_entry += f"STEP: {step}\n"
            log_entry += f"{'-'*80}\n"
            log_entry += f"{message}\n"
            log_entry += f"{'='*80}\n"

            with open(log_file, "a") as f:
                f.write(log_entry)

        except Exception as e:
            logger.error(f"Error writing workflow step: {e}")

    async def request_file_from_monitor(self, file_path: str, workflow_id: str = None) -> Dict[str, Any]:
        """Request specific file content from Monitor on demand"""
        try:
            monitor_url = self.config.get("monitor_url", "http://localhost:8080")

            request_data = {
                "file_path": file_path,
                "requester": "planner",
                "workflow_id": workflow_id
            }

            logger.info(f"Requesting file from Monitor: {file_path}")

            async with ClientSession() as session:
                async with session.post(
                    f"{monitor_url}/api/files/get-content",
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"Received file content: {file_path} ({result.get('size_bytes', 0)} bytes)")
                        return result
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to get file from Monitor: {resp.status} - {error_text}")
                        return {"error": error_text, "status": resp.status}

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting file from Monitor: {file_path}")
            return {"error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error requesting file from Monitor: {e}")
            return {"error": str(e)}

    def export_plan_to_file(self, plan: Dict[str, Any], workflow_id: str):
        """Export plan to a separate JSON file for easy reading"""
        try:
            # Create plans directory if it doesn't exist
            plans_dir = "plans"
            if not os.path.exists(plans_dir):
                os.makedirs(plans_dir)

            plan_id = plan.get("plan_id", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{plans_dir}/plan_{workflow_id}_{plan_id}_{timestamp}.json"

            with open(filename, "w") as f:
                json.dump(plan, f, indent=2, default=str)

            print(f"{TerminalColor.GREEN.apply('✓')} Plan exported to: {filename}")
            logger.info(f"Plan exported to {filename}")

            # Also write plan location to shared log
            self.write_workflow_step(
                workflow_id,
                "PLANNER",
                "8. PLAN EXPORTED",
                f"Plan file: {filename}\nPlan ID: {plan_id}",
                "INFO"
            )

        except Exception as e:
            logger.error(f"Error exporting plan to file: {e}")

    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_post('/webhooks/analysis-complete', self.handle_analysis_complete)
        self.app.router.add_post('/api/create-plan', self.handle_create_plan)
        self.app.router.add_get('/api/plans/{plan_id}', self.handle_get_plan)
        self.app.router.add_post('/api/plans/{plan_id}/approve', self.handle_approve_plan)
        self.app.router.add_get('/api/plans', self.handle_list_plans)

    async def handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "agent_type": "planner",
            "agent_id": "planner_001",
            "capabilities": [
                "llm_plan_generation",
                "catalog_aware_planning",
                "risk_assessment",
                "execution_request_generation"
            ],
            "ollama_available": self.planner.ollama_manager.is_healthy,
            "timestamp": datetime.now().isoformat()
        })

    async def handle_analysis_complete(self, request):
        """Handle analysis completion webhook from Analyzer"""
        try:
            data = await request.json()

            workflow_id = data.get("workflow_id")
            analysis_result = data.get("result", {}).get("analysis", {})
            catalogs = data.get("catalogs", {})
            workflow_files = data.get("workflow_files", {})  # ENHANCED: Get workflow files from Monitor
            parent_error_analysis = data.get("parent_error_analysis")  # ENHANCED: Get root cause analysis

            workflow_context = {
                "workflow_id": workflow_id,
                "workflow_dir": data.get("workflow_dir"),
                "state": "failed",
                "workflow_files": workflow_files,  # ENHANCED: Include workflow files in context
                "parent_error_analysis": parent_error_analysis  # ENHANCED: Include root cause analysis
            }

            # Write to shared log
            catalog_count = sum(1 for k, v in catalogs.items() if isinstance(v, dict))
            receive_summary = f"Catalogs Received: {catalog_count}\n"
            receive_summary += f"Workflow Files Received: {len(workflow_files)}\n"
            receive_summary += f"Problems to Solve: {len(analysis_result.get('problems_and_solutions', []))}"

            # ENHANCED: Add parent error info to summary
            if parent_error_analysis and parent_error_analysis.get('parent_error'):
                parent = parent_error_analysis['parent_error']
                cascade_count = parent_error_analysis.get('cascade_count', 0)
                receive_summary += f"\n\nROOT CAUSE ANALYSIS:"
                receive_summary += f"\nParent Error: {parent.get('problem', 'Unknown')}"
                receive_summary += f"\nCascade Errors: {cascade_count}"
                receive_summary += f"\nConfidence: {parent_error_analysis.get('confidence', 'unknown')}"

            self.write_workflow_step(
                workflow_id,
                "PLANNER",
                "6. RECEIVED FROM ANALYZER - STARTING PLAN GENERATION",
                receive_summary,
                "INFO"
            )

            # STEP 1: Received webhook
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_CYAN.apply('📥 STEP 1: RECEIVED ANALYSIS FROM ANALYZER')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.YELLOW.apply('Workflow ID:')} {workflow_id}")
            print(f"{TerminalColor.YELLOW.apply('Workflow Dir:')} {workflow_context.get('workflow_dir')}")

            # Count only dict-type catalogs (exclude metadata fields)
            catalog_count = sum(1 for k, v in catalogs.items() if isinstance(v, dict))
            print(f"{TerminalColor.YELLOW.apply('Catalogs Received:')} {catalog_count}")
            for cat_type, cat_info in catalogs.items():
                if isinstance(cat_info, dict):  # Only process dict-type catalogs
                    print(f"  {TerminalColor.GREEN.apply('✓')} {cat_type}: {cat_info.get('path')} ({cat_info.get('format')})")
            print(f"{TerminalColor.YELLOW.apply('Workflow Files Received:')} {len(workflow_files)}")
            if workflow_files.get('workflow_yaml'):
                wf = workflow_files['workflow_yaml']
                print(f"  {TerminalColor.GREEN.apply('✓')} Workflow YAML: {wf.get('filename')} ({wf.get('size')} bytes)")

                # Show parsed structure details
                parsed = wf.get('parsed_structure', {})
                if parsed:
                    if parsed.get('jobs'):
                        print(f"    • Jobs: {len(parsed['jobs'])}")
                    if parsed.get('transformations'):
                        print(f"    • Transformations: {len(parsed['transformations'])} (embedded)")
                        for trans in parsed['transformations'][:3]:  # Show first 3
                            print(f"      - {trans.get('namespace', '')}::{trans.get('name', '')}")
                        if len(parsed['transformations']) > 3:
                            print(f"      - ... and {len(parsed['transformations']) - 3} more")
                    if parsed.get('replicas'):
                        print(f"    • Replicas: {len(parsed['replicas'])} (embedded)")
                    if parsed.get('sites'):
                        print(f"    • Sites: {len(parsed['sites'])} (embedded)")
                        for site in parsed['sites']:
                            print(f"      - {site.get('name', 'unknown')}")

            if workflow_files.get('generator_script'):
                gs = workflow_files['generator_script']
                print(f"  {TerminalColor.GREEN.apply('✓')} Generator Script: {gs.get('filename')} ({gs.get('size')} bytes)")
            print(f"{TerminalColor.YELLOW.apply('Problems to solve:')} {len(analysis_result.get('problems_and_solutions', []))}")

            # ENHANCED: Display parent error analysis if available
            if parent_error_analysis and parent_error_analysis.get('parent_error'):
                print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('🔍 ROOT CAUSE ANALYSIS:')}")
                parent = parent_error_analysis['parent_error']
                cascade_count = parent_error_analysis.get('cascade_count', 0)
                confidence = parent_error_analysis.get('confidence', 'unknown')

                print(f"  {TerminalColor.YELLOW.apply('Parent Error:')} {parent.get('problem', 'Unknown')}")
                print(f"  {TerminalColor.YELLOW.apply('Cascade Errors:')} {cascade_count}")
                print(f"  {TerminalColor.YELLOW.apply('Confidence:')} {confidence}")
                print(f"  {TerminalColor.YELLOW.apply('Method:')} {parent_error_analysis.get('analysis_method', 'unknown')}")

                if cascade_count > 0:
                    print(f"  {TerminalColor.CYAN.apply('💡 Strategy:')} Focus on fixing parent error - cascade errors should resolve automatically")

            print(f"{'='*80}\n")

            logger.info(f"Received analysis completion for workflow {workflow_id}")

            # STEP 2: Generate plan with LLM
            print(f"{'='*80}")
            print(f"{TerminalColor.BRIGHT_MAGENTA.apply('🤖 STEP 2: GENERATING REPAIR PLAN WITH LLM')}")
            print(f"{'='*80}")
            print(f"{TerminalColor.CYAN.apply('→')} Building catalog-aware prompt...")
            print(f"{TerminalColor.CYAN.apply('→')} Calling Ollama LLM ({self.planner.ollama_manager.ollama_model})...")

            plan = await self.planner.generate_plan_with_llm(
                analysis_result,
                catalogs,
                workflow_context
            )

            print(f"{TerminalColor.GREEN.apply('✓')} Plan generated successfully")
            print(f"{'='*80}\n")

            # STEP 3: Validation and risk assessment
            print(f"{'='*80}")
            print(f"{TerminalColor.BRIGHT_YELLOW.apply('🔍 STEP 3: VALIDATING PLAN & ASSESSING RISK')}")
            print(f"{'='*80}")

            validation = plan.get("validation_result", {})
            risk = validation.get("risk_assessment", {})

            print(f"{TerminalColor.CYAN.apply('Plan ID:')} {plan.get('plan_id')}")
            print(f"{TerminalColor.CYAN.apply('Risk Level:')} {plan.get('risk_level', 'unknown')}")
            print(f"{TerminalColor.CYAN.apply('Confidence Score:')} {plan.get('confidence_score', {}).get('score', 'N/A')}")
            print(f"{TerminalColor.CYAN.apply('Repair Steps:')} {len(plan.get('repair_steps', []))}")
            print(f"{TerminalColor.CYAN.apply('Requires Approval:')} {plan.get('requires_approval', True)}")
            print(f"{TerminalColor.CYAN.apply('Auto Execute:')} {risk.get('auto_execute', False)}")

            if validation.get("valid"):
                print(f"{TerminalColor.GREEN.apply('✓')} Plan validation: PASSED")
            else:
                print(f"{TerminalColor.RED.apply('✗')} Plan validation: FAILED")
                for issue in validation.get("issues", []):
                    print(f"  {TerminalColor.RED.apply('•')} {issue}")

            print(f"{'='*80}\n")

            # STEP 4: Check auto-execution
            if risk.get("auto_execute", False):
                print(f"{'='*80}")
                print(f"{TerminalColor.BRIGHT_GREEN.apply('🚀 STEP 4: AUTO-EXECUTION APPROVED')}")
                print(f"{'='*80}")
                print(f"{TerminalColor.GREEN.apply('✓')} Low risk plan approved for auto-execution")
                print(f"{TerminalColor.YELLOW.apply('→')} TODO: Send to Executor agent (port 8083)")
                print(f"{'='*80}\n")

                logger.info(f"Plan {plan['plan_id']} approved for auto-execution")
                # TODO: Send to executor
                # await self.send_to_executor(plan)
            else:
                print(f"{'='*80}")
                print(f"{TerminalColor.YELLOW.apply('⚠️  STEP 4: MANUAL APPROVAL REQUIRED')}")
                print(f"{'='*80}")
                print(f"{TerminalColor.YELLOW.apply('⚠')} Plan requires manual approval before execution")
                print(f"{TerminalColor.CYAN.apply('→')} Reason: {plan.get('risk_level', 'medium/high')} risk level")
                print(f"{'='*80}\n")

            print(f"{'='*80}")
            print(f"{TerminalColor.BRIGHT_GREEN.apply('✅ PLANNING WORKFLOW COMPLETED SUCCESSFULLY')}")
            print(f"{'='*80}\n")

            # Write to shared log
            plan_summary = f"Plan ID: {plan.get('plan_id')}\n"
            plan_summary += f"Risk Level: {plan.get('risk_level', 'unknown')}\n"
            plan_summary += f"Repair Steps: {len(plan.get('repair_steps', []))}\n"
            plan_summary += f"Auto Execute: {risk.get('auto_execute', False)}\n"
            plan_summary += f"Requires Approval: {plan.get('requires_approval', True)}\n"
            plan_summary += f"Validation: {'PASSED' if validation.get('valid') else 'FAILED'}"

            self.write_workflow_step(
                workflow_id,
                "PLANNER",
                "7. PLAN GENERATED SUCCESSFULLY",
                plan_summary,
                "SUCCESS"
            )

            # ENHANCED: Export plan to separate JSON file for easy reading
            self.export_plan_to_file(plan, workflow_id)

            return web.json_response({
                "status": "success",
                "plan_id": plan.get("plan_id"),
                "auto_execute": risk.get("auto_execute", False),
                "requires_approval": plan.get("requires_approval", False)
            })

        except Exception as e:
            logger.error(f"Error handling analysis completion: {e}")

            print(f"\n{'='*80}")
            print(f"{TerminalColor.RED.apply('❌ PLANNING WORKFLOW FAILED')}")
            print(f"{TerminalColor.RED.apply('Error:')} {str(e)}")
            print(f"{'='*80}\n")

            # Write error to shared log
            if 'workflow_id' in locals():
                self.write_workflow_step(
                    workflow_id,
                    "PLANNER",
                    "7. PLAN GENERATION FAILED",
                    f"Error: {str(e)}",
                    "ERROR"
                )

            return web.json_response({"error": str(e)}, status=500)

    async def handle_create_plan(self, request):
        """Manual plan creation endpoint"""
        try:
            data = await request.json()

            plan = await self.planner.generate_plan_with_llm(
                data.get("analysis_result", {}),
                data.get("catalogs", {}),
                data.get("workflow_context", {})
            )

            return web.json_response(plan)

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_get_plan(self, request):
        """Get plan by ID"""
        try:
            plan_id = request.match_info['plan_id']
            plan = plans_table.get(Query().plan_id == plan_id)

            if plan:
                return web.json_response(plan)
            else:
                return web.json_response({"error": "Plan not found"}, status=404)

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_approve_plan(self, request):
        """Approve plan for execution"""
        try:
            plan_id = request.match_info['plan_id']
            plan = plans_table.get(Query().plan_id == plan_id)

            if not plan:
                return web.json_response({"error": "Plan not found"}, status=404)

            # Update plan approval status
            plans_table.update({
                "approved": True,
                "approved_at": datetime.now().isoformat()
            }, Query().plan_id == plan_id)

            logger.info(f"Plan {plan_id} approved")

            return web.json_response({
                "status": "approved",
                "plan_id": plan_id
            })

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_list_plans(self, request):
        """List all plans"""
        try:
            plans = plans_table.all()
            return web.json_response({
                "plans": plans,
                "total": len(plans)
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


async def verify_agent_connections(config):
    """Verify connections to other agents (non-blocking)"""
    print(f"\n{TerminalColor.BRIGHT_CYAN.apply('🔗 CHECKING AGENT CONNECTIONS')}")
    print(f"{'='*80}")
    print(f"{TerminalColor.YELLOW.apply('ℹ')} Agents may not be started yet - will retry periodically")

    # Check Analyzer connection
    analyzer_url = config.get("analyzer_url", "http://localhost:8081")
    print(f"\n{TerminalColor.CYAN.apply('→ Analyzer Agent:')} {analyzer_url}")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async with session.get(f"{analyzer_url}/health") as resp:
                if resp.status == 200:
                    print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                else:
                    print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
    except Exception as e:
        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

    # Check Executor connection (future)
    executor_url = config.get("executor_url", "http://localhost:8083")
    print(f"\n{TerminalColor.CYAN.apply('→ Executor Agent:')} {executor_url}")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async with session.get(f"{executor_url}/health") as resp:
                if resp.status == 200:
                    print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                else:
                    print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
    except Exception as e:
        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

    # Check Monitor connection
    monitor_url = config.get("monitor_url", "http://localhost:8080")
    print(f"\n{TerminalColor.CYAN.apply('→ Monitor Agent:')} {monitor_url}")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async with session.get(f"{monitor_url}/health") as resp:
                if resp.status == 200:
                    print(f"  {TerminalColor.GREEN.apply('✓')} Status: Connected")
                else:
                    print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not ready (HTTP {resp.status})")
    except Exception as e:
        print(f"  {TerminalColor.YELLOW.apply('○')} Status: Not started yet")

    print(f"\n{'='*80}")


async def main():
    """Main function"""
    # Initialize planner
    planner = LLMPlanner("planner_config.json")

    # Initialize HTTP server
    http_server = PlannerHTTPServer(planner, planner.config)

    # Start HTTP server
    runner = web.AppRunner(http_server.app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", HTTP_PORT)
    await site.start()

    # Verify connections to other agents
    await verify_agent_connections(planner.config)

    # Print startup info
    print(f"\n{TerminalColor.BRIGHT_GREEN.apply('✓ LLM-Powered Planner Agent Started')}")
    print(f"{'='*80}")
    print(f"{TerminalColor.CYAN.apply('🌐 HTTP API:')} http://localhost:{HTTP_PORT}")
    print(f"{TerminalColor.CYAN.apply('🦙 Ollama Model:')} {planner.ollama_manager.ollama_model}")
    print(f"{TerminalColor.CYAN.apply('🔗 Ollama URL:')} {planner.ollama_manager.ollama_url}")

    if planner.ollama_manager.is_healthy:
        print(f"{TerminalColor.GREEN.apply('✅ Ollama:')} Connected")
    else:
        print(f"{TerminalColor.YELLOW.apply('⚠ Ollama:')} Not available (fallback mode)")

    print(f"\n{TerminalColor.BRIGHT_CYAN.apply('📋 Available Endpoints:')}")
    print(f"   POST /webhooks/analysis-complete - Receive analysis from Analyzer")
    print(f"   POST /api/create-plan - Manually create plan")
    print(f"   GET  /api/plans - List all plans")
    print(f"   GET  /api/plans/{{id}} - Get specific plan")
    print(f"   POST /api/plans/{{id}}/approve - Approve plan for execution")
    print(f"   GET  /health - Health check")
    print(f"\n{TerminalColor.CYAN.apply('Press Ctrl+C to stop')}")
    print(f"{'='*80}\n")

    logger.info(f"Planner agent running on http://localhost:{HTTP_PORT}")

    # Keep running
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{TerminalColor.YELLOW.apply('👋')} Planner Agent shutting down...")
