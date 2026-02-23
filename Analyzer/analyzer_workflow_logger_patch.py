"""
INTEGRATION PATCH FOR ANALYZER
Add this code to your Analyzer/analyzer_rest.py

This adds workflow-specific logging that:
1. Creates separate DB per workflow
2. Logs all LLM interactions
3. Logs all prints and outputs
4. Provides API endpoints to retrieve logs
"""

# ============================================================================
# STEP 1: Add import at top of file (around line 27)
# ============================================================================
"""
from workflow_interaction_logger import get_workflow_logger, close_workflow_logger
import time
"""

# ============================================================================
# STEP 2: Modify _try_llm_request method (around line 1234-1324)
# Add workflow_id parameter and logging
# ============================================================================

def _try_llm_request_WITH_LOGGING(self, prompt: str, workflow_id: str, analysis_type: str, use_json_format: bool = True) -> Optional[Dict[str, Any]]:
    """Try a single LLM request with detailed error handling AND WORKFLOW LOGGING"""

    # GET WORKFLOW LOGGER
    wf_logger = get_workflow_logger(workflow_id)

    payload = {
        "model": self.ollama_manager.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 2048
        }
    }

    if use_json_format:
        payload["format"] = "json"

    max_retries = self.config.get("retry_attempts", 3)
    generation_timeout = self.config.get("generation_timeout", 120)

    for attempt in range(max_retries):
        try:
            self.logger.info(f"LLM request attempt {attempt + 1}/{max_retries} (JSON format: {use_json_format})")

            # LOG LLM REQUEST
            wf_logger.log_print(f"LLM request attempt {attempt + 1}/{max_retries} (JSON format: {use_json_format})")
            interaction_id = wf_logger.log_llm_request(
                prompt=prompt,
                metadata={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "ollama_model": self.ollama_manager.ollama_model,
                    "ollama_url": self.ollama_manager.ollama_url,
                    "analysis_type": analysis_type,
                    "use_json_format": use_json_format,
                    "temperature": 0.1,
                    "num_predict": 2048
                }
            )

            # LOG PAYLOAD AS JSON
            wf_logger.log_json(payload, label=f"llm_request_payload_attempt_{attempt + 1}")

            start_time = time.time()

            response = requests.post(
                self.ollama_manager.ollama_url,
                json=payload,
                timeout=generation_timeout,
                headers={'User-Agent': 'PegasusAnalyzerAgent/1.0'}
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                ollama_response = response.json()
                response_text = ollama_response.get('response', '').strip()

                if not response_text:
                    self.logger.warning(f"Empty response from Ollama on attempt {attempt + 1}")
                    wf_logger.log_print(f"Empty response from Ollama on attempt {attempt + 1}", level="warning")
                    wf_logger.log_llm_response(
                        interaction_id=interaction_id,
                        response="",
                        success=False,
                        latency_ms=latency_ms,
                        error="Empty response from LLM"
                    )
                    continue

                # Update connection status on success
                self.ollama_manager.is_healthy = True
                self.ollama_manager.last_error = None
                self.ollama_manager.log_connection_attempt("generate", True)

                # LOG SUCCESSFUL RESPONSE
                wf_logger.log_print(f"LLM response received ({len(response_text)} chars) in {latency_ms:.2f}ms")
                wf_logger.log_json(ollama_response, label=f"llm_response_raw_attempt_{attempt + 1}")
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=response_text,
                    success=True,
                    latency_ms=latency_ms
                )

                return {
                    "choices": [{
                        "message": {
                            "content": response_text
                        }
                    }]
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                self.logger.error(f"Ollama API Error on attempt {attempt + 1}: {error_msg}")
                wf_logger.log_print(f"Ollama API Error on attempt {attempt + 1}: {error_msg}", level="error")
                self.ollama_manager.log_connection_attempt("generate", False, error_msg)

                # LOG FAILURE
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=None,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

                # Don't retry on client errors (4xx)
                if 400 <= response.status_code < 500:
                    break

        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
            error_msg = f"Request timeout ({generation_timeout}s) on attempt {attempt + 1}"
            self.logger.error(error_msg)
            wf_logger.log_print(error_msg, level="error")
            self.ollama_manager.log_connection_attempt("generate", False, error_msg)

            # LOG TIMEOUT
            if 'interaction_id' in locals():
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=None,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

        except requests.exceptions.ConnectionError as e:
            latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
            error_msg = f"Connection error on attempt {attempt + 1}: {str(e)}"
            self.logger.error(error_msg)
            wf_logger.log_print(error_msg, level="error")
            self.ollama_manager.log_connection_attempt("generate", False, error_msg)

            if 'interaction_id' in locals():
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=None,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
            error_msg = f"Request failed on attempt {attempt + 1}: {str(e)}"
            self.logger.error(error_msg)
            wf_logger.log_print(error_msg, level="error")
            self.ollama_manager.log_connection_attempt("generate", False, error_msg)

            if 'interaction_id' in locals():
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=None,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
            error_msg = f"Unexpected error on attempt {attempt + 1}: {str(e)}"
            self.logger.error(error_msg)
            wf_logger.log_print(error_msg, level="error")
            self.ollama_manager.log_connection_attempt("generate", False, error_msg)

            if 'interaction_id' in locals():
                wf_logger.log_llm_response(
                    interaction_id=interaction_id,
                    response=None,
                    success=False,
                    latency_ms=latency_ms,
                    error=error_msg
                )

        # Wait before retry (exponential backoff)
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            self.logger.info(f"Waiting {wait_time}s before retry...")
            wf_logger.log_print(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    # Mark as unhealthy after all retries failed
    self.ollama_manager.is_healthy = False
    self.ollama_manager.last_error = "All generation attempts failed"
    wf_logger.log_event("llm_all_attempts_failed", {"max_retries": max_retries})

    return None


# ============================================================================
# STEP 3: Modify send_logs_and_workflow_to_llm_enhanced (around line 1202)
# Add workflow_id parameter
# ============================================================================

def send_logs_and_workflow_to_llm_enhanced_WITH_LOGGING(self, logs: str, workflow: Dict[str, Any], workflow_id: str, analysis_type: str = "failed", hold_reason: str = "", stderr_summary: str = "") -> Optional[Dict[str, Any]]:
    """Enhanced LLM communication with better error handling and fallback AND WORKFLOW LOGGING"""

    # GET WORKFLOW LOGGER
    wf_logger = get_workflow_logger(workflow_id)

    # LOG INPUT DATA
    wf_logger.log_json({"logs": logs, "logs_length": len(logs)}, label="input_logs")
    wf_logger.log_json(workflow, label="input_workflow_yaml")
    if stderr_summary:
        wf_logger.log_json({"stderr_summary": stderr_summary, "length": len(stderr_summary)}, label="input_stderr_summary")

    # First, check if Ollama is healthy
    if not self.ollama_manager.quick_health_check():
        self.logger.warning(f"Ollama not healthy: {self.ollama_manager.last_error}")
        wf_logger.log_event("ollama_health_check_failed", {"error": self.ollama_manager.last_error})
        if not self.fallback_mode:
            return None
        # Continue to try anyway in fallback mode

    # Generate appropriate prompt based on analysis type
    if analysis_type == "held":
        prompt = self.prompt_manager.get_held_workflow_analysis_prompt(logs, workflow, hold_reason)
    else:
        prompt = self.prompt_manager.get_workflow_analysis_prompt(logs, workflow, stderr_summary)

    wf_logger.log_print(f"Generated {analysis_type} analysis prompt ({len(prompt)} chars)")
    wf_logger.log_json({"prompt": prompt, "prompt_length": len(prompt), "analysis_type": analysis_type}, label="generated_prompt")

    # Try with JSON format first (if supported)
    if self.config.get("use_json_format", True):
        wf_logger.log_event("trying_json_format", {"use_json_format": True})
        result = self._try_llm_request(prompt, workflow_id, analysis_type, use_json_format=True)
        if result:
            wf_logger.log_event("llm_success", {"format": "json"})
            return result

        self.logger.info("JSON format failed, trying without format parameter")
        wf_logger.log_event("json_format_failed", {"fallback": "plain_text"})

    # Fallback: try without JSON format
    wf_logger.log_event("trying_plain_text_format", {"use_json_format": False})
    result = self._try_llm_request(prompt, workflow_id, analysis_type, use_json_format=False)
    if result:
        wf_logger.log_event("llm_success", {"format": "plain_text"})
        return result

    self.logger.error("All LLM request attempts failed")
    wf_logger.log_event("llm_completely_failed", {"all_attempts_exhausted": True})
    return None


# ============================================================================
# STEP 4: Modify analyze_failed_workflow (around line 1686)
# Add logging throughout the method
# ============================================================================

async def analyze_failed_workflow_WITH_LOGGING(self, workflow_id: str, workflow_dir: str, job_out_files: List = None) -> Dict[str, Any]:
    """Analyze a failed workflow using enhanced LLM integration WITH WORKFLOW LOGGING"""

    # CREATE WORKFLOW LOGGER
    wf_logger = get_workflow_logger(workflow_id)

    try:
        wf_logger.log_event("analysis_start", {
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "analysis_type": "failed",
            "job_out_files_count": len(job_out_files) if job_out_files else 0
        })

        self.logger.info(f"Analyzing failed workflow: {workflow_id}")
        wf_logger.log_print(f"Starting failed workflow analysis for: {workflow_id}")

        if job_out_files is None:
            job_out_files = []

        logs = self.run_pegasus_analyzer(workflow_dir)
        yaml_path = self.find_yaml_file(workflow_dir)

        workflow_data = {}
        if yaml_path:
            workflow_data = self.load_workflow_yaml(yaml_path)
            wf_logger.log_json(workflow_data, label="loaded_workflow_yaml")

        # Extract stderr summary from .out files
        wf_logger.log_print(f"Processing {len(job_out_files)} job .out file(s)")
        stderr_summary = self._extract_stderr_summary(job_out_files)

        if stderr_summary:
            wf_logger.log_print(f"Extracted stderr summary ({len(stderr_summary)} chars)")
            wf_logger.log_json({"stderr_summary": stderr_summary}, label="stderr_summary")
        else:
            wf_logger.log_print("No stderr data available - using pegasus-analyzer only", level="warning")

        analysis_result = None
        llm_response = self.send_logs_and_workflow_to_llm_enhanced(logs, workflow_data, workflow_id, "failed", stderr_summary=stderr_summary)

        if llm_response:
            wf_logger.log_json(llm_response, label="raw_llm_response")
            analysis_result = self.extract_workflow_info_enhanced(llm_response)
            wf_logger.log_json(analysis_result, label="parsed_llm_response")

            if "error" not in analysis_result:
                self.logger.info(f"LLM analysis successful for {workflow_id}")
                wf_logger.log_event("llm_analysis_success", {"problems_count": len(analysis_result.get("problems_and_solutions", []))})
            else:
                self.logger.warning(f"LLM analysis had errors: {analysis_result['error']}")
                wf_logger.log_event("llm_analysis_error", {"error": analysis_result['error']})
                llm_response = None

        if not llm_response or not analysis_result or "error" in analysis_result:
            self.logger.warning(f"Using fallback analysis for {workflow_id}")
            wf_logger.log_event("using_fallback_analysis", {"reason": "llm_failed"})
            analysis_result = self.generate_fallback_analysis(workflow_id, workflow_dir, logs, "failed")
            wf_logger.log_json(analysis_result, label="fallback_analysis_result")

        # Smart missing file detection
        try:
            analysis_result = self.missing_file_helper.enhance_analysis_with_suggestions(
                analysis_result, logs, workflow_id
            )
            wf_logger.log_event("missing_file_helper_success", {})
        except Exception as e:
            self.logger.warning(f"Missing file helper error (non-critical): {e}")
            wf_logger.log_event("missing_file_helper_error", {"error": str(e)})

        # Store analysis result
        analysis_result.update({
            "workflow_id": workflow_id,
            "workflow_dir": workflow_dir,
            "analysis_type": "failed",
            "timestamp": datetime.now().isoformat(),
            "logs": logs,
            "yaml_path": yaml_path,
            "llm_available": self.ollama_manager.is_healthy,
            "fallback_used": not llm_response
        })

        wf_logger.log_json(analysis_result, label="final_analysis_result")
        wf_logger.log_event("analysis_complete", {
            "success": True,
            "llm_used": bool(llm_response),
            "problems_count": len(analysis_result.get("problems_and_solutions", []))
        })

        self.analysis_table.insert(analysis_result)
        wf_logger.log_event("result_stored_in_db", {"table": "workflow_analysis"})

        return analysis_result

    except Exception as e:
        wf_logger.log_print(f"Error during analysis: {e}", level="error")
        wf_logger.log_event("analysis_error", {"error": str(e), "type": type(e).__name__})
        raise

    finally:
        # CLOSE WORKFLOW LOGGER
        close_workflow_logger(workflow_id)


# ============================================================================
# STEP 5: Add API endpoints to retrieve workflow logs
# Add to setup_http_routes method (around line 777)
# ============================================================================
"""
Add these routes in setup_http_routes():

self.app.router.add_get('/api/analyzer/workflow-logs/{workflow_id}', self.get_workflow_logs)
self.app.router.add_get('/api/analyzer/workflow-logs/{workflow_id}/download', self.download_workflow_logs)
self.app.router.add_get('/api/analyzer/workflow-logs', self.list_workflow_logs)
"""

# Then add these handler methods:

async def get_workflow_logs(self, request: web.Request) -> web.Response:
    """Get complete interaction logs for a specific workflow"""
    try:
        workflow_id = request.match_info['workflow_id']

        import os
        from tinydb import TinyDB

        db_path = f"workflow_logs/{workflow_id}/interactions.json"

        if not os.path.exists(db_path):
            return web.json_response({
                "success": False,
                "error": f"No logs found for workflow {workflow_id}"
            }, status=404)

        # Load the database
        db = TinyDB(db_path)

        result = {
            "success": True,
            "workflow_id": workflow_id,
            "database_path": db_path,
            "tables": {
                "llm_interactions": db.table('llm_interactions').all(),
                "outputs": db.table('outputs').all(),
                "events": db.table('events').all()
            },
            "counts": {
                "llm_interactions": len(db.table('llm_interactions').all()),
                "outputs": len(db.table('outputs').all()),
                "events": len(db.table('events').all())
            }
        }

        db.close()

        return web.json_response(result)

    except Exception as e:
        self.logger.error(f"Error getting workflow logs: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)


async def download_workflow_logs(self, request: web.Request) -> web.Response:
    """Download workflow logs as JSON file"""
    try:
        workflow_id = request.match_info['workflow_id']

        import os

        db_path = f"workflow_logs/{workflow_id}/interactions.json"

        if not os.path.exists(db_path):
            return web.json_response({
                "success": False,
                "error": f"No logs found for workflow {workflow_id}"
            }, status=404)

        # Return the file
        return web.FileResponse(
            db_path,
            headers={
                'Content-Disposition': f'attachment; filename="workflow_{workflow_id}_logs.json"'
            }
        )

    except Exception as e:
        self.logger.error(f"Error downloading workflow logs: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)


async def list_workflow_logs(self, request: web.Request) -> web.Response:
    """List all workflows that have logs"""
    try:
        import os
        import glob

        workflow_logs_dir = "workflow_logs"

        if not os.path.exists(workflow_logs_dir):
            return web.json_response({
                "success": True,
                "workflows": [],
                "count": 0
            })

        # Find all workflow log directories
        workflow_dirs = glob.glob(f"{workflow_logs_dir}/*/")

        workflows = []
        for dir_path in workflow_dirs:
            workflow_id = os.path.basename(os.path.normpath(dir_path))
            db_path = os.path.join(dir_path, "interactions.json")

            if os.path.exists(db_path):
                # Get basic stats
                from tinydb import TinyDB
                db = TinyDB(db_path)

                llm_count = len(db.table('llm_interactions').all())
                output_count = len(db.table('outputs').all())
                event_count = len(db.table('events').all())

                # Get first and last timestamps
                events = db.table('events').all()
                timestamps = [e.get('timestamp') for e in events if e.get('timestamp')]

                db.close()

                workflows.append({
                    "workflow_id": workflow_id,
                    "database_path": db_path,
                    "file_size_bytes": os.path.getsize(db_path),
                    "counts": {
                        "llm_interactions": llm_count,
                        "outputs": output_count,
                        "events": event_count
                    },
                    "first_timestamp": min(timestamps) if timestamps else None,
                    "last_timestamp": max(timestamps) if timestamps else None
                })

        # Sort by last timestamp (most recent first)
        workflows.sort(key=lambda x: x.get('last_timestamp', ''), reverse=True)

        return web.json_response({
            "success": True,
            "workflows": workflows,
            "count": len(workflows)
        })

    except Exception as e:
        self.logger.error(f"Error listing workflow logs: {e}", exc_info=True)
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)
