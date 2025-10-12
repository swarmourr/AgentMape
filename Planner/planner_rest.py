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
import glob
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
    BRIGHT_RED = '\033[91m'
    BRIGHT_WHITE = '\033[97;1m'
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
            "stream": True,  # Enable streaming to avoid timeout on long responses
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 16000  # Increased to allow longer plan generation (128K context - 45K input = plenty of room)
            }
        }

        try:
            logger.info(f"Calling Ollama with prompt length: {len(full_prompt)} chars")

            # Use streaming to avoid timeout on long responses
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.connection_timeout,
                stream=True
            )

            if response.status_code == 200:
                # Collect streaming chunks
                full_response = ""
                done = False
                last_print_len = 0

                print(f"  {TerminalColor.CYAN.apply('⏳ Streaming LLM response...')}", end='', flush=True)

                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            full_response += chunk.get("response", "")
                            done = chunk.get("done", False)

                            # Show progress every 2000 chars with animated dots
                            if len(full_response) - last_print_len >= 2000:
                                print(f"\r  {TerminalColor.CYAN.apply('⏳ Streaming LLM response...')} {len(full_response):,} chars", end='', flush=True)
                                last_print_len = len(full_response)

                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse streaming chunk: {e}")
                            continue

                # Clear progress line and show completion
                print(f"\r  {TerminalColor.GREEN.apply('✓ LLM response received:')} {len(full_response):,} chars                    ")
                logger.info(f"Ollama response length: {len(full_response)} chars")

                # Return in same format as non-streaming
                return {
                    "response": full_response,
                    "done": done
                }
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                logger.error(f"Response body: {response.text[:500]}")
                return None

        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
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

⚠️ CRITICAL: READ THE ACTUAL ERROR - DON'T ASSUME!

ERROR TYPE MATCHING (match solution to ACTUAL error):
1. If analysis mentions "SyntaxError" or "Python error" → Fix Python script, NOT catalog
2. If analysis mentions "memory exceeded" or "out of memory" → Fix memory in catalog
3. If analysis mentions "missing file" or "file not found" → Fix replica catalog
4. If analysis mentions "permission denied" → Fix permissions, NOT catalog
5. If analysis mentions "syntax error in script" → Fix the script code (use sed/awk)
6. If error doesn't match known patterns → Use diagnostic commands

🚨 STOP DEFAULTING TO MEMORY FIXES! 🚨
- NOT every workflow error is a memory issue!
- Read the analysis.problems_and_solutions carefully
- Look at the actual error message in the problem field
- Match your solution to the ACTUAL error type
- If it's a SyntaxError → Fix syntax, NOT memory
- If it's a missing file → Fix path, NOT memory
- If it's a permission issue → Fix permissions, NOT memory

IMPORTANT RULES:
- ALWAYS include NEW submission step after modifying workflow YAML
- Generate ONLY ONE plan with the best solution
- Focus on the ROOT CAUSE from parent_error_analysis if available
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

        # Get actual workflow YAML path from metadata (stored by Monitor)
        # This is the REAL path, not a hardcoded fallback
        dax_path = workflow_files.get('workflow_yaml_path') or braindump_metadata.get('dax', 'workflow.yml')

        # If dax_path is still a placeholder or doesn't exist, try to find it
        if dax_path == 'workflow.yml' and submit_dir:
            # Try to find actual workflow YAML in submit directory
            possible_yamls = glob.glob(os.path.join(submit_dir, '*.yml'))
            if possible_yamls:
                # Use the first YAML file found (usually the workflow descriptor)
                dax_path = possible_yamls[0]
                logger.info(f"Using discovered workflow YAML: {dax_path}")

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

        # ENHANCED: Add requested files content if available
        requested_files_content = workflow_context.get('requested_files_content', {})
        if requested_files_content:
            files_section = "\n\n=== FILES RETRIEVED FOR YOUR ANALYSIS ===\n"
            files_section += "✅ The Analyzer identified these files as necessary to create a specific fix.\n"
            files_section += "✅ They have been automatically fetched and are provided below.\n"
            files_section += "✅ You now have ACTUAL file content - do NOT guess or use generic placeholders!\n\n"

            for file_path, content in requested_files_content.items():
                files_section += f"\n--- FILE: {file_path} ---\n"
                if content.startswith("ERROR:"):
                    files_section += f"{content}\n"
                    files_section += "⚠️ This file could not be retrieved. You may need to mark this as requires_manual_intervention: true\n"
                else:
                    # Limit content to 10000 chars for very large files
                    if len(content) > 10000:
                        files_section += f"{content[:10000]}\n... (truncated - file too large)\n"
                    else:
                        files_section += f"{content}\n"
                files_section += f"--- END FILE: {file_path} ---\n"

            files_section += "\n🎯 ACTION REQUIRED:\n"
            files_section += "Now that you have the ACTUAL file content above, create a SPECIFIC fix:\n"
            files_section += "\n"
            files_section += "⚠️ IMPORTANT STRATEGY FOR TRANSFORMATION SCRIPT ERRORS:\n"
            files_section += "DO NOT modify the generator script file directly! Instead:\n"
            files_section += "\n"
            files_section += "1. Identify the exact syntax/code error in the script content above\n"
            files_section += "2. Create the CORRECTED version of the script\n"
            files_section += "3. EMBED the corrected script in the workflow YAML using yq\n"
            files_section += "4. Re-submit the workflow with the embedded fix\n"
            files_section += "\n"
            files_section += "Example workflow fix for SyntaxError in transformation script:\n"
            files_section += "```\n"
            files_section += "# Step 1: Create corrected script content (fix the syntax error you identified)\n"
            files_section += "cat > /tmp/fixed_script.py <<'EOF'\n"
            files_section += "#!/usr/bin/env python3\n"
            files_section += "import sys\n"
            files_section += "def finetune(model):  # <-- FIXED: Added missing colon\n"
            files_section += "    return model\n"
            files_section += "if __name__ == '__main__':\n"
            files_section += "    finetune(sys.argv[1])\n"
            files_section += "EOF\n"
            files_section += "\n"
            files_section += "# Step 2: Embed the fixed script in workflow YAML transformation\n"
            files_section += "yq eval '.pegasus.transformations[] | select(.name == \"FineTuneLLM\") | .type = \"STAGEABLE\"' -i workflow.yml\n"
            files_section += "yq eval '.pegasus.transformations[] | select(.name == \"FineTuneLLM\") | .pfn = \"/tmp/fixed_script.py\"' -i workflow.yml\n"
            files_section += "\n"
            files_section += "# OR embed script content directly as inline transformation (preferred):\n"
            files_section += "# Use yq to set .metadata.script_content with the corrected script\n"
            files_section += "\n"
            files_section += "# Step 3: Re-submit workflow\n"
            files_section += "pegasus-plan --dir /path/to/workflow.yml --submit\n"
            files_section += "```\n"
            files_section += "\n"
            files_section += "For other error types:\n"
            files_section += "- Config errors: Create precise yq/sed commands to update the specific values\n"
            files_section += "- Memory errors: Use yq to update resource limits in workflow YAML\n"
            files_section += "- DO NOT create generic fixes like 'sed -i s/error// file.py'\n"
            prompt += files_section

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

🚨🚨🚨 STEP 1: DO YOU HAVE THE FILES NEEDED TO FIX THIS? 🚨🚨🚨

BEFORE creating any repair plan, you MUST verify you have the actual file content!

🔍 CRITICAL QUESTION: Can you create a SPECIFIC fix with the information you have?
1. Do I have enough information to create a specific fix?
2. For SyntaxError/script issues: Do I have the actual script content?
3. For configuration issues: Do I have the relevant config file?
4. For path issues: Do I have the workflow descriptor details?

📋 DECISION TREE - FOLLOW THIS EXACTLY:

IF the error is "SyntaxError in FineTuneLLM script":
  ├─ Check: Is "FineTuneLLM" script content in workflow_files.transformation_scripts?
  ├─ ✅ YES → You can see the code → Create specific sed/awk fix
  └─ ❌ NO → You CANNOT see the code → REQUEST IT!

IF the error is "Config file has wrong path":
  ├─ Check: Is the config file content available?
  ├─ ✅ YES → You can see the path value → Create yq/sed command to fix it
  └─ ❌ NO → REQUEST the config file!

IF the error is "Memory exceeded":
  ├─ Check: workflow_files.workflow_yaml has memory catalog?
  ├─ ✅ YES → You have it → Create yq command to increase memory
  └─ ❌ NO → Usually workflow_yaml is always provided, proceed

🚨 WHEN IN DOUBT → REQUEST THE FILE! 🚨

HOW TO REQUEST FILES (use this EXACT JSON format):

{{
  "needs_more_information": true,
  "requested_files": [
    {{
      "file_path": "/absolute/path/to/file",
      "reason": "Why you need this file - be specific about what you'll look for"
    }}
  ],
  "analysis_summary": "What you know so far and what's missing"
}}

EXAMPLE 1 - Request script to fix SyntaxError:
{{
  "needs_more_information": true,
  "requested_files": [
    {{
      "file_path": "/srv/pegasus-5.0.8/share/pegasus/common/bin/FineTuneLLM",
      "reason": "Need to see the actual Python script content to identify the specific syntax error (missing comma, parenthesis, indentation, etc.) and create a targeted sed/awk fix command"
    }}
  ],
  "analysis_summary": "Root cause is SyntaxError in FineTuneLLM transformation script. The error log shows syntax error but I don't have the script content in transformation_scripts section. Without seeing the actual code, I cannot create a specific fix - I would just be guessing with generic sed commands."
}}

EXAMPLE 2 - Request config file:
{{
  "needs_more_information": true,
  "requested_files": [
    {{
      "file_path": "/home/user/.pegasus/pegasus.conf",
      "reason": "Need to see the current configuration values to understand which parameter is causing the path resolution error"
    }}
  ],
  "analysis_summary": "Error indicates configuration issue with path resolution. Need to inspect the actual config file to identify the incorrect parameter value."
}}

IF YOU HAVE ENOUGH INFORMATION TO FIX:
Generate a complete repair plan with this JSON structure:

{{
  "needs_more_information": false,
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

Example 5 - SYNTAX ERROR IN TRANSFORMATION SCRIPT (WORKFLOW YAML FIX - PREFERRED!):
  Problem: SyntaxError in FineTuneLLM script: "def finetune(model)" missing colon

  ⚠️ IMPORTANT: DO NOT modify the generator script file directly!
  ✅ INSTEAD: Embed the corrected script in the workflow YAML

  Strategy:
  1. Analyzer provides the original script content from pfn path
  2. Planner identifies the syntax error
  3. Planner creates corrected script
  4. Planner embeds corrected script in workflow YAML
  5. Re-submit workflow with the fix

  Step 1: Create corrected script with syntax error fixed
    cat > /tmp/FineTuneLLM_fixed.py <<'SCRIPT_END'
    #!/usr/bin/env python3
    import sys
    def finetune(model):  # <-- FIXED: Added missing colon
        return model

    if __name__ == '__main__':
        result = finetune(sys.argv[1])
        print(result)
    SCRIPT_END

  Step 2: Update workflow YAML to use the corrected script
    # Option A: Point transformation to the fixed script
    yq eval '.pegasus.transformations[] | select(.name == "FineTuneLLM") | .pfn = "/tmp/FineTuneLLM_fixed.py"' -i {dax_path}

    # Option B: Change to STAGEABLE type so Pegasus stages the fixed script
    yq eval '.pegasus.transformations[] | select(.name == "FineTuneLLM") | .type = "STAGEABLE"' -i {dax_path}

  Step 3: Validate the corrected script syntax
    python3 -m py_compile /tmp/FineTuneLLM_fixed.py

  Step 4: Submit NEW workflow with the embedded fix
    pegasus-plan --dir {dax_path} --output-sites local --submit

  Step 5: Monitor new workflow
    # New run will be created with fixed script
    # Original generator script remains unchanged

  ✅ Benefits:
    - Quick fix without modifying generator code
    - Workflow-specific correction
    - Original scripts remain safe
    - Easy to revert if needed

  📝 Note for permanent fix:
    After validating the workflow fix works, consider updating the generator script
    for future workflows. Add this to generator_modifications_suggested field.

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

🎯 REPAIR STRATEGY DECISION - CHOOSE THE BEST ONE:

You must generate ONE SINGLE plan with the BEST solution, not multiple options!

Choose the most appropriate strategy:
1. WORKFLOW YAML FIX (PREFERRED): Modify workflow.yml for immediate resolution
   - ✅ Use this for: Script errors, memory issues, catalog updates
   - ✅ Benefits: Fast, safe, workflow-specific, no code changes
   - ✅ For script errors: Create corrected script + embed in YAML

2. WORKFLOW REGENERATION: Only if workflow.yml structure needs major changes
   - Use this for: Multiple catalog updates, architecture changes
   - Requires: Generator script available

3. PERMANENT FIX: Suggest in "generator_modifications_suggested" field
   - DO NOT modify generator scripts in repair_steps!
   - ONLY suggest what changes are needed for future workflows

⚠️ CRITICAL RULES:
- Generate ONLY ONE plan with the BEST approach for this specific error
- Do NOT create multiple alternative plans
- Do NOT include "Option 1", "Option 2" in your plan
- Pick the MOST EFFECTIVE solution and create repair_steps for ONLY that solution

🚨 FOR TRANSFORMATION SCRIPT ERRORS:
- DO NOT modify /srv/pegasus.../bin/ScriptName files directly!
- INSTEAD: Create corrected script → embed in workflow YAML → re-submit
- See Example 5 above for the exact pattern to follow
- Original generator scripts must remain unchanged in repair_steps
- You can suggest generator updates in "generator_modifications_suggested"

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
   - SyntaxError in transformation script? → Do you have the script content?
   - Memory error? → Fix memory in catalog
   - Missing file? → Fix replica catalog
   - Other? → Diagnostic commands

2. ⚠️ CRITICAL: Do you have the information needed to create a SPECIFIC fix?

   For SyntaxError/Script errors:
   - ✅ Script content in transformation_scripts? → Analyze and create sed/awk fix!
   - ❌ NO script content? → REQUEST IT using needs_more_information: true
   - DO NOT create generic "sed -i 's/error//' script.py" commands without seeing the code!

   For Configuration errors:
   - ✅ Config file content available? → Generate specific yq/sed commands
   - ❌ NO config content? → REQUEST IT using needs_more_information: true

   For Memory/Resource errors:
   - ✅ Catalog shows memory/disk values? → Modify catalog with specific values
   - (Usually available in workflow_files.workflow_yaml)

3. 🚨 NEVER GUESS AT FIXES! 🚨
   - If you DON'T have the actual file content → REQUEST IT!
   - Use the needs_more_information: true JSON format shown earlier
   - Example: SyntaxError in "FineTuneLLM" script but NO script content in transformation_scripts?
     → Request: {"file_path": "/path/to/FineTuneLLM", "reason": "Need script content to fix syntax error"}

4. Only proceed with repair_steps if:
   - ✅ You have the ACTUAL file content to modify
   - ✅ You can create SPECIFIC commands (not generic placeholders)
   - ✅ You are confident the fix addresses the root cause

🎯 GENERATE ONE SINGLE PLAN - NO ALTERNATIVES:
- Output ONLY ONE JSON plan object
- Do NOT generate multiple plans or options
- Do NOT use "Option 1", "Alternative A", "Approach 1" language
- Pick the BEST solution and create steps for ONLY that solution
- If you want to mention alternatives, use the "generator_modifications_suggested" field for permanent fixes

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
        confidence_obj = plan.get("confidence_score") or {}
        confidence = confidence_obj.get("score", 0)
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

        # Track files that failed to fetch (prevent looping)
        self.failed_files_cache = set()

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
        workflow_context: Dict[str, Any],
        additional_files: Dict[str, str] = None,
        use_multi_stage: bool = True
    ) -> Dict[str, Any]:
        """Generate repair plan using LLM with optional multi-stage approach"""

        workflow_id = workflow_context.get('workflow_id')
        logger.info(f"Generating plan for workflow {workflow_id}")

        # Check if multi-stage approach should be used
        if use_multi_stage and not additional_files:
            logger.info("Using multi-stage LLM approach to reduce prompt size")
            return await self.generate_plan_multi_stage(analysis_result, catalogs, workflow_context)

        # Check if Analyzer identified files needed for fix
        if not additional_files:  # Only on first call, not after file request
            auto_requested_files = {}
            problems = analysis_result.get('problems_and_solutions', [])

            # Collect all files needed across all problems
            all_files_needed = []
            for problem in problems:
                files_needed = problem.get('files_needed_for_fix', [])
                if files_needed:
                    all_files_needed.extend(files_needed)

            if all_files_needed:
                print(f"\n{'='*80}")
                print(f"{TerminalColor.BRIGHT_CYAN.apply('📋 AUTO-FETCHING REQUIRED FILES')}")
                print(f"{'='*80}")
                print(f"{TerminalColor.YELLOW.apply('Analyzer identified files needed to create a specific fix')}")
                print(f"Total files to fetch: {len(all_files_needed)}\n")

                for idx, file_info in enumerate(all_files_needed, 1):
                    file_path = file_info.get('path')
                    reason = file_info.get('reason', 'Required for fix')

                    print(f"{TerminalColor.BRIGHT_WHITE.apply(f'[{idx}/{len(all_files_needed)}]')} {TerminalColor.CYAN.apply('Fetching:')} {file_path}")
                    print(f"     {TerminalColor.YELLOW.apply('Reason:')} {reason}")

                    # Auto-fetch the file
                    file_data = await self.request_file_from_monitor(file_path, workflow_id)

                    if file_data.get('success'):
                        auto_requested_files[file_path] = file_data.get('content')
                        size_kb = file_data.get('size_bytes', 0) / 1024
                        print(f"     {TerminalColor.GREEN.apply('✓ Success:')} Retrieved {size_kb:.1f} KB\n")
                    else:
                        error_msg = file_data.get('error', 'Unknown error')
                        print(f"     {TerminalColor.RED.apply('✗ Failed:')} {error_msg}\n")

            # If we fetched files, add them to additional_files
            if auto_requested_files:
                additional_files = auto_requested_files
                print(f"{'='*80}")
                print(f"{TerminalColor.BRIGHT_GREEN.apply(f'✓ Successfully fetched {len(auto_requested_files)}/{len(all_files_needed)} file(s)')}")
                print(f"{TerminalColor.GREEN.apply('Planner now has the actual file content to create specific fixes')}")
                print(f"{'='*80}\n")

        # Add additional files to workflow context if provided
        if additional_files:
            if 'requested_files_content' not in workflow_context:
                workflow_context['requested_files_content'] = {}
            workflow_context['requested_files_content'].update(additional_files)

        # Build prompt
        prompt = self.prompt_builder.build_planner_prompt(analysis_result, catalogs, workflow_context)

        # Call LLM
        llm_response = self.ollama_manager.call_llm(prompt, self.prompt_builder.SYSTEM_PROMPT)

        if llm_response:
            try:
                # Parse LLM output
                plan = self.parse_llm_response(llm_response)

                # Check if LLM is requesting more files
                if plan.get('needs_more_information'):
                    logger.info(f"LLM requesting additional files for {workflow_id}")
                    return await self.handle_file_request(plan, analysis_result, catalogs, workflow_context)

                # Validate plan
                validation_result = self.validator.validate_plan(plan, workflow_context)

                # Add metadata
                plan["plan_id"] = str(uuid.uuid4())
                plan["workflow_id"] = workflow_id
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

    async def generate_plan_multi_stage(
        self,
        analysis_result: Dict[str, Any],
        catalogs: Dict[str, Any],
        workflow_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Multi-stage LLM approach to handle large prompts
        Stage 1: Identify what files are needed
        Stage 2: Fetch those files
        Stage 3: Generate repair plan with file content
        """
        workflow_id = workflow_context.get('workflow_id')

        print(f"\n╔{'═'*78}╗")
        print(f"║ {TerminalColor.BRIGHT_CYAN.apply('🔄 MULTI-STAGE LLM PLANNING'):76} ║")
        print(f"╠{'═'*78}╣")
        print(f"║ {TerminalColor.YELLOW.apply('Breaking down planning into smaller, focused requests'):76} ║")
        print(f"╚{'═'*78}╝\n")

        # ===== STAGE 1: Identify Required Files =====
        print(f"┌─ {TerminalColor.BRIGHT_MAGENTA.apply('STAGE 1/3:')} {TerminalColor.BRIGHT_WHITE.apply('Identifying Required Files')} {'─'*34}")
        print(f"│  Analyzing error to determine which files are needed for the fix...")
        print(f"│")

        try:
            stage1_prompt = self._build_file_identification_prompt(analysis_result, workflow_context)
            logger.info(f"Stage 1 prompt size: {len(stage1_prompt)} chars")
        except Exception as e:
            logger.error(f"Failed to build Stage 1 prompt: {e}", exc_info=True)
            print(f"{TerminalColor.RED.apply('✗ Error:')} Failed to build prompt: {str(e)}")
            print(f"{TerminalColor.YELLOW.apply('→')} Falling back to single-stage approach\n")
            return await self.generate_plan_with_llm(analysis_result, catalogs, workflow_context, use_multi_stage=False)

        try:
            stage1_response = self.ollama_manager.call_llm(stage1_prompt, "You are a Pegasus workflow debugging assistant. Identify which files are needed to fix errors.")
        except Exception as e:
            logger.error(f"Stage 1 LLM call failed: {e}")
            print(f"{TerminalColor.RED.apply('✗ Error:')} LLM call failed: {str(e)}")
            print(f"{TerminalColor.YELLOW.apply('→')} Falling back to single-stage approach\n")
            return await self.generate_plan_with_llm(analysis_result, catalogs, workflow_context, use_multi_stage=False)

        if not stage1_response:
            logger.warning("Stage 1 LLM returned None (Ollama not available)")
            print(f"{TerminalColor.YELLOW.apply('⚠ Warning:')} Ollama LLM not available")
            print(f"{TerminalColor.YELLOW.apply('→')} Falling back to single-stage approach\n")
            return await self.generate_plan_with_llm(analysis_result, catalogs, workflow_context, use_multi_stage=False)

        try:
            files_needed = self._parse_file_identification_response(stage1_response)

            if files_needed:
                print(f"│  {TerminalColor.GREEN.apply('✓ Success:')} Identified {len(files_needed)} file(s) needed for fix")
                for f in files_needed:
                    path = f.get('path', '')
                    reason = f.get('reason', 'No reason provided')
                    # Truncate long paths
                    if len(path) > 50:
                        path = '...' + path[-47:]
                    print(f"│    {TerminalColor.CYAN.apply('•')} {path}")
                    print(f"│      {TerminalColor.YELLOW.apply('→')} {reason}")
            else:
                print(f"│  {TerminalColor.YELLOW.apply('⚠ Info:')} No additional files needed")
            print(f"└{'─'*78}\n")

        except Exception as e:
            logger.error(f"Stage 1 parsing failed: {e}")
            return await self.generate_plan_with_llm(analysis_result, catalogs, workflow_context, use_multi_stage=False)

        # ===== STAGE 2: Fetch Required Files =====
        fetched_files = {}
        if files_needed:
            print(f"┌─ {TerminalColor.BRIGHT_MAGENTA.apply('STAGE 2/3:')} {TerminalColor.BRIGHT_WHITE.apply('Fetching Required Files')} {'─'*37}")

            for idx, file_info in enumerate(files_needed, 1):
                file_path = file_info.get('path')
                file_type = file_info.get('type', 'file')
                reason = file_info.get('reason', 'Required for fix')

                # Skip placeholder paths
                if not file_path or '/absolute/path' in file_path or file_path == 'path':
                    print(f"│  {TerminalColor.YELLOW.apply('⚠ Warning:')} LLM returned placeholder path: {file_path}")
                    print(f"│  {TerminalColor.YELLOW.apply('  Skipping')} - cannot fetch placeholder paths")
                    continue

                try:
                    # Truncate path for display
                    display_path = file_path
                    if len(display_path) > 55:
                        display_path = '...' + display_path[-52:]

                    if file_type == 'directory_listing':
                        print(f"│  {TerminalColor.BRIGHT_WHITE.apply(f'[{idx}/{len(files_needed)}]')} {TerminalColor.CYAN.apply('Listing Dir:')} {display_path}")
                        file_data = await self.request_directory_listing_from_monitor(file_path, workflow_id)
                    else:
                        print(f"│  {TerminalColor.BRIGHT_WHITE.apply(f'[{idx}/{len(files_needed)}]')} {TerminalColor.CYAN.apply('Fetching:')} {display_path}")
                        file_data = await self.request_file_from_monitor(file_path, workflow_id)
                except Exception as e:
                    logger.error(f"Error during fetch: {e}")
                    print(f"│      {TerminalColor.RED.apply('✗ Error:')} {str(e)[:60]}")
                    continue

                if file_data.get('success'):
                    if file_type == 'directory_listing':
                        # Format directory listing nicely
                        files_list = file_data.get('files', [])
                        content = f"Directory listing of {file_path}:\n"
                        content += f"Found {len(files_list)} file(s):\n"
                        for f in files_list:
                            content += f"  - {f}\n"
                        fetched_files[file_path] = content
                        print(f"│      {TerminalColor.GREEN.apply('✓ Success:')} Found {len(files_list)} file(s)")
                    else:
                        fetched_files[file_path] = file_data.get('content')
                        size_kb = file_data.get('size_bytes', 0) / 1024
                        print(f"│      {TerminalColor.GREEN.apply('✓ Success:')} Retrieved {size_kb:.1f} KB")
                else:
                    error_msg = file_data.get('error', 'Unknown error')
                    print(f"│      {TerminalColor.RED.apply('✗ Failed:')} {error_msg[:50]}")

            print(f"│")
            print(f"│  {TerminalColor.BRIGHT_GREEN.apply(f'✓ Fetched {len(fetched_files)}/{len(files_needed)} file(s) successfully')}")
            print(f"└{'─'*78}\n")

        # ===== STAGE 3: Generate Repair Plan =====
        print(f"┌─ {TerminalColor.BRIGHT_MAGENTA.apply('STAGE 3/3:')} {TerminalColor.BRIGHT_WHITE.apply('Generating Repair Plan')} {'─'*39}")
        print(f"│  Creating specific repair steps with the fetched file content...")
        print(f"│  {TerminalColor.YELLOW.apply('⏳ This may take 2-5 minutes for large prompts...')}")
        print(f"└{'─'*78}\n")

        # Now call single-stage with fetched files and multi_stage=False to avoid recursion
        return await self.generate_plan_with_llm(
            analysis_result,
            catalogs,
            workflow_context,
            additional_files=fetched_files,
            use_multi_stage=False
        )

    def _extract_transformations_from_yaml(self, workflow_yaml: Dict[str, Any]) -> List[Dict]:
        """
        Extract transformations directly from raw workflow YAML
        Handles both transformationCatalog.transformations and pegasus.transformations
        """
        transformations = []

        if not workflow_yaml:
            return transformations

        # Get raw content or parsed structure
        raw_content = workflow_yaml.get('raw_content')
        if raw_content and isinstance(raw_content, dict):
            workflow_data = raw_content
        else:
            # Fallback to parsed_structure if raw_content not available
            parsed_structure = workflow_yaml.get('parsed_structure') or {}
            return parsed_structure.get('transformations', [])

        # Check transformationCatalog.transformations first
        tc_section = workflow_data.get('transformationCatalog', {})
        transformations_list = tc_section.get('transformations', [])

        # Fallback to pegasus.transformations if needed
        if not transformations_list:
            pegasus_section = workflow_data.get('pegasus', {})
            transformations_list = pegasus_section.get('transformations', [])

        # Extract transformations with pfn
        for trans in transformations_list:
            sites = trans.get('sites', [])

            if sites:
                # Use first site's pfn (nested structure)
                first_site = sites[0]
                pfn = first_site.get('pfn', '')
                site = first_site.get('name', '')
            else:
                # Direct pfn (older format)
                pfn = trans.get('pfn', '')
                site = trans.get('site', '')

            transformations.append({
                "namespace": trans.get('namespace', ''),
                "name": trans.get('name', ''),
                "version": trans.get('version', ''),
                "site": site,
                "pfn": pfn,
                "type": trans.get('type', 'STAGEABLE')
            })

        return transformations

    def _format_transformations(self, transformations: List[Dict]) -> str:
        """Format transformations list for LLM prompt"""
        if not transformations:
            return "  (No transformations defined in workflow)"

        formatted = []
        for trans in transformations:
            name = trans.get('name', 'unknown')
            pfn = trans.get('pfn', 'N/A')
            namespace = trans.get('namespace', '')
            full_name = f"{namespace}::{name}" if namespace else name
            formatted.append(f"  - {full_name}")
            formatted.append(f"    pfn: {pfn}")

        return '\n'.join(formatted) if formatted else "  (No transformations)"

    def _build_file_identification_prompt(self, analysis_result: Dict[str, Any], workflow_context: Dict[str, Any]) -> str:
        """Build compact prompt for Stage 1: File identification"""

        # Defensive checks for None values
        if not analysis_result:
            analysis_result = {}
        if not workflow_context:
            workflow_context = {}

        problems = analysis_result.get('problems_and_solutions', [])
        parent_error_analysis = workflow_context.get('parent_error_analysis') or {}
        parent_error = parent_error_analysis.get('parent_error', {})

        # Use parent error if available, otherwise first problem
        main_error = parent_error if parent_error else (problems[0] if problems else {})

        workflow_files = workflow_context.get('workflow_files') or {}
        workflow_yaml = workflow_files.get('workflow_yaml') or {}
        parsed_structure = workflow_yaml.get('parsed_structure') or {}

        # Extract transformations directly from raw YAML
        transformations = self._extract_transformations_from_yaml(workflow_yaml)

        # Debug: Log extracted transformations
        logger.info(f"Extracted {len(transformations)} transformations from YAML")
        for trans in transformations:
            logger.info(f"  - {trans.get('name')}: pfn={trans.get('pfn')}")

        prompt = f"""
You are analyzing a Pegasus workflow error to identify which files are needed to create a fix.

ERROR TO FIX:
Problem: {main_error.get('problem', 'Unknown')}
Explanation: {main_error.get('explanation', 'Unknown')}
Error Level: {main_error.get('error_level', 'unknown')}

WORKFLOW STRUCTURE:
Jobs: {len(parsed_structure.get('jobs', []))}
Transformations Available:
{self._format_transformations(transformations)}

YOUR TASK:
Analyze this error and determine which files/directories are needed to create a specific fix.

OUTPUT JSON FORMAT:
{{
  "files_needed": [
    {{
      "path": "/absolute/path/to/file_or_directory",
      "type": "file" or "directory_listing",
      "reason": "Why this is needed"
    }}
  ],
  "analysis": "Brief explanation of what needs to be fixed"
}}

RULES:
1. For MISSING REPLICA/DATA FILE errors (File not found, data.json not found, etc.):
   - DO NOT request the workflow YAML file
   - INSTEAD: Request a directory listing of the parent directory
   - Extract parent directory from the missing file path
   - Example: If error says "/home/user/data/data1.json not found"
     → Request: {{"path": "/home/user/data", "type": "directory_listing", "reason": "Check for typos or similar files to data1.json"}}
   - The directory listing will help identify if the file has a typo or different name

2. For SyntaxError/script errors:
   - Extract the transformation/script name from the error message (e.g., "FineTuneLLM")
   - Look in the Transformations list above for that name
   - Find the 'pfn' (Physical File Name) field - this is the REAL file path
   - Use that exact 'pfn' value in your response
   - DO NOT use placeholder paths like "/absolute/path/to/..."
   - EXAMPLE: If Transformations shows {{"name": "FineTuneLLM", "pfn": "/srv/pegasus/bin/FineTuneLLM"}}, use "/srv/pegasus/bin/FineTuneLLM"

3. For memory/resource errors: Usually no additional files needed (workflow YAML is already available)

4. For config errors: Request the specific config file mentioned in the error

5. If no additional files needed, return empty files_needed array

⚠️ CRITICAL:
- For missing data files → Request DIRECTORY LISTING of parent directory
- For script errors → Use ACTUAL paths from Transformations list
- DO NOT request workflow.yml for missing replica errors!

IMPORTANT: Keep your response concise. Only include the JSON object, no extra text.
"""
        return prompt

    def _parse_file_identification_response(self, llm_response: Dict[str, Any]) -> List[Dict[str, str]]:
        """Parse Stage 1 response to extract file list"""
        if not llm_response:
            logger.error("LLM response is None")
            return []

        response_text = llm_response.get("response", "")

        # Clean up markdown
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.rfind("```")
            if end > start:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.rfind("```")
            if end > start:
                response_text = response_text[start:end].strip()

        try:
            result = json.loads(response_text)
            return result.get('files_needed', [])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Stage 1 response: {e}")
            logger.error(f"Response: {response_text[:500]}")
            return []

    async def handle_file_request(
        self,
        file_request: Dict[str, Any],
        analysis_result: Dict[str, Any],
        catalogs: Dict[str, Any],
        workflow_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle LLM's request for additional files"""

        workflow_id = workflow_context.get('workflow_id')
        requested_files = file_request.get('requested_files', [])

        print(f"\n{'='*80}")
        print(f"{TerminalColor.BRIGHT_YELLOW.apply('🔍 PLANNER LLM REQUESTING ADDITIONAL FILES')}")
        print(f"{'='*80}")
        print(f"{TerminalColor.CYAN.apply('Analysis Summary:')}")
        print(f"  {file_request.get('analysis_summary', 'No summary provided')}")
        print(f"\n{TerminalColor.CYAN.apply('Files Requested:')} {len(requested_files)}")

        # Fetch files from Monitor
        fetched_files = {}

        for idx, file_req in enumerate(requested_files, 1):
            file_path = file_req.get('file_path')
            reason = file_req.get('reason', 'Not specified')

            print(f"\n{TerminalColor.BRIGHT_WHITE.apply(f'[{idx}/{len(requested_files)}]')} {TerminalColor.CYAN.apply('Fetching:')} {file_path}")
            print(f"     {TerminalColor.YELLOW.apply('Reason:')} {reason}")

            # Request file from Monitor via PlannerHTTPServer's method
            file_data = await self.request_file_from_monitor(file_path, workflow_id)

            if file_data.get('success'):
                content = file_data.get('content')
                size_kb = file_data.get('size_bytes', 0) / 1024
                fetched_files[file_path] = content
                print(f"     {TerminalColor.GREEN.apply('✓ Success:')} Retrieved {size_kb:.1f} KB")
            else:
                error = file_data.get('error', 'Unknown error')
                print(f"     {TerminalColor.RED.apply('✗ Failed:')} {error}")
                fetched_files[file_path] = f"ERROR: Could not fetch file - {error}"

        # Regenerate plan with the fetched files
        if fetched_files:
            print(f"\n{'='*80}")
            print(f"{TerminalColor.BRIGHT_GREEN.apply(f'✓ Successfully fetched {len(fetched_files)}/{len(requested_files)} file(s)')}")
            print(f"{'='*80}")
            print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('🤖 REGENERATING PLAN WITH FILE CONTENT...')}\n")
            return await self.generate_plan_with_llm(
                analysis_result,
                catalogs,
                workflow_context,
                additional_files=fetched_files
            )
        else:
            print(f"\n{TerminalColor.RED.apply('✗ No files could be fetched')}")
            logger.warning("No files could be fetched, generating fallback plan")
            return self.generate_fallback_plan(analysis_result, workflow_context)

    async def request_directory_listing_from_monitor(self, directory_path: str, workflow_id: str = None) -> Dict[str, Any]:
        """Request directory listing from Monitor to check for similar files"""

        # Check if this directory has already failed - don't retry
        if directory_path in self.failed_files_cache:
            logger.warning(f"Skipping directory that previously failed: {directory_path}")
            return {
                "success": False,
                "path": directory_path,
                "error": f"Directory previously failed to list (cached failure)",
                "method": "cached_failure"
            }

        try:
            monitor_url = self.config.get("monitor_url", "http://localhost:8080")

            request_data = {
                "directory_path": directory_path,
                "requester": "planner",
                "workflow_id": workflow_id
            }

            logger.info(f"Requesting directory listing from Monitor: {directory_path}")

            async with ClientSession() as session:
                async with session.post(
                    f"{monitor_url}/api/files/list-directory",
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"Received directory listing from Monitor: {directory_path} ({len(result.get('files', []))} files)")
                        return result
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to get directory listing from Monitor: {resp.status} - {error_text}")
                        # Add to failed cache to prevent retrying
                        self.failed_files_cache.add(directory_path)
                        logger.info(f"Added {directory_path} to failed files cache (won't retry)")
                        return {"success": False, "error": error_text, "status": resp.status}

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting directory listing from Monitor: {directory_path}")
            self.failed_files_cache.add(directory_path)
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error requesting directory listing from Monitor: {e}")
            self.failed_files_cache.add(directory_path)
            return {"success": False, "error": str(e)}

    async def request_file_from_monitor(self, file_path: str, workflow_id: str = None) -> Dict[str, Any]:
        """Request file content from Monitor (which has access to cluster filesystem)"""

        # Check if this file has already failed - don't retry to prevent loops
        if file_path in self.failed_files_cache:
            logger.warning(f"Skipping file that previously failed: {file_path}")
            return {
                "success": False,
                "file_path": file_path,
                "error": f"File previously failed to fetch (cached failure)",
                "method": "cached_failure"
            }

        # Check if this looks like a cluster/remote path
        remote_prefixes = ['/srv/', '/home/', '/opt/', '/usr/local/', '/data/', '/scratch/']
        is_remote_path = any(file_path.startswith(prefix) for prefix in remote_prefixes)

        # STRATEGY 1: Try direct read ONLY for local paths (workflow YAML, config files in same dir)
        if not is_remote_path and os.path.exists(file_path):
            try:
                logger.info(f"Reading file directly (local): {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_size = os.path.getsize(file_path)

                # Limit file size to 10MB
                if file_size > 10 * 1024 * 1024:
                    logger.warning(f"File too large: {file_size} bytes, truncating to 10MB")
                    content = content[:10 * 1024 * 1024]

                return {
                    "success": True,
                    "file_path": file_path,
                    "content": content,
                    "size_bytes": file_size,
                    "method": "direct_read"
                }

            except Exception as e:
                logger.error(f"Failed to read file directly: {e}")
                # Fall through to Monitor request

        # STRATEGY 2: Request from Monitor (for cluster/remote files)
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
                        result['method'] = 'monitor_request'
                        logger.info(f"Received file from Monitor: {file_path} ({result.get('size_bytes', 0)} bytes)")
                        return result
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to get file from Monitor: {resp.status} - {error_text}")
                        # Add to failed cache to prevent retrying
                        self.failed_files_cache.add(file_path)
                        logger.info(f"Added {file_path} to failed files cache (won't retry)")
                        return {"success": False, "error": error_text, "status": resp.status}

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting file from Monitor: {file_path}")
            # Add to failed cache to prevent retrying
            self.failed_files_cache.add(file_path)
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error requesting file from Monitor: {e}")
            # Add to failed cache to prevent retrying
            self.failed_files_cache.add(file_path)
            return {"success": False, "error": str(e)}

    def parse_llm_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM JSON response"""
        response_text = llm_response.get("response", "")

        # Log raw response for debugging
        logger.info(f"Raw LLM response (first 500 chars): {response_text[:500]}")

        # Clean up markdown if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.rfind("```")
            if end > start:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            # Try without json keyword
            start = response_text.find("```") + 3
            end = response_text.rfind("```")
            if end > start:
                response_text = response_text[start:end].strip()

        # Log cleaned response
        logger.info(f"Cleaned response (first 500 chars): {response_text[:500]}")

        try:
            # Parse JSON
            plan = json.loads(response_text)
            logger.info(f"Successfully parsed plan with keys: {list(plan.keys())}")

            # Validate: Check if LLM returned empty or invalid plan
            if not plan or len(plan) == 0:
                logger.error("LLM returned empty JSON object {}")
                raise ValueError("LLM returned empty plan - likely prompt too long or model confused")

            # Check for required fields
            if 'needs_more_information' not in plan and 'repair_steps' not in plan:
                logger.error(f"LLM returned incomplete plan with only keys: {list(plan.keys())}")
                raise ValueError("LLM returned plan without repair_steps or needs_more_information")

            return plan
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Failed to parse response: {response_text[:1000]}")
            raise
        except ValueError as e:
            logger.error(f"Plan validation error: {e}")
            raise

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
        print(f"{TerminalColor.BRIGHT_GREEN.apply('✅ REPAIR PLAN GENERATED SUCCESSFULLY')}")
        print(f"{'='*80}\n")

        # Plan metadata
        print(f"{TerminalColor.BRIGHT_CYAN.apply('📋 PLAN DETAILS:')}")
        print(f"  {TerminalColor.CYAN.apply('Plan ID:')} {plan.get('plan_id', 'N/A')[:16]}...")
        print(f"  {TerminalColor.CYAN.apply('Workflow:')} {plan.get('workflow_id', 'N/A')}")
        print(f"  {TerminalColor.CYAN.apply('Strategy:')} {plan.get('repair_strategy', 'N/A').upper()}")

        # Risk assessment
        risk_level = plan.get('risk_level', 'unknown')
        risk_color = {
            'low': TerminalColor.GREEN,
            'medium': TerminalColor.YELLOW,
            'high': TerminalColor.RED
        }.get(risk_level, TerminalColor.WHITE)
        print(f"  {TerminalColor.CYAN.apply('Risk Level:')} {risk_color.apply(risk_level.upper())}")

        validation = plan.get('validation_result') or {}
        risk_assessment = validation.get('risk_assessment') or {}
        auto_exec = risk_assessment.get('auto_execute', False)
        auto_color = TerminalColor.GREEN if auto_exec else TerminalColor.YELLOW
        print(f"  {TerminalColor.CYAN.apply('Auto Execute:')} {auto_color.apply(str(auto_exec))}")

        # Plan summary
        print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('📝 SUMMARY:')}")
        print(f"  {plan.get('plan_summary', 'No summary provided')}")

        # Repair steps
        print(f"\n{TerminalColor.BRIGHT_YELLOW.apply('🔧 REPAIR STEPS:')}")
        print(f"{'─'*80}")
        for step in plan.get("repair_steps", []):
            step_num = step.get("step_number")
            step_desc = step.get("description")
            print(f"\n{TerminalColor.BRIGHT_WHITE.apply(f'  Step {step_num}:')} {step_desc}")

            commands = step.get("commands", [])
            if commands:
                print(f"  {TerminalColor.CYAN.apply('Commands:')}")
                for cmd in commands:
                    # Truncate very long commands for readability
                    if len(cmd) > 100:
                        print(f"    {TerminalColor.GREEN.apply('$')} {cmd[:97]}...")
                    else:
                        print(f"    {TerminalColor.GREEN.apply('$')} {cmd}")

            # Show validation if present
            validation_cmd = step.get("validation_command")
            if validation_cmd and validation_cmd != "echo 'No validation'":
                print(f"  {TerminalColor.YELLOW.apply('Validation:')} {validation_cmd}")

        # Confidence score
        confidence = plan.get("confidence_score", {})
        conf_score = confidence.get('score', 'N/A')
        print(f"\n{'─'*80}")
        print(f"{TerminalColor.BRIGHT_MAGENTA.apply('📊 CONFIDENCE SCORE:')} {conf_score}")
        print(f"  {confidence.get('explanation', 'No explanation provided')}")

        # Generator script modifications (permanent fix suggestions)
        if plan.get("generator_script_review_needed"):
            print(f"\n{'─'*80}")
            print(f"{TerminalColor.BRIGHT_YELLOW.apply('💡 PERMANENT FIX SUGGESTIONS:')}")
            print(f"  {TerminalColor.YELLOW.apply('For future workflows, consider updating the generator:')}")
            for suggestion in plan.get("generator_modifications_suggested", []):
                print(f"    • {suggestion}")

        # Workflow regeneration
        if plan.get("workflow_regeneration_needed"):
            print(f"\n{'─'*80}")
            print(f"{TerminalColor.BRIGHT_CYAN.apply('🔄 REGENERATION RECOMMENDED:')}")
            print(f"  {plan.get('regeneration_reason', 'Major changes required')}")

        # Manual intervention warning
        if plan.get("requires_manual_intervention"):
            print(f"\n{'─'*80}")
            print(f"{TerminalColor.BRIGHT_RED.apply('⚠️  MANUAL INTERVENTION REQUIRED:')}")
            print(f"  {plan.get('manual_intervention_reason', 'Complex issue requiring human review')}")

        print(f"\n{'='*80}\n")

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

    def save_request_to_file(self, request_type: str, data: Dict[str, Any], agent_name: str = "planner"):
        """Save last request to file for debugging"""
        try:
            import json
            from datetime import datetime

            # Create logs directory if it doesn't exist
            logs_dir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(logs_dir, exist_ok=True)

            # Create filename
            filename = f"{agent_name}_last_{request_type}.json"
            filepath = os.path.join(logs_dir, filename)

            # Also keep timestamped version
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            timestamped_filename = f"{agent_name}_{request_type}_{timestamp}.json"
            timestamped_filepath = os.path.join(logs_dir, timestamped_filename)

            # Prepare data with metadata
            request_log = {
                "timestamp": datetime.now().isoformat(),
                "request_type": request_type,
                "agent": agent_name,
                "data": data
            }

            # Write to both files
            with open(filepath, 'w') as f:
                json.dump(request_log, f, indent=2)

            with open(timestamped_filepath, 'w') as f:
                json.dump(request_log, f, indent=2)

            logger.info(f"Saved {request_type} request to {filename}")

        except Exception as e:
            logger.error(f"Failed to save request to file: {e}")

    async def handle_analysis_complete(self, request):
        """Handle analysis completion webhook from Analyzer"""
        try:
            data = await request.json()

            # Save incoming request to file
            self.save_request_to_file("analysis_complete", data, "planner")

            workflow_id = data.get("workflow_id")

            # Clear failed files cache for new workflow analysis (fresh start)
            self.planner.failed_files_cache.clear()
            logger.info(f"Cleared failed files cache for new workflow: {workflow_id}")

            # Defensive extraction with None handling
            result = data.get("result") or {}
            analysis_result = result.get("analysis") or {}
            catalogs = data.get("catalogs") or {}
            workflow_files = data.get("workflow_files") or {}
            parent_error_analysis = data.get("parent_error_analysis")

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
                print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('🔍 INTELLIGENT ROOT CAUSE ANALYSIS:')}")
                parent = parent_error_analysis['parent_error']
                cascade_count = parent_error_analysis.get('cascade_count', 0)
                confidence = parent_error_analysis.get('confidence', 'unknown')
                error_class = parent_error_analysis.get('parent_class', 'unknown')
                reasoning = parent_error_analysis.get('reasoning', 'No reasoning provided')

                print(f"  {TerminalColor.YELLOW.apply('🎯 Root Cause:')} {parent.get('problem', 'Unknown')}")
                print(f"  {TerminalColor.YELLOW.apply('📊 Error Type:')} {error_class.replace('_', ' ').title()}")
                print(f"  {TerminalColor.YELLOW.apply('🔗 Cascade Errors:')} {cascade_count} (these are SYMPTOMS, not root causes)")
                print(f"  {TerminalColor.YELLOW.apply('✅ Confidence:')} {confidence.upper()}")
                print(f"  {TerminalColor.YELLOW.apply('🧠 Method:')} {parent_error_analysis.get('analysis_method', 'unknown').replace('_', ' ').title()}")

                print(f"\n  {TerminalColor.CYAN.apply('💭 Causality Chain:')}")
                print(f"     {reasoning}")

                if cascade_count > 0:
                    print(f"\n  {TerminalColor.GREEN.apply('✨ Smart Strategy:')}")
                    print(f"     Fix ONLY the root cause ({error_class.replace('_', ' ')})")
                    print(f"     → Cascade errors will auto-resolve")
                    print(f"     → No need to fix {cascade_count} separate errors!")

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
